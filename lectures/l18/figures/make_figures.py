#!/usr/bin/env python3
"""Measurements and figures for L18, context engineering.

Everything here is measured on the course's own notes: the frozen L1-L17 snapshot in
../data/notes-l01-l17.json (516 chunks, one per section) and the hand-written gold set in
../data/gold.json (28 questions, each labelled with the sections that answer it). Every number
the notes quote about retrieval comes from the cache this script writes, and the notebook runs
the same code inline.

    cd lectures/l18/figures
    TRANSFORMERS_OFFLINE=0 HF_HUB_OFFLINE=0 uv run --no-project --python 3.12 \\
        --with numpy --with matplotlib --with scikit-learn --with sentence-transformers \\
        --with faiss-cpu --with pylate python make_figures.py [group ...]

Groups: ladder (retrieval on the gold set), sweep (chunk size and overlap), scale (memory and
search time at larger N), widgets (data for the interactive figures), plots (PNG figures from
the cache). With no argument, all of them. Results are cached in .cache/results.json (gitignored);
`plots` alone redraws from the cache. Timings are measured on the author's machine
(CPU, Apple silicon) and move between machines; recall and rank do not.
"""
import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)
RESULTS = CACHE / "results.json"
WIDGET_JS = HERE.parent.parent.parent / "_static" / "l18-widget-data.js"

DENSE = "sentence-transformers/all-MiniLM-L6-v2"
CROSS = "cross-encoder/ms-marco-MiniLM-L-6-v2"
COLBERT = "lightonai/answerai-colbert-small-v1"
K1, B = 1.2, 0.75          # SQLite FTS5's fixed values; Robertson and Zaragoza give ranges
RRF_K = 60                 # Cormack, Clarke and Buettcher 2009
POOL, TOPK = 20, 5

STOP = set("""a an and are as at be by can do does for from how i in is it its my of on or
that the their them this to was what when where which why will with you your""".split())


def load():
    chunks = json.loads((DATA / "notes-l01-l17.json").read_text())["chunks"]
    gold = json.loads((DATA / "gold.json").read_text())["queries"]
    return chunks, gold


def is_rel(cid, rel):
    """A chunk is relevant if it is a listed section or a continuation of one (-2, -3, ...)."""
    return any(cid == r or (cid.startswith(r + "-") and cid[len(r) + 1:].isdigit()) for r in rel)


def tokens(text):
    return [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if t not in STOP]


class BM25:
    """BM25 written out: idf times a saturating, length-normalised term frequency."""

    def __init__(self, docs, k1=K1, b=B):
        self.k1, self.b = k1, b
        self.docs = [tokens(d) for d in docs]
        self.len = np.array([len(d) for d in self.docs], float)
        self.avg = self.len.mean()
        self.tf = []
        df = {}
        for d in self.docs:
            c = {}
            for t in d:
                c[t] = c.get(t, 0) + 1
            self.tf.append(c)
            for t in c:
                df[t] = df.get(t, 0) + 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - m + 0.5) / (m + 0.5)) for t, m in df.items()}

    def scores(self, query):
        s = np.zeros(len(self.docs))
        norm = self.k1 * (1 - self.b + self.b * self.len / self.avg)
        for t in set(tokens(query)):
            if t not in self.idf:
                continue
            f = np.array([c.get(t, 0) for c in self.tf], float)
            s += self.idf[t] * f * (self.k1 + 1) / (f + norm)
        return s


def fts5_rank(texts, query, n):
    """The same question through SQLite's built-in BM25 (FTS5, porter stemming)."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE t USING fts5(body, tokenize='porter unicode61')")
    db.executemany("INSERT INTO t(rowid, body) VALUES (?, ?)", [(i, x) for i, x in enumerate(texts)])
    q = " OR ".join(f'"{t}"' for t in set(tokens(query)))
    rows = db.execute("SELECT rowid FROM t WHERE t MATCH ? ORDER BY bm25(t) LIMIT ?", (q, n)).fetchall()
    return [r[0] for r in rows]


def rrf(*rankings, k=RRF_K, n=POOL):
    s = {}
    for rk in rankings:
        for r, i in enumerate(rk):
            s[i] = s.get(i, 0) + 1 / (k + r + 1)
    return [i for i, _ in sorted(s.items(), key=lambda x: -x[1])][:n]


def metrics(rankings, gold, chunks):
    """hit@5 (a relevant section in the top 5) and MRR@10, over the answerable questions."""
    ids = [c["id"] for c in chunks]
    out = []
    for rk, g in zip(rankings, gold):
        if not g["relevant"]:
            continue
        ranks = [r for r, i in enumerate(rk[:10]) if is_rel(ids[i], g["relevant"])]
        out.append({"kind": g["kind"], "hit5": bool(ranks and ranks[0] < TOPK),
                    "rr": 1 / (ranks[0] + 1) if ranks else 0.0})
    return out


def summarize(m):
    kinds = ["identifier", "paraphrase", "near-duplicate"]
    res = {"all": {"hit5": float(np.mean([x["hit5"] for x in m])), "mrr": float(np.mean([x["rr"] for x in m]))}}
    for k in kinds:
        sub = [x for x in m if x["kind"] == k]
        res[k] = {"hit5": float(np.mean([x["hit5"] for x in sub])), "mrr": float(np.mean([x["rr"] for x in sub])), "n": len(sub)}
    return res


def cache_get():
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def cache_put(key, value):
    c = cache_get()
    c[key] = value
    RESULTS.write_text(json.dumps(c, indent=1))


# ----------------------------------------------------------------- ladder

def run_ladder():
    from sentence_transformers import CrossEncoder, SentenceTransformer
    chunks, gold = load()
    texts = [c["text"] for c in chunks]
    queries = [g["q"] for g in gold]
    out, timing = {}, {}

    t = time.perf_counter()
    bm = BM25(texts)
    timing["bm25_index_s"] = time.perf_counter() - t
    t = time.perf_counter()
    r_bm = [list(np.argsort(-bm.scores(q))[:50]) for q in queries]
    timing["bm25_ms_per_query"] = 1000 * (time.perf_counter() - t) / len(queries)
    r_fts = [fts5_rank(texts, q, 50) for q in queries]

    enc = SentenceTransformer(DENSE, device="cpu")
    t = time.perf_counter()
    E = enc.encode(texts, normalize_embeddings=True, batch_size=32)
    timing["dense_index_s"] = time.perf_counter() - t
    t = time.perf_counter()
    Q = enc.encode(queries, normalize_embeddings=True)
    S = Q @ E.T
    timing["dense_ms_per_query"] = 1000 * (time.perf_counter() - t) / len(queries)
    r_dense = [list(np.argsort(-s)[:50]) for s in S]
    r_hyb = [rrf(a[:50], b[:50]) for a, b in zip(r_bm, r_dense)]

    ce = CrossEncoder(CROSS, device="cpu")
    t = time.perf_counter()
    r_rr, ce_top = [], []
    for q, rk in zip(queries, r_hyb):
        sc = ce.predict([(q, texts[i]) for i in rk])
        order = np.argsort(-sc)
        r_rr.append([rk[i] for i in order])
        ce_top.append(float(sc[order[0]]))
    timing["rerank_ms_per_query"] = 1000 * (time.perf_counter() - t) / len(queries)

    from pylate import models
    cb = models.ColBERT(model_name_or_path=COLBERT, device="cpu")
    t = time.perf_counter()
    D = cb.encode(texts, is_query=False, batch_size=16, show_progress_bar=False)
    timing["colbert_index_s"] = time.perf_counter() - t
    t = time.perf_counter()
    QC = cb.encode(queries, is_query=True, show_progress_bar=False)
    r_cb = []
    for qv in QC:
        s = np.array([(qv @ d.T).max(axis=1).sum() for d in D])
        r_cb.append(list(np.argsort(-s)[:50]))
    timing["colbert_ms_per_query"] = 1000 * (time.perf_counter() - t) / len(queries)
    ntok = int(sum(len(d) for d in D))

    methods = {"BM25": r_bm, "BM25 (SQLite FTS5)": r_fts, "dense": r_dense, "hybrid (RRF)": r_hyb,
               "hybrid + rerank": r_rr, "ColBERT": r_cb}
    for name, rk in methods.items():
        out[name] = summarize(metrics(rk, gold, chunks))
    # Per-query detail for the notes: rank of the first relevant chunk under each method.
    ids = [c["id"] for c in chunks]
    detail = []
    for qi, g in enumerate(gold):
        row = {"q": g["q"], "kind": g["kind"], "top_cos": float(S[qi].max()), "top_ce": ce_top[qi]}
        for name, rk in methods.items():
            rr = [r for r, i in enumerate(rk[qi][:50]) if is_rel(ids[i], g["relevant"])]
            row[name] = rr[0] + 1 if rr else None
        detail.append(row)
    sizes = {"chunks": len(texts), "dense_bytes_f32": int(E.size * 4), "colbert_vectors": ntok,
             "colbert_dim": int(D[0].shape[1]), "colbert_bytes_f32": int(ntok * D[0].shape[1] * 4)}
    cache_put("ladder", {"methods": out, "detail": detail, "timing": timing, "sizes": sizes})
    for name, v in out.items():
        print(f"{name:20s} hit@5 {v['all']['hit5']:.2f}  MRR {v['all']['mrr']:.2f}  " +
              "  ".join(f"{k[:5]} {v[k]['hit5']:.2f}" for k in ["identifier", "paraphrase", "near-duplicate"]))
    print({k: round(v, 3) for k, v in timing.items()}, sizes)


# ----------------------------------------------------------------- sweep

def windows(chunks, size, overlap):
    """Fixed word windows over each lecture's notes, ignoring section boundaries, as a naive
    splitter would. Each word remembers which section chunk it came from."""
    out = []
    by_lec = {}
    for c in chunks:
        by_lec.setdefault(c["lecture"], []).append(c)
    step = max(1, int(size * (1 - overlap)))
    for lec, cs in by_lec.items():
        words, src = [], []
        for c in cs:
            w = c["text"].split()
            words += w
            src += [c["id"]] * len(w)
        for s in range(0, max(1, len(words) - size // 2), step):
            ws, ss = words[s:s + size], src[s:s + size]
            if len(ws) < 20:
                continue
            out.append((" ".join(ws), ss))
    return out


def run_sweep():
    from sentence_transformers import SentenceTransformer
    chunks, gold = load()
    gold = [g for g in gold if g["relevant"]]
    enc = SentenceTransformer(DENSE, device="cpu")
    Q = enc.encode([g["q"] for g in gold], normalize_embeddings=True)
    res = []

    def score(texts, rel_of):
        E = enc.encode(texts, normalize_embeddings=True, batch_size=64)
        S = Q @ E.T
        bm = BM25(texts)
        hd = hb = 0
        for qi, g in enumerate(gold):
            hd += any(rel_of(i, g) for i in np.argsort(-S[qi])[:TOPK])
            hb += any(rel_of(i, g) for i in np.argsort(-bm.scores(g["q"]))[:TOPK])
        return hd / len(gold), hb / len(gold)

    sec = [c["text"] for c in chunks]
    d, b = score(sec, lambda i, g: is_rel(chunks[i]["id"], g["relevant"]))
    res.append({"config": "sections", "size": None, "overlap": None, "n": len(sec), "dense": d, "bm25": b})
    print(f"sections: n={len(sec)} dense {d:.2f} bm25 {b:.2f}")
    for size in [64, 128, 256, 512]:
        for ov in [0.0, 0.25]:
            win = windows(chunks, size, ov)

            def rel_of(i, g, win=win):
                src = win[i][1]
                return sum(is_rel(s, g["relevant"]) for s in src) * 2 >= len(src)
            d, b = score([w[0] for w in win], rel_of)
            res.append({"config": f"{size} words, {int(ov * 100)}% overlap", "size": size, "overlap": ov,
                        "n": len(win), "dense": d, "bm25": b})
            print(f"{size:4d} words {int(ov * 100):2d}% overlap: n={len(win)} dense {d:.2f} bm25 {b:.2f}")
    cache_put("sweep", res)


# ----------------------------------------------------------------- scale

def run_scale(n=100_000, d=384, nq=200):
    """Exact against approximate search at a larger N. The vectors are synthetic but structured:
    384 dimensions generated from a 32-dimensional latent space plus a little noise, because real
    embeddings have a low intrinsic dimension, and full-dimensional random noise is a regime where
    nearest neighbors barely mean anything and approximate search looks far worse than it is."""
    import faiss
    faiss.omp_set_num_threads(1)   # one thread, as in the notebook, so the timings compare
    rng = np.random.default_rng(0)
    A = rng.standard_normal((32, d)).astype("float32")
    X = rng.standard_normal((n, 32)).astype("float32") @ A + 0.5 * rng.standard_normal((n, d)).astype("float32")
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    Qv = X[rng.integers(0, n, nq)] + 0.05 * rng.standard_normal((nq, d)).astype("float32")
    Qv /= np.linalg.norm(Qv, axis=1, keepdims=True)
    t = time.perf_counter()
    S = Qv @ X.T
    truth = np.argsort(-S, axis=1)[:, :10]
    exact_ms = 1000 * (time.perf_counter() - t) / nq
    res = {"n": n, "d": d, "exact_ms_per_query": exact_ms,
           "bytes": {"float32": n * d * 4, "int8": n * d, "binary": n * d // 8}}
    t = time.perf_counter()
    idx = faiss.IndexHNSWFlat(d, 16, faiss.METRIC_INNER_PRODUCT)
    idx.hnsw.efConstruction = 64
    idx.add(X)
    res["hnsw_build_s"] = time.perf_counter() - t
    res["hnsw_graph_bytes_estimate"] = n * 16 * 2 * 4
    res["hnsw"] = []
    for ef in [8, 16, 32, 64, 128, 256]:
        idx.hnsw.efSearch = ef
        t = time.perf_counter()
        _, I = idx.search(Qv, 10)
        ms = 1000 * (time.perf_counter() - t) / nq
        rec = float(np.mean([len(set(I[i]) & set(truth[i])) / 10 for i in range(nq)]))
        res["hnsw"].append({"ef_search": ef, "ms_per_query": ms, "recall_at_10": rec})
        print(f"efSearch {ef:4d}: {ms:.3f} ms/query, recall@10 {rec:.3f}")
    print(f"exact: {exact_ms:.2f} ms/query; build {res['hnsw_build_s']:.1f} s")
    cache_put("scale", res)


# ----------------------------------------------------------------- widgets

def run_widgets():
    """Data for _static/widgets.js: a 2-D map of the notes and one ColBERT MaxSim matrix."""
    from sentence_transformers import SentenceTransformer
    from sklearn.decomposition import PCA
    chunks, gold = load()
    texts = [c["text"] for c in chunks]
    enc = SentenceTransformer(DENSE, device="cpu")
    E = enc.encode(texts, normalize_embeddings=True, batch_size=32)
    pick = [g for g in gold if g["kind"] in ("paraphrase", "identifier", "out-of-corpus")][:]
    pick = [gold[i] for i in (0, 8, 10, 13, 16, 24)]
    Q = enc.encode([g["q"] for g in pick], normalize_embeddings=True)
    pca = PCA(n_components=2, random_state=0).fit(E)
    P, PQ = pca.transform(E), pca.transform(Q)
    S = Q @ E.T
    bm = BM25(texts)
    cmap = {
        "points": [[round(float(x), 3), round(float(y), 3), c["lecture"], c["section"][:70]] for (x, y), c in zip(P, chunks)],
        "queries": [{"q": g["q"], "kind": g["kind"], "xy": [round(float(a), 3) for a in PQ[i]],
                     "dense": [[int(j), round(float(S[i, j]), 3)] for j in np.argsort(-S[i])[:5]],
                     "bm25": [int(j) for j in np.argsort(-bm.scores(g["q"]))[:5]]} for i, g in enumerate(pick)],
        "explained": [round(float(v), 3) for v in pca.explained_variance_ratio_],
    }
    from pylate import models
    cb = models.ColBERT(model_name_or_path=COLBERT, device="cpu")
    q = "what happens if you forget zero_grad in a PyTorch training loop"
    doc = next(c for c in chunks if c["id"] == "l11-n-the-loop-that-forgot-zero-grad")["text"]
    doc = " ".join(doc.split()[:45])
    qv = cb.encode([q], is_query=True, show_progress_bar=False)[0]
    dv = cb.encode([doc], is_query=False, show_progress_bar=False)[0]
    # Labels for the vectors: a query is padded with [MASK] to 32 tokens (query augmentation), and
    # a passage loses the punctuation tokens on ColBERT's skiplist, so tokenize the way PyLate does.
    tok, skip = cb.tokenizer, set(cb.skiplist)
    qt = tok.convert_ids_to_tokens(cb.tokenize([q], is_query=True)["input_ids"][0])
    dids = [int(i) for i in cb.tokenize([doc], is_query=False)["input_ids"][0] if int(i) not in skip]
    dt = tok.convert_ids_to_tokens(dids)
    M = qv @ dv.T
    maxsim = {"query": q, "doc": doc, "q_tokens": qt, "d_tokens": dt,
              "q_len": int(qv.shape[0]), "d_len": int(dv.shape[0]),
              "matrix": [[round(float(v), 3) for v in row] for row in M]}
    data = {"corpusMap": cmap, "maxsim": maxsim}
    WIDGET_JS.write_text("/* Generated by lectures/l18/figures/make_figures.py (group widgets). Do not edit. */\n"
                         "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
                         f"window.COURSE_WIDGET_DATA.l18 = {json.dumps(data, separators=(',', ':'))};\n")
    print(f"wrote {WIDGET_JS.name}: {WIDGET_JS.stat().st_size / 1e3:.0f} kB; q tokens {len(qt)} vs {qv.shape[0]} vectors, "
          f"d tokens {len(dt)} vs {dv.shape[0]} vectors; PCA explains {cmap['explained']}")


# ----------------------------------------------------------------- plots

def run_plots():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 150, "savefig.bbox": "tight"})
    c = cache_get()
    BLUE, ORANGE, GREEN, GRAY, RED = "#1f6fb2", "#c2410c", "#2b8a3e", "#777777", "#c41230"

    L = c["ladder"]["methods"]
    names = ["BM25", "dense", "hybrid (RRF)", "hybrid + rerank", "ColBERT"]
    kinds = ["identifier", "paraphrase", "near-duplicate"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.2))
    x = np.arange(len(names))
    a1.bar(x - 0.2, [L[n]["all"]["hit5"] for n in names], 0.4, color=BLUE, label="hit@5")
    a1.bar(x + 0.2, [L[n]["all"]["mrr"] for n in names], 0.4, color=ORANGE, label="MRR@10")
    for i, n in enumerate(names):
        a1.text(i - 0.2, L[n]["all"]["hit5"] + 0.01, f"{L[n]['all']['hit5']:.2f}", ha="center", fontsize=9)
        a1.text(i + 0.2, L[n]["all"]["mrr"] + 0.01, f"{L[n]['all']['mrr']:.2f}", ha="center", fontsize=9)
    a1.set_xticks(x, names, rotation=12)
    a1.set(ylim=(0, 1.25), title=f"All {sum(L['BM25'][k]['n'] for k in kinds)} answerable questions")
    a1.legend(frameon=False, loc="upper center", ncol=2)
    w = 0.16
    for j, n in enumerate(names):
        a2.bar(np.arange(3) + (j - 2) * w, [L[n][k]["hit5"] for k in kinds], w, label=n,
               color=[GRAY, BLUE, GREEN, ORANGE, RED][j])
    a2.set_xticks(np.arange(3), [f"{k} ({L['BM25'][k]['n']})" for k in kinds])
    a2.set(ylim=(0, 1.3), ylabel="hit@5", title="By kind of question")
    a2.legend(frameon=False, fontsize=8, ncol=3, loc="upper center")
    fig.savefig(HERE / "recall-ladder.png"); plt.close(fig)

    D = c["ladder"]["detail"]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ans = [r for r in D if r["kind"] != "out-of-corpus"]
    ooc = [r for r in D if r["kind"] == "out-of-corpus"]
    ax.scatter([r["top_cos"] for r in ans], [r["top_ce"] for r in ans], color=BLUE, label="answerable")
    ax.scatter([r["top_cos"] for r in ooc], [r["top_ce"] for r in ooc], color=RED, marker="x", s=60, label="not in the notes")
    ax.axhline(0, color=GRAY, ls="--", lw=1)
    ax.set(xlabel="best cosine (embedding search)", ylabel="best cross-encoder score",
           title="Which questions the notes cannot answer")
    ax.legend(frameon=False)
    fig.savefig(HERE / "abstention.png"); plt.close(fig)

    SW = c["sweep"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    sec = SW[0]
    for ov, mk in [(0.0, "o-"), (0.25, "s--")]:
        r = [s for s in SW[1:] if s["overlap"] == ov]
        ax.plot([s["size"] for s in r], [s["dense"] for s in r], mk, color=BLUE, label=f"dense, {int(ov * 100)}% overlap")
        ax.plot([s["size"] for s in r], [s["bm25"] for s in r], mk, color=ORANGE, label=f"BM25, {int(ov * 100)}% overlap")
    ax.axhline(sec["dense"], color=BLUE, lw=1, alpha=0.5)
    ax.axhline(sec["bm25"], color=ORANGE, lw=1, alpha=0.5)
    ax.text(520, sec["dense"], " sections, dense", va="center", fontsize=9, color=BLUE)
    ax.text(520, sec["bm25"], " sections, BM25", va="center", fontsize=9, color=ORANGE)
    ax.set_xscale("log", base=2)
    ax.set_xticks([64, 128, 256, 512], ["64", "128", "256", "512"])
    ax.set(xlabel="chunk size (words)", ylabel="hit@5", ylim=(0, 1.05), title="Fixed-size chunks against section chunks")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.savefig(HERE / "chunk-sweep.png"); plt.close(fig)

    SC = c["scale"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 3.8))
    for N, col in [(1_000_000, BLUE)]:
        vals = [N * 768 * 4, N * 768, N * 768 / 8, N * 16 * 2 * 4]
        a1.barh(["float32", "int8", "binary", "HNSW links (M=16)"], [v / 1e9 for v in vals], color=[col, col, col, GRAY])
        for i, v in enumerate(vals):
            a1.text(v / 1e9, i, f" {v / 1e9:.2f} GB", va="center", fontsize=9)
    a1.set(xlabel="GB", title="One million 768-dimension vectors", xlim=(0, 3.8))
    h = SC["hnsw"]
    a2.plot([r["ms_per_query"] for r in h], [r["recall_at_10"] for r in h], "o-", color=BLUE)
    for r in h:
        a2.annotate(f"ef={r['ef_search']}", (r["ms_per_query"], r["recall_at_10"]), fontsize=8,
                    textcoords="offset points", xytext=(4, -10))
    a2.axvline(SC["exact_ms_per_query"], color=GRAY, ls="--")
    lo = min(r["recall_at_10"] for r in h)
    a2.text(SC["exact_ms_per_query"], lo, " exact\n (NumPy)", fontsize=9, color=GRAY, va="bottom")
    a2.set_xscale("log")
    a2.set(xlabel="ms per query", ylabel="recall@10 against exact",
           title=f"HNSW on {SC['n']:,} vectors of {SC['d']} dims")
    fig.savefig(HERE / "scale.png"); plt.close(fig)

    W = json.loads(WIDGET_JS.read_text().split("COURSE_WIDGET_DATA.l18 = ", 1)[1].rstrip(";\n"))
    M = W["corpusMap"]
    fig, ax = plt.subplots(figsize=(9, 6))
    lecs = sorted({p[2] for p in M["points"]})
    cm = plt.get_cmap("tab20")
    for k, lec in enumerate(lecs):
        pts = np.array([p[:2] for p in M["points"] if p[2] == lec])
        ax.scatter(pts[:, 0], pts[:, 1], s=10, color=cm(k % 20), label=lec.upper())
    qq = M["queries"][1]
    ax.scatter(*qq["xy"], marker="*", s=300, color="k", zorder=5)
    for j, _ in qq["dense"]:
        ax.plot([qq["xy"][0], M["points"][j][0]], [qq["xy"][1], M["points"][j][1]], color="k", lw=0.8)
    ax.set(title=f"The notes in two dimensions (PCA); star: \"{qq['q'][:48]}...\"", xticks=[], yticks=[])
    ax.legend(frameon=False, fontsize=7, ncol=2, loc="upper left", bbox_to_anchor=(1, 1))
    fig.savefig(HERE / "widget-corpus-map.png"); plt.close(fig)

    X = W["maxsim"]
    Mx = np.array(X["matrix"])
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.imshow(Mx, aspect="auto", cmap="Blues")
    ax.set_yticks(range(min(len(X["q_tokens"]), Mx.shape[0])), X["q_tokens"][:Mx.shape[0]], fontsize=8)
    ax.set_xticks(range(min(len(X["d_tokens"]), Mx.shape[1])), X["d_tokens"][:Mx.shape[1]], fontsize=7, rotation=90)
    ax.set_xlabel("passage tokens")
    ax.set_title("ColBERT: each query token keeps its best match in the passage (MaxSim); the score is their sum")
    for i, j in enumerate(Mx.argmax(axis=1)):
        ax.plot(j, i, "o", ms=4, color=RED)
    fig.savefig(HERE / "widget-maxsim.png"); plt.close(fig)
    # Static stand-in for the bm25-terms widget: the same six passages, query and formula as
    # _static/widgets.js, at k1 = 1.2 and b = 0.75.
    js = (HERE.parent.parent.parent / "_static" / "widgets.js").read_text()
    docs = re.findall(r"\['([^']+)', '([^']+)'\]", js[js.index("var BM25_DOCS"):js.index("var BM25_STOP")])
    stop = set(re.findall(r"(\w+): 1", js[js.index("var BM25_STOP"):js.index("function bm25Tokens")]))
    tok = lambda t: [w.rstrip(".") for w in re.findall(r"[a-z0-9_.]+", t.lower()) if w.rstrip(".") and w.rstrip(".") not in stop]
    D = [tok(d[1]) for d in docs]
    avg = np.mean([len(d) for d in D])
    terms = ["pump", "suction", "pressure"]
    idf = [math.log(1 + (len(D) - sum(t in d for d in D) + 0.5) / (sum(t in d for d in D) + 0.5)) for t in terms]
    parts = np.array([[idf[j] * d.count(t) * 2.2 / (d.count(t) + 1.2 * (0.25 + 0.75 * len(d) / avg)) if d.count(t) else 0
                       for j, t in enumerate(terms)] for d in D])
    order = np.argsort(-parts.sum(axis=1))
    fig, ax = plt.subplots(figsize=(9, 3.6))
    left = np.zeros(len(order))
    for j, (t, col) in enumerate(zip(terms, [BLUE, ORANGE, GREEN])):
        ax.barh(range(len(order)), parts[order, j], left=left, color=col, label=f"{t} (idf {idf[j]:.2f})")
        left += parts[order, j]
    ax.set_yticks(range(len(order)), [f"{docs[i][0]} ({len(D[i])} words)" for i in order], fontsize=9)
    ax.invert_yaxis()
    ax.set(xlabel="BM25 score", title='"pump suction pressure", k1 = 1.2, b = 0.75')
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.savefig(HERE / "widget-bm25.png"); plt.close(fig)
    print("wrote recall-ladder, abstention, chunk-sweep, scale, widget-corpus-map, widget-maxsim, widget-bm25")


GROUPS = {"ladder": run_ladder, "sweep": run_sweep, "scale": run_scale, "widgets": run_widgets, "plots": run_plots}

if __name__ == "__main__":
    for g in sys.argv[1:] or list(GROUPS):
        GROUPS[g]()
