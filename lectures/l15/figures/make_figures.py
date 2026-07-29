#!/usr/bin/env python3
"""Generate the L15 figures: a from-scratch BPE tokenizer and a lexical baseline
for embeddings.

Run with:
    uv run --with numpy,matplotlib,scikit-learn python make_figures.py

Every number quoted in notes.md and slides.md is printed by this script.

Neither figure calls a hosted LLM or embedding API. This session's sandbox has
no network route to Anthropic, OpenAI, or Hugging Face (only package
registries are reachable), so a live provider tokenizer or embedding model
cannot be executed here. Rather than assert numbers from memory, this script
trains a small byte-pair-encoding tokenizer from scratch on a corpus written
for this file, and it computes TF-IDF cosine similarity as an explicit,
labelled stand-in for a semantic embedding. Both are real, rerunnable
computations, and both are honest about what they are not: the toy BPE is not
GPT's or Claude's tokenizer, and TF-IDF is not a learned embedding. The point
each figure makes (subword fragmentation is frequency-driven; lexical overlap
is not semantic similarity) is the same point the real APIs would make, and
`demo.ipynb` calls the real APIs in class, where network access and a
provider key are available.

Outputs (committed alongside this script):
    bpe-fragmentation.png     a toy BPE trained on engineering prose, applied
                              to units, alloy codes, and a chemical formula
    lexical-similarity.png    TF-IDF cosine similarity across 24 maintenance
                              log entries in 5 fault categories
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

FIGDIR = Path(__file__).parent
EOW = "·"  # end-of-word marker, kept out of the corpus text itself

# ---------------------------------------------------------------------------
# Part A: a byte-pair-encoding tokenizer, trained from scratch on a small
# corpus of ordinary engineering prose (the kind of sentence a datasheet's
# cover page or a maintenance report's narrative field contains).
# ---------------------------------------------------------------------------

CORPUS = """
the pump operated within specification during the trial run
the technician recorded the pressure and the temperature at the start of the shift
the valve closed within the specified time and the seal held
the operator inspected the bearing and reported no unusual noise
the report noted that the motor current stayed within the normal range
the inspection found the coupling aligned within tolerance
the crew replaced the filter and restarted the pump without incident
the gauge reading matched the reference value recorded at commissioning
the technician logged the flow rate and the discharge pressure
the maintenance team verified the torque on the mounting bolts
the operator confirmed the alarm cleared after the reset
the shift log recorded a routine inspection with no findings
""".strip()


def word_freqs(corpus: str) -> Counter:
    words = re.findall(r"[a-z]+", corpus.lower())
    return Counter(words)


def train_bpe(corpus: str, num_merges: int) -> list[tuple[str, str]]:
    """Learn `num_merges` merge rules by iteratively combining the most
    frequent adjacent symbol pair, weighted by word frequency. This is the
    Sennrich, Haddow and Birch (2016) algorithm, run on characters."""
    freqs = word_freqs(corpus)
    # Each word starts as a tuple of characters plus an end-of-word marker.
    vocab = {tuple(w) + (EOW,): c for w, c in freqs.items()}
    merges: list[tuple[str, str]] = []

    for _ in range(num_merges):
        pair_counts: Counter = Counter()
        for symbols, count in vocab.items():
            for a, b in zip(symbols, symbols[1:]):
                pair_counts[(a, b)] += count
        if not pair_counts:
            break
        # Deterministic tie-break: highest count, then lexicographic.
        best = max(pair_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        if pair_counts[best] < 2:
            break
        merges.append(best)
        new_vocab = {}
        merged_token = best[0] + best[1]
        for symbols, count in vocab.items():
            out = []
            i = 0
            while i < len(symbols):
                if (
                    i < len(symbols) - 1
                    and symbols[i] == best[0]
                    and symbols[i + 1] == best[1]
                ):
                    out.append(merged_token)
                    i += 2
                else:
                    out.append(symbols[i])
                    i += 1
            new_vocab[tuple(out)] = new_vocab.get(tuple(out), 0) + count
        vocab = new_vocab
    return merges


def apply_bpe(word: str, merges: list[tuple[str, str]]) -> list[str]:
    symbols = list(word.lower()) + [EOW]
    rank = {pair: i for i, pair in enumerate(merges)}
    while len(symbols) > 1:
        pairs = list(zip(symbols, symbols[1:]))
        candidates = [(rank[p], i) for i, p in enumerate(pairs) if p in rank]
        if not candidates:
            break
        _, i = min(candidates)
        symbols = symbols[:i] + [symbols[i] + symbols[i + 1]] + symbols[i + 2 :]
    return symbols


def tokenize(text: str, merges: list[tuple[str, str]]) -> list[str]:
    tokens: list[str] = []
    for chunk in re.findall(r"[a-zA-Z]+|[^a-zA-Z\s]|[0-9]+", text):
        if chunk.isalpha():
            tokens.extend(apply_bpe(chunk, merges))
        else:
            # Digits and symbols never appeared in the training corpus, so no
            # merge rule ever applies to them: each becomes its own token,
            # same as a single out-of-vocabulary byte would in a real BPE.
            tokens.extend(list(chunk))
    return tokens


MERGES = train_bpe(CORPUS, num_merges=80)
print(f"[bpe] learned {len(MERGES)} merge rules from a {len(word_freqs(CORPUS))}-word vocabulary")
print(f"[bpe] first 10 merges: {MERGES[:10]}")

TEST_STRINGS = [
    ("plain prose", "the pump operated within specification"),
    ("tolerance", "±0.05 mm"),
    ("diameter callout", "Ø25"),
    ("alloy code", "AISI 4140"),
    ("stainless grade", "SS316L"),
    ("pressure value", "10.5 MPa"),
    ("chemical formula", "Fe2O3"),
]

results = []
for label, s in TEST_STRINGS:
    toks = tokenize(s, MERGES)
    chars = len(s.replace(" ", ""))
    results.append((label, s, toks, len(toks), chars, len(toks) / chars))
    print(f"[bpe] {label!r:22s} {s!r:26s} -> {len(toks):2d} tokens / {chars:2d} chars "
          f"= {len(toks) / chars:.2f} tok/char  {toks}")

fig, ax = plt.subplots(figsize=(9, 5))
labels = [f"{lbl}\n\"{s}\"" for lbl, s, *_ in results]
ratios = [r[5] for r in results]
colors = ["#4C72B0" if r[0] == "plain prose" else "#C44E52" for r in results]
bars = ax.bar(range(len(results)), ratios, color=colors)
ax.set_xticks(range(len(results)))
ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
ax.set_ylabel("tokens per character")
ax.set_title(
    "A tokenizer trained on ordinary prose fragments units, alloy codes,\n"
    "and formulas it never saw, because its merges are frequency-driven"
)
for bar, r in zip(bars, results):
    ax.annotate(f"{r[3]} tok", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                ha="center", va="bottom", fontsize=8)
fig.tight_layout()
fig.savefig(FIGDIR / "bpe-fragmentation.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------------
# Part B: TF-IDF cosine similarity across maintenance-log entries, as an
# explicit lexical-overlap baseline, not a semantic embedding.
# ---------------------------------------------------------------------------

LOG_ENTRIES = [
    ("bearing", "bearing noise reported on drive-end bearing"),
    ("bearing", "noisy bearing, intermittent, worse under load"),
    ("bearing", "brg vibration increasing over past week"),
    ("bearing", "operator heard grinding near the shaft bearing"),
    ("bearing", "abnormal bearing sound at startup, cleared after warmup"),
    ("seal", "seal weeping at the pump gland"),
    ("seal", "leaking gland packing, minor drip rate"),
    ("seal", "pump drips at seal, tightened packing gland"),
    ("seal", "mechanical seal leak, product visible at base"),
    ("seal", "packing gland requires adjustment, slow leak"),
    ("valve", "valve stuck partially open, will not seat"),
    ("valve", "control valve not responding to setpoint change"),
    ("valve", "isolation valve jammed in open position"),
    ("valve", "valve actuator failed to close on command"),
    ("valve", "sticking valve, freed after lubrication"),
    ("corrosion", "corrosion observed on external piping surface"),
    ("corrosion", "rust and pitting on flange face"),
    ("corrosion", "external corrosion under insulation, coating failed"),
    ("corrosion", "surface rust noted on support bracket"),
    ("corrosion", "pitting corrosion found during inspection"),
    ("overheat", "motor running hot, exceeds normal temperature"),
    ("overheat", "high temperature alarm on drive motor"),
    ("overheat", "overheating detected, thermal shutdown triggered"),
    ("overheat", "elevated casing temperature, cooling fan checked"),
]

categories = [c for c, _ in LOG_ENTRIES]
texts = [t for _, t in LOG_ENTRIES]

vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(texts)
sim = cosine_similarity(X)

n = len(texts)
within, between = [], []
for i in range(n):
    for j in range(n):
        if i == j:
            continue
        (within if categories[i] == categories[j] else between).append(sim[i, j])
print(f"[tfidf] mean within-category cosine similarity: {np.mean(within):.3f}")
print(f"[tfidf] mean between-category cosine similarity: {np.mean(between):.3f}")

brg_idx = texts.index("brg vibration increasing over past week")
bearing_idxs = [i for i, c in enumerate(categories) if c == "bearing" and i != brg_idx]
brg_to_own_category = np.mean([sim[brg_idx, j] for j in bearing_idxs])
brg_best_other = max(sim[brg_idx, j] for j in range(n) if categories[j] != "bearing")
print(f"[tfidf] 'brg vibration' mean similarity to its own (bearing) cluster: {brg_to_own_category:.3f}")
print(f"[tfidf] 'brg vibration' best similarity to any other cluster: {brg_best_other:.3f}")

fig, ax = plt.subplots(figsize=(8, 7))
im = ax.imshow(sim, cmap="viridis", vmin=0, vmax=1)
ax.set_xticks(range(n))
ax.set_yticks(range(n))
short_labels = [f"{c}: {t[:28]}" for c, t in LOG_ENTRIES]
ax.set_xticklabels(range(1, n + 1), fontsize=7)
ax.set_yticklabels(short_labels, fontsize=6.5)
ax.set_title(
    "TF-IDF cosine similarity, 24 maintenance-log entries\n"
    "(a lexical-overlap baseline, not a semantic embedding)"
)
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="cosine similarity")
fig.savefig(FIGDIR / "lexical-similarity.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("\nWrote bpe-fragmentation.png and lexical-similarity.png")
