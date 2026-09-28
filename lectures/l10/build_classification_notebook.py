#!/usr/bin/env python3
"""Generate lectures/l10/l10-classification.ipynb.

The live classification demo. One dataset, one classifier, six short steps:

  1. load the miniproject's two Tennessee Eastman (TEP) files
  2. build the train and test tables by run, exactly as figures/make_figures.py does
  3. fit the 52-channel classifier (a small neural network)
  4. read its confusion matrix, precision and recall at the default threshold
  5. move the threshold and watch precision trade against recall
  6. check its recall on eight faults it never trained on

Design notes:
  - One classifier, not four. The four model families from Lecture 9 are discussed as a
    table in the notes and the slides; this notebook fits only the neural network, so a
    student watching it live sees one thing done well rather than four things done fast.
  - Same data, split, model and seeds as figures/make_figures.py, so the notebook
    reproduces the numbers in the notes and the deck (training rows 172,500 at 12.5%
    faulty; test rows 59,000 at 14.6% faulty; accuracy 0.994, precision 0.998, recall
    0.961; recall on the unseen faults from 0.001 to 0.924).
  - Faults 3, 9 and 15 never appear. The miniproject's evidence script checks that
    students find those three for themselves.
  - The two plant files download once, 45 MB, into data/ next to the notebook, which
    is gitignored.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed
.ipynb carries no outputs and must run top to bottom.

    python3 lectures/l10/build_classification_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l10-classification.ipynb"

_n = 0


def _next_id(kind):
    global _n
    _n += 1
    return f"{kind}-{_n:02d}"


def _src(text):
    lines = text.strip("\n").split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


def md(text):
    return {"cell_type": "markdown", "id": _next_id("md"),
            "metadata": {}, "source": _src(text)}


def code(text):
    return {"cell_type": "code", "id": _next_id("code"), "execution_count": None,
            "metadata": {}, "outputs": [], "source": _src(text)}


cells = [
    md("""
# L10 demo: is the plant faulty?

A classifier works like the regression models of Lecture 9: `model.fit(X_train, y_train)`,
then `model.predict(X)`. It predicts a category instead of a number. This notebook fits one
classifier on the Tennessee Eastman process (TEP), a simulated chemical plant.

1. **Build the tables.** Load the plant data and split it by run, the way Lecture 8 and
   Lecture 9 both did.
2. **Fit and read.** One classifier, a confusion matrix, and what happens when you slide
   the decision threshold.
3. **Faults it never saw.** How it does on faults that were not in its training data.
"""),

    code("""
import urllib.request
from pathlib import Path

import pandas as pd
import pyarrow    # noqa: F401  pandas needs it to read the Parquet files

from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    confusion_matrix,
)

DATA = Path("data")
DATA.mkdir(exist_ok=True)
"""),

    md("""
## 1. Load the two plant files

The two files hold fault-free runs of the plant and runs with faults 1 to 20, sampled every
three minutes. Each fault run starts fault-free and switches the fault on after
sample 20. The first time, the two files download 45 MB into `data/`.
"""),

    code("""
HOST = "https://kitchin-services.cheme.cmu.edu/f26-06763/data/"
for name in ["tep_fault_free_training.parquet", "tep_faulty_training_runs01-20.parquet"]:
    if not (DATA / name).exists():
        urllib.request.urlretrieve(HOST + name, DATA / name)

fault_free = pd.read_parquet(DATA / "tep_fault_free_training.parquet")
faulty = pd.read_parquet(DATA / "tep_faulty_training_runs01-20.parquet")
print(f"Fault-free rows: {len(fault_free):,}   faulty rows: {len(faulty):,}")
"""),

    md("""
## 2. Build the train and test tables, by run

A sample is **faulty** once it comes from a fault run after sample 20. The rows are split by
run, as in Lecture 8 and Lecture 9, so no run appears on both sides: training uses fault-free
runs 1 to 300 and runs 1 to 5 of nine faults, testing uses fault-free runs 401 to 500 and runs
11 and 12 of the same nine faults. Every one of the plant's 52 channels goes in.
"""),

    code("""
CHANNELS = [f"xmeas_{i}" for i in range(1, 42)] + [f"xmv_{i}" for i in range(1, 12)]
SEEN = [1, 2, 4, 5, 6, 7, 8, 12, 13]      # the faults this classifier trains on

def tep_table(normal_runs, faults, fault_runs):
    \"\"\"52 channels and a 0/1 label, built from whole runs only.\"\"\"
    d = pd.concat(
        [
            fault_free[fault_free.simulationRun.isin(normal_runs)],
            faulty[faulty.faultNumber.isin(faults) & faulty.simulationRun.isin(fault_runs)],
        ],
        ignore_index=True,
    )
    label = ((d.faultNumber > 0) & (d["sample"] > 20)).astype(int).to_numpy()
    return d[CHANNELS].to_numpy(), label

X_train, y_train = tep_table(range(1, 301), SEEN, range(1, 6))
X_test, y_test = tep_table(range(401, 501), SEEN, range(11, 13))
print(f"Train: {len(y_train):,} rows, {y_train.mean():.1%} faulty")
print(f"Test:  {len(y_test):,} rows, {y_test.mean():.1%} faulty")
print(f"A classifier that always said 'normal' would score {1 - y_test.mean():.1%}"
      " accuracy and 0 recall.")
"""),

    md("""
## 3. Fit one classifier

- `StandardScaler` rescales each channel to mean 0 and standard deviation 1.
- `MLPClassifier` is a small neural network: one hidden layer of 32 ReLU (rectified linear
  unit) units.
- `make_pipeline` chains the two, so the scaling is learned from the training rows only.
- `early_stopping=True` sets aside 10% of the training rows and stops training when the score
  on them stops improving.

The classifier sees all 52 channels at once. It never sees the fault number, only whether the
sample is faulty.
"""),

    code("""
model = make_pipeline(
    StandardScaler(),
    MLPClassifier(
        hidden_layer_sizes=(32,),
        max_iter=300,
        early_stopping=True,
        random_state=0,
    ),
).fit(X_train, y_train)
print(f"Stopped after {model[-1].n_iter_} passes over the training data.")
"""),

    md("""
## 4. Confusion matrix, precision and recall

The confusion matrix counts test rows by their actual class (the rows) and their predicted
class (the columns). Four counts fall out of it:

- **TP (true positive)**: actually faulty, predicted faulty.
- **FN (false negative)**: actually faulty, predicted normal. A missed fault.
- **FP (false positive)**: actually normal, predicted faulty. A false alarm.
- **TN (true negative)**: actually normal, predicted normal.

With `labels=[1, 0]` the faulty class comes first, so the top row of the matrix holds TP
and FN. Precision and recall come from these four counts:

- **Precision** = TP / (TP + FP): the share of the alarms that were real faults.
- **Recall** = TP / (TP + FN): the share of the real faults that were caught.
"""),

    code("""
pred = model.predict(X_test)
cm = confusion_matrix(
    y_test,
    pred,
    labels=[1, 0],
)
(tp, fn), (fp, tn) = cm

print(f"Accuracy  {accuracy_score(y_test, pred):.3f}")
print(f"Precision {precision_score(y_test, pred):.3f}   TP / (TP + FP)")
print(f"Recall    {recall_score(y_test, pred):.3f}   TP / (TP + FN)")

pd.DataFrame(
    cm,
    index=["Actually faulty", "Actually normal"],
    columns=["Predicted faulty", "Predicted normal"],
)
"""),

    md("""
## 5. Moving the threshold

`predict` returns the class it thinks each row belongs to, faulty or normal, using a 0.5
cutoff on the predicted probability. `predict_proba` returns the probability of each class
instead, so you can choose your own cutoff; its column 1 is the probability of a fault.
Move the cutoff down and more faults get caught, with more false alarms. Move it up and the
reverse happens.
"""),

    code("""
proba = model.predict_proba(X_test)[:, 1]

for t in [0.1, 0.5, 0.9]:
    call = (proba >= t).astype(int)
    tp = int(((call == 1) & (y_test == 1)).sum())
    fp = int(((call == 1) & (y_test == 0)).sum())
    fn = int(((call == 0) & (y_test == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    print(f"threshold {t:.1f}   precision {precision:.3f}   recall {recall:.3f}")
"""),

    md("""
## 6. Faults it never saw

The classifier learned faults 1, 2, 4, 5, 6, 7, 8, 12 and 13. Here it meets eight faults that
were never in its training data, on runs 11 and 12 again, after each fault starts.
"""),

    code("""
UNSEEN = [10, 11, 14, 16, 17, 18, 19, 20]   # never trained on

print(f"Faults it learned:  recall {model.predict(X_test[y_test == 1]).mean():.3f}")
for fault in UNSEEN:
    run = faulty[(faulty.faultNumber == fault) & faulty.simulationRun.isin(range(11, 13))
                & (faulty["sample"] > 20)]
    print(f"Fault {fault:2d} (never seen): recall {model.predict(run[CHANNELS].to_numpy()).mean():.3f}")
"""),

    md("""
**What happened.** On the faults it learned, the classifier catches 96% of the faulty
samples. On faults it never trained on, recall goes from almost nothing (fault 19) to most of
them (fault 18), and nothing in the classifier tells you in advance which. It only answers
"does this look like a fault I have seen?"

**Try it.** In step 5, add `0.99` to the threshold list. Precision is already at 1.000 by
0.9, so watch recall alone keep falling as the bar rises further.
"""),
]

# The Colab bootstrap cell, injected from the notebook's own imports.
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
