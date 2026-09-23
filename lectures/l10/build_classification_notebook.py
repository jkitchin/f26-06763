#!/usr/bin/env python3
"""Generate lectures/l10/l10-classification.ipynb.

The classification demo, which moved here from Lecture 9 with that material. Three steps:

  1. the moons (make_moons): logistic regression, a depth-3 tree, a network of five ReLU
     units and a Gaussian process classifier, and their decision regions
  2. Tennessee Eastman (the miniproject's two files, split by run): a baseline that always
     says normal, logistic regression, a tree and a network, scored by accuracy,
     precision, recall and F1, and the network's confusion matrix with the faulty class
     first
  3. the same network on eight faults it never saw

Design notes:
  - Same data, splits, models and seeds as figures/make_figures.py, and as the Lecture 9
    notebook these cells came from, so the notebook reproduces the numbers in the notes
    (moons test accuracy 0.867, 0.911, 0.933 and 0.967; TEP recall 0.803 for logistic
    regression, 0.855 for the tree and 0.961 for the network; recall on the unseen
    faults from 0.001 to 0.924).
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
# L10 demo: classification with scikit-learn

Classification predicts a category instead of a number. Every model here is used the same way
as the regression models of Lecture 9: `model.fit(X_train, y_train)`, then `model.predict(X)`.

1. **The moons.** Four classifiers on two features, so you can see each one's decision regions.
2. **Tennessee Eastman.** Each snapshot of the plant is normal or faulty, and four classifiers
   are scored with accuracy, precision, recall and F1.
3. **Faults it never saw.** The best of those classifiers meets eight faults that were not in
   its training data.
"""),

    code("""
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pyarrow    # noqa: F401  pandas needs it to read the Parquet files

from sklearn.datasets import make_moons
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF
from sklearn.metrics import (accuracy_score, precision_score, recall_score, f1_score,
                             confusion_matrix)

DATA = Path("data"); DATA.mkdir(exist_ok=True)
"""),

    md("""
## 1. The moons

The moons are a synthetic dataset from scikit-learn's `make_moons`: two interleaving
half-circles, one for each class, with Gaussian noise added to every point. There are 300
points, of which 210 train the models and 90 test them. The data have two features, so the
whole plane can be colored by each model's prediction, and no straight line separates the two
classes.
"""),

    code("""
Xm, ym = make_moons(
    n_samples=300,
    noise=0.25,
    random_state=0,
)
Xm_tr, Xm_te, ym_tr, ym_te = train_test_split(
    Xm, ym,
    test_size=0.3,
    random_state=42,
)
print(f"Training points: {len(ym_tr)}, test points: {len(ym_te)}")
print(f"Class 0: {(ym == 0).sum()} points, class 1: {(ym == 1).sum()} points")
"""),

    md("""
Four classifiers, one from each family, each fitted on the same 210 points and scored on the
other 90. The shading is each model's predicted probability of class 1.
"""),

    code("""
classifiers = {
    "Logistic regression": LogisticRegression(),
    "Decision tree (depth 3)": DecisionTreeClassifier(
        max_depth=3,
        random_state=0,
    ),
    "Neural network (5 ReLU)": MLPClassifier(
        hidden_layer_sizes=(5,),
        activation="relu",
        solver="lbfgs",
        max_iter=2000,
        random_state=0,
    ),
    "Gaussian process": GaussianProcessClassifier(
        kernel=RBF(1.0),
        random_state=0,
        max_iter_predict=200,
    ),
}

xx, yy = np.meshgrid(np.linspace(-2, 3.2, 300), np.linspace(-1.7, 2.1, 300))
fig, axes = plt.subplots(
    1, 4,
    figsize=(15, 3.8),
    sharey=True,
)
for ax, (name, clf) in zip(axes, classifiers.items()):
    clf.fit(Xm_tr, ym_tr)
    accuracy = accuracy_score(ym_te, clf.predict(Xm_te))
    print(f"{name:24s} test accuracy {accuracy:.3f}")
    zz = clf.predict_proba(np.c_[xx.ravel(), yy.ravel()])[:, 1].reshape(xx.shape)
    ax.contourf(
        xx, yy, zz,
        levels=11,
        alpha=0.45,
    )
    ax.scatter(
        Xm[:, 0], Xm[:, 1],
        c=ym,
        edgecolor="k",
        s=14,
    )
    ax.set_title(f"{name}\\nTest accuracy {accuracy:.3f}")
plt.tight_layout()
"""),

    md("""
**What to look for.** Logistic regression can only draw a straight line. The tree cuts the
plane into rectangles, and the network bends its boundary out of a few straight pieces. The
Gaussian process draws a smooth curve, and its probability fades toward 0.5 away from the data.
"""),

    md("""
## 2. Tennessee Eastman: normal or faulty?

The miniproject's two files hold fault-free runs of the plant and runs with faults 1 to 20, where
each fault starts after sample 20. A sample is **faulty** if it comes from a fault run after the
fault started. The first time, the two files download 45 MB into `data/`.
"""),

    code("""
HOST = "https://kitchin-services.cheme.cmu.edu/f26-06763/data/"
for f in ["tep_fault_free_training.parquet", "tep_faulty_training_runs01-20.parquet"]:
    if not (DATA / f).exists():
        urllib.request.urlretrieve(HOST + f, DATA / f)
fault_free = pd.read_parquet(DATA / "tep_fault_free_training.parquet")
faulty = pd.read_parquet(DATA / "tep_faulty_training_runs01-20.parquet")
"""),

    md("""
The rows are split by run, as in Lecture 8, so no run appears on both sides. The classifiers
train on fault-free runs 1 to 300 and on runs 1 to 5 of nine faults. They are tested on
fault-free runs 401 to 500 and on runs 11 and 12 of the same nine faults.
"""),

    code("""
CHANNELS = [f"xmeas_{i}" for i in range(1, 42)] + [f"xmv_{i}" for i in range(1, 12)]
SEEN = [1, 2, 4, 5, 6, 7, 8, 12, 13]           # the faults the classifier learns

def plant_table(normal_runs, faults, fault_runs):
    \"\"\"52 channels and a 0/1 label, from whole runs only.\"\"\"
    d = pd.concat([fault_free[fault_free.simulationRun.isin(normal_runs)],
                   faulty[faulty.faultNumber.isin(faults) & faulty.simulationRun.isin(fault_runs)]])
    label = ((d.faultNumber > 0) & (d["sample"] > 20)).astype(int).to_numpy()
    return d[CHANNELS].to_numpy(), label

Xp_tr, yp_tr = plant_table(range(1, 301), SEEN, range(1, 6))       # train on these runs
Xp_te, yp_te = plant_table(range(401, 501), SEEN, range(11, 13))   # test on other runs
print(f"Train: {len(yp_tr):,} samples, {yp_tr.mean():.1%} faulty")
print(f"Test:  {len(yp_te):,} samples, {yp_te.mean():.1%} faulty")
"""),

    md("""
There are four classifiers. The first is a baseline that always answers "normal", so it never
raises an alarm. Compare its accuracy with its recall.
"""),

    code("""
plant_models = {
    "Baseline: always normal": DummyClassifier(strategy="most_frequent"),
    "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    "Decision tree": DecisionTreeClassifier(
        max_depth=8,
        random_state=0,
    ),
    "Neural network": make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(32,),
            max_iter=300,
            early_stopping=True,
            random_state=0,
        ),
    ),
}
rows = {}
for name, clf in plant_models.items():
    p = clf.fit(Xp_tr, yp_tr).predict(Xp_te)
    rows[name] = {
        "accuracy": accuracy_score(yp_te, p),
        "precision": precision_score(yp_te, p, zero_division=0),
        "recall": recall_score(yp_te, p),
        "F1": f1_score(yp_te, p),
    }
pd.DataFrame(rows).T.round(3)
"""),

    md("""
The confusion matrix counts the test samples by their actual class (the rows) and their
predicted class (the columns). With `labels=[1, 0]` the faulty class comes first, so the top row
holds the true positives and the false negatives. Precision, recall and F1 all come from these
four numbers.
"""),

    code("""
cm = confusion_matrix(
    yp_te,
    plant_models["Neural network"].predict(Xp_te),
    labels=[1, 0],
)
(tp, fn), (fp, tn) = cm
precision, recall = tp / (tp + fp), tp / (tp + fn)
print(f"Precision TP / (TP + FP) = {precision:.3f}")
print(f"Recall    TP / (TP + FN) = {recall:.3f}")
print(f"F1        2PR / (P + R)  = {2 * precision * recall / (precision + recall):.3f}")
pd.DataFrame(
    cm,
    index=["Actually faulty", "Actually normal"],
    columns=["Predicted faulty", "Predicted normal"],
)
"""),

    md("""
## 3. Faults it never saw

The network learned faults 1, 2, 4, 5, 6, 7, 8, 12 and 13. Here it is on eight faults that were
not in its training data, again on runs 11 and 12 after each fault starts.
"""),

    code("""
nn = plant_models["Neural network"]
print(f"Faults it learned: recall {nn.predict(Xp_te[yp_te == 1]).mean():.3f}")
for f in [10, 11, 14, 16, 17, 18, 19, 20]:
    run = faulty[(faulty.faultNumber == f) & faulty.simulationRun.isin(range(11, 13))
                 & (faulty["sample"] > 20)]
    print(f"Fault {f:2d}: recall {nn.predict(run[CHANNELS].to_numpy()).mean():.3f}")
"""),

    md("""
**What happened.** On the faults it knows, the network catches 96% of the faulty samples. On new
faults it catches anything from almost nothing to most of them, and nothing about the classifier
tells you which in advance. A supervised model answers the question "does this look like a fault
I have seen?". The miniproject asks the other question, "does this still look like normal
operation?", with detectors trained on the fault-free runs only.

**Try it.** In step 2, train on fault 14 alone (`SEEN = [14]`) and compare the logistic
regression with the tree. Why does the straight line miss it? A histogram of `xmv_10` shows why.
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
