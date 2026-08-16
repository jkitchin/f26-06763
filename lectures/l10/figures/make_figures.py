#!/usr/bin/env python3
"""Generate the L10 figures for experiment tracking and hyperparameter search.

Run with the course env:
    /opt/anaconda3/envs/sys_tools/bin/python make_figures.py

L10 is MLflow tracking plus hyperparameter search. Two figures, computed on the
UCI Combined Cycle Power Plant data (the same set L9 uses):

    grid_vs_random.png   why random search beats grid when few dimensions
                         matter (Bergstra and Bengio 2012), redrawn as original
                         artwork rather than copied.
    optuna_search.png    a real Optuna study: TPE versus random sampling, best
                         validation RMSE so far against trial number.

The selection-bias lesson (that the best validation score is an optimistic
estimate) is left to the prose, because on this large, easy dataset the effect is
genuinely tiny except at very small training sizes: the module measured it at
+0.19 MW at n=80 and -0.003 MW on all 9,568 rows, so a figure computed at full
size would show nothing and mislead. The notes cite those measured numbers.

The numbers printed here are the ones the notes and slides cite. CCPP is fetched
once and cached under .cache/ (gitignored); do not commit it.
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
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import KFold, cross_val_score, train_test_split

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)
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

plt.rcParams.update({
    "font.size": 13, "axes.labelsize": 13, "axes.titlesize": 15,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "figure.dpi": 160, "savefig.bbox": "tight",
})


def load_ccpp():
    """Fetch (once) and parse CCPP Sheet1. Same source as L9."""
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


if __name__ == "__main__":
    X, y = load_ccpp()
    print(f"loaded CCPP: {X.shape[0]} rows, {X.shape[1]} features -> PE (MW)")
    Xtr, _, ytr, _ = train_test_split(X, y, test_size=0.2, random_state=SEED)
    fig_grid_vs_random()
    fig_optuna_search(Xtr, ytr)
