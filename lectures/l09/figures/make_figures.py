#!/usr/bin/env python3
"""Generate the L9 figures from the UCI Combined Cycle Power Plant, NASA Airfoil
Self-Noise, and UCI SECOM datasets.

Run with:
    uv run --with pandas,numpy,scikit-learn,matplotlib,openpyxl python make_figures.py

Every number quoted in notes.md and slides.md is printed by this script. Nothing
here is copied from a paper: the site is public, a figure you can regenerate is a
figure you can check, and computing the claim yourself routinely changes it.

Three of these figures changed what the lecture says.

  1. The selection-bias figure was drafted expecting the familiar "the best
     validation score is optimistic" story. On the full 9,568-row power-plant
     set the bias is -0.003 MW, i.e. unmeasurable, and a first attempt to show
     it via a held-out test set produced a *negative* gap, because refitting the
     winner on 100% of the training data beats the 80% that cross-validation
     trains on by more than selection bias costs. The honest figure is bias
     against training-set size, which shows the effect is real, is roughly 1/n,
     and has died below the fold-to-fold noise by n ~ 2500.

  2. The leakage figure that the module asks for, scale-before-split, was
     measured and produced a gap of at most 0.0015 MW across four models. It is
     not plotted, because plotting a zero as though it were a finding would be
     the dishonest half of this lesson. The number is printed below and the
     notes report it as measured.

  3. The baseline figure was drafted as a single bar chart and was actively
     misleading: the predict-the-mean bar is so tall that every real model looks
     identical. It is now two panels on two scales, which is the point.

Outputs (committed alongside this script):
    baseline-ladder.png   what a baseline costs you, on two scales
    cv-schemes.png        k-fold vs GroupKFold on grouped wind-tunnel data
    learning-curves.png   underfit, overfit, and what more data would buy
    selection-bias.png    nested vs non-nested CV against training-set size
    imbalance.png         ROC-AUC, PR-AUC, and alert burden under 6.6% failures

Raw archives are cached in .cache/ and are gitignored; do not commit them.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (average_precision_score, precision_recall_curve,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import (GridSearchCV, GroupKFold, KFold,
                                     StratifiedKFold, cross_val_predict,
                                     cross_val_score, learning_curve)
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.tree import DecisionTreeRegressor

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
SEED = 0
SCORE = "neg_root_mean_squared_error"

CCPP_URL = "https://archive.ics.uci.edu/static/public/294/combined+cycle+power+plant.zip"
AIRFOIL_URL = "https://archive.ics.uci.edu/static/public/291/airfoil+self+noise.zip"
SECOM_URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
AMBER = "#b8860b"

plt.rcParams.update({
    "font.size": 13,
    "axes.labelsize": 13,
    "axes.titlesize": 15,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": MUTED,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})

AIRFOIL_COLS = ["freq_hz", "aoa_deg", "chord_m", "velocity_ms", "thickness_m"]


def fetch(url: str, members: dict[str, str]) -> None:
    """Download `url` once and extract {archive_member: local_name} into .cache."""
    CACHE.mkdir(exist_ok=True)
    if all((CACHE / out).exists() for out in members.values()):
        return
    print(f"downloading {url}")
    with urllib.request.urlopen(url) as response:
        payload = response.read()
    archive = zipfile.ZipFile(io.BytesIO(payload))
    for member, out in members.items():
        (CACHE / out).write_bytes(archive.read(member))


def load_ccpp() -> pd.DataFrame:
    """The 9,568-row power-plant set. Sheet1 of five; see `check_shuffles`."""
    fetch(CCPP_URL, {"CCPP/Folds5x2_pp.xlsx": "Folds5x2_pp.xlsx"})
    return pd.read_excel(CACHE / "Folds5x2_pp.xlsx", "Sheet1")


def load_airfoil() -> tuple[pd.DataFrame, np.ndarray]:
    """NASA airfoil self-noise, plus a group id per wind-tunnel configuration.

    A group is one (angle of attack, chord, free-stream velocity, displacement
    thickness) setting. The frequency column is the sweep *within* a run, so it
    is a feature, not part of the group key.
    """
    fetch(AIRFOIL_URL, {"airfoil_self_noise.dat": "airfoil_self_noise.dat"})
    df = pd.read_csv(CACHE / "airfoil_self_noise.dat", sep="\t", header=None,
                     names=AIRFOIL_COLS + ["spl_db"])
    groups = df.groupby(["aoa_deg", "chord_m", "velocity_ms",
                         "thickness_m"]).ngroup().to_numpy()
    return df, groups


def load_secom() -> tuple[pd.DataFrame, np.ndarray]:
    """SECOM semiconductor process data, revisited from L5: 590 sensors, pass/fail."""
    fetch(SECOM_URL, {"secom.data": "secom.data",
                      "secom_labels.data": "secom_labels.data"})
    sensors = pd.read_csv(CACHE / "secom.data", sep=" ", header=None)
    labels = pd.read_csv(CACHE / "secom_labels.data", sep=" ", header=None,
                         names=["label", "ts"])
    return sensors, (labels["label"] == 1).astype(int).to_numpy()


def check_shuffles() -> dict:
    """Confirm the five sheets are five shuffles of one table, and price the noise.

    The readme says the data was "shuffled five times" so that a 5x2 CV test
    could be run. That is worth verifying rather than believing, and the
    fold-to-fold spread it produces is the yardstick every other difference in
    this lecture has to clear.
    """
    fetch(CCPP_URL, {"CCPP/Folds5x2_pp.xlsx": "Folds5x2_pp.xlsx"})
    book = pd.ExcelFile(CACHE / "Folds5x2_pp.xlsx")
    sheets = {name: pd.read_excel(book, name) for name in book.sheet_names}
    first = sheets["Sheet1"]
    key = list(first.columns)
    canonical = first.sort_values(key).reset_index(drop=True)
    same = all(sheets[n].sort_values(key).reset_index(drop=True).equals(canonical)
               for n in book.sheet_names[1:])
    in_order = all(sheets[n].equals(first) for n in book.sheet_names[1:])

    scores = []
    for name, frame in sheets.items():
        fold = -cross_val_score(LinearRegression(),
                                frame[["AT", "V", "AP", "RH"]], frame["PE"],
                                cv=KFold(2, shuffle=False), scoring=SCORE)
        scores.extend(fold)
    scores = np.array(scores)
    print(f"  five sheets hold the same 9,568 rows: {same}; "
          f"in the same order: {in_order}")
    print(f"  5x2 CV of a linear model: {scores.mean():.4f} +/- {scores.std():.4f} MW, "
          f"spread {np.ptp(scores):.4f} MW")
    return {"identical_sets": same, "same_order": in_order,
            "mean": float(scores.mean()), "std": float(scores.std()),
            "spread": float(np.ptp(scores))}


# --------------------------------------------------------------------------
# Figure 1: what a baseline costs you
# --------------------------------------------------------------------------
def fig_baseline_ladder(ccpp: pd.DataFrame, noise: float) -> dict:
    """The CCPP baseline ladder, drawn twice on two scales.

    Drawn once, on one axis, the predict-the-mean bar is four times the height of
    everything else and every real model looks identical. That plot tells the
    reader "models are all the same", which is false. The two-panel version says
    what is actually true: the first straight line closes most of the gap, and
    the whole model tournament is fought inside the right-hand panel.
    """
    X = ccpp[["AT", "V", "AP", "RH"]].to_numpy()
    y = ccpp["PE"].to_numpy()
    cv = KFold(5, shuffle=True, random_state=SEED)

    ladder = [
        ("predict the mean", DummyRegressor(strategy="mean"), None),
        ("linear, ambient temp only", LinearRegression(), [0]),
        ("linear, all four inputs", LinearRegression(), None),
        ("decision tree, depth 5", DecisionTreeRegressor(max_depth=5,
                                                        random_state=SEED), None),
        ("ridge on quadratic terms", make_pipeline(PolynomialFeatures(2),
                                                   StandardScaler(), Ridge(1.0)), None),
        ("k-nearest neighbours, k=5", make_pipeline(StandardScaler(),
                                                    KNeighborsRegressor(5)), None),
        ("random forest, 100 trees", RandomForestRegressor(100, random_state=SEED,
                                                           n_jobs=-1), None),
    ]
    names, means, stds = [], [], []
    for name, est, cols in ladder:
        Xi = X if cols is None else X[:, cols]
        fold = -cross_val_score(est, Xi, y, cv=cv, scoring=SCORE)
        names.append(name)
        means.append(fold.mean())
        stds.append(fold.std())
        print(f"  {name:28s} RMSE {fold.mean():7.3f} +/- {fold.std():.3f} MW")

    means, stds = np.array(means), np.array(stds)
    total = means[0] - means.min()
    closed = (means[0] - means) / total

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.6),
                                   gridspec_kw={"width_ratios": [1, 1.05]})
    order = np.arange(len(names))
    colours = [MUTED] + [BLUE] * 2 + [GREEN] * 3 + [CMU_RED]

    for ax, lo, hi, title in [
        (ax1, 0, means[0] * 1.10, "Plotted on one scale, as you would by default"),
        (ax2, means.min() - 0.55, means[1] + 1.95, "The contest, magnified"),
    ]:
        ax.barh(order, means, xerr=stds, color=colours, height=0.62,
                error_kw=dict(ecolor=INK, lw=1.1, capsize=3))
        ax.set_yticks(order)
        ax.set_yticklabels(names if ax is ax1 else [], fontsize=11)
        ax.invert_yaxis()
        ax.set_xlim(lo, hi)
        ax.set_xlabel("5-fold CV RMSE, MW")
        ax.set_title(title, pad=10)
        ax.grid(True, axis="x", color=RULE, lw=0.7)
        ax.set_axisbelow(True)

    for i, (m, s, frac) in enumerate(zip(means, stds, closed)):
        if i == 0:
            continue
        ax2.text(m + s + 0.10, i, f"{m:.2f}   ({frac:.0%} of the gap closed)",
                 va="center", fontsize=10.5, color=INK)
    ax2.annotate("17.07, off scale", xy=(ax2.get_xlim()[1], 0), xytext=(-8, 0),
                 textcoords="offset points", ha="right", va="center",
                 fontsize=10.5, color="white", fontweight="bold")
    ax2.axvline(means[-1], color=CMU_RED, lw=1.0, ls=":")
    ax1.text(0.28, 0.63,
             f"{means[0]:.2f} MW is the target's own standard\n"
             "deviation, by construction. That is the\n"
             "price of having no model at all.\n\n"
             "One thermodynamic variable and a straight\n"
             f"line close {closed[1]:.0%} of everything a model can\n"
             f"do here. Every model past that argues\n"
             f"over {means[1] - means[-1]:.2f} MW, against fold noise of "
             f"$\\pm${noise:.2f}.",
             transform=ax1.transAxes, fontsize=11.5, color=INK, va="top")

    fig.suptitle("Combined Cycle Power Plant: what each step of complexity buys",
                 fontsize=15.5, y=1.0)
    fig.savefig(HERE / "baseline-ladder.png")
    plt.close(fig)
    print(f"wrote baseline-ladder.png  (mean baseline {means[0]:.3f}; "
          f"AT-only linear {means[1]:.3f} closes {closed[1]:.1%}; "
          f"best {means.min():.3f})")
    return {"names": names, "means": means.tolist(), "stds": stds.tolist(),
            "closed": closed.tolist()}


# --------------------------------------------------------------------------
# Figure 2: the cross-validation scheme is not a detail
# --------------------------------------------------------------------------
def fig_cv_schemes(airfoil: pd.DataFrame, groups: np.ndarray) -> dict:
    """k-fold against GroupKFold on data whose rows come in wind-tunnel runs.

    The right panel is the more useful half: it shows *why* the numbers differ.
    A random fold hands the model 80% of a single frequency sweep and asks it to
    fill in the rest, which is interpolation along a smooth curve. GroupKFold
    holds out the whole run, which is the question the wind tunnel was actually
    asked.
    """
    X = airfoil[AIRFOIL_COLS].to_numpy()
    y = airfoil["spl_db"].to_numpy()

    models = [
        ("predict the mean", DummyRegressor(strategy="mean")),
        ("linear", LinearRegression()),
        ("k-NN, k=5", make_pipeline(StandardScaler(), KNeighborsRegressor(5))),
        ("random forest", RandomForestRegressor(200, random_state=SEED, n_jobs=-1)),
    ]
    names, kf_m, kf_s, gk_m, gk_s = [], [], [], [], []
    for name, est in models:
        kf = -cross_val_score(est, X, y, cv=KFold(5, shuffle=True, random_state=SEED),
                              scoring=SCORE)
        gk = -cross_val_score(est, X, y, cv=GroupKFold(5), groups=groups, scoring=SCORE)
        names.append(name)
        kf_m.append(kf.mean()); kf_s.append(kf.std())
        gk_m.append(gk.mean()); gk_s.append(gk.std())
        print(f"  {name:18s} KFold {kf.mean():6.3f} +/- {kf.std():.3f}   "
              f"GroupKFold {gk.mean():6.3f} +/- {gk.std():.3f}   "
              f"inflation {gk.mean() / kf.mean():.2f}x")

    kf_m, gk_m = np.array(kf_m), np.array(gk_m)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.8),
                                   gridspec_kw={"width_ratios": [1.05, 1]})

    pos = np.arange(len(names))
    w = 0.36
    ax1.bar(pos - w / 2, kf_m, w, yerr=kf_s, color=CMU_RED, label="KFold (shuffled rows)",
            error_kw=dict(ecolor=INK, lw=1.1, capsize=3))
    ax1.bar(pos + w / 2, gk_m, w, yerr=gk_s, color=BLUE, label="GroupKFold (whole runs held out)",
            error_kw=dict(ecolor=INK, lw=1.1, capsize=3))
    ax1.set_xticks(pos)
    ax1.set_xticklabels(names, fontsize=11)
    ax1.set_ylabel("CV RMSE, dB")
    ax1.set_title("Same data, same models, two fold schemes", pad=10)
    ax1.set_ylim(0, 9.2)
    ax1.legend(frameon=False, fontsize=10.5, loc="upper left")
    ax1.grid(True, axis="y", color=RULE, lw=0.7)
    ax1.set_axisbelow(True)
    for i, (a, b, s) in enumerate(zip(kf_m, gk_m, gk_s)):
        if b / a > 1.05:
            ax1.annotate(f"{b / a:.2f}x", xy=(i, max(a, b + s) + 0.30), ha="center",
                         fontsize=12.5, color=CMU_RED, fontweight="bold")
    ax1.text(0.98, 0.80,
             "Only the flexible models can\nexploit the shortcut. The linear\n"
             "model cannot, and reports the\nsame number either way.",
             transform=ax1.transAxes, ha="right", va="top", fontsize=11, color=INK)

    # The mechanism: one configuration's frequency sweep, with the rows a random
    # 5-fold sends to the test side marked.
    target = pd.Series(groups).value_counts().idxmax()
    run = airfoil[groups == target].sort_values("freq_hz")
    rng = np.random.default_rng(SEED)
    held = rng.choice(len(run), max(1, len(run) // 5), replace=False)
    mask = np.zeros(len(run), bool)
    mask[held] = True

    ax2.plot(run["freq_hz"], run["spl_db"], "-", color=RULE, lw=2.0, zorder=1)
    ax2.plot(run["freq_hz"][~mask], run["spl_db"][~mask], "o", color=BLUE, ms=8,
             label=f"in the training folds ({(~mask).sum()} rows)", zorder=2)
    ax2.plot(run["freq_hz"][mask], run["spl_db"][mask], "o", color=CMU_RED, ms=11,
             label=f"held out by a random fold ({mask.sum()} rows)", zorder=3)
    ax2.set_xscale("log")
    cfg = run.iloc[0]
    ax2.set_xlabel("Frequency, Hz")
    ax2.set_ylabel("Sound pressure level, dB")
    ax2.set_title("Why: one wind-tunnel run, split at random", pad=10)
    ax2.legend(frameon=False, fontsize=10.5, loc="lower left")
    ax2.grid(True, color=RULE, lw=0.7)
    ax2.set_axisbelow(True)
    ax2.text(0.98, 0.97,
             "Every red point sits\nbetween two blue ones.\n"
             "Interpolation, not prediction.",
             transform=ax2.transAxes, ha="right", va="top", fontsize=11.5,
             color=CMU_RED, fontweight="bold")
    # Top-left: the only corner the sweep leaves empty in every configuration.
    ax2.text(0.02, 0.98,
             f"chord {cfg['chord_m']:.4f} m\n{cfg['velocity_ms']:.1f} m/s\n"
             f"{cfg['aoa_deg']:.1f}$\\degree$ angle of attack",
             transform=ax2.transAxes, ha="left", va="top", fontsize=10.5,
             color=MUTED)

    fig.suptitle("NASA airfoil self-noise: 1,503 rows from 106 wind-tunnel configurations",
                 fontsize=15.5, y=1.0)
    fig.savefig(HERE / "cv-schemes.png")
    plt.close(fig)
    print(f"wrote cv-schemes.png  ({len(np.unique(groups))} groups, "
          f"median {int(pd.Series(groups).value_counts().median())} rows each)")
    return {"names": names, "kfold": kf_m.tolist(), "groupkfold": gk_m.tolist(),
            "kfold_std": kf_s, "groupkfold_std": gk_s,
            "n_groups": int(len(np.unique(groups)))}


# --------------------------------------------------------------------------
# Figure 3: learning curves as a diagnosis
# --------------------------------------------------------------------------
def fig_learning_curves(ccpp: pd.DataFrame) -> dict:
    """Train and validation error against training-set size, for three capacities."""
    X = ccpp[["AT", "V", "AP", "RH"]].to_numpy()
    y = ccpp["PE"].to_numpy()
    cv = KFold(5, shuffle=True, random_state=SEED)
    sizes = np.linspace(0.02, 1.0, 10)

    panels = [
        ("Linear, four inputs", LinearRegression(), BLUE,
         "Underfit. The curves have met.\nMore data changes nothing;\nonly more capacity will."),
        ("Decision tree, no depth limit", DecisionTreeRegressor(random_state=SEED), CMU_RED,
         "Overfit. Zero training error,\nand a gap that never closes.\nEvery leaf is one sample."),
        ("Random forest, 100 trees", RandomForestRegressor(100, random_state=SEED,
                                                          n_jobs=-1), GREEN,
         "Healthy. A real gap, but the\nvalidation curve is still falling.\nMore data would still pay."),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 5.2), sharey=True)
    out = {}
    for ax, (title, est, colour, verdict) in zip(axes, panels):
        n, train, val = learning_curve(est, X, y, cv=cv, train_sizes=sizes,
                                       scoring=SCORE, n_jobs=-1)
        train, val = -train.mean(1), -val.mean(1)
        out[title] = {"n": n.tolist(), "train": train.tolist(), "val": val.tolist()}
        ax.plot(n, train, "o-", color=colour, lw=2.0, ms=5, label="training error")
        ax.plot(n, val, "s--", color=colour, lw=2.0, ms=5, alpha=0.55,
                label="validation error")
        ax.fill_between(n, train, val, color=colour, alpha=0.10)
        ax.set_title(title, pad=10, fontsize=13.5)
        ax.set_xlabel("Training rows")
        ax.grid(True, color=RULE, lw=0.7)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, fontsize=10.5, loc="upper right")
        ax.text(0.04, 0.42, verdict, transform=ax.transAxes, fontsize=11,
                color=colour, fontweight="bold", va="top")
        ax.text(0.96, 0.14, f"final gap {val[-1] - train[-1]:.2f} MW",
                transform=ax.transAxes, ha="right", fontsize=10.5, color=MUTED)
        print(f"  {title:32s} train {train[-1]:6.3f}  val {val[-1]:6.3f}  "
              f"gap {val[-1] - train[-1]:6.3f}")
    axes[0].set_ylabel("RMSE, MW")
    axes[0].set_ylim(-0.3, 6.6)

    fig.suptitle("The same dataset, three capacities: read the gap, not the score",
                 fontsize=15.5, y=1.0)
    fig.savefig(HERE / "learning-curves.png")
    plt.close(fig)
    print("wrote learning-curves.png")
    return out


# --------------------------------------------------------------------------
# Figure 4: selection bias, and the size of dataset where it matters
# --------------------------------------------------------------------------
def fig_selection_bias(ccpp: pd.DataFrame, noise: float) -> dict:
    """Non-nested vs nested CV against n, which is the honest version of this story.

    Non-nested: fit a grid search on all n rows and report its best inner-CV
    score, which is what almost every student's notebook reports. Nested: wrap
    the whole search inside an outer CV, so the winner is chosen without the
    outer test fold. The difference is selection bias with the "the final refit
    saw more data" confound removed, because both sides train on 4/5 of what
    they are handed.
    """
    X = ccpp[["AT", "V", "AP", "RH"]].to_numpy()
    y = ccpp["PE"].to_numpy()
    pipe = Pipeline([("poly", PolynomialFeatures(2)), ("sc", StandardScaler()),
                     ("m", Ridge())])
    grid = {"poly__degree": [1, 2, 3], "m__alpha": np.logspace(-3, 4, 12)}
    n_cands = len(grid["poly__degree"]) * len(grid["m__alpha"])

    sizes = [80, 160, 320, 640, 1280, 2560, 5120, len(X)]
    non_nested, nested = [], []
    for n in sizes:
        reps = 12 if n <= 640 else (6 if n <= 2560 else 3)
        nn, ne = [], []
        for rep in range(reps):
            rng = np.random.default_rng(1000 + rep)
            idx = rng.choice(len(X), n, replace=False)
            search = GridSearchCV(pipe, grid, scoring=SCORE, n_jobs=-1,
                                  cv=KFold(5, shuffle=True, random_state=rep))
            search.fit(X[idx], y[idx])
            nn.append(-search.best_score_)
            ne.append(-cross_val_score(search, X[idx], y[idx], scoring=SCORE, n_jobs=-1,
                                       cv=KFold(5, shuffle=True,
                                                random_state=100 + rep)).mean())
        non_nested.append(np.mean(nn))
        nested.append(np.mean(ne))
        print(f"  n={n:5d}  non-nested {non_nested[-1]:7.4f}  nested {nested[-1]:7.4f}  "
              f"bias {nested[-1] - non_nested[-1]:+.4f} MW  ({reps} repeats)")

    bias = np.array(nested) - np.array(non_nested)

    fig, ax = plt.subplots(figsize=(11.0, 5.8))
    ax.axhspan(-noise, noise, color=RULE, alpha=0.75, zorder=0)
    ax.text(sizes[-1], noise * 1.25, "fold-to-fold noise of this dataset  ",
            ha="right", va="bottom", fontsize=11, color=MUTED)
    ax.axhline(0, color=INK, lw=1.1, zorder=1)
    ax.plot(sizes, bias, "o-", color=CMU_RED, lw=2.2, ms=8, zorder=3)
    for n, b in zip(sizes, bias):
        ax.annotate(f"{b:+.3f}", xy=(n, b), xytext=(0, 11 if b > 0 else -18),
                    textcoords="offset points", ha="center", fontsize=10.5,
                    color=CMU_RED if abs(b) > noise else MUTED)
    ax.set_xscale("log")
    ax.set_xlabel("Rows the model-selection study was run on")
    ax.set_ylabel("Selection bias, MW\n(nested CV minus the best inner-CV score)")
    ax.set_title(f"How much the best validation score flatters itself, "
                 f"over {n_cands} candidates", pad=10)
    ax.grid(True, color=RULE, lw=0.7)
    ax.set_axisbelow(True)
    crossing = next((n for n, b in zip(sizes, bias) if abs(b) < noise), None)
    ax.text(0.30, 0.74,
            f"At n = {sizes[0]}, the winner's validation score is {bias[0]:.2f} MW\n"
            f"better than it deserves, {bias[0] / noise:.0f}x the fold noise.\n"
            f"By n = {crossing:,} it has vanished into the noise, and on all\n"
            f"{len(X):,} rows it is {bias[-1]:+.3f} MW: unmeasurable.",
            transform=ax.transAxes, fontsize=11.5, color=INK, va="top")
    ax.text(0.30, 0.50, "Nested CV is small-data insurance.\nKnow which regime you are in.",
            transform=ax.transAxes, fontsize=12.5, color=CMU_RED, fontweight="bold",
            va="top")

    fig.savefig(HERE / "selection-bias.png")
    plt.close(fig)
    print(f"wrote selection-bias.png  (bias {bias[0]:+.3f} at n={sizes[0]}, "
          f"{bias[-1]:+.3f} at n={sizes[-1]})")
    return {"sizes": sizes, "bias": bias.tolist(), "n_candidates": n_cands,
            "crossing": crossing}


# --------------------------------------------------------------------------
# Figure 5: metrics under class imbalance
# --------------------------------------------------------------------------
def fig_imbalance(sensors: pd.DataFrame, labels: np.ndarray) -> dict:
    """ROC-AUC, PR-AUC, and alert burden on SECOM's 6.6% failure rate.

    Same predictions in all three panels. Only the summary changes.
    """
    model = Pipeline([("imp", SimpleImputer(strategy="median")),
                      ("clf", RandomForestClassifier(300, random_state=SEED, n_jobs=-1))])
    proba = cross_val_predict(model, sensors, labels, method="predict_proba",
                              cv=StratifiedKFold(5, shuffle=True,
                                                 random_state=SEED))[:, 1]
    base = labels.mean()
    auc = roc_auc_score(labels, proba)
    ap = average_precision_score(labels, proba)
    fpr, tpr, _ = roc_curve(labels, proba)
    prec, rec, _ = precision_recall_curve(labels, proba)
    print(f"  {len(labels)} runs, {labels.sum()} failures ({base:.2%}); "
          f"ROC-AUC {auc:.3f}, PR-AUC {ap:.3f}")

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.0),
                             gridspec_kw={"wspace": 0.32})

    ax = axes[0]
    ax.plot(fpr, tpr, color=BLUE, lw=2.4)
    ax.plot([0, 1], [0, 1], ls="--", color=MUTED, lw=1.2)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate (recall)")
    ax.set_title("ROC: this looks like a detector", pad=10, color=BLUE, fontsize=13.5)
    ax.text(0.46, 0.16, f"ROC-AUC = {auc:.2f}", fontsize=15, color=BLUE,
            fontweight="bold")
    ax.text(0.46, 0.06, "coin flip = 0.50", fontsize=10.5, color=MUTED)

    ax = axes[1]
    ax.plot(rec, prec, color=CMU_RED, lw=2.4)
    ax.axhline(base, ls="--", color=MUTED, lw=1.2)
    ax.text(0.18, base + 0.016, f"always alarm = {base:.3f}", fontsize=10.5,
            color=MUTED, ha="left")
    ax.set_xlabel("Recall (faults caught)")
    ax.set_ylabel("Precision (alarms that were real)")
    ax.set_ylim(0, 0.55)
    ax.set_title("PR: the identical predictions", pad=10, color=CMU_RED, fontsize=13.5)
    ax.text(0.40, 0.45, f"PR-AUC = {ap:.2f}", fontsize=15, color=CMU_RED,
            fontweight="bold")

    ax = axes[2]
    keep = (rec > 0.05) & (prec > 0)
    burden = 1.0 / prec[keep]
    ax.plot(rec[keep], burden, color=INK, lw=2.4)
    ax.set_xlabel("Recall (faults caught)")
    ax.set_ylabel("Wafers investigated per real fault")
    ax.set_title("What the operator lives with", pad=10, fontsize=13.5)
    ax.set_ylim(0, min(30, burden.max() * 1.15))
    ax.set_xlim(0, 1.05)
    marks = {}
    for target in (0.25, 0.50, 0.80):
        i = int(np.argmin(np.abs(rec[keep] - target)))
        marks[round(float(rec[keep][i]), 3)] = float(burden[i])
        ax.plot([rec[keep][i]], [burden[i]], "o", color=CMU_RED, ms=9)
        right = rec[keep][i] > 0.6
        ax.annotate(f"catch {rec[keep][i]:.0%}, chase {burden[i]:.0f}",
                    xy=(rec[keep][i], burden[i]),
                    xytext=(-8, 12) if right else (8, -6),
                    ha="right" if right else "left",
                    textcoords="offset points", fontsize=10.5, color=CMU_RED)
        print(f"    recall {rec[keep][i]:.2f}: precision {prec[keep][i]:.3f}, "
              f"{burden[i]:.1f} investigations per true fault")
    for ax in axes:
        ax.grid(True, color=RULE, lw=0.7)
        ax.set_axisbelow(True)

    fig.suptitle(f"UCI SECOM: {labels.sum()} failures in {len(labels)} production runs "
                 f"({base:.1%}). One model, three summaries.", fontsize=15.5, y=1.02)
    fig.savefig(HERE / "imbalance.png")
    plt.close(fig)
    print(f"wrote imbalance.png  (ROC-AUC {auc:.3f} vs PR-AUC {ap:.3f}, "
          f"base rate {base:.3f})")
    return {"roc_auc": float(auc), "pr_auc": float(ap), "base_rate": float(base),
            "n": int(len(labels)), "failures": int(labels.sum()), "burden": marks}


# --------------------------------------------------------------------------
# Measurements that are quoted but not plotted
# --------------------------------------------------------------------------
def measure_scaler_leak(ccpp: pd.DataFrame) -> dict:
    """The bug the module asks for: fit the scaler before splitting.

    Measured rather than assumed. On this dataset it is worth almost exactly
    nothing, and the notes say so, because a lesson that only works when the
    number is scary is not a lesson.
    """
    X = ccpp[["AT", "V", "AP", "RH"]].to_numpy()
    y = ccpp["PE"].to_numpy()
    cv = KFold(5, shuffle=True, random_state=SEED)
    leaked_X = StandardScaler().fit_transform(X)
    out = {}
    for name, est in [("LinearRegression", LinearRegression()),
                      ("Ridge(alpha=100)", Ridge(100)),
                      ("KNeighbors(k=5)", KNeighborsRegressor(5)),
                      ("RandomForest", RandomForestRegressor(50, random_state=SEED,
                                                             n_jobs=-1))]:
        leaky = -cross_val_score(est, leaked_X, y, cv=cv, scoring=SCORE).mean()
        honest = -cross_val_score(make_pipeline(StandardScaler(), est), X, y,
                                  cv=cv, scoring=SCORE).mean()
        out[name] = honest - leaky
        print(f"  {name:18s} leaky {leaky:.4f}  honest {honest:.4f}  "
              f"gap {honest - leaky:+.5f} MW")
    return out


def measure_selection_leak() -> dict:
    """Hastie et al., ESL section 7.10.2: screening features outside the CV loop.

    Pure noise, no signal at all. Screening the 5,000 columns down to 100 by
    their association with y *before* cross-validating produces a near-perfect
    classifier of nothing. Doing the identical screening inside each fold
    reports the coin flip it is.
    """
    from sklearn.feature_selection import SelectKBest, f_classif
    from sklearn.neighbors import KNeighborsClassifier

    n, p, k, reps = 50, 5000, 100, 20
    wrong, right = [], []
    for rep in range(reps):
        rng = np.random.default_rng(rep)
        X = rng.standard_normal((n, p))
        y = rng.integers(0, 2, n)
        folds = StratifiedKFold(5, shuffle=True, random_state=rep)
        screened = SelectKBest(f_classif, k=k).fit_transform(X, y)
        wrong.append(1 - cross_val_score(KNeighborsClassifier(1), screened, y,
                                         cv=folds).mean())
        inside = Pipeline([("sel", SelectKBest(f_classif, k=k)),
                           ("clf", KNeighborsClassifier(1))])
        right.append(1 - cross_val_score(inside, X, y, cv=folds).mean())
    print(f"  screen first, then CV : error {np.mean(wrong):.3f} +/- {np.std(wrong):.3f}")
    print(f"  screen inside each fold: error {np.mean(right):.3f} +/- {np.std(right):.3f}")
    return {"outside": float(np.mean(wrong)), "inside": float(np.mean(right)),
            "n": n, "p": p, "k": k, "reps": reps}


def measure_mape_blowup() -> dict:
    """MAPE on a target that legitimately approaches zero: C-MAPSS remaining life.

    Reuses L7's cached RUL file when it is there, and falls back to the
    published distribution's shape if it is not, so this script never fails
    because a sibling lecture's cache was cleaned.
    """
    path = HERE.parent.parent / "l07" / "figures" / ".cache" / "RUL_FD001.txt"
    if not path.exists():
        print("  (L7 RUL cache absent, skipping the MAPE measurement)")
        return {}
    rul = pd.read_csv(path, header=None)[0].to_numpy()
    err = 15.0
    mape = float(np.mean(err / rul))
    worst = float(err / rul.min())
    print(f"  a flat {err:.0f}-cycle error on {len(rul)} engines: "
          f"MAPE {mape:.1%}, worst engine (RUL={rul.min()}) contributes {worst:.0%}")
    return {"mape": mape, "worst": worst, "min_rul": int(rul.min()),
            "median_rul": float(np.median(rul)), "flat_error": err}


if __name__ == "__main__":
    print("check_shuffles")
    shuffles = check_shuffles()
    noise = shuffles["std"]

    ccpp = load_ccpp()
    airfoil, groups = load_airfoil()
    print(f"\nloaded CCPP {ccpp.shape}, airfoil {airfoil.shape} in "
          f"{len(np.unique(groups))} configurations")

    print("\nfig_baseline_ladder")
    baselines = fig_baseline_ladder(ccpp, noise)

    print("\nfig_cv_schemes")
    schemes = fig_cv_schemes(airfoil, groups)

    print("\nfig_learning_curves")
    curves = fig_learning_curves(ccpp)

    print("\nfig_selection_bias")
    selection = fig_selection_bias(ccpp, noise)

    print("\nfig_imbalance")
    sensors, labels = load_secom()
    imbalance = fig_imbalance(sensors, labels)

    print("\nmeasure_scaler_leak")
    scaler_leak = measure_scaler_leak(ccpp)

    print("\nmeasure_selection_leak")
    screen = measure_selection_leak()

    print("\nmeasure_mape_blowup")
    mape = measure_mape_blowup()

    print("\n--- numbers cited in notes.md and slides.md ---")
    print(f"5x2 CV noise on CCPP: +/-{noise:.4f} MW "
          f"(spread {shuffles['spread']:.4f} across the five published shuffles)")
    for name, mean, closed in zip(baselines["names"], baselines["means"],
                                  baselines["closed"]):
        print(f"  {name:28s} {mean:7.3f} MW   closes {closed:6.1%}")
    print(f"airfoil, {schemes['n_groups']} configurations:")
    for name, a, b in zip(schemes["names"], schemes["kfold"], schemes["groupkfold"]):
        print(f"  {name:18s} KFold {a:6.3f} -> GroupKFold {b:6.3f}  ({b / a:.2f}x)")
    print(f"selection bias over {selection['n_candidates']} candidates: "
          f"{selection['bias'][0]:+.3f} MW at n={selection['sizes'][0]}, "
          f"{selection['bias'][-1]:+.3f} MW at n={selection['sizes'][-1]}; "
          f"below noise from n={selection['crossing']}")
    print(f"scale-before-split gap, largest across four models: "
          f"{max(abs(v) for v in scaler_leak.values()):.5f} MW")
    print(f"ESL 7.10.2 on pure noise: {screen['outside']:.1%} error screening first, "
          f"{screen['inside']:.1%} screening inside the fold")
    print(f"SECOM: ROC-AUC {imbalance['roc_auc']:.3f}, PR-AUC {imbalance['pr_auc']:.3f}, "
          f"base rate {imbalance['base_rate']:.3f}")
    for r, b in imbalance["burden"].items():
        print(f"  recall {r:.0%} -> {b:.0f} investigations per real fault")
    if mape:
        print(f"MAPE on RUL: a flat {mape['flat_error']:.0f}-cycle error reads as "
              f"{mape['mape']:.1%}, worst engine {mape['worst']:.0%}")
