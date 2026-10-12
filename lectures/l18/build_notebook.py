#!/usr/bin/env python3
"""Generate lectures/l18/l18-context-engineering.ipynb, the L18 worked example.

Retrieval over the course's own notes, measured on a gold set: BM25 by hand and in SQLite FTS5,
embedding search, reciprocal rank fusion, a cross-encoder reranker and ColBERT, the recall ladder
across all of them, calibrating a "not in the notes" gate, a chunk-size sweep, exact against
approximate search at a larger N, and a grounded prompt with citations. CPU only, no API key.
It uses the frozen L1-L17 snapshot and the gold set in data/, and the same code and seeds as
figures/make_figures.py, so its numbers are the numbers the notes quote.

(The previous build_notebook.py in this folder generated the structured-extraction notebook of
the old L18, which moved to L17; it is in git history.)

    python3 lectures/l18/build_notebook.py
    export JUPYTER_DATA_DIR=$(mktemp -d) TRANSFORMERS_OFFLINE=0 HF_HUB_OFFLINE=0
    cd lectures/l18 && uv run --no-project --python 3.12 --with numpy --with sentence-transformers \\
        --with faiss-cpu --with pylate --with nbclient --with nbformat --with ipykernel python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l18-context-engineering.ipynb', as_version=4)
NotebookClient(nb, timeout=1800, kernel_name='python3', resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l18-context-engineering.ipynb')
"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l18-context-engineering.ipynb"
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells, n = [], 0


def md(text):
    global n
    n += 1
    cells.append({"cell_type": "markdown", "id": f"md-{n:02d}", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    global n
    n += 1
    cells.append({"cell_type": "code", "id": f"code-{n:02d}", "execution_count": None,
                  "metadata": {}, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


md("""
# L18 worked example: retrieval over the course notes, measured

An LLM answers from what is in its context window, so the question for this notebook is which
passages of the course notes a retriever puts there. You will build five retrievers over the same
516 sections of the L1 to L17 notes and score each on the same 28 questions, whose answering
sections were labelled by hand:

1. keyword search with BM25, written out and then in SQLite;
2. embedding search with a sentence-embedding model;
3. hybrid search, fusing the two with reciprocal rank fusion;
4. the hybrid list reranked by a cross-encoder;
5. ColBERT, late interaction with one vector per token.

Then three practical questions: when should the system say "not in the notes", how big should a
chunk be, and what happens to memory and search time at a hundred thousand chunks.

The data are in `data/`: `notes-l01-l17.json` (a frozen snapshot, so these numbers do not move
when a lecture is edited) and `gold.json`. Everything runs on a CPU. The first run downloads three
small models (about 30, 90 and 130 MB).
""")

code("""
import json, math, re, sqlite3, time
from pathlib import Path
import numpy as np

chunks = json.loads(Path("data/notes-l01-l17.json").read_text())["chunks"]
gold = json.loads(Path("data/gold.json").read_text())["queries"]
texts = [c["text"] for c in chunks]
ids = [c["id"] for c in chunks]
queries = [g["q"] for g in gold]
print(f"{len(chunks)} chunks from {len({c['lecture'] for c in chunks})} lectures, "
      f"{sum(len(t.split()) for t in texts):,} words; {len(gold)} gold questions")
print({k: sum(g['kind'] == k for g in gold) for k in ['identifier', 'paraphrase', 'near-duplicate', 'out-of-corpus']})
print(chunks[0]["id"], "|", chunks[0]["section"])
""")

md("""
A chunk is one section of the notes, with its heading at the top. A question's answer is "found" if
one of its labelled sections (or a continuation of a long one, `-2`, `-3`) is in the top five.
Two numbers summarize a retriever over the 24 answerable questions: **hit@5**, the fraction with
a relevant section in the top five, and **MRR@10**, the mean of 1 / rank of the first relevant
section, which rewards putting it first.
""")

code("""
def is_rel(cid, rel):
    return any(cid == r or (cid.startswith(r + "-") and cid[len(r) + 1:].isdigit()) for r in rel)

def score(rankings, label):
    rows = [(g, rk) for g, rk in zip(gold, rankings) if g["relevant"]]
    hit, rr, by = [], [], {}
    for g, rk in rows:
        ranks = [r for r, i in enumerate(rk[:10]) if is_rel(ids[i], g["relevant"])]
        h = bool(ranks and ranks[0] < 5)
        hit.append(h); rr.append(1 / (ranks[0] + 1) if ranks else 0.0)
        by.setdefault(g["kind"], []).append(h)
    print(f"{label:18s} hit@5 {np.mean(hit):.2f}  MRR@10 {np.mean(rr):.2f}   " +
          "  ".join(f"{k} {np.mean(v):.2f}" for k, v in by.items()))
    return np.mean(hit), np.mean(rr)

def first_rank(rk, g):
    r = [k for k, i in enumerate(rk[:50]) if is_rel(ids[i], g["relevant"])]
    return r[0] + 1 if r else None
""")

md("""
## 1. Keyword search: BM25

An inverted index maps each word to the chunks that contain it. BM25 scores a chunk by summing,
over the query words it contains, an inverse document frequency (rare words count more) times a
term frequency that **saturates** (the tenth "pump" adds less than the first, set by `k1`) and is
**normalized by length** (a long chunk is not rewarded for being long, set by `b`). SQLite's
FTS5 fixes `k1 = 1.2` and `b = 0.75`; we use the same values.
""")

code("""
STOP = set("a an and are as at be by can do does for from how i in is it its my of on or that the "
           "their them this to was what when where which why will with you your".split())

def tokens(text):
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t not in STOP]

class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.tf = [{} for _ in docs]
        df = {}
        for c, d in zip(self.tf, docs):
            for t in tokens(d):
                c[t] = c.get(t, 0) + 1
            for t in c:
                df[t] = df.get(t, 0) + 1
        self.len = np.array([sum(c.values()) for c in self.tf], float)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - m + 0.5) / (m + 0.5)) for t, m in df.items()}

    def scores(self, query):
        s = np.zeros(len(self.tf))
        norm = self.k1 * (1 - self.b + self.b * self.len / self.len.mean())
        for t in set(tokens(query)):
            if t in self.idf:
                f = np.array([c.get(t, 0) for c in self.tf], float)
                s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return s

bm = BM25(texts)
r_bm = [list(np.argsort(-bm.scores(q))[:50]) for q in queries]
score(r_bm, "BM25");
""")

code("""
# The same thing in a database: SQLite's FTS5 virtual table and its built-in bm25().
db = sqlite3.connect(":memory:")
db.execute("CREATE VIRTUAL TABLE notes USING fts5(body, tokenize='porter unicode61')")
db.executemany("INSERT INTO notes(rowid, body) VALUES (?, ?)", list(enumerate(texts)))

def fts5(q, k=50):
    match = " OR ".join(f'"{t}"' for t in set(tokens(q)))
    return [r[0] for r in db.execute(
        "SELECT rowid FROM notes WHERE notes MATCH ? ORDER BY bm25(notes) LIMIT ?", (match, k))]

r_fts = [fts5(q) for q in queries]
score(r_fts, "BM25 (FTS5)")
print("top 3 for 'zero_grad':", [ids[i] for i in fts5("zero_grad", 3)])
""")

md("""
Keyword search finds every identifier question: `GroupKFold`, `MAPIE`, `SiNDAE` are rare tokens
with a high idf. It misses paraphrases, where the question and the notes use different words for
the same idea. Look at one.
""")

code("""
g = next(g for g in gold if g["q"].startswith("adding up money"))
qi = gold.index(g)
print(g["q"]); print("relevant:", g["relevant"])
print("BM25 rank of the first relevant section:", first_rank(r_bm[qi], g))
print("BM25 top 3:", [ids[i] for i in r_bm[qi][:3]])
""")

md("""
## 2. Embedding search

A sentence-embedding model maps each chunk to one vector, once (L17); a question is embedded the
same way and compared by cosine. With 516 chunks the search is a single matrix product: exact,
and a few milliseconds. The model truncates its input at 256 word pieces, so it reads roughly the
first 200 words of a chunk; the heading at the top of each chunk is what keeps a truncated
embedding on topic.
""")

code("""
from sentence_transformers import SentenceTransformer
enc = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")
t = time.perf_counter()
E = enc.encode(texts, normalize_embeddings=True, batch_size=32)
print(f"embedded {len(texts)} chunks in {time.perf_counter() - t:.1f} s: {E.shape}, {E.nbytes / 1e6:.2f} MB as float32")
Q = enc.encode(queries, normalize_embeddings=True)
S = Q @ E.T
r_dense = [list(np.argsort(-s)[:50]) for s in S]
score(r_dense, "dense")
print("dense rank for the money question:", first_rank(r_dense[qi], g))
""")

md("""
## 3. Hybrid search: reciprocal rank fusion

The two retrievers fail on different questions, so combine their rankings. Reciprocal rank fusion
gives each chunk `1 / (60 + rank)` from each list and adds them. It uses ranks only, so it never has
to compare a BM25 score with a cosine, which live on unrelated scales.
""")

code("""
def rrf(*rankings, k=60, n=20):
    s = {}
    for rk in rankings:
        for r, i in enumerate(rk):
            s[i] = s.get(i, 0) + 1 / (k + r + 1)
    return [i for i, _ in sorted(s.items(), key=lambda x: -x[1])][:n]

r_hyb = [rrf(a, b) for a, b in zip(r_bm, r_dense)]
score(r_hyb, "hybrid (RRF)");
""")

md("""
## 4. Reranking with a cross-encoder

A bi-encoder embeds the question and the chunk separately; a cross-encoder reads them together
and scores the pair, which is more accurate and far too slow to run over every chunk. So it
reranks the hybrid top 20.
""")

code("""
from sentence_transformers import CrossEncoder
ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")
t = time.perf_counter()
r_rr, ce_top = [], []
for q, rk in zip(queries, r_hyb):
    sc = ce.predict([(q, texts[i]) for i in rk])
    order = np.argsort(-sc)
    r_rr.append([rk[i] for i in order]); ce_top.append(float(sc[order[0]]))
print(f"{1000 * (time.perf_counter() - t) / len(queries):.0f} ms per question to rerank 20 pairs on a CPU")
score(r_rr, "hybrid + rerank");
""")

md("""
## 5. ColBERT: late interaction

ColBERT keeps one vector per token instead of one per chunk. A chunk's score is the sum, over the
question's tokens, of each token's best match among the chunk's tokens (**MaxSim**). It sits
between the two: finer than a bi-encoder, and precomputable unlike a cross-encoder, at the cost
of storing a vector for every token.
""")

code("""
from pylate import models
cb = models.ColBERT(model_name_or_path="lightonai/answerai-colbert-small-v1", device="cpu")
t = time.perf_counter()
D = cb.encode(texts, is_query=False, batch_size=16, show_progress_bar=False)
QC = cb.encode(queries, is_query=True, show_progress_bar=False)
r_cb = [list(np.argsort(-np.array([(qv @ d.T).max(axis=1).sum() for d in D]))[:50]) for qv in QC]
ntok = sum(len(d) for d in D)
print(f"{time.perf_counter() - t:.0f} s; {ntok:,} token vectors of {D[0].shape[1]} dims = "
      f"{ntok * D[0].shape[1] * 4 / 1e6:.0f} MB, against {E.nbytes / 1e6:.2f} MB for one vector per chunk")
score(r_cb, "ColBERT");
""")

md("""
## 6. The ladder
""")

code("""
for rk, name in [(r_bm, "BM25"), (r_dense, "dense"), (r_hyb, "hybrid (RRF)"), (r_rr, "hybrid + rerank"), (r_cb, "ColBERT")]:
    score(rk, name)
""")

md("""
Fusion lifts the hit rate because the two retrievers miss different questions; reranking mostly
improves the **order** (MRR) of what fusion already found. Neither number reaches 1: some
paraphrases share no words with the notes and land far from them in embedding space too.

## 7. When to say "not in the notes"

Four gold questions are not answered anywhere in the notes. A small LLM handed weak passages
answers anyway, so the decision belongs in code. Compare the best cosine and the best
cross-encoder score for answerable and unanswerable questions.
""")

code("""
print(f"{'kind':14s} {'best cos':>8s} {'best CE':>8s}  question")
for g, s, c in sorted(zip(gold, S.max(axis=1), ce_top), key=lambda x: x[1]):
    print(f"{g['kind']:14s} {s:8.2f} {c:8.2f}  {g['q'][:60]}")
""")

md("""
The ranges overlap. A cross-encoder score below 0, the obvious cutoff, would refuse several
answerable paraphrases, because this reranker was trained on short web queries. On this corpus, a
best cosine below 0.285 or a cross-encoder score below −6 catches three of the four and refuses
none of the answerable questions, by thin margins. A threshold is a property of the corpus and the
models: calibrate it on a gold set and expect to recalibrate when either changes.

## 8. Tuning: chunk size

Fixed-size word windows that ignore section boundaries, against the section chunks above. A window
counts as relevant if most of its words came from a relevant section. (The figure in the notes
sweeps more sizes; two keep this notebook quick.)
""")

code("""
def windows(size, overlap):
    out = []
    for lec in sorted({c["lecture"] for c in chunks}):
        words, src = [], []
        for c in chunks:
            if c["lecture"] == lec:
                w = c["text"].split(); words += w; src += [c["id"]] * len(w)
        step = max(1, int(size * (1 - overlap)))
        for s in range(0, max(1, len(words) - size // 2), step):
            if len(words[s:s + size]) >= 20:
                out.append((" ".join(words[s:s + size]), src[s:s + size]))
    return out

answerable = [g for g in gold if g["relevant"]]
QA = enc.encode([g["q"] for g in answerable], normalize_embeddings=True)
for size, ov in [(128, 0.0), (128, 0.25), (512, 0.0)]:
    win = windows(size, ov)
    W = enc.encode([w[0] for w in win], normalize_embeddings=True, batch_size=64)
    hits = sum(any(sum(is_rel(s, g["relevant"]) for s in win[i][1]) * 2 >= len(win[i][1])
                   for i in np.argsort(-(QA[k] @ W.T))[:5]) for k, g in enumerate(answerable))
    print(f"{size} words, {int(ov * 100)}% overlap: {len(win)} chunks, dense hit@5 {hits / len(answerable):.2f}")
""")

md("""
## 9. Scaling: memory and search time

Memory is arithmetic: N vectors × d dimensions × bytes per number. Search time is measured here on
100,000 synthetic vectors with structure (384 dimensions generated from a 32-dimensional latent
space, because real embeddings have a low intrinsic dimension), exact against an HNSW index from
FAISS.
""")

code("""
for N in [516, 100_000, 1_000_000]:
    print(f"{N:>9,} x 768: float32 {N * 768 * 4 / 1e9:7.3f} GB   int8 {N * 768 / 1e9:7.3f} GB   binary {N * 768 / 8 / 1e9:7.4f} GB")

import faiss
# One thread: with PyTorch already loaded in this process, multi-threaded FAISS segfaults on macOS
# (both bring their own OpenMP runtime).
faiss.omp_set_num_threads(1)
rng = np.random.default_rng(0)
n, d = 100_000, 384
A = rng.standard_normal((32, d)).astype("float32")
X = rng.standard_normal((n, 32)).astype("float32") @ A + 0.5 * rng.standard_normal((n, d)).astype("float32")
X /= np.linalg.norm(X, axis=1, keepdims=True)
Qs = X[rng.integers(0, n, 200)] + 0.05 * rng.standard_normal((200, d)).astype("float32")
Qs /= np.linalg.norm(Qs, axis=1, keepdims=True)
t = time.perf_counter(); truth = np.argsort(-(Qs @ X.T), axis=1)[:, :10]
print(f"exact: {1000 * (time.perf_counter() - t) / 200:.2f} ms per query")
idx = faiss.IndexHNSWFlat(d, 16, faiss.METRIC_INNER_PRODUCT); idx.hnsw.efConstruction = 64
t = time.perf_counter(); idx.add(X); print(f"HNSW build: {time.perf_counter() - t:.1f} s")
for ef in [16, 64, 256]:
    idx.hnsw.efSearch = ef
    t = time.perf_counter(); _, I = idx.search(Qs, 10); ms = 1000 * (time.perf_counter() - t) / 200
    rec = np.mean([len(set(I[i]) & set(truth[i])) / 10 for i in range(200)])
    print(f"HNSW efSearch {ef:3d}: {ms:.3f} ms per query, recall@10 {rec:.3f}")
""")

md("""
## 10. Assembling the context

The last step is the prompt: the top passages, numbered, inside an instruction to answer from them
and cite them, and the question. This is what the capstone in the deck sends to the model in the
browser.
""")

code("""
q = "why can't I shuffle sensor readings before splitting them into training and test sets"
top = rrf(list(np.argsort(-bm.scores(q))[:50]), list(np.argsort(-(enc.encode([q], normalize_embeddings=True)[0] @ E.T))[:50]))[:5]
passages = "\\n\\n".join(f"[{k + 1}] {chunks[i]['title']}: {chunks[i]['section']}\\n{' '.join(texts[i].split()[:120])}"
                        for k, i in enumerate(top))
prompt = (f"Answer in two or three sentences using only the passages. End each sentence with the passage "
          f"number in square brackets. If the passages do not answer, reply exactly: Not in the notes.\\n\\n"
          f"Question: {q}\\n\\n{passages}\\n\\nQuestion: {q}")
print(prompt[:1500], "...")
print(f"\\n{len(prompt.split())} words, roughly {int(len(prompt.split()) * 1.3)} tokens (count them properly as in L17)")
""")

md("""
## Try it

- Add three questions of your own to `gold.json`, with the sections that answer them, and rerun.
  Which retriever wins each, and why?
- Change BM25's `k1` to 2.0 and `b` to 0.3. Which questions move?
- Replace `all-MiniLM-L6-v2` with another embedding model from the MTEB leaderboard, and remember
  to embed the questions with the same model. Is the gain worth the larger vectors?
- Rerank the dense top 20 instead of the hybrid top 20. What changes?
- Recalibrate the gate after your changes. Do the thresholds move?
""")

cells = with_colab_cell(cells, OUT)
nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT.name} ({len(cells)} cells)")
