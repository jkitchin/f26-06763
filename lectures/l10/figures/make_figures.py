#!/usr/bin/env python3
"""Generate the L10 figures, and print every number the notes and the deck quote.

Run from this directory. With no argument both groups run; name a group to run only it:
    /opt/anaconda3/envs/sys_tools/bin/python make_figures.py
    uv run --no-project --with numpy --with pandas --with xlrd --with pyarrow \
        --with scikit-learn --with matplotlib --with scipy python make_figures.py classification
    uv run --no-project --with numpy --with pandas --with openpyxl --with scikit-learn \
        --with matplotlib --with optuna python make_figures.py search

The groups, and what each writes:
    search          grid_vs_random, optuna_search (experiment tracking and hyperparameter
                    search, on the UCI Combined Cycle Power Plant data), then prints the
                    selection-bias measurement; needs optuna
    classification  tep-data, moons-data, card-moons, logistic-moons, moons-regions,
                    cv-stratified, tep-confusion, tep-unseen, tep-fault14 (the
                    classification material, which moved here from Lecture 9)

The printed block is the record. The classification group takes about 20 seconds and the
search group about a minute.

THE SEARCH FIGURES
------------------
L10 is MLflow tracking plus hyperparameter search. Two figures, computed on the
UCI Combined Cycle Power Plant data (CCPP), this session's search dataset:

    grid_vs_random.png   why random search beats grid when few dimensions
                         matter (Bergstra and Bengio 2012), redrawn as original
                         artwork rather than copied.
    optuna_search.png    a real Optuna study: TPE versus random sampling, best
                         validation RMSE so far against trial number.

The selection-bias lesson (that the best validation score is an optimistic
estimate) is printed rather than plotted. selection_bias() measures it as nested CV
minus the best inner-CV score of a 36-candidate grid (ridge on polynomial features),
against training-set size, and ccpp_fold_noise() prices the fold-to-fold noise from
the workbook's five shuffled sheets (5x2 CV of a linear model, +/-0.051 MW). On this
large, easy dataset the effect is tiny except at small sizes: +0.19 MW at n=80, inside
the fold noise from n=320, and -0.003 MW on all 9,568 rows, so a figure at full size
would show nothing and mislead. The notes cite those printed numbers. Lecture 9's
script computed them before its rewrite dropped CCPP; they moved here with the same
grid, sizes, repeats and seeds, and reproduce the values that script printed.

The committed PNGs and the Optuna bests the notes quote (random 3.335, TPE 3.326 MW)
come from the sys_tools env (scikit-learn 1.9.0, matplotlib 3.11.1), which redraws both
PNGs byte for byte. The uv line above resolved scikit-learn 1.6.1 and matplotlib 3.10.6
on 2026-09-22, which moves the Optuna bests to 3.339 and 3.329 MW and changes the PNG
bytes; the selection-bias numbers are the same under both.

CCPP is fetched once and cached under .cache/ (gitignored); do not commit it.

THE CLASSIFICATION FIGURES
--------------------------
These moved from Lecture 9 with the classification material, and they are drawn here with
the same data, splits, seeds, models, sizes and fonts that lectures/l09/figures/make_figures.py
used for them, so every number they print is the number Lecture 9's record printed.
tep-data.png is the one figure the two scripts share: Lecture 9 introduces the Tennessee
Eastman data with it too, and each lecture's figures live in its own folder.

Where the material comes from. The moons, the Gini impurity example and the Gaussian process
classifier follow Victor Alves's F25 06-325 lecture 9
(https://github.com/victoraalves/06-325-Numerical-Methods-And-Machine-Learning-for-ChemE-Fall-2025);
logistic regression is added beside his three classifiers. The Tennessee Eastman data are the
miniproject's two files, from Rieth et al. (2017), https://doi.org/10.7910/DVN/6C3JR1, CC0,
25 MB and 20 MB from the course data host, cached in .cache/ (gitignored).

Faults 3, 9 and 15 are deliberately absent from every figure: the miniproject's evidence
script checks that students find them. The classifier learns faults 1, 2, 4, 5, 6, 7, 8, 12
and 13 (SEEN), and tep-unseen.png tests it on the other eight (UNSEEN).

A FINDING THAT SHAPED THE SESSION
---------------------------------
On TEP, fault 14 (sticking reactor cooling water valve) keeps the mean of xmv_10 and widens
its spread fourteen-fold, so a linear classifier catches none of it and a two-cut tree
catches most of it.

WHEN A TEP FAULT STARTS
-----------------------
Rieth et al. sample every 3 minutes, 500 samples (25 hours) per training run, and their
dataset description says the faults are introduced 1 hour into the faulty training runs.
The data agree: faulty run r of every fault is identical to fault-free run r, channel for
channel, through sample 20 (1.0 hours) at least. Fault 1, the one tep-data.png plots, first
differs at sample 21 in all twenty runs. tep_onset() finds the first differing sample for
each run, and time is plotted as sample x 3 minutes, so the fault line sits at 1.0 hours. A
sample is labelled faulty when it comes from a fault run after sample 20.

FIGURE SHAPES
-------------
Every classification figure lands on a 1280x720 MARP slide, sized with its fonts so that its
smallest text lands at 16 px or more at the width the deck shows it (the comment on each
rc_context gives that width, and fonts() gives the arithmetic). card-moons.png is saved at
exactly 3.4 x 2.3 inches with fixed margins and no axes, like Lecture 9's dataset cards.
"""
from __future__ import annotations

import io
import urllib.request
import warnings
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.datasets import make_moons
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.gaussian_process import GaussianProcessClassifier
from sklearn.gaussian_process.kernels import RBF
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import (GridSearchCV, KFold, StratifiedKFold,
                                     cross_val_score, train_test_split)
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore", category=UserWarning)

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
URL = "https://archive.ics.uci.edu/static/public/294/combined+cycle+power+plant.zip"
MEMBER = "CCPP/Folds5x2_pp.xlsx"
FEATURES = ["AT", "V", "AP", "RH"]
TARGET = "PE"
SEED = 0

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#1a7f37"

# Each group draws under its own style, applied on top of Matplotlib's defaults with
# plt.rc_context, so the two never leak into each other.
SEARCH_STYLE = {
    "font.size": 13, "axes.labelsize": 13, "axes.titlesize": 15,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "figure.dpi": 160, "savefig.bbox": "tight",
}
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


def load_ccpp():
    """Fetch (once) and parse CCPP Sheet1, this session's search dataset."""
    CACHE.mkdir(exist_ok=True)
    xlsx = CACHE / "Folds5x2_pp.xlsx"
    if not xlsx.exists():
        print("downloading", URL)
        with urllib.request.urlopen(URL) as r:
            archive = zipfile.ZipFile(io.BytesIO(r.read()))
        xlsx.write_bytes(archive.read(MEMBER))
    df = pd.read_excel(xlsx, "Sheet1")
    return df[FEATURES].to_numpy(), df[TARGET].to_numpy()


def fig_grid_vs_random() -> None:
    """Grid versus random over two hyperparameters, one of which matters.

    The classic Bergstra and Bengio picture: nine trials each. Grid tries three
    distinct values of the important parameter; random tries nine. Redrawn.
    """
    rng = np.random.default_rng(SEED)
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.2))

    def importance(x):  # a smooth "important parameter" response, for the margins
        return np.exp(-((x - 0.7) ** 2) / 0.05)

    for ax, mode in zip(axes, ["grid", "random"]):
        if mode == "grid":
            g = np.linspace(0.1, 0.9, 3)
            xs, ys = np.meshgrid(g, g)
            xs, ys = xs.ravel(), ys.ravel()
        else:
            xs, ys = rng.uniform(0.05, 0.95, 9), rng.uniform(0.05, 0.95, 9)
        ax.scatter(xs, ys, s=90, color=CMU_RED, zorder=3, edgecolor="white")
        # marginal on the "important" (x) axis: the response curve and the tried values
        gx = np.linspace(0, 1, 200)
        ax.plot(gx, 0.02 + 0.12 * importance(gx), color=MUTED, lw=1.5, alpha=0.7)
        for x in xs:
            ax.plot([x, x], [0, 0.02 + 0.12 * importance(x)], color=BLUE, lw=1, alpha=0.6)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_xlabel("important hyperparameter")
        ax.set_ylabel("unimportant hyperparameter")
        n_distinct = len(np.unique(np.round(xs, 6)))
        ax.set_title(f"{mode}: {n_distinct} distinct values tried\n"
                     "on the important axis", fontsize=12.5)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Nine trials each: random covers the axis that matters", fontsize=15, y=1.0)
    fig.savefig(HERE / "grid_vs_random.png")
    plt.close(fig)
    print("wrote grid_vs_random.png  (grid 3 distinct x-values, random 9)")


def _objective(trial, X, y):
    params = dict(
        learning_rate=trial.suggest_float("learning_rate", 0.01, 0.5, log=True),
        max_leaf_nodes=trial.suggest_int("max_leaf_nodes", 8, 128, log=True),
        max_iter=trial.suggest_int("max_iter", 50, 250),
        l2_regularization=trial.suggest_float("l2_regularization", 1e-6, 10.0, log=True),
        min_samples_leaf=trial.suggest_int("min_samples_leaf", 5, 60),
    )
    model = HistGradientBoostingRegressor(random_state=SEED, **params)
    cv = KFold(n_splits=3, shuffle=True, random_state=SEED)
    rmse = -cross_val_score(model, X, y, cv=cv, n_jobs=-1,
                            scoring="neg_root_mean_squared_error").mean()
    return rmse


def fig_optuna_search(Xtr, ytr) -> dict:
    """A real Optuna study: TPE versus random, best-so-far validation RMSE."""
    # Imported here, so that the classification group runs without optuna installed.
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    n_trials = 30
    curves = {}
    for name, sampler in [("random", optuna.samplers.RandomSampler(seed=SEED)),
                          ("TPE", optuna.samplers.TPESampler(seed=SEED))]:
        study = optuna.create_study(direction="minimize", sampler=sampler)
        study.optimize(lambda t: _objective(t, Xtr, ytr), n_trials=n_trials)
        vals = [t.value for t in study.trials]
        curves[name] = np.minimum.accumulate(vals)

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.plot(range(1, n_trials + 1), curves["random"], color=BLUE, lw=2,
            marker="o", ms=3, label="random search")
    ax.plot(range(1, n_trials + 1), curves["TPE"], color=CMU_RED, lw=2,
            marker="o", ms=3, label="Optuna TPE")
    ax.set_xlabel("trial")
    ax.set_ylabel("best validation RMSE so far, MW")
    ax.set_title("Hyperparameter search on CCPP: TPE versus random", pad=10)
    ax.legend(frameon=False)
    fig.savefig(HERE / "optuna_search.png")
    plt.close(fig)
    best = {k: float(v[-1]) for k, v in curves.items()}
    print(f"wrote optuna_search.png  (best RMSE: random {best['random']:.3f}, "
          f"TPE {best['TPE']:.3f} MW over {n_trials} trials)")
    return best


def ccpp_fold_noise() -> float:
    """The fold-to-fold noise of CCPP: the spread of a linear model's 5x2 CV test RMSE.

    The UCI workbook holds the same 9,568 rows on five sheets, each shuffled differently, so
    that a 5x2 CV test can be run. Two unshuffled folds per sheet give ten test RMSEs, and
    their standard deviation is the yardstick a selection-bias estimate has to clear.
    """
    xlsx = CACHE / "Folds5x2_pp.xlsx"
    if not xlsx.exists():
        load_ccpp()                                # fetches the workbook into .cache/
    book = pd.ExcelFile(xlsx)
    scores = []
    for name in book.sheet_names:
        frame = pd.read_excel(book, name)
        folds = cross_val_score(
            LinearRegression(),
            frame[FEATURES],
            frame[TARGET],
            cv=KFold(n_splits=2, shuffle=False),
            scoring="neg_root_mean_squared_error",
        )
        scores.extend(-folds)
    scores = np.array(scores)
    print(f"  fold-to-fold noise: 5x2 CV of a linear model over the {len(book.sheet_names)} sheets, "
          f"{scores.mean():.4f} +/- {scores.std():.4f} MW ({len(scores)} fold RMSEs)")
    return float(scores.std())


def selection_bias(X, y) -> dict:
    """How much the best validation score flatters itself, against training-set size.

    Print only, no figure. Non-nested: run a grid search on n rows and report its best
    inner-CV RMSE, which is the number a search hands you. Nested: wrap the whole search in
    an outer 5-fold CV, so each outer fold's winner is chosen without seeing that fold, which
    is the honest estimate. Both sides train on 4/5 of the rows they are given, so the gap is
    selection bias alone, without the confound of a final refit on more data. The candidates
    are ridge on polynomial features, 3 degrees x 12 alphas = 36, and each size is averaged
    over repeated random subsamples of the rows.
    """
    print("\n=== Selection bias: the best validation score against the honest one ===")
    score = "neg_root_mean_squared_error"
    pipe = Pipeline([
        ("poly", PolynomialFeatures(2)),
        ("sc", StandardScaler()),
        ("m", Ridge()),
    ])
    grid = {
        "poly__degree": [1, 2, 3],
        "m__alpha": np.logspace(-3, 4, 12),
    }
    n_candidates = len(grid["poly__degree"]) * len(grid["m__alpha"])
    noise = ccpp_fold_noise()

    sizes = [80, 160, 320, 640, 1280, 2560, 5120, len(X)]
    bias = []
    for n in sizes:
        reps = 12 if n <= 640 else (6 if n <= 2560 else 3)
        non_nested, nested = [], []
        for rep in range(reps):
            rng = np.random.default_rng(1000 + rep)
            idx = rng.choice(len(X), n, replace=False)
            search = GridSearchCV(
                pipe,
                grid,
                scoring=score,
                n_jobs=-1,
                cv=KFold(n_splits=5, shuffle=True, random_state=rep),
            )
            search.fit(X[idx], y[idx])
            non_nested.append(-search.best_score_)
            outer = cross_val_score(
                search,
                X[idx],
                y[idx],
                scoring=score,
                n_jobs=-1,
                cv=KFold(n_splits=5, shuffle=True, random_state=100 + rep),
            )
            nested.append(-outer.mean())
        bias.append(np.mean(nested) - np.mean(non_nested))
        where = "inside" if abs(bias[-1]) < noise else "outside"
        print(f"  n={n:5d}  best validation {np.mean(non_nested):7.4f}  "
              f"nested {np.mean(nested):7.4f}  optimism {bias[-1]:+.4f} MW  "
              f"({abs(bias[-1]) / noise:.2f}x the noise, {where}; {reps} repeats)")

    crossing = next((n for n, b in zip(sizes, bias) if abs(b) < noise), None)
    print(f"  over {n_candidates} candidates: {bias[0]:+.3f} MW at n={sizes[0]} "
          f"({bias[0] / noise:.1f}x the fold noise of {noise:.4f} MW); "
          f"first inside the noise at n={crossing}; {bias[-1]:+.3f} MW on all {len(X):,} rows")
    return {
        "sizes": sizes,
        "bias": bias,
        "noise": noise,
        "n_candidates": n_candidates,
        "crossing": crossing,
    }


def search_figures():
    """The search group: the two search figures, then the selection-bias measurement."""
    X, y = load_ccpp()
    print(f"loaded CCPP: {X.shape[0]} rows, {X.shape[1]} features -> PE (MW)")
    Xtr, _, ytr, _ = train_test_split(X, y, test_size=0.2, random_state=SEED)
    fig_grid_vs_random()
    fig_optuna_search(Xtr, ytr)
    selection_bias(X, y)


# --------------------------------------------------------------------------------------
# Classification: helpers and data
# --------------------------------------------------------------------------------------
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


def fetch(url, local):
    CACHE.mkdir(exist_ok=True)
    path = CACHE / local
    if not path.exists():
        print(f"  downloading {url}")
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        path.write_bytes(urllib.request.urlopen(req).read())
    return path


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


def moons_data():
    """The 300 moons and the 70/30 split every moons figure uses."""
    X, y = make_moons(
        n_samples=300,
        noise=0.25,
        random_state=0,
    )
    split = train_test_split(
        X,
        y,
        test_size=0.3,
        random_state=42,
    )
    return X, y, *split


# Class colours for the moons: the two ends of the viridis map moons-regions.png shades with.
MOON_COLOURS = [plt.cm.viridis(0.0), plt.cm.viridis(1.0)]


# --------------------------------------------------------------------------------------
# The Tennessee Eastman data, introduced (the same figure Lecture 9 draws)
# --------------------------------------------------------------------------------------
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


def tep_trace(frame):
    """Hours and reactor pressure for one run, with sample k at k x 3 minutes."""
    frame = frame.sort_values("sample")
    return frame["sample"].to_numpy() * 3 / 60, frame["xmeas_7"].to_numpy()


def tep_data_figure(ff, fa):
    print("\n=== The Tennessee Eastman data, drawn ===")
    firsts = tep_onset(ff, fa, TEP_FAULT, range(1, 21))
    print(f"  TEP fault {TEP_FAULT}, runs 1-20: each identical to the fault-free run of the same number through"
          f" sample {min(firsts) - 1} and first different at sample {sorted(set(firsts))}")
    others = sorted({s for f in SEEN for s in tep_onset(ff, fa, f, range(1, 4))})
    print(f"  every fault in SEEN, runs 1-3: identical through sample 20 at least, first differences at samples"
          f" {others} (a slow fault takes longer to reach the 52 channels)")
    onset = (min(firsts) - 1) * 3 / 60
    print(f"  so the fault starts after sample {min(firsts) - 1}, at {onset:.2f} hours (samples every 3 minutes)")
    t0, p0 = tep_trace(ff[ff.simulationRun == TEP_RUN])
    t1, p1 = tep_trace(fa[(fa.faultNumber == TEP_FAULT) & (fa.simulationRun == TEP_RUN)])
    print(f"  run {TEP_RUN}: fault-free pressure {p0.min():.0f} to {p0.max():.0f} kPa;"
          f" fault {TEP_FAULT} pressure {p1.min():.0f} to {p1.max():.0f} kPa")
    with plt.rc_context(fonts(14)):             # shown at w:700
        fig, ax = plt.subplots(figsize=(7.7, 2.75))
        ax.plot(
            t0,
            p0,
            color="0.55",
            lw=1.1,
            label=f"Fault-free run {TEP_RUN}",
        )
        ax.plot(
            t1,
            p1,
            color=CMU_RED,
            lw=1.3,
            label=f"Fault {TEP_FAULT}, run {TEP_RUN} (A/C feed ratio step)",
        )
        ax.axvline(
            onset,
            color=INK,
            ls="--",
            lw=1.1,
        )
        ax.text(
            onset + 0.3,
            2585,
            f"Fault {TEP_FAULT} starts at {onset:.0f} hour",
            color=INK,
            va="bottom",
        )
        ax.set(
            xlabel="Time (hours)",
            ylabel="Reactor pressure,\nxmeas_7 (kPa)",
            xlim=(0, 25),
            ylim=(2580, 2850),
            yticks=[2600, 2700, 2800],
        )
        ax.legend(
            loc="upper right",
            handlelength=1.5,
            borderaxespad=0.2,
        )
        save(fig, "tep-data.png")


# --------------------------------------------------------------------------------------
# The moons (Victor's F25 lecture 9, plus logistic regression)
# --------------------------------------------------------------------------------------
def bare_card(name, draw):
    """A thumbnail with no axes, ticks or labels, 3.4 x 2.3 inches like Lecture 9's cards.

    The moons card is shown 96 px tall beside a line of text, where tick labels would be too
    small to read, so it carries only the points.
    """
    with plt.rc_context({"savefig.bbox": "standard"}):
        fig = plt.figure(figsize=(3.4, 2.3))
        ax = fig.add_axes([0.03, 0.04, 0.94, 0.92])
        draw(ax)
        ax.axis("off")
        save(fig, name)


def moons_data_figure():
    """The moons before any model: 300 points, two classes, and their dataset card."""
    print("\n=== The moons, drawn ===")
    X, y, *_ = moons_data()
    print(f"  {len(y)} points, {int((y == 0).sum())} of class 0 and {int((y == 1).sum())} of class 1")
    fig, ax = plt.subplots(figsize=(6, 3.8))
    for c in (0, 1):
        ax.scatter(
            X[y == c, 0],
            X[y == c, 1],
            s=18,
            color=MOON_COLOURS[c],
            edgecolor="k",
            linewidths=0.4,
            label=f"Class {c}",
        )
    ax.set(
        xlabel="x1",
        ylabel="x2",
    )
    ax.legend(loc="lower left")
    save(fig, "moons-data.png")

    def moons_card(ax):
        for c in (0, 1):
            ax.scatter(
                X[y == c, 0],
                X[y == c, 1],
                s=16,
                color=MOON_COLOURS[c],
                linewidths=0,
            )

    print("  dataset card, 3.4 x 2.3 in")
    bare_card("card-moons.png", moons_card)


def logistic_moons_figure():
    """The logistic function, and the straight boundary it draws on the moons."""
    print("\n=== Logistic regression on the moons ===")
    X, y, Xtr, Xte, ytr, yte = moons_data()
    m = LogisticRegression().fit(Xtr, ytr)
    acc = accuracy_score(yte, m.predict(Xte))
    print(f"  logistic regression: test accuracy {acc:.3f}; w {m.coef_[0].round(3)}, b {m.intercept_[0]:.3f}")
    fig, (a, b) = plt.subplots(
        1,
        2,
        figsize=(11, 3.9),
        gridspec_kw={"width_ratios": [1, 1.25]},
    )
    z = np.linspace(-6, 6, 300)
    guide = {
        "color": MUTED,
        "ls": "--",
        "lw": 1,
    }
    a.axhline(0.5, **guide)
    a.axvline(0, **guide)
    a.plot(
        z,
        1 / (1 + np.exp(-z)),
        color=BLUE,
        lw=2.4,
    )
    a.text(
        1.3,
        0.6,
        "Predict class 1\nwhen p > 0.5",
        fontsize=11,
        color=INK,
        va="center",
        linespacing=1.3,
    )
    a.text(
        5.8,
        0.1,
        "$z = w^T x + b$",
        fontsize=13,
        color=INK,
        ha="right",
        va="center",
    )
    a.set(
        xlabel="z",
        ylabel="p = $\\sigma(z)$",
        ylim=(-0.03, 1.03),
        title="Logistic function $\\sigma(z) = 1 / (1 + e^{-z})$",
    )
    xx, yy = np.meshgrid(
        np.linspace(X[:, 0].min() - 0.5, X[:, 0].max() + 0.5, 300),
        np.linspace(X[:, 1].min() - 0.5, X[:, 1].max() + 0.5, 300),
    )
    zz = m.predict_proba(np.c_[xx.ravel(), yy.ravel()])[:, 1].reshape(xx.shape)
    cs = b.contourf(
        xx,
        yy,
        zz,
        levels=np.linspace(0, 1, 11),
        cmap="viridis",
        alpha=0.45,
    )
    b.contour(
        xx,
        yy,
        zz,
        levels=[0.5],
        colors="k",
        linewidths=1.2,
    )
    b.scatter(
        X[:, 0],
        X[:, 1],
        c=y,
        edgecolor="k",
        s=14,
        cmap="viridis",
        linewidths=0.5,
    )
    cb = fig.colorbar(
        cs,
        ax=b,
        pad=0.02,
        ticks=[0, 0.5, 1],
    )
    cb.set_label("Probability of class 1")
    b.set(
        xlabel="x1",
        ylabel="x2",
        title=f"Logistic regression, test accuracy {acc:.3f}",
    )
    save(fig, "logistic-moons.png")


def moons_figure():
    print("\n=== Moons (Victor's F25 lecture 9, plus logistic regression) ===")
    X, y, Xtr, Xte, ytr, yte = moons_data()
    models = [
        ("Logistic regression", LogisticRegression()),
        ("Decision tree (depth 3)", DecisionTreeClassifier(
            max_depth=3,
            random_state=0,
        )),
        ("Neural network (5 ReLU)", MLPClassifier(
            hidden_layer_sizes=(5,),
            activation="relu",
            solver="lbfgs",
            max_iter=2000,
            random_state=0,
        )),
        ("Gaussian process (RBF)", GaussianProcessClassifier(
            kernel=RBF(1.0),
            random_state=0,
            max_iter_predict=200,
        )),
    ]
    xx, yy = np.meshgrid(np.linspace(X[:, 0].min() - 0.5, X[:, 0].max() + 0.5, 300),
                         np.linspace(X[:, 1].min() - 0.5, X[:, 1].max() + 0.5, 300))
    grid = np.c_[xx.ravel(), yy.ravel()]
    with plt.rc_context(fonts(13)):             # shown at w:1120
        fig, axes = plt.subplots(
            1,
            4,
            figsize=(13, 3.25),
            sharey=True,
            gridspec_kw={"wspace": 0.1},
        )
        for ax, (name, m) in zip(axes, models):
            m.fit(Xtr, ytr)
            acc = accuracy_score(yte, m.predict(Xte))
            print(f"  {name:26s} test accuracy {acc:.3f}")
            zz = m.predict_proba(grid)[:, 1].reshape(xx.shape)
            ax.contourf(
                xx,
                yy,
                zz,
                levels=np.linspace(0, 1, 11),
                cmap="viridis",
                alpha=0.45,
            )
            ax.contour(
                xx,
                yy,
                zz,
                levels=[0.5],
                colors="k",
                linewidths=1,
            )
            ax.scatter(
                X[:, 0],
                X[:, 1],
                c=y,
                edgecolor="k",
                s=14,
                cmap="viridis",
            )
            ax.set(
                title=f"{name}\nTest accuracy {acc:.3f}",
                xlabel="x1",
                xticks=[-1, 0, 1, 2],
            )
        axes[0].set_ylabel("x2")
        save(fig, "moons-regions.png")


def gini_example():
    """The worked Gini impurity example: a node of 5 samples, 4 of one class and 1 of the other."""
    print("\n=== Gini impurity, worked ===")
    counts = np.array([4, 1])
    p = counts / counts.sum()
    print(f"  a node with {counts[0]} blue and {counts[1]} red: p = {p.round(2).tolist()},"
          f" G = 1 - ({p[0]:.1f}^2 + {p[1]:.1f}^2) = {1 - np.sum(p**2):.2f}; a pure node has G = 0")


# --------------------------------------------------------------------------------------
# Stratified k-fold: a rare class and five folds
# --------------------------------------------------------------------------------------
def cv_stratified_figure():
    print("\n=== Stratified k-fold, drawn ===")
    y = np.r_[np.ones(5), np.zeros(45)].astype(int)

    def kfold(seed):
        return KFold(
            5,
            shuffle=True,
            random_state=seed,
        )

    stratified = StratifiedKFold(
        5,
        shuffle=True,
        random_state=0,
    )
    hit = sum(min(y[te].sum() for _, te in kfold(s).split(np.zeros(50))) == 0
              for s in range(10000))
    print(f"  50 samples, 5 positive: KFold leaves some fold with no positive in {hit / 100:.1f}% of 10,000 shuffles;"
          f" StratifiedKFold puts {[int(y[te].sum()) for _, te in stratified.split(np.zeros(50), y)]} in the folds")

    # Drawn: the first KFold seed that leaves exactly one fold with no faulty sample, so the
    # title can name that fold, against StratifiedKFold.
    def per_fold(seed):
        return [int(y[te].sum()) for _, te in kfold(seed).split(np.zeros(50))]

    seed = next(s for s in range(10000) if per_fold(s).count(0) == 1)
    empty = per_fold(seed).index(0) + 1
    print(f"  drawn: KFold(random_state={seed}) puts {per_fold(seed)} faulty samples in the folds (fold {empty} has none)")
    splitters = [
        (
            kfold(seed),
            {},
            f"KFold: fold {empty} has no faulty sample",
        ),
        (
            stratified,
            {"y": y},
            "StratifiedKFold: 1 faulty per fold",
        ),
    ]
    with plt.rc_context(fonts(13)):             # shown at w:680
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(8.2, 2.45),
            sharey=True,
            gridspec_kw={"wspace": 0.12},
        )
        for ax, (cv, kw, title) in zip(axes, splitters):
            for i, (_, te) in enumerate(cv.split(np.zeros(50), **kw)):
                ax.scatter(
                    np.arange(len(te)),
                    [i] * len(te),
                    marker="s",
                    s=60,
                    c=[CMU_RED if y[j] else "0.85" for j in te],
                    linewidths=0,
                )
                n = int(y[te].sum())
                ax.text(
                    len(te) - 0.3,
                    i,
                    f"{n} faulty",
                    va="center",
                    color=CMU_RED if n == 0 else MUTED,
                )
            ax.set(
                title=title,
                xlim=(-0.7, len(te) + 3.0),
                xticks=[],
                yticks=range(5),
                yticklabels=[f"Fold {i + 1}" for i in range(5)],
            )
            ax.spines["bottom"].set_visible(False)
            ax.spines["left"].set_visible(False)
            ax.tick_params(
                axis="y",
                length=0,
            )
        axes[0].set_ylim(4.6, -0.6)
        for colour, label in [(CMU_RED, "Faulty"), ("0.85", "Normal")]:
            axes[0].scatter(
                [],
                [],
                marker="s",
                s=80,
                color=colour,
                label=label,
            )
        fig.legend(
            loc="lower center",
            ncol=2,
            bbox_to_anchor=(0.5, 0.97),
        )
        fig.text(
            0.5,
            0.08,
            "Each row is one fold's 10 validation samples",
            ha="center",
            va="top",
        )
        save(fig, "cv-stratified.png")


# --------------------------------------------------------------------------------------
# Tennessee Eastman: a supervised fault classifier
# --------------------------------------------------------------------------------------
def tep_table(ff, fa, normal_runs, faults, fault_runs):
    d = pd.concat([ff[ff.simulationRun.isin(normal_runs)],
                   fa[fa.faultNumber.isin(faults) & fa.simulationRun.isin(fault_runs)]], ignore_index=True)
    y = ((d.faultNumber > 0) & (d["sample"] > 20)).astype(int).to_numpy()
    return d, d[CH].to_numpy(), y


def tep_figures(ff, fa):
    print("\n=== Tennessee Eastman, normal against faulty ===")
    _, Xtr, ytr = tep_table(ff, fa, range(1, 301), SEEN, range(1, 6))
    _, Xte, yte = tep_table(ff, fa, range(401, 501), SEEN, range(11, 13))
    print(f"  training rows {len(ytr)} ({ytr.mean():.1%} faulty); test rows {len(yte)} ({yte.mean():.1%} faulty)")
    shuffled = KFold(
        5,
        shuffle=True,
        random_state=0,
    )
    fr = [ytr[te].mean() for _, te in shuffled.split(Xtr)]
    print(f"  plain shuffled KFold on the training table: faulty fraction per fold {np.round(fr, 3)}")
    print(f"  a GP classifier on all {len(ytr)} training rows: a {len(ytr)} x {len(ytr)} kernel matrix,"
          f" {len(ytr) ** 2 * 8 / 1e9:.0f} GB in double precision")
    models = {
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

    cells = [["TP", "FN"], ["FP", "TN"]]          # rows actually faulty, normal; columns predicted
    panels = [
        ("Baseline: always normal", "Baseline: always normal"),
        ("Neural network", "Neural network (32 ReLU units)"),
    ]
    with plt.rc_context(fonts(14)):             # shown at w:760
        fig, axes = plt.subplots(
            1,
            2,
            figsize=(8.4, 3.1),
            sharey=True,
            gridspec_kw={"wspace": 0.1},
        )
        for ax, (name, title) in zip(axes, panels):
            cm = cms[name]
            ax.imshow(
                cm,
                cmap="Blues",
                vmin=0,
                vmax=cm.sum() * 0.25,
                aspect="auto",
            )
            for (r, c), v in np.ndenumerate(cm):
                ax.text(
                    c,
                    r,
                    f"{cells[r][c]}\n{v:,}",
                    ha="center",
                    va="center",
                    fontsize=15,
                    linespacing=1.3,
                    color="white" if v > cm.sum() * 0.2 else INK,
                )
            ax.set_xticks([0, 1], ["Predicted\nfaulty", "Predicted\nnormal"])
            ax.set_yticks([0, 1], ["Actually\nfaulty", "Actually\nnormal"])
            ax.set_title(title)
            ax.tick_params(length=0)
            for spine in ax.spines.values():
                spine.set_visible(False)
        save(fig, "tep-confusion.png")

    rec = {"Faults it learned\n(test runs 11-12)": models["Neural network"].predict(Xte[yte == 1]).mean()}
    print("  recall of the same neural network on faults it never saw (runs 11-12, after the fault starts):")
    for f in UNSEEN:
        a = fa[(fa.faultNumber == f) & fa.simulationRun.isin(range(11, 13)) & (fa["sample"] > 20)]
        rec[f"Fault {f}"] = models["Neural network"].predict(a[CH].to_numpy()).mean()
        print(f"    fault {f:2d}: {rec[f'Fault {f}']:.3f}")
    with plt.rc_context(fonts(13)):             # shown at w:900
        fig, ax = plt.subplots(figsize=(11, 3.8))
        keys = list(rec)
        # The first bar gets a wider slot, for its two-line label.
        xs = np.r_[0, np.arange(1, len(keys)) + 0.6]
        ax.bar(xs, [rec[k] for k in keys], color=[BLUE] + ["0.6"] * len(UNSEEN))
        for x, k in zip(xs, keys):
            ax.text(x, rec[k] + 0.03, f"{rec[k]:.3f}", ha="center")
        ax.set_xticks(xs, keys)
        ax.tick_params(
            axis="x",
            length=0,
        )
        ax.set(
            ylabel="Recall",
            ylim=(0, 1.12),
            yticks=[0, 0.5, 1],
            title="The same classifier, on faults it was trained on and faults it never saw",
        )
        save(fig, "tep-unseen.png")

    print("\n  fault 14, one fault at a time (normal runs 1-300 + fault 14 runs 1-10; test runs 401-500 + 11-20):")
    trn = ff[ff.simulationRun <= 300]
    a = fa[fa.faultNumber == 14]
    A_tr, A_te = a[a.simulationRun <= 10], a[(a.simulationRun > 10) & (a["sample"] > 20)]
    X14 = np.vstack([trn[CH].to_numpy(), A_tr[CH].to_numpy()])
    y14 = np.r_[np.zeros(len(trn)), (A_tr["sample"] > 20).to_numpy()]
    nrm = ff[ff.simulationRun > 400]
    lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)).fit(X14, y14)
    print(f"    logistic regression recall {lr.predict(A_te[CH].to_numpy()).mean():.3f}")
    cuts = None
    for d in [1, 2, 8]:
        t = DecisionTreeClassifier(
            max_depth=d,
            random_state=0,
        ).fit(X14, y14)
        print(f"    tree depth {d}: recall {t.predict(A_te[CH].to_numpy()).mean():.3f},"
              f" false alarms on normal runs {t.predict(nrm[CH].to_numpy()).mean():.4f}")
        if d == 2:
            tr_ = t.tree_
            cuts = sorted({tr_.threshold[i] for i in range(tr_.node_count)
                           if tr_.feature[i] == CH.index("xmv_10")})
            print(f"    depth-2 tree splits xmv_10 at {[round(c, 2) for c in cuts]}")
    v_n, v_f = nrm["xmv_10"], A_te["xmv_10"]
    lo, hi = v_n.mean() - 3 * v_n.std(), v_n.mean() + 3 * v_n.std()
    print(f"    xmv_10 normal mean {v_n.mean():.2f} std {v_n.std():.2f}; fault 14 mean {v_f.mean():.2f} std {v_f.std():.2f};"
          f" {np.mean(v_f < lo):.1%} below and {np.mean(v_f > hi):.1%} above the normal +/- 3 std band")
    with plt.rc_context(fonts(13)):             # shown at about w:620, beside the bullets
        fig, ax = plt.subplots(figsize=(6.5, 3.1))
        bins = np.linspace(20, 62, 120)
        ax.hist(
            v_n,
            bins=bins,
            density=True,
            color="0.6",
            alpha=0.8,
            label="Normal (runs 401-500)",
        )
        ax.hist(
            v_f,
            bins=bins,
            density=True,
            color=CMU_RED,
            alpha=0.55,
            label="Fault 14 (runs 11-20)",
        )
        for c in cuts:
            ax.axvline(
                c,
                color=INK,
                ls="--",
                lw=1.2,
            )
        ax.text(
            cuts[1] + 0.5,
            0.3,
            "The tree's two cuts",
            va="bottom",
        )
        ax.set(
            xlabel="xmv_10, reactor cooling water flow (%)",
            ylabel="Density",
            yscale="log",
            xlim=(25, 58),
            ylim=(3e-5, 1.5),
            yticks=[1e-4, 1e-2, 1],
        )
        ax.minorticks_off()
        fig.legend(
            loc="lower center",
            ncol=2,
            bbox_to_anchor=(0.55, 0.88),
            handlelength=1.4,
            columnspacing=1.2,
        )
        save(fig, "tep-fault14.png")


def classification_figures():
    """The classification group, drawn under Lecture 9's style with every warning silenced.

    The silenced warnings are convergence notices from the moons network and the TEP
    classifiers; Lecture 9's script silenced them the same way.
    """
    with warnings.catch_warnings(), plt.rc_context(CLASSIFICATION_STYLE):
        warnings.simplefilter("ignore")
        ff, fa = load_tep()
        tep_data_figure(ff, fa)
        moons_data_figure()
        logistic_moons_figure()
        moons_figure()
        gini_example()
        cv_stratified_figure()
        tep_figures(ff, fa)


if __name__ == "__main__":
    import sys

    # `python make_figures.py classification` regenerates only that group.
    groups = {"search", "classification"}
    want = set(sys.argv[1:]) or groups
    unknown = want - groups
    if unknown:
        sys.exit(f"unknown group(s) {sorted(unknown)}; the groups are {sorted(groups)}")
    if "search" in want:
        with plt.rc_context(SEARCH_STYLE):
            search_figures()
    if "classification" in want:
        classification_figures()
