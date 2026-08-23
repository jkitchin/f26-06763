#!/usr/bin/env python3
"""Generate lectures/l18/l18-prompt-vs-rag.ipynb.

The L18 demo is a prompting-vs-RAG bake-off: one small engineering corpus, one
query->answer gold set, two systems scored on the same metric. It makes the
adaptation decision framework concrete and measurable, with no GPU and no network.

  - Prompting baseline: the model answers from its latent knowledge alone. For
    niche spec values it does not have, it guesses (a stand-in for hallucination).
  - RAG: real TF-IDF retrieval over the corpus, then a deterministic extractive
    reader pulls the answer from the retrieved context, with a confidence
    threshold that returns "not in the provided documents" when nothing matches.

The retrieval and the reading are genuinely computed, so RAG's score is driven by
whether retrieval surfaced the answer, not by canned responses. The prompting
answers are canned to represent a base model without the corpus. The point is the
contrast: RAG wins on knowledge lookups, prompting already suffices on the
formatting task, and fine-tuning (discussed in the notes, not run) is the scaled
version of the formatting lever.

Design notes: sklearn + numpy only; deterministic; runs top to bottom offline.
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l18-prompt-vs-rag.ipynb"

_n = 0


def _next_id(kind):
    global _n
    _n += 1
    return f"{kind}-{_n:02d}"


def md(*lines):
    return {"cell_type": "markdown", "id": _next_id("md"),
            "metadata": {}, "source": list(lines)}


def code(*lines):
    return {"cell_type": "code", "id": _next_id("code"), "execution_count": None,
            "metadata": {}, "outputs": [], "source": list(lines)}


cells = [
    md("# L18 demo: prompting vs RAG, measured\n",
       "\n",
       "One engineering corpus, one gold set, two systems scored the same way. This is the\n",
       "decision framework made concrete: when does retrieval earn its keep over a bare prompt?\n",
       "\n",
       "> Companion notes: [`notes.md`](notes.md). Fine-tuning is the third lever; the notes\n",
       "> explain when to use it, and why it is not what you reach for here.\n",
       "\n",
       "No GPU, no network, no API key: retrieval and scoring are computed locally."),

    md("## Setup"),
    code("import re, json\n",
         "import numpy as np\n",
         "from sklearn.feature_extraction.text import TfidfVectorizer\n",
         "from sklearn.metrics.pairwise import cosine_similarity\n",
         "np.random.seed(0)"),

    md("## The corpus\n",
       "\n",
       "A handful of engineering-reference snippets, the kind an engineer looks things up in.\n",
       "Each carries a source tag so a grounded answer can cite it. Some are distractors: near\n",
       "the queries in wording but not the answer."),
    code("CORPUS = [\n",
         "  ('PlumbCode 7.3', 'Cold bending of annealed copper tube. The minimum centerline bend '\n",
         "   'radius for 12 mm outside-diameter annealed copper tube is 45 mm. For 15 mm tube it is 60 mm.'),\n",
         "  ('PipeSpec 4.1', 'Schedule 40 carbon steel pipe, ASTM A53. The maximum allowable working '\n",
         "   'pressure for 2-inch Schedule 40 pipe at 200 C is 2.4 MPa; at 20 C it is 3.1 MPa.'),\n",
         "  ('FastenGuide 2.2', 'Grade 8.8 M12 hex bolts, lightly oiled, shall be tightened to a '\n",
         "   'torque of 86 N-m. Grade 10.9 M12 bolts to 121 N-m.'),\n",
         "  ('GasketMan 3.5', 'Spiral-wound gaskets with flexible graphite filler are rated for '\n",
         "   'continuous service from -200 C to 450 C.'),\n",
         "  ('PumpManual 9.1', 'The required NPSH for the CP-4L pump at rated flow is 3.2 m. Available '\n",
         "   'NPSH must exceed this value by a margin of 0.6 m.'),\n",
         "  # distractors: similar vocabulary, not the answer\n",
         "  ('PlumbCode 7.1', 'Copper tube shall be cut square and deburred before bending. Annealed '\n",
         "   'tube bends cold; hard-drawn tube requires a bending spring or fittings.'),\n",
         "  ('PipeSpec 1.2', 'Carbon steel pipe shall be marked with the heat number, schedule, and '\n",
         "   'specification. Schedule 40 is the most common wall thickness for general service.'),\n",
         "  ('FastenGuide 1.1', 'Bolt torque depends on grade, lubrication, and thread pitch. Always '\n",
         "   'use a calibrated wrench; dry threads need more torque than oiled ones.'),\n",
         "]\n",
         "SOURCES = [c[0] for c in CORPUS]\n",
         "TEXTS = [c[1] for c in CORPUS]\n",
         "print(f'{len(CORPUS)} chunks ({sum(t.count(\".\") for t in TEXTS)} sentences)')"),

    md("## The gold set\n",
       "\n",
       "The questions an engineer actually asks. Five are **knowledge lookups** whose answers live\n",
       "in the corpus (or, for one, deliberately do not). One is a **formatting** task that needs\n",
       "no lookup at all. Each has a hand-written correct answer, so we can score automatically."),
    code("GOLD = [\n",
         "  ('what is the minimum bend radius for 12 mm copper tube?', '45 mm', 'knowledge'),\n",
         "  ('maximum allowable working pressure of 2-inch schedule 40 pipe at 200 C?', '2.4 MPa', 'knowledge'),\n",
         "  ('tightening torque for a grade 8.8 M12 bolt?', '86 N-m', 'knowledge'),\n",
         "  ('lower temperature limit of a spiral-wound graphite gasket?', '-200 C', 'knowledge'),\n",
         "  ('required NPSH for the CP-4L pump at rated flow?', '3.2 m', 'knowledge'),\n",
         "  # deliberately NOT in the corpus: a grounded system must decline\n",
         "  ('flash point of ISO VG 46 hydraulic oil?', 'not in the provided documents', 'knowledge-absent'),\n",
         "  # a formatting task: no lookup needed, the base model can already do it\n",
         "  ('normalize the log \"brng making noise on P-101\" to component/symptom', 'bearing/noise', 'formatting'),\n",
         "]\n",
         "print(f'{len(GOLD)} gold queries')"),

    md("## System 1: prompting only\n",
       "\n",
       "The base model answers from what it already knows. It handles the formatting task, but it\n",
       "has never seen these particular specs, so on the lookups it does what a confident model\n",
       "does without grounding: it guesses. These canned answers stand in for a real base model\n",
       "with no access to the corpus."),
    code("# what a base model without the corpus tends to produce: plausible, wrong\n",
         "PROMPT_ONLY = {\n",
         "  'what is the minimum bend radius for 12 mm copper tube?': 'about 3 times the diameter, so ~36 mm',\n",
         "  'maximum allowable working pressure of 2-inch schedule 40 pipe at 200 C?': 'roughly 2.0 MPa',\n",
         "  'tightening torque for a grade 8.8 M12 bolt?': 'approximately 60 N-m',\n",
         "  'lower temperature limit of a spiral-wound graphite gasket?': 'around -50 C',\n",
         "  'required NPSH for the CP-4L pump at rated flow?': 'typically 2 to 3 m',\n",
         "  'flash point of ISO VG 46 hydraulic oil?': 'about 210 C',   # confident and unverifiable\n",
         "  'normalize the log \"brng making noise on P-101\" to component/symptom': 'bearing/noise',\n",
         "}\n",
         "def answer_prompting(query):\n",
         "    return PROMPT_ONLY[query]"),

    md("## System 2: RAG\n",
       "\n",
       "Real retrieval, then a grounded read. We TF-IDF the corpus, retrieve the top-k chunks for\n",
       "the query, then pick the single sentence in those chunks most similar to the query. A\n",
       "confidence threshold makes the system **decline** when nothing matches well, which is what\n",
       "keeps it from inventing an answer that is not in the documents. The formatting task has no\n",
       "answer to retrieve, so RAG falls back to the same normalization the prompt does."),
    code("vec = TfidfVectorizer(stop_words='english').fit(TEXTS)\n",
         "chunk_mat = vec.transform(TEXTS)\n",
         "\n",
         "def retrieve(query, k=3):\n",
         "    sims = cosine_similarity(vec.transform([query]), chunk_mat)[0]\n",
         "    top = np.argsort(sims)[::-1][:k]\n",
         "    return [(SOURCES[i], TEXTS[i]) for i in top]\n",
         "\n",
         "def sentences(chunks):\n",
         "    out = []\n",
         "    for src, text in chunks:\n",
         "        for s in re.split(r'(?<=[.;]) ', text):\n",
         "            if s.strip():\n",
         "                out.append((src, s.strip()))\n",
         "    return out\n",
         "\n",
         "def answer_rag(query, k=3, threshold=0.12):\n",
         "    if 'normalize the log' in query:                 # formatting: nothing to ground\n",
         "        return 'bearing/noise', None\n",
         "    chunks = retrieve(query, k)\n",
         "    cand = sentences(chunks)\n",
         "    svec = vec.transform([s for _, s in cand])\n",
         "    sims = cosine_similarity(vec.transform([query]), svec)[0]\n",
         "    best = int(sims.argmax())\n",
         "    if sims[best] < threshold:\n",
         "        return 'not in the provided documents', None\n",
         "    return cand[best][1], cand[best][0]              # grounded sentence + source"),

    md("## Score them on the same gold set\n",
       "\n",
       "A prediction counts as correct if the gold answer string appears in it (for the absent\n",
       "query, the system must decline). Same metric, same data, both systems."),
    code("def correct(pred, gold):\n",
         "    return gold.lower() in pred.lower()\n",
         "\n",
         "rows = []\n",
         "for query, gold, cat in GOLD:\n",
         "    p = answer_prompting(query)\n",
         "    r, src = answer_rag(query)\n",
         "    rows.append((cat, query, gold, p, correct(p, gold), r, src, correct(r, gold)))\n",
         "\n",
         "print(f'{\"category\":16} {\"prompting\":10} {\"RAG\":6}')\n",
         "for cat in ['knowledge', 'knowledge-absent', 'formatting']:\n",
         "    sub = [x for x in rows if x[0] == cat]\n",
         "    pc = sum(x[4] for x in sub); rc = sum(x[7] for x in sub)\n",
         "    print(f'{cat:16} {pc}/{len(sub):<8} {rc}/{len(sub)}')"),
    code("# the detail, one row per query\n",
         "for cat, q, gold, p, pok, r, src, rok in rows:\n",
         "    print(f'Q: {q}')\n",
         "    print(f'   gold     : {gold}')\n",
         "    print(f'   prompting: {p[:70]:70} {\"OK\" if pok else \"X\"}')\n",
         "    print(f'   RAG      : {(r[:60] + (\" [\" + src + \"]\" if src else \"\"))[:70]:70} {\"OK\" if rok else \"X\"}')\n",
         "    print()"),

    md("## Read the result\n",
       "\n",
       "On the knowledge lookups RAG grounds its answers in a cited chunk while the bare prompt\n",
       "guesses every one, and on the absent query RAG declines where the prompt confidently\n",
       "invents a flash point. RAG scores 4 of 5 rather than a clean sweep, and the miss is worth\n",
       "keeping: the bolt-torque query retrieved a *distractor* sentence (\"Bolt torque depends on\n",
       "grade, lubrication, and thread pitch\") instead of the one with the actual 86 N-m value, so\n",
       "the grounded answer is on-topic but wrong. That is L17's lesson showing up here: retrieval\n",
       "quality is not free, and a distractor that shares the query's words can outrank the answer.\n",
       "On the formatting task the two tie, because there is nothing to retrieve and a decent\n",
       "prompt already does the job. The framework falls out of the table: **knowledge is RAG's\n",
       "job; behavior and format are the prompt's, and fine-tuning's at scale.**"),
    code("import matplotlib.pyplot as plt\n",
         "cats = ['knowledge', 'knowledge-absent', 'formatting']\n",
         "labels = ['knowledge\\nlookup', 'absent\\n(must decline)', 'formatting']\n",
         "prompting = [sum(x[4] for x in rows if x[0] == c) / max(1, sum(1 for x in rows if x[0] == c)) for c in cats]\n",
         "rag = [sum(x[7] for x in rows if x[0] == c) / max(1, sum(1 for x in rows if x[0] == c)) for c in cats]\n",
         "x = np.arange(len(cats)); w = 0.38\n",
         "fig, ax = plt.subplots(figsize=(8, 4.6))\n",
         "ax.bar(x - w/2, [v*100 for v in prompting], w, label='prompting', color='#5c5c5c')\n",
         "ax.bar(x + w/2, [v*100 for v in rag], w, label='RAG', color='#c41230')\n",
         "ax.set_xticks(x); ax.set_xticklabels(labels)\n",
         "ax.set_ylabel('accuracy (%)'); ax.set_ylim(0, 105)\n",
         "ax.set_title('Prompting vs RAG on the same gold set'); ax.legend(frameon=False)\n",
         "for spine in ['top', 'right']: ax.spines[spine].set_visible(False)\n",
         "plt.show()"),

    md("---\n",
       "\n",
       "## Takeaway\n",
       "\n",
       "The lever follows the need. When the task is **knowledge** the model lacks, retrieval wins\n",
       "and, just as important, lets the system cite its source and decline when it does not know.\n",
       "When the task is **behavior or format**, a good prompt already suffices, and fine-tuning is\n",
       "the same lever scaled up for when the format must be baked in across thousands of calls.\n",
       "The mistake the notes warn about is reaching for fine-tuning to inject knowledge: this\n",
       "bake-off is the measured version of why that is the wrong tool. Assignment A9 builds the\n",
       "RAG half of this for real."),
]

# The Colab bootstrap cell, injected from the notebook's own imports so this
# generator does not carry a second copy of the requirement list. See
# tools/colab_setup.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells = with_colab_cell(cells, OUT)

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT} ({len(cells)} cells)")
