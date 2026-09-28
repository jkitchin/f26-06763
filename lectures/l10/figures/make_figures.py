#!/usr/bin/env python3
"""Generate the L10 figures, and print every number the notes and the deck quote.

Run from this directory:
    uv run --no-project --with numpy --with pandas --with xlrd --with pyarrow \
        --with scikit-learn --with matplotlib --with scipy --with optuna --with mlflow \
        python make_figures.py

Name groups to regenerate only those; with no names, every group runs. The groups, and
what each writes:
    classification  tep-data (the L9 recap figure, reactor pressure under fault 1),
                    tep-fault4-signal (fault 4 as a raw time trace, before any classifier),
                    tep-logistic (the gentle first classifier: logistic regression on one
                    channel), tep-fault14 (rebuilt as two panels: a time trace showing the
                    same mean and a wider spread, and the histogram with the tree's two
                    cuts drawn on it), confusion-explained (the 52-channel classifier's test
                    confusion matrix, drawn as a labeled 2x2 grid with every acronym spelled
                    out), tep-unseen, classifier-shapes (decision regions of four model
                    families on one small synthetic dataset, so a student sees what "a
                    straight line" versus "boxes" versus "a smooth curve" actually looks
                    like; the network there uses tanh units, whose boundary bends smoothly),
                    and the anim-*.png frames the deck's model-family cards play: each
                    model at six stages of training.
    shapes          classifier-shapes and the anim-*.png frames alone, without the TEP data.
    search          grid_vs_random.png (rebuilt so the score curve underneath the points is
                    visible, not just the points), optuna_search.png (Optuna TPE against
                    random search, now tuning Lecture 9's decision tree on concrete instead
                    of a gradient-boosted model) and tpe-explained.png (how TPE splits good
                    and bad trials to choose where to look next); needs optuna and scipy.
    widgets         no figure: prints the constants the interactive slides embed (the TEP
                    threshold sweep, the grid and random search points and the score curve
                    under them, and both Optuna trial tables), so the deck's JavaScript can
                    be checked against it.
    logo            downloads optuna-logo.png from Optuna's own GitHub repository (MIT
                    licensed), unchanged, for the search slides; needs network access.
    recap           copies five PNGs from lectures/l09/figures/, unchanged, for the L9 recap
                    that opens this session.

The printed block is the record. Classification takes under a minute; search (two Optuna
studies of 40 trials each) takes one to two minutes.

WHAT MOVED, AND WHY
--------------------
Classification is one dataset: the Tennessee Eastman process (TEP), normal against faulty.
The moons dataset, its dataset card and its straight-line logistic fit are gone from the TEP
story; what remains of "one dataset, four model shapes" is classifier-shapes.png, a small
synthetic 2D set with a curved true boundary, used only to show what a straight line, a set
of boxes, a smooth network curve and a smooth Gaussian-process curve look like side by side,
with no accuracy numbers attached to that comparison.

Tree ensembles (random forests, gradient boosting) are removed from this lecture entirely,
along with the winner's-curse measurement: both used to live on concrete. What remains on
concrete is the hyperparameter search, now tuning Lecture 9's own decision tree
(`DecisionTreeRegressor`) rather than a gradient-boosted model the room has not met, scored
the same way L9 scored everything: `GroupShuffleSplit(n_splits=1, test_size=0.2,
random_state=42)` on the 428 mix groups gives the same 835 training rows and 195 test rows
(342 and 86 mixes) that L9's script used, and `GroupKFold(5)` on those 835 rows is the
search's CV.

Faults 3, 9 and 15 are deliberately absent from every figure, table and print: the
miniproject's evidence script checks that students find them. The classifier trains on
faults 1, 2, 4, 5, 6, 7, 8, 12 and 13 (SEEN) and is tested on the other eight (UNSEEN).

THE GENTLE INTRODUCTION (tep-fault4-signal.png, tep-logistic.png)
-------------------------------------------------------------------
Before the 52-channel classifier, one channel: fault 4 (a reactor cooling water inlet
temperature step) shifts the mean of xmv_10 (the reactor cooling water valve) cleanly, from
41.1 to 44.9% open, with its spread almost unchanged (std 0.54 against 0.53). tep-fault4-
signal.png draws that shift as a raw time trace, so a student sees the channel move before
any model touches it; tep-logistic.png then fits a 1-D logistic regression to that one
number and draws the S-curve and the threshold. Fault 14 is the deliberate counter-example a
few slides later, on the very same channel: it does not move the mean of xmv_10 at all, only
its spread (0.54 to 7.44), so the same kind of straight decision boundary catches none of it
and a two-cut tree catches most of it. One channel, two fault signatures: a boundary that
works perfectly on one fault can be blind to another.

SEARCH (optuna_search.png, tpe-explained.png)
------------------------------------------------
`grid_vs_random.png` is rebuilt synthetic artwork (Bergstra and Bengio's picture: nine
trials each, only one hyperparameter matters), now drawn with the fabricated validation-
score curve underneath the points so the bump, and which tried point is best, are visible
at a glance. `optuna_search.png` is a real Optuna study on concrete:
`DecisionTreeRegressor(random_state=0)` over `max_depth` (2 to 20) and `min_samples_leaf`
(1 to 50), scored by `GroupKFold(5)` CV RMSE on the 835 training rows, 40 trials,
`TPESampler(seed=0)` against `RandomSampler(seed=0)`. `tpe-explained.png` takes the TPE
study's first 20 trials, splits them the way Optuna's TPESampler does (the best 10% by RMSE
are "good", the rest "bad"), and draws each group's smoothed histogram over
`min_samples_leaf`, the hyperparameter that separates the two groups most clearly, so a
student sees the idea TPE uses to pick where to look next.

DATA (cached, never committed)
-------------------------------
TEP: the miniproject's two files (Rieth et al. 2017, CC0), fetched once into `.cache/` here
or, if `lectures/l09/figures/.cache/` already holds them (L9 fetches the same files), read
from there instead. Concrete: the UCI Concrete Compressive Strength workbook (Yeh 1998, CC BY
4.0), read from `lectures/l09/figures/.cache/Concrete_Data.xls` if present, else downloaded.
`cached()` checks both directories before fetching anything over the network.

FIGURE SHAPES
-------------
Every figure lands on a 1280x720 MARP slide, sized with its fonts so that its smallest text
lands at 16 px or more at the width the deck shows it (the comment on each rc_context is a
working estimate of that width, to be checked against the finished deck with
`tools/check_slides.py`).
"""
from __future__ import annotations

import io
import shutil
import urllib.request
import warnings
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde
from sklearn.datasets import make_moons
from sklearn.dummy import DummyClassifier
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_score
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
L09_CACHE = HERE.parent.parent / "l09" / "figures" / ".cache"
L09_FIGURES = HERE.parent.parent / "l09" / "figures"

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
GOLD = "#b07d12"
GREEN = "#2e7d32"
SEED = 0

# Each group draws under its own style, applied on top of Matplotlib's defaults with
# plt.rc_context, so the two never leak into each other.
CLASSIFICATION_STYLE = {                          # Lecture 9's, unchanged
    "font.size": 12,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": MUTED,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "legend.frameon": False,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
}
QUANT_STYLE = {                                   # search, on concrete
    "font.size": 13, "axes.labelsize": 13, "axes.titlesize": 15,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "figure.dpi": 160, "savefig.bbox": "tight",
}


def fonts(size):
    """rcParams for plt.rc_context that set every text in a figure to `size` pt.

    A figure saved Wsave px wide and shown W px wide on the 1280x720 slide renders an f pt
    font at f * (150 / 72) * (W / Wsave) px. Each classification figure is sized so that its
    smallest text lands at 16 px or more at the width the deck shows it.
    """
    return {
        "font.size": size,
        "axes.labelsize": size,
        "axes.titlesize": size,
        "xtick.labelsize": size,
        "ytick.labelsize": size,
        "legend.fontsize": size,
    }


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def cached(local):
    """A file already fetched by this script or by Lecture 9's, in either .cache/."""
    for d in (CACHE, L09_CACHE):
        p = d / local
        if p.exists():
            return p
    return None


def fetch(url, local):
    path = cached(local)
    if path is not None:
        return path
    CACHE.mkdir(exist_ok=True)
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    path = CACHE / local
    path.write_bytes(urllib.request.urlopen(req).read())
    return path


# --------------------------------------------------------------------------------------
# The Tennessee Eastman data
# --------------------------------------------------------------------------------------
TEP_HOST = "https://kitchin-services.cheme.cmu.edu/f26-06763/data/"
CH = [f"xmeas_{i}" for i in range(1, 42)] + [f"xmv_{i}" for i in range(1, 12)]
SEEN = [1, 2, 4, 5, 6, 7, 8, 12, 13]           # never 3, 9 or 15 (see the docstring)
UNSEEN = [10, 11, 14, 16, 17, 18, 19, 20]
TEP_FAULT, TEP_RUN = 1, 1      # IDV(1), A/C feed ratio step; in SEEN, never 3, 9 or 15


def load_tep():
    ff = pd.read_parquet(fetch(TEP_HOST + "tep_fault_free_training.parquet",
                               "tep_fault_free_training.parquet"))
    fa = pd.read_parquet(fetch(TEP_HOST + "tep_faulty_training_runs01-20.parquet",
                               "tep_faulty_training_runs01-20.parquet"))
    return ff, fa


def tep_onset(ff, fa, fault, runs):
    """First sample at which faulty run r of `fault` differs from fault-free run r.

    Rieth et al. seeded each faulty run like the fault-free run with the same number, so
    the two are identical until the fault is switched on. Returns one sample per run.
    """
    firsts = []
    for r in runs:
        a = fa[(fa.faultNumber == fault) & (fa.simulationRun == r)].sort_values("sample")
        z = ff[ff.simulationRun == r].sort_values("sample")
        same = np.all(a[CH].to_numpy() == z[CH].to_numpy(), axis=1)
        k = int(np.argmin(same))
        assert same[:k].all() and not same[k], "runs differ from the start"
        firsts.append(int(a["sample"].iloc[k]))
    return firsts


def tep_trace(frame, channel="xmeas_7"):
    """Hours and one channel for one run, with sample k at k x 3 minutes."""
    frame = frame.sort_values("sample")
    return frame["sample"].to_numpy() * 3 / 60, frame[channel].to_numpy()


def tep_table(ff, fa, normal_runs, faults, fault_runs):
    d = pd.concat([ff[ff.simulationRun.isin(normal_runs)],
                   fa[fa.faultNumber.isin(faults) & fa.simulationRun.isin(fault_runs)]],
                  ignore_index=True)
    y = ((d.faultNumber > 0) & (d["sample"] > 20)).astype(int).to_numpy()
    return d, d[CH].to_numpy(), y


def tep_data_figure(ff, fa):
    print("\n=== The Tennessee Eastman data, drawn (same figure as Lecture 9) ===")
    firsts = tep_onset(ff, fa, TEP_FAULT, range(1, 21))
    print(f"  TEP fault {TEP_FAULT}, runs 1-20: each identical to the fault-free run of the same number through"
          f" sample {min(firsts) - 1} and first different at sample {sorted(set(firsts))}")
    onset = (min(firsts) - 1) * 3 / 60
    print(f"  so the fault starts after sample {min(firsts) - 1}, at {onset:.2f} hours (samples every 3 minutes)")
    t0, p0 = tep_trace(ff[ff.simulationRun == TEP_RUN])
    t1, p1 = tep_trace(fa[(fa.faultNumber == TEP_FAULT) & (fa.simulationRun == TEP_RUN)])
    print(f"  run {TEP_RUN}: fault-free pressure {p0.min():.0f} to {p0.max():.0f} kPa;"
          f" fault {TEP_FAULT} pressure {p1.min():.0f} to {p1.max():.0f} kPa")
    with plt.rc_context(fonts(14)):             # shown at w:700
        fig, ax = plt.subplots(figsize=(7.7, 2.75))
        ax.plot(t0, p0, color="0.55", lw=1.1, label=f"Fault-free run {TEP_RUN}")
        ax.plot(t1, p1, color=CMU_RED, lw=1.3,
               label=f"Fault {TEP_FAULT}, run {TEP_RUN} (A/C feed ratio step)")
        ax.axvline(onset, color=INK, ls="--", lw=1.1)
        ax.text(onset + 0.3, 2585, f"Fault {TEP_FAULT} starts at {onset:.0f} hour", color=INK, va="bottom")
        ax.set(xlabel="Time (hours)", ylabel="Reactor pressure,\nxmeas_7 (kPa)",
              xlim=(0, 25), ylim=(2580, 2850), yticks=[2600, 2700, 2800])
        ax.legend(loc="upper right", handlelength=1.5, borderaxespad=0.2)
        save(fig, "tep-data.png")


def tep_fault4_signal_figure(ff, fa):
    """Fault 4, drawn as a raw time trace, before any classifier touches it.

    Same fault, same channel (xmv_10, the reactor cooling water valve) as
    tep_logistic_figure, so a student sees the shift itself before a fitted probability
    curve stands in for it. The normal band (mean +/- 3 std) comes from the same 300
    fault-free training runs tep_logistic_figure fits its classifier on, so the two
    figures' numbers agree.
    """
    print("\n=== Fault 4, one channel over time (xmv_10, before any classifier) ===")
    fault, channel, run = 4, "xmv_10", TEP_RUN
    _, Xtr_full, ytr = tep_table(ff, fa, range(1, 301), [fault], range(1, 6))
    j = CH.index(channel)
    xtr = Xtr_full[:, j]
    mu, sd = float(xtr[ytr == 0].mean()), float(xtr[ytr == 0].std())
    print(f"  normal mean {mu:.2f}% open (std {sd:.2f});"
          f" fault {fault} mean {xtr[ytr == 1].mean():.2f}% open (std {xtr[ytr == 1].std():.2f})")
    firsts = tep_onset(ff, fa, fault, [run])
    onset = (firsts[0] - 1) * 3 / 60
    print(f"  fault {fault} starts at sample {firsts[0]}, {onset:.2f} hours")
    t0, v0 = tep_trace(ff[ff.simulationRun == run], channel)
    t1, v1 = tep_trace(fa[(fa.faultNumber == fault) & (fa.simulationRun == run)], channel)
    print(f"  run {run}: fault-free {channel} {v0.min():.2f} to {v0.max():.2f}% open;"
          f" fault {fault} {channel} {v1.min():.2f} to {v1.max():.2f}% open")
    lo = min(v0.min(), v1.min(), mu - 3 * sd) - 0.6
    hi = max(v0.max(), v1.max(), mu + 3 * sd) + 1.8
    with plt.rc_context(fonts(14)):             # shown at w:600 beside the flowsheet
        fig, ax = plt.subplots(figsize=(7.6, 4.4))
        ax.axhspan(mu - 3 * sd, mu + 3 * sd, color=BLUE, alpha=0.14, zorder=0,
                  label="Normal range")
        ax.plot(t0, v0, color="0.55", lw=1.2, label="Normal run", zorder=2)
        ax.plot(t1, v1, color=CMU_RED, lw=1.4, label=f"Fault {fault} run", zorder=2)
        ax.axvline(onset, color=INK, ls="--", lw=1.2, zorder=1)
        ax.text(onset + 0.4, hi - 0.3, f"Fault {fault} starts", color=INK, va="top", fontsize=13)
        k = int(np.argmin(np.abs(t1 - 15)))
        ax.annotate(f"The valve opens further:\nabout {mu:.0f}% to {xtr[ytr == 1].mean():.0f}% open",
                   xy=(t1[k], v1[k]), xytext=(6.5, hi - 1.4),
                   arrowprops=dict(arrowstyle="->", color=INK, lw=1.4),
                   color=INK, fontsize=13, va="top")
        ax.set(xlabel="Time (hours)", ylabel="Reactor cooling water valve,\nxmv_10 (% open)",
              xlim=(0, 25), ylim=(lo, hi))
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=3, handlelength=1.4)
        fig.tight_layout()
        save(fig, "tep-fault4-signal.png")


def tep_logistic_figure(ff, fa):
    """A gentle first classifier: logistic regression on one channel, one fault.

    Fault 4 and fault 14 share a channel (xmv_10, the reactor cooling water valve) but tell
    opposite stories: fault 4 moves its mean cleanly and leaves its spread alone, so a
    straight boundary separates the classes perfectly; fault 14 (tep_fault14_figure, drawn
    next) does the reverse. Neither fault is 3, 9 or 15.
    """
    print("\n=== Logistic regression on one channel: the gentle introduction ===")
    fault, channel = 4, "xmv_10"        # reactor cooling water inlet temperature step
    _, Xtr_full, ytr = tep_table(ff, fa, range(1, 301), [fault], range(1, 6))
    _, Xte_full, yte = tep_table(ff, fa, range(401, 501), [fault], range(11, 13))
    j = CH.index(channel)
    xtr, xte = Xtr_full[:, [j]], Xte_full[:, [j]]
    m = LogisticRegression(max_iter=2000).fit(xtr, ytr)
    w, b = float(m.coef_[0, 0]), float(m.intercept_[0])
    boundary = -b / w
    acc = accuracy_score(yte, m.predict(xte))
    print(f"  fault {fault}, channel {channel}: w {w:.4f}, b {b:.4f}, boundary at"
          f" {channel} = {boundary:.2f}% open, test accuracy {acc:.3f}")
    print(f"  normal mean {xtr[ytr == 0].mean():.2f}% (std {xtr[ytr == 0].std():.2f});"
          f" fault mean {xtr[ytr == 1].mean():.2f}% (std {xtr[ytr == 1].std():.2f})")

    with plt.rc_context(fonts(14)):             # shown at w:760
        fig, ax = plt.subplots(figsize=(7.6, 3.2))
        lo, hi = float(xtr.min()) - 0.5, float(xtr.max()) + 0.5
        zz = np.linspace(lo, hi, 300)
        pp = 1 / (1 + np.exp(-(w * zz + b)))
        ax.plot(zz, pp, color=BLUE, lw=2.4, zorder=3, label="Fitted probability")
        ax.axhline(0.5, color=MUTED, ls="--", lw=1)
        ax.axvline(boundary, color=INK, ls="--", lw=1)
        ax.plot(xtr[ytr == 0, 0], np.full(int((ytr == 0).sum()), -0.05), "|",
               color=MUTED, ms=9, mew=1.2, label="Normal (train)")
        ax.plot(xtr[ytr == 1, 0], np.full(int((ytr == 1).sum()), 1.05), "|",
               color=CMU_RED, ms=9, mew=1.2, label="Fault 4 (train)")
        # The label sits right of the boundary and below the 0.5 line, where the curve has
        # already risen past it, and the legend sits in the empty upper left.
        ax.text(boundary + 0.2, 0.28, f"Boundary\n{boundary:.1f}% open", color=INK, fontsize=12, va="center")
        ax.set(xlabel="Reactor cooling water valve, xmv_10 (% open)", ylabel="P(fault)",
              ylim=(-0.14, 1.14), xlim=(lo, hi))
        ax.legend(loc="upper left", fontsize=11, handlelength=1.3, borderaxespad=0.3)
        save(fig, "tep-logistic.png")


def tep_models():
    return {
        "Baseline: always normal": DummyClassifier(strategy="most_frequent"),
        "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
        "Decision tree": DecisionTreeClassifier(max_depth=8, random_state=0),
        "Neural network": make_pipeline(
            StandardScaler(),
            MLPClassifier(hidden_layer_sizes=(32,), max_iter=300, early_stopping=True, random_state=0),
        ),
    }


def fit_tep_classifier(ff, fa):
    """The 52-channel classifier (the neural network of tep_models()), fit fresh."""
    _, Xtr, ytr = tep_table(ff, fa, range(1, 301), SEEN, range(1, 6))
    _, Xte, yte = tep_table(ff, fa, range(401, 501), SEEN, range(11, 13))
    model = tep_models()["Neural network"].fit(Xtr, ytr)
    return model, Xte, yte


def confusion_explained_figure(cm):
    """The 52-channel classifier's test confusion matrix, every cell named and counted.

    `cm` is `confusion_matrix(y_true, y_pred, labels=[1, 0]).ravel()`-shaped: TP, FN, FP,
    TN in that order. Green for the two correct cells, red for the two errors, and every
    cell carries its full name, its acronym and a plain description, not just a number.
    """
    print("\n=== Confusion matrix, explained (52-channel classifier, test set) ===")
    tp, fn, fp, tn = (int(v) for v in cm.ravel())
    print(f"  TP {tp}  FN {fn}  FP {fp}  TN {tn}")
    # rows: 0 = actually faulty (drawn on top), 1 = actually normal (drawn on bottom)
    grid = [
        [("True positive (TP)", "fault caught", tp, GREEN), ("False negative (FN)", "fault missed", fn, CMU_RED)],
        [("False positive (FP)", "false alarm", fp, CMU_RED), ("True negative (TN)", "normal, left alone", tn, GREEN)],
    ]
    with plt.rc_context(fonts(15)):             # shown at w:640
        fig, ax = plt.subplots(figsize=(7.4, 4.6))
        for r in range(2):
            y0 = 1 - r    # row 0 (faulty) occupies [1, 2], row 1 (normal) occupies [0, 1]
            for c in range(2):
                name, meaning, count, color = grid[r][c]
                ax.add_patch(plt.Rectangle((c, y0), 1, 1, facecolor=color, alpha=0.16,
                                           edgecolor=color, linewidth=1.8))
                ax.text(c + 0.5, y0 + 0.66, name, ha="center", va="center",
                       fontsize=14.5, fontweight="bold", color=INK)
                ax.text(c + 0.5, y0 + 0.44, meaning, ha="center", va="center",
                       fontsize=12.5, color=INK)
                ax.text(c + 0.5, y0 + 0.20, f"{count:,}", ha="center", va="center",
                       fontsize=18, fontweight="bold", color=INK)
        ax.set_xlim(0, 2)
        ax.set_ylim(0, 2)
        ax.set_xticks([0.5, 1.5], ["Predicted fault", "Predicted normal"])
        ax.set_yticks([0.5, 1.5], ["Actually normal", "Actually faulty"])
        ax.tick_params(length=0, labelsize=13)
        for spine in ax.spines.values():
            spine.set_visible(False)
        save(fig, "confusion-explained.png")


def tep_figures(ff, fa):
    print("\n=== Tennessee Eastman, normal against faulty (the 52-channel classifier) ===")
    _, Xtr, ytr = tep_table(ff, fa, range(1, 301), SEEN, range(1, 6))
    _, Xte, yte = tep_table(ff, fa, range(401, 501), SEEN, range(11, 13))
    print(f"  training rows {len(ytr)} ({ytr.mean():.1%} faulty); test rows {len(yte)} ({yte.mean():.1%} faulty)")
    print(f"  a GP classifier on all {len(ytr)} training rows would need a {len(ytr)} x {len(ytr)}"
          f" kernel matrix, {len(ytr) ** 2 * 8 / 1e9:.0f} GB in double precision")
    models = tep_models()
    cms = {}
    for name, m in models.items():
        p = m.fit(Xtr, ytr).predict(Xte)
        cms[name] = confusion_matrix(yte, p, labels=[1, 0])      # faulty first, as the deck draws it
        tp, fn, fp, tn = cms[name].ravel()
        print(f"  {name:23s} accuracy {accuracy_score(yte, p):.3f}  precision {precision_score(yte, p, zero_division=0):.3f}"
              f"  recall {recall_score(yte, p):.3f}  F1 {f1_score(yte, p):.3f}   TN {tn} FP {fp} FN {fn} TP {tp}")
    tp, fn, fp, tn = cms["Neural network"].ravel()
    days = (tn + fp) / 480                          # 480 samples a day, one every 3 minutes
    print(f"  neural network: {fp} false alarms on {tn + fp} normal test samples, {days:.1f} days of normal"
          f" operation at 480 samples a day, so one false alarm every {days / fp:.1f} days")

    confusion_explained_figure(cms["Neural network"])

    rec = {"Faults it learned\n(test runs 11-12)": models["Neural network"].predict(Xte[yte == 1]).mean()}
    print("  recall of the same neural network on faults it never saw (runs 11-12, after the fault starts):")
    for f in UNSEEN:
        a = fa[(fa.faultNumber == f) & fa.simulationRun.isin(range(11, 13)) & (fa["sample"] > 20)]
        rec[f"Fault {f}"] = models["Neural network"].predict(a[CH].to_numpy()).mean()
        print(f"    fault {f:2d}: {rec[f'Fault {f}']:.3f}")
    with plt.rc_context(fonts(16)):             # shown at w:720 on the slide
        fig, ax = plt.subplots(figsize=(9.6, 4.4))
        keys = list(rec)
        xs = np.r_[0, np.arange(1, len(keys)) + 0.6]
        ax.bar(xs, [rec[k] for k in keys], color=[BLUE] + ["0.6"] * len(UNSEEN))
        for x, k in zip(xs, keys):
            ax.text(x, rec[k] + 0.03, f"{rec[k]:.3f}", ha="center", fontsize=14)
        labels = ["Faults it\nlearned"] + [k.replace("Fault ", "Fault\n") for k in keys[1:]]
        ax.set_xticks(xs, labels)
        ax.tick_params(axis="x", length=0)
        ax.set(ylabel="Recall", ylim=(0, 1.12), yticks=[0, 0.5, 1])
        ax.text((xs[1] + xs[-1]) / 2, 1.08, "Eight faults it never saw", ha="center", color=MUTED)
        fig.tight_layout()
        save(fig, "tep-unseen.png")


def tep_fault14_figure(ff, fa):
    """Fault 14: same mean, bigger spread. A straight boundary cannot see it; a tree can.

    Left panel: xmv_10 over time for one normal run and one fault 14 run, so a student sees
    the wider swings directly. Right panel: the two populations' histograms, with the depth-
    2 tree's two cuts drawn on top and a note on why one straight cut (logistic regression)
    cannot separate a band that has fault on both sides of it.
    """
    print("\n=== Fault 14: a straight boundary cannot see a change in spread ===")
    trn = ff[ff.simulationRun <= 300]
    a = fa[fa.faultNumber == 14]
    A_tr, A_te = a[a.simulationRun <= 10], a[(a.simulationRun > 10) & (a["sample"] > 20)]
    X14 = np.vstack([trn[CH].to_numpy(), A_tr[CH].to_numpy()])
    y14 = np.r_[np.zeros(len(trn)), (A_tr["sample"] > 20).to_numpy()]
    nrm = ff[ff.simulationRun > 400]
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X14, y14)
    lr_recall = float(lr.predict(A_te[CH].to_numpy()).mean())
    print(f"    logistic regression recall {lr_recall:.3f}")
    cuts = None
    tree_recall = {}
    for d in [1, 2, 8]:
        t = DecisionTreeClassifier(max_depth=d, random_state=0).fit(X14, y14)
        rec = float(t.predict(A_te[CH].to_numpy()).mean())
        tree_recall[d] = rec
        print(f"    tree depth {d}: recall {rec:.3f},"
              f" false alarms on normal runs {t.predict(nrm[CH].to_numpy()).mean():.4f}")
        if d == 2:
            tr_ = t.tree_
            cuts = sorted({tr_.threshold[i] for i in range(tr_.node_count)
                          if tr_.feature[i] == CH.index("xmv_10")})
            print(f"    depth-2 tree splits xmv_10 at {[round(c, 2) for c in cuts]}")
    v_n, v_f = nrm["xmv_10"], A_te["xmv_10"]
    lo_band, hi_band = v_n.mean() - 3 * v_n.std(), v_n.mean() + 3 * v_n.std()
    print(f"    xmv_10 normal mean {v_n.mean():.2f} std {v_n.std():.2f}; fault 14 mean {v_f.mean():.2f} std {v_f.std():.2f};"
          f" {np.mean(v_f < lo_band):.1%} below and {np.mean(v_f > hi_band):.1%} above the normal +/- 3 std band")

    lo_cut, hi_cut = cuts
    rule = lambda v: (v < lo_cut) | (v > hi_cut)
    print(f"    the two cuts alone (flag xmv_10 below {lo_cut:.2f} or above {hi_cut:.2f}):"
          f" recall {rule(v_f).mean():.3f}, false alarms on normal runs {rule(v_n).mean():.4f}")

    onset14 = tep_onset(ff, fa, 14, [1])[0]
    onset_hr = (onset14 - 1) * 3 / 60
    t0, v0t = tep_trace(ff[ff.simulationRun == 1], "xmv_10")
    t1, v1t = tep_trace(fa[(fa.faultNumber == 14) & (fa.simulationRun == 1)], "xmv_10")
    print(f"    run 1 (drawn in the left panel): fault-free xmv_10 {v0t.min():.2f} to {v0t.max():.2f}%;"
          f" fault 14 {v1t.min():.2f} to {v1t.max():.2f}%")

    # Right half: the normal samples and the fault 14 samples on two rows with a shared
    # x axis and a linear scale each, so the narrow normal band and the wide fault spread
    # are both visible without a log axis. The band between the tree's two cuts is shaded.
    def draw_trace(ax, legend_below=False):
        ax.plot(t1, v1t, color=CMU_RED, lw=1.0, label="Fault 14 run", zorder=2)
        ax.plot(t0, v0t, color="0.35", lw=1.7, label="Normal run", zorder=3)
        ax.axvline(onset_hr, color=INK, ls="--", lw=1.1)
        top = max(v0t.max(), v1t.max())
        bot = min(v0t.min(), v1t.min())
        ax.text(onset_hr + 0.4, top + 0.6, "Fault 14 starts", color=INK, va="bottom", fontsize=14)
        k = int(np.argmin(np.abs(t1 - 20)))
        ax.annotate("Same average,\nmuch bigger swings", xy=(t1[k], v1t[k]),
                    xytext=(onset_hr + 6.5, top + 2.6),
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.3), fontsize=14, color=INK)
        ax.set(xlabel="Time (hours)", ylabel="Reactor cooling water valve,\nxmv_10 (% open)",
               xlim=(0, 25), ylim=(bot - 1, top + 6.5))
        if legend_below:
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, handlelength=1.3)
        else:
            ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, handlelength=1.3)

    def draw_cuts(top_r, bot_r):
        bins = np.linspace(26, 57, 94)
        rows = [(top_r, v_n, "0.5", "Normal runs: a narrow band"),
                (bot_r, v_f, CMU_RED, "Fault 14 runs: spread out on both sides")]
        for ax, v, color, label in rows:
            ax.axvspan(lo_cut, hi_cut, color=BLUE, alpha=0.13, zorder=0)
            counts, _, _ = ax.hist(v, bins=bins, color=color, alpha=0.85, zorder=2)
            for c in cuts:
                ax.axvline(c, color=INK, ls="--", lw=1.3, zorder=3)
            ax.set_ylim(0, counts.max() * 1.55)
            ax.set_yticks([])
            ax.spines["left"].set_visible(False)
            ax.set_title(label, loc="left", fontsize=15, pad=4)
        top_r.tick_params(labelbottom=False)
        top_r.annotate(f"A tree's two cuts:\n{lo_cut:.1f}% and {hi_cut:.1f}%",
                       xy=(hi_cut, top_r.get_ylim()[1] * 0.62), xytext=(hi_cut + 3.2, top_r.get_ylim()[1] * 0.5),
                       arrowprops=dict(arrowstyle="->", color=INK, lw=1.3), fontsize=14, color=INK, va="center")
        y_arrow = bot_r.get_ylim()[1] * 0.72
        bot_r.annotate("", xy=(29.5, y_arrow), xytext=(lo_cut - 0.4, y_arrow),
                       arrowprops=dict(arrowstyle="->", color=INK, lw=1.6))
        bot_r.annotate("", xy=(53.5, y_arrow), xytext=(hi_cut + 0.4, y_arrow),
                       arrowprops=dict(arrowstyle="->", color=INK, lw=1.6))
        bot_r.text(48.4, y_arrow * 1.05, "Flagged as fault", ha="center", va="bottom", fontsize=14, color=INK)
        bot_r.text(34.0, y_arrow * 1.05, "Flagged as fault", ha="center", va="bottom", fontsize=14, color=INK)
        bot_r.set(xlabel="Reactor cooling water valve, xmv_10 (% open)", xlim=(26, 57))

    # The notes: both halves side by side.
    with plt.rc_context(fonts(15)):
        fig = plt.figure(figsize=(13.2, 4.8))
        gs = fig.add_gridspec(2, 2, width_ratios=[1.1, 1], hspace=0.28, wspace=0.16)
        draw_trace(fig.add_subplot(gs[:, 0]))
        top_r = fig.add_subplot(gs[0, 1])
        draw_cuts(top_r, fig.add_subplot(gs[1, 1], sharex=top_r))
        fig.subplots_adjust(left=0.08, right=0.99, bottom=0.14, top=0.88)
        save(fig, "tep-fault14.png")

    # The deck: fault 14 takes two slides, the trace beside the flowsheet, then the two cuts.
    with plt.rc_context(fonts(14)):             # shown at w:600 beside the flowsheet
        fig, ax = plt.subplots(figsize=(7.6, 4.4))
        draw_trace(ax, legend_below=True)
        fig.tight_layout()
        save(fig, "tep-fault14-trace.png")
    with plt.rc_context(fonts(15)):             # shown at w:900
        fig = plt.figure(figsize=(9.0, 4.6))
        gs = fig.add_gridspec(2, 1, hspace=0.32)
        top_r = fig.add_subplot(gs[0])
        draw_cuts(top_r, fig.add_subplot(gs[1], sharex=top_r))
        fig.subplots_adjust(left=0.03, right=0.98, bottom=0.14, top=0.93)
        save(fig, "tep-fault14-cuts.png")


def tep_flowsheet_figures():
    """Where faults 4 and 14 act on the plant: the course's own P&ID, marked up.

    The base drawing is Lecture 5's tep-screenshot.png, read in place as Lecture 7 does
    (P&ID from Lyu, Botcha, Kulkarni, Pagaria, Alves, Sunshine and Kitchin 2026). It is
    cropped to the process units, with the analysers left out, and the labels sit in a
    white margin on the right so they cover none of the drawing. Both faults act on the
    reactor's cooling water loop:
      fault 4   a step in the temperature of the cooling water entering the reactor; the
                reactor temperature controller (TC 10) answers by opening the reactor
                cooling water valve, xmv_10
      fault 14  that same valve sticks
    Coordinates are pixels of tep-screenshot.png (1908 x 1160), read off the drawing by
    hand, so they move if that PNG is ever regenerated.
    """
    print("\n=== TEP flowsheet: where faults 4 and 14 act ===")
    raw = HERE.parent.parent / "l05" / "figures" / "tep-screenshot.png"
    if not raw.exists():
        print("skipped the flowsheet figures (L5's tep-screenshot.png not found)")
        return
    img = plt.imread(raw)
    x0, x1, y0, y1 = 290, 1395, 105, 945           # the process units, analysers left out
    crop = img[y0:y1, x0:x1]
    margin = 470                                    # white space on the right for the labels
    h, w = crop.shape[0], crop.shape[1] + margin
    valve, cw_in = (879 - x0, 641 - y0), (812 - x0, 834 - y0)

    def figure(labels, name):
        fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.imshow(crop, extent=(0, crop.shape[1], crop.shape[0], 0))
        ax.set(xlim=(0, w), ylim=(h, 0))
        ax.set_axis_off()
        for xy, text_xy, text, color in labels:
            ax.add_patch(plt.Circle(xy, 38, fill=False, ec=color, lw=5, zorder=4))
            ax.annotate(text, xy=xy, xytext=text_xy, fontsize=30, color="white", weight="bold",
                        ha="left", va="center", zorder=5,
                        bbox=dict(boxstyle="round,pad=0.4", fc=color, ec="none"),
                        arrowprops=dict(arrowstyle="-|>", color=color, lw=4, shrinkA=4, shrinkB=40,
                                        mutation_scale=30, connectionstyle="arc3,rad=-0.1"))
        fig.savefig(HERE / name, dpi=100)
        plt.close(fig)
        print(f"  wrote {name}")

    figure([(valve, (crop.shape[1] + 30, 360), "xmv_10:\nthe valve\nopens further", BLUE),
            (cw_in, (crop.shape[1] + 30, 680), "Fault 4:\nthe cooling\nwater gets\nwarmer", CMU_RED)],
           "tep-flowsheet-fault4.png")
    figure([(valve, (crop.shape[1] + 30, 470), "Fault 14:\nthis valve,\nxmv_10,\nsticks", CMU_RED)],
           "tep-flowsheet-fault14.png")


def _classifier_shape_dataset(seed=SEED, n=150):
    """One small synthetic 2D two-class set with a curved true boundary, seeded."""
    X, y = make_moons(n_samples=n, noise=0.25, random_state=seed)
    return X, y


def _decision_region(ax, model, X, y, title):
    """Shade a model's predicted P(class 1) over the plane and scatter the training points."""
    lo0, hi0 = X[:, 0].min() - 0.6, X[:, 0].max() + 0.6
    lo1, hi1 = X[:, 1].min() - 0.6, X[:, 1].max() + 0.6
    xx, yy = np.meshgrid(np.linspace(lo0, hi0, 250), np.linspace(lo1, hi1, 250))
    zz = model.predict_proba(np.c_[xx.ravel(), yy.ravel()])[:, 1].reshape(xx.shape)
    ax.contourf(xx, yy, zz, levels=np.linspace(0, 1, 21), cmap="RdBu_r", vmin=0, vmax=1)
    ax.scatter(X[y == 0, 0], X[y == 0, 1], s=20, color=BLUE, edgecolor="white", linewidth=0.5, zorder=3)
    ax.scatter(X[y == 1, 0], X[y == 1, 1], s=20, color=CMU_RED, edgecolor="white", linewidth=0.5, zorder=3)
    ax.set(title=title, xticks=[], yticks=[], xlim=(lo0, hi0), ylim=(lo1, hi1))


def classifier_shapes_figure():
    """Four model families, one dataset: what a decision boundary can look like.

    No accuracy numbers are drawn on the panels; the point is the shape of the boundary,
    not which family scores highest on 150 synthetic points.
    """
    print("\n=== Classifier shapes: one dataset, four model families ===")
    X, y = _classifier_shape_dataset()
    print(f"  {len(y)} points, {y.mean():.1%} class 1")
    models = {
        "Logistic regression: a straight line":
            make_pipeline(StandardScaler(), LogisticRegression()),
        "Decision tree: boxes":
            DecisionTreeClassifier(max_depth=3, random_state=0),
        # tanh units, not ReLU: a ReLU network's boundary is made of straight pieces, which
        # on 150 points looks jagged; tanh units bend it smoothly
        "Neural network: a smooth curve":
            make_pipeline(StandardScaler(),
                         MLPClassifier(hidden_layer_sizes=(8,), activation="tanh", alpha=0.3,
                                      solver="lbfgs", max_iter=5000, random_state=0)),
        "Gaussian process: smooth probabilities":
            make_pipeline(StandardScaler(),
                         GaussianProcessClassifier(1.0 * RBF(1.0), random_state=0)),
    }
    fitted = {name: m.fit(X, y) for name, m in models.items()}
    for name, m in fitted.items():
        print(f"  {name}: training accuracy {m.score(X, y):.3f} (not drawn on the panel)")

    with plt.rc_context(fonts(14)):             # shown at w:1180
        fig, axes = plt.subplots(1, 4, figsize=(15.6, 4.0))
        for ax, (name, m) in zip(axes, fitted.items()):
            _decision_region(ax, m, X, y, name)
        fig.tight_layout()
        save(fig, "classifier-shapes.png")

    classifier_training_frames(X, y)


def _region_frame(proba, X, y, shown, fname):
    """One animation frame: P(class 1) over the plane and the points in `shown`, no title.

    Every frame shares the axis limits of the whole dataset, so the frames line up when the
    deck swaps one for the next.
    """
    lo0, hi0 = X[:, 0].min() - 0.6, X[:, 0].max() + 0.6
    lo1, hi1 = X[:, 1].min() - 0.6, X[:, 1].max() + 0.6
    xx, yy = np.meshgrid(np.linspace(lo0, hi0, 200), np.linspace(lo1, hi1, 200))
    zz = proba(np.c_[xx.ravel(), yy.ravel()]).reshape(xx.shape)
    fig, ax = plt.subplots(figsize=(4.0, 3.4))
    ax.imshow(zz, extent=(lo0, hi0, lo1, hi1), origin="lower", cmap="RdBu_r", vmin=0, vmax=1,
              aspect="auto", interpolation="bilinear")
    Xs, ys = X[shown], y[shown]
    ax.scatter(Xs[ys == 0, 0], Xs[ys == 0, 1], s=18, color=BLUE, edgecolor="white", linewidth=0.5, zorder=3)
    ax.scatter(Xs[ys == 1, 0], Xs[ys == 1, 1], s=18, color=CMU_RED, edgecolor="white", linewidth=0.5, zorder=3)
    ax.set(xticks=[], yticks=[], xlim=(lo0, hi0), ylim=(lo1, hi1))
    fig.tight_layout(pad=0.2)
    save(fig, fname)


def classifier_training_frames(X, y):
    """Frames for the deck's four model-family cards: each model learning its boundary.

    Every frame is a real fit at a real stage of training, on the same seeded data as
    classifier-shapes.png, and the last frame of each is the fully trained model:
      logistic regression  gradient descent on scikit-learn's own objective
                           (0.5 |w|^2 + C * sum of log losses, C = 1), from w = 0
      decision tree        depth 0 (no split, the class shares) to depth 3
      neural network       the same lbfgs network stopped after 1, 3, 10, 30, 100
                           iterations, then trained to convergence
      Gaussian process     fit on the first 4, 8, 16, 32, 75 and 150 points of a
                           class-balanced shuffle, with only those points drawn
    The labels printed here are the ones the deck shows under each frame.
    """
    print("\n=== Classifier training frames: four model families learning, for the deck ===")
    everyone = np.arange(len(y))

    # logistic regression: plain gradient descent on the objective LogisticRegression minimizes
    scaler = StandardScaler().fit(X)
    Z, t, C, lr = scaler.transform(X), 2 * y - 1, 1.0, 0.004
    w, b, step = np.zeros(2), 0.0, 0
    stages = [0, 1, 3, 10, 40, 3000]
    for k, target in enumerate(stages):
        while step < target:
            s_ = 1 / (1 + np.exp(t * (Z @ w + b)))          # sigma(-margin)
            w, b = w - lr * (w - C * (Z * (t * s_)[:, None]).sum(0)), b - lr * (-C * (t * s_).sum())
            step += 1
        ww, bb = w.copy(), b
        _region_frame(lambda P, ww=ww, bb=bb: 1 / (1 + np.exp(-(scaler.transform(P) @ ww + bb))),
                      X, y, everyone, f"anim-logistic-{k}.png")
    ref = LogisticRegression().fit(Z, y)
    print(f"  logistic regression: after {stages[-1]} steps w = {np.round(w, 3)}, b = {b:.3f};"
          f" scikit-learn's fit w = {np.round(ref.coef_[0], 3)}, b = {ref.intercept_[0]:.3f}")
    print("  logistic labels: " + " | ".join(["Before training"] + [f"Step {n}" for n in stages[1:]]))

    # decision tree: one depth at a time
    tree_models = [DummyClassifier(strategy="prior")] + [
        DecisionTreeClassifier(max_depth=d, random_state=0) for d in (1, 2, 3)]
    for k, m in enumerate(tree_models):
        m.fit(X, y)
        _region_frame(lambda P, m=m: m.predict_proba(P)[:, 1], X, y, everyone, f"anim-tree-{k}.png")
    print("  tree labels: No split yet | Depth 1 | Depth 2 | Depth 3")

    # neural network: the same network stopped early, then trained to convergence
    iters, done = [1, 3, 10, 30, 100, 5000], None
    for k, n_it in enumerate(iters):
        m = make_pipeline(StandardScaler(),
                          MLPClassifier(hidden_layer_sizes=(8,), activation="tanh", alpha=0.3,
                                        solver="lbfgs", max_iter=n_it, random_state=0)).fit(X, y)
        done = m[-1].n_iter_
        _region_frame(lambda P, m=m: m.predict_proba(P)[:, 1], X, y, everyone, f"anim-network-{k}.png")
    print(f"  network: converged after {done} lbfgs iterations")
    print("  network labels: " + " | ".join([f"{n} iteration" + ("s" if n > 1 else "") for n in iters[:-1]]
                                            + [f"Trained ({done} iterations)"]))

    # Gaussian process: the data arrive a few points at a time
    rng = np.random.default_rng(SEED)
    i0, i1 = rng.permutation(np.flatnonzero(y == 0)), rng.permutation(np.flatnonzero(y == 1))
    order = np.ravel(np.column_stack([i0, i1]))
    sizes = [4, 8, 16, 32, 75, 150]
    for k, n in enumerate(sizes):
        idx = order[:n]
        m = make_pipeline(StandardScaler(),
                          GaussianProcessClassifier(1.0 * RBF(1.0), random_state=0)).fit(X[idx], y[idx])
        _region_frame(lambda P, m=m: m.predict_proba(P)[:, 1], X, y, idx, f"anim-gp-{k}.png")
    print("  gp labels: " + " | ".join(f"{n} points" for n in sizes))


def classification_figures():
    """The classification group: TEP throughout, plus the model-shapes comparison."""
    with warnings.catch_warnings(), plt.rc_context(CLASSIFICATION_STYLE):
        warnings.simplefilter("ignore")
        ff, fa = load_tep()
        tep_data_figure(ff, fa)
        tep_fault4_signal_figure(ff, fa)
        tep_logistic_figure(ff, fa)
        tep_fault14_figure(ff, fa)
        tep_flowsheet_figures()
        tep_figures(ff, fa)
        classifier_shapes_figure()


# --------------------------------------------------------------------------------------
# Concrete: the shared split for the search group (L9's grouped data, unchanged recipe)
# --------------------------------------------------------------------------------------
COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
          "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]
UCI_CONCRETE = ("https://archive.ics.uci.edu/static/public/165/"
               "concrete+compressive+strength.zip")


def load_concrete():
    path = cached("Concrete_Data.xls")
    if path is None:
        CACHE.mkdir(exist_ok=True)
        print(f"  downloading {UCI_CONCRETE}")
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI_CONCRETE).read()))
        path = CACHE / "Concrete_Data.xls"
        path.write_bytes(z.read("Concrete_Data.xls"))
    df = pd.read_excel(path)
    df.columns = COLUMNS
    return df


def concrete_split():
    """L9's grouped test split, unchanged: 835 training rows (342 mixes), 195 test (86 mixes)."""
    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df.strength_mpa.to_numpy()
    groups = df.groupby(MIX).ngroup().to_numpy()
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
    return X, y, groups, X[tr], y[tr], groups[tr], X[te], y[te]


# --------------------------------------------------------------------------------------
# Search: grid versus random (synthetic, with the score curve drawn in), then a real
# Optuna study on concrete's decision tree, and how TPE picks its next trial
# --------------------------------------------------------------------------------------
def grid_random_points(seed=SEED):
    """The nine grid points and nine random points fig_grid_vs_random() draws."""
    rng = np.random.default_rng(seed)
    g = np.linspace(0.1, 0.9, 3)
    gx, gy = np.meshgrid(g, g)
    gx, gy = gx.ravel(), gy.ravel()
    rx, ry = rng.uniform(0.05, 0.95, 9), rng.uniform(0.05, 0.95, 9)
    return (gx, gy), (rx, ry)


def hp_score(x, peak=0.7, width=0.12, amp=0.35, base=0.55):
    """The fabricated 'validation score' curve grid_vs_random.png draws underneath its
    points: higher is better, one bump, peak at `peak`. Made up for the picture; the shape
    (not the exact values) is what a real hyperparameter response often looks like.
    """
    x = np.asarray(x, dtype=float)
    return base + amp * np.exp(-((x - peak) ** 2) / (2 * width ** 2))


def fig_grid_vs_random():
    """Grid versus random over two hyperparameters, one of which matters.

    Top row: the nine points each strategy tried, in the plane of both hyperparameters.
    Bottom row: the fabricated validation-score curve over the important one alone, with
    every tried value marked and the best tried value highlighted, so a student can read
    off why random search finds a better setting from the same nine trials.
    """
    print("\n=== Grid versus random search, with the score curve underneath the points ===")
    (gx, gy), (rx, ry) = grid_random_points()
    print(f"  grid: distinct x-values {sorted(set(np.round(gx, 3).tolist()))}")
    print(f"  random: x-values {np.round(np.sort(rx), 3).tolist()}")
    print(f"  score curve: hp_score(x) = {0.55} + {0.35} * exp(-((x - {0.7})^2) / (2 * {0.12}^2)),"
          f" peak at x = 0.70, score {hp_score(0.7):.3f}")

    xs_curve = np.linspace(0, 1, 300)
    cols = [("grid", gx, gy, "Grid: 3 different values of the important one"),
           ("random", rx, ry, "Random: 9 different values")]
    with plt.rc_context(fonts(14)):             # shown at w:900
        fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.6),
                                 gridspec_kw={"height_ratios": [1, 1.1], "hspace": 0.5, "wspace": 0.3})
        for col, (mode, xs, ys, title) in enumerate(cols):
            top, bot = axes[0, col], axes[1, col]
            top.scatter(xs, ys, s=85, color=CMU_RED, zorder=3, edgecolor="white")
            top.set(xlim=(0, 1), ylim=(0, 1), xticks=[], yticks=[])
            top.set_xlabel("Important hyperparameter", fontsize=11.5)
            if col == 0:
                top.set_ylabel("Unimportant\nhyperparameter", fontsize=11.5)
            top.set_title(title, fontsize=13)

            bot.plot(xs_curve, hp_score(xs_curve), color=MUTED, lw=2.2, label="Validation score")
            tried = hp_score(xs)
            bot.scatter(xs, tried, s=60, color=BLUE, zorder=3, label="Tried")
            best_i = int(np.argmax(tried))
            bot.scatter([xs[best_i]], [tried[best_i]], s=170, facecolor="none",
                       edgecolor=GOLD, linewidth=2.6, zorder=4, label="Best tried")
            bot.set(xlim=(0, 1), ylim=(0.5, 0.95))
            bot.set_xlabel("Important hyperparameter", fontsize=11.5)
            if col == 0:
                bot.set_ylabel("Validation score\n(higher is better)", fontsize=11.5)
            bot.legend(loc="upper left", fontsize=9.5, frameon=False, handlelength=1.2)
            print(f"  {mode}: best tried x={xs[best_i]:.2f}, score {tried[best_i]:.3f}")
        save(fig, "grid_vs_random.png")


SEARCH_SPACE = dict(max_depth=(2, 20), min_samples_leaf=(1, 50))


def _tree_objective(trial, X, y, groups):
    """GroupKFold(5) CV RMSE of a DecisionTreeRegressor, Lecture 9's own model family."""
    params = dict(
        max_depth=trial.suggest_int("max_depth", *SEARCH_SPACE["max_depth"]),
        min_samples_leaf=trial.suggest_int("min_samples_leaf", *SEARCH_SPACE["min_samples_leaf"]),
    )
    model = DecisionTreeRegressor(random_state=0, **params)
    rmse = -cross_val_score(model, X, y, groups=groups, cv=GroupKFold(5),
                            scoring="neg_root_mean_squared_error").mean()
    return rmse


_OPTUNA_CACHE = {}     # in-process only: both samplers are seeded, so a second call in the
                       # same run (e.g. search then widgets) would just repeat the same
                       # work. A fresh process (running "widgets" alone) still recomputes
                       # from scratch, which is the point: nothing here is cached to disk,
                       # so nothing can go stale.


def optuna_study(Xtr, ytr, gtr, n_trials=40):
    """TPE against random search, both seeded, tuning a DecisionTreeRegressor on concrete."""
    if n_trials in _OPTUNA_CACHE:
        return _OPTUNA_CACHE[n_trials]
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    curves, tables = {}, {}
    for name, sampler in [("random", optuna.samplers.RandomSampler(seed=SEED)),
                         ("TPE", optuna.samplers.TPESampler(seed=SEED))]:
        study = optuna.create_study(direction="minimize", sampler=sampler)
        study.optimize(lambda t: _tree_objective(t, Xtr, ytr, gtr), n_trials=n_trials)
        vals = [t.value for t in study.trials]
        curves[name] = np.minimum.accumulate(vals)
        tables[name] = [(t.number, dict(t.params), float(t.value)) for t in study.trials]
    _OPTUNA_CACHE[n_trials] = (curves, tables)
    return curves, tables


def fig_optuna_search(Xtr, ytr, gtr):
    print("\n=== Hyperparameter search on concrete: Lecture 9's decision tree, tuned ===")
    curves, tables = optuna_study(Xtr, ytr, gtr, n_trials=40)
    n_trials = len(curves["random"])
    fig, ax = plt.subplots(figsize=(7.8, 4.9))
    # both samplers draw their first 10 trials at random with the same seed, so those 10 are
    # the same trials; TPE only starts using the past at trial 11
    ax.axvspan(0.5, 10.5, color=MUTED, alpha=0.10, zorder=0)
    ax.text(5.5, 8.68, "Trials 1 to 10:\nthe same random start", ha="center", va="bottom",
            fontsize=11, color=MUTED)
    for name, color in [("random", GOLD), ("TPE", CMU_RED)]:
        vals = [v for _, _, v in tables[name]]
        ax.scatter(range(1, n_trials + 1), vals, color=color, s=20, alpha=0.55, zorder=2)
        ax.step(range(1, n_trials + 1), curves[name], where="post", color=color, lw=2.4, zorder=3)
    handles = [
        Line2D([0], [0], color=GOLD, lw=2.4, label="Random search"),
        Line2D([0], [0], color=CMU_RED, lw=2.4, label="TPE"),
        Line2D([0], [0], marker="o", color=MUTED, lw=0, label="Dot: one trial"),
        Line2D([0], [0], color=MUTED, lw=2.4, label="Line: best so far"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper right", fontsize=11)
    ax.set(xlabel="Trial", ylabel="Validation RMSE (MPa)", ylim=(8.6, 13.5),
          title="Tuning Lecture 9's decision tree on the concrete strength dataset")
    save(fig, "optuna_search.png")

    for name in ["random", "TPE"]:
        vals = [v for _, _, v in tables[name]]
        best_i = int(np.argmin(vals))
        best_num, best_params, best_val = tables[name][best_i]
        print(f"  {name} trials (number, params, RMSE):")
        for number, params, value in tables[name]:
            print(f"    {number:2d}  {params}  {value:.4f}")
        print(f"  {name} best: trial {best_num}, {best_params}, RMSE {best_val:.4f} MPa")
    print("  compare with Lecture 9 on the same data: a tree with no depth limit scored"
          " 9.42 MPa GroupKFold RMSE; the best depth chosen by eye (9) scored 9.10 MPa")
    return curves, tables


def tpe_explained_figure(tables):
    """How TPE picks its next trial, from the TPE study's first 20 trials.

    Optuna's TPESampler calls the best 10% of the trials so far "good" (its default_gamma,
    ceil(0.1 n) trials, at most 25) and the rest "bad", smooths where each group's values
    fall (a Parzen estimator is a smoothed histogram), and tries next where the good curve
    is high and the bad one low. The figure draws that over min_samples_leaf, the
    hyperparameter that separates the two groups most clearly in this study. The smoothing
    is a plain Gaussian kernel of fixed width, simpler than Optuna's own, so the figure
    shows the idea and not Optuna's exact internal numbers.
    """
    print("\n=== TPE explained: good trials against bad trials, over min_samples_leaf ===")
    trials = tables["TPE"][:20]
    leaves = np.array([p["min_samples_leaf"] for _, p, _ in trials], dtype=float)
    vals = np.array([v for _, _, v in trials])
    order = np.argsort(vals)
    n_good = min(int(np.ceil(0.1 * len(vals))), 25)          # Optuna's default_gamma
    good, bad = leaves[order[:n_good]], leaves[order[n_good:]]
    print(f"  first {len(vals)} TPE trials: {n_good} good (the best 10%), {len(bad)} bad")
    print(f"  good min_samples_leaf values: {sorted(good.astype(int).tolist())}"
          f" (RMSE {', '.join(f'{v:.4f}' for v in np.sort(vals)[:n_good])} MPa)")
    print(f"  bad min_samples_leaf values: {sorted(bad.astype(int).tolist())}")

    xs = np.linspace(1, 50, 491)
    width = 3.0                                    # leaves; the kernel's standard deviation

    def parzen(points):
        z = (xs[:, None] - points[None, :]) / width
        return np.exp(-0.5 * z ** 2).sum(axis=1) / (len(points) * width * np.sqrt(2 * np.pi))

    g, b = parzen(good), parzen(bad)
    ratio = g / b
    peak = float(xs[np.argmax(ratio)])
    window = xs[ratio >= 0.5 * ratio.max()]
    print(f"  good/bad ratio peaks at min_samples_leaf = {peak:.1f};"
          f" at least half its peak from {window.min():.1f} to {window.max():.1f}")
    nxt = tables["TPE"][20]
    print(f"  the study's next trial, number {nxt[0]}: {nxt[1]}, RMSE {nxt[2]:.4f} MPa")

    with plt.rc_context(fonts(14)):             # shown at w:720
        fig, ax = plt.subplots(figsize=(7.8, 4.3))
        top = max(g.max(), b.max())
        ax.axvspan(window.min(), window.max(), color=GOLD, alpha=0.2, zorder=0)
        ax.fill_between(xs, g, color=BLUE, alpha=0.25, zorder=1)
        ax.fill_between(xs, b, color=MUTED, alpha=0.25, zorder=1)
        ax.plot(xs, g, color=BLUE, lw=2.4, zorder=2,
                label=f"Good trials: the best 10% ({n_good} of {len(vals)})")
        ax.plot(xs, b, color=MUTED, lw=2.4, zorder=2, label=f"Bad trials: the other {len(bad)}")
        # each trial as a dot under the axis, one row per group; a value tried twice stacks
        def dots(points, y0, color):
            seen = {}
            for v in points:
                k = seen.get(v, 0)
                seen[v] = k + 1
                ax.scatter([v], [y0 - k * 0.06 * top], s=60, color=color, zorder=3, clip_on=False)
        dots(good, -0.07 * top, BLUE)
        dots(bad, -0.22 * top, MUTED)
        ax.annotate("Try next here:\ngood is common, bad is rare",
                   xy=(window.max(), 0.8 * top), xytext=(window.max() + 6, 0.8 * top),
                   arrowprops=dict(arrowstyle="->", color=INK, lw=1.4),
                   fontsize=14, color=INK, va="center")
        ax.set(xlabel="min_samples_leaf (one dot per trial)", xlim=(0, 50),
               ylim=(-0.33 * top, top * 1.35), yticks=[])
        ax.spines["left"].set_visible(False)
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.legend(loc="upper right", frameon=False)
        fig.tight_layout()
        save(fig, "tpe-explained.png")


def search_figures():
    print("\n=== Hyperparameter search on concrete ===")
    X, y, groups, Xtr, ytr, gtr, Xte, yte = concrete_split()
    print(f"  {len(Xtr)} training rows for GroupKFold(5); {len(Xte)} held-out test rows")
    fig_grid_vs_random()
    curves, tables = fig_optuna_search(Xtr, ytr, gtr)
    tpe_explained_figure(tables)


# --------------------------------------------------------------------------------------
# Widgets: every constant the slide widgets embed, printed for a JS author to paste
# --------------------------------------------------------------------------------------
def widget_numbers():
    print("\n=== Slide widget: TEP threshold sweep (52-channel classifier) ===")
    ff, fa = load_tep()
    with warnings.catch_warnings(), plt.rc_context(CLASSIFICATION_STYLE):
        warnings.simplefilter("ignore")
        model, Xte, yte = fit_tep_classifier(ff, fa)
    proba = model.predict_proba(Xte)[:, 1]
    print(f"  {len(yte)} test rows, {yte.mean():.1%} faulty")
    for t in np.round(np.arange(0.01, 1.00, 0.01), 2):
        pred = (proba >= t).astype(int)
        tp = int(((pred == 1) & (yte == 1)).sum())
        fp = int(((pred == 1) & (yte == 0)).sum())
        fn = int(((pred == 0) & (yte == 1)).sum())
        tn = int(((pred == 0) & (yte == 0)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        print(f"    t={t:.2f}  TP {tp:6d} FP {fp:6d} FN {fn:5d} TN {tn:6d}  precision {prec:.3f}  recall {rec:.3f}")

    print("\n=== Slide widget: grid versus random search points and score curve ===")
    (gx, gy), (rx, ry) = grid_random_points()
    print("  GRID_X " + str(np.round(gx, 4).tolist()))
    print("  GRID_Y " + str(np.round(gy, 4).tolist()))
    print("  RANDOM_X " + str(np.round(rx, 4).tolist()))
    print("  RANDOM_Y " + str(np.round(ry, 4).tolist()))
    print("  SCORE_PEAK 0.7  SCORE_WIDTH 0.12  SCORE_AMP 0.35  SCORE_BASE 0.55")
    xs_widget = np.linspace(0, 1, 101)
    print("  SCORE_CURVE_X " + str(np.round(xs_widget, 3).tolist()))
    print("  SCORE_CURVE_Y " + str(np.round(hp_score(xs_widget), 4).tolist()))

    print("\n=== Slide widget: Optuna replay, two trial tables ===")
    X, y, groups, Xtr, ytr, gtr, Xte, yte = concrete_split()
    curves, tables = optuna_study(Xtr, ytr, gtr, n_trials=40)
    for name in ["random", "TPE"]:
        print(f"  {name.upper()} trials (number, params, RMSE):")
        for number, params, value in tables[name]:
            print(f"    {number:2d}  {params}  {value:.4f}")
        print(f"  {name.upper()}_BEST_SO_FAR " + str(np.round(curves[name], 4).tolist()))


# --------------------------------------------------------------------------------------
# Recap: the last slide of Lecture 9, reused unchanged for the opening recap
# --------------------------------------------------------------------------------------
RECAP_FILES = ["water-hook.png", "opt-paths.png", "concrete-cv.png",
              "concrete-learning.png", "concrete-depth.png"]


def recap_figures():
    """Copy five PNGs from Lecture 9, unchanged: this session documents where they come from.

    They are generated by lectures/l09/figures/make_figures.py (the water, optim and concrete
    groups); L10 does not regenerate them, only reuses them for the opening recap.
    """
    print("\n=== Recap figures, copied from Lecture 9 (lectures/l09/figures/make_figures.py) ===")
    for name in RECAP_FILES:
        src = L09_FIGURES / name
        if not src.exists():
            raise SystemExit(f"missing {src}; run lectures/l09/figures/make_figures.py first")
        shutil.copy(src, HERE / name)
        print(f"  copied {name} from lectures/l09/figures/")


# --------------------------------------------------------------------------------------
# Logo: the official Optuna wordmark, fetched from its own GitHub repository rather than
# redrawn, because it is the project's own mark rather than a chart of someone else's
# result (the "generate, do not copy" rule in CLAUDE.md section 5b is about the latter).
# --------------------------------------------------------------------------------------
OPTUNA_LOGO_URL = "https://raw.githubusercontent.com/optuna/optuna/master/docs/image/optuna-logo.png"
OPTUNA_LOGO_SOURCE = "https://github.com/optuna/optuna/blob/master/docs/image/optuna-logo.png"
OPTUNA_LOGO_LICENSE = "MIT License (github.com/optuna/optuna, LICENSE file at the repository root)"


def fetch_optuna_logo():
    """Download Optuna's own logo into lectures/l10/figures/, unchanged.

    Source: {OPTUNA_LOGO_SOURCE}. License: {OPTUNA_LOGO_LICENSE}. Re-downloaded every run
    rather than cached, since the file is small and this keeps the deck honest about where
    it came from if the upstream logo ever changes.
    """
    print("\n=== Logo: Optuna's own wordmark, from its GitHub repository ===")
    print(f"  source {OPTUNA_LOGO_SOURCE}")
    print(f"  license {OPTUNA_LOGO_LICENSE}")
    req = urllib.request.Request(OPTUNA_LOGO_URL, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req).read()
    path = HERE / "optuna-logo.png"
    path.write_bytes(data)
    print(f"  wrote {path.name} ({len(data)} bytes)")


if __name__ == "__main__":
    import sys

    groups = {"classification", "shapes", "flowsheet", "search", "widgets", "recap", "logo"}
    want = set(sys.argv[1:]) or groups
    unknown = want - groups
    if unknown:
        sys.exit(f"unknown group(s) {sorted(unknown)}; the groups are {sorted(groups)}")
    if "classification" in want:
        classification_figures()
    elif "flowsheet" in want:                   # the marked-up P&ID only, no TEP data needed
        tep_flowsheet_figures()
    if "shapes" in want and "classification" not in want:   # the model-shapes figure and its frames
        with warnings.catch_warnings(), plt.rc_context(CLASSIFICATION_STYLE):
            warnings.simplefilter("ignore")
            classifier_shapes_figure()
    if "search" in want:
        with plt.rc_context(QUANT_STYLE):
            search_figures()
    if "widgets" in want:
        widget_numbers()
    if "recap" in want:
        recap_figures()
    if "logo" in want:
        fetch_optuna_logo()
