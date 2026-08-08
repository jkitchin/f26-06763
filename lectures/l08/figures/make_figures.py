#!/usr/bin/env python3
"""Generate the L8 figures from the NASA C-MAPSS FD001 turbofan data.

Run with the course env:
    /opt/anaconda3/envs/sys_tools/bin/python make_figures.py

L8 is about splits, leakage, versioning, and data-centric iteration. The two
figures are the payoff of the whole Data Systems arc, computed rather than
asserted:

    leakage.png   the same model and features scored two ways: a random
                  row-level split (which leaks, because adjacent cycles of one
                  engine land in both train and test) versus a per-unit
                  GroupKFold split (honest). The gap is the illusion.
    splits.png    a schematic of the two splits over a handful of engines,
                  showing an engine straddling train and test under a random
                  split and whole engines held out under a grouped split.

The leakage figure runs a RandomForest under both splits and prints the RMSEs
the notes and slides cite. C-MAPSS FD001 is fetched once and cached under
.cache/ (gitignored); do not commit it.

Loader (URL, columns, nested-zip handling) is the same one L7's demo uses.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, GroupKFold, cross_val_score

HERE = Path(__file__).parent
CACHE = HERE / ".cache" / "CMAPSS"
URL = ("https://phm-datasets.s3.amazonaws.com/NASA/"
       "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip")
NEEDED = ["train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt", "readme.txt"]

N_SETTINGS, N_SENSORS = 3, 21
COLUMNS = (["unit", "cycle"]
           + [f"setting{i + 1}" for i in range(N_SETTINGS)]
           + [f"sensor{i + 1}" for i in range(N_SENSORS)])

RUL_CAP = 125           # standard C-MAPSS clip; a modeling choice, see L7
WINDOW = 5
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


def load_train() -> pd.DataFrame:
    """Fetch (once) and parse C-MAPSS FD001 training data. Same loader as L7."""
    CACHE.mkdir(parents=True, exist_ok=True)
    if not all((CACHE / f).exists() for f in NEEDED):
        print("downloading", URL)
        with urllib.request.urlopen(URL) as r:
            payload = r.read()
        outer = zipfile.ZipFile(io.BytesIO(payload))
        inner_name = next(n for n in outer.namelist() if n.lower().endswith(".zip"))
        inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
        for name in NEEDED:
            (CACHE / name).write_bytes(inner.read(name))
        print(f"cached {len(NEEDED)} files in {CACHE}/")
    df = pd.read_csv(CACHE / "train_FD001.txt", sep=r"\s+", header=None, names=COLUMNS)
    df[["unit", "cycle"]] = df[["unit", "cycle"]].astype(int)
    return df


def build_features(df: pd.DataFrame):
    """Per-unit features and a clipped RUL target. Returns X, y, groups.

    Features are deliberately ordinary (raw non-constant sensors plus per-unit
    rolling mean and std). The point of L8 is the split, not the features, so
    the same X, y, and groups feed both experiments unchanged.
    """
    df = df.sort_values(["unit", "cycle"]).reset_index(drop=True)

    # drop channels that never vary (six are constant in FD001)
    sensor_cols = [c for c in df.columns if c.startswith("sensor")]
    live = [c for c in sensor_cols if df[c].nunique() > 1]

    g = df.groupby("unit", group_keys=False)
    feats = {"cycle": df["cycle"]}
    for c in live:
        feats[c] = df[c]
        feats[f"{c}_rmean"] = g[c].transform(lambda s: s.rolling(WINDOW, min_periods=1).mean())
        feats[f"{c}_rstd"] = g[c].transform(
            lambda s: s.rolling(WINDOW, min_periods=1).std()).fillna(0.0)
    X = pd.DataFrame(feats)

    life = g["cycle"].transform("max")
    y = (life - df["cycle"]).clip(upper=RUL_CAP)
    groups = df["unit"].to_numpy()
    return X, y.to_numpy(), groups, len(live)


def leak_rmse(X, y, groups) -> dict:
    """RMSE under a random row split versus a per-unit grouped split.

    Same model, same features, same number of folds. Only the split differs.
    The random split leaks: adjacent cycles of one engine are near-duplicates,
    so a shuffled row split scatters an engine across train and test.
    """
    model = RandomForestRegressor(n_estimators=100, n_jobs=-1, random_state=SEED)
    scorer = "neg_root_mean_squared_error"

    kf = KFold(n_splits=5, shuffle=True, random_state=SEED)
    rmse_random = -cross_val_score(model, X, y, cv=kf, scoring=scorer).mean()

    gkf = GroupKFold(n_splits=5)
    rmse_group = -cross_val_score(model, X, y, cv=gkf, groups=groups, scoring=scorer).mean()

    return {"random": float(rmse_random), "group": float(rmse_group)}


def fig_leakage(rmse: dict) -> None:
    labels = ["random row split\n(leaks)", "per-unit GroupKFold\n(honest)"]
    vals = [rmse["random"], rmse["group"]]
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    bars = ax.bar(labels, vals, color=[BLUE, CMU_RED], width=0.55)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}",
                ha="center", va="bottom", fontsize=13, fontweight="bold")
    ax.set_ylabel("RUL error, RMSE in cycles")
    ax.set_ylim(0, max(vals) * 1.25)
    ax.set_title("Same model, same features: only the split differs", pad=10)
    factor = rmse["group"] / rmse["random"]
    ax.text(0.5, -0.30,
            f"The random split reports {rmse['random']:.1f} cycles; the honest per-unit split "
            f"reports {rmse['group']:.1f}.\nThe leak makes the model look about {factor:.1f}x "
            "better than it is on a new engine.",
            transform=ax.transAxes, ha="center", va="top", fontsize=10.5, color=MUTED)
    fig.savefig(HERE / "leakage.png")
    plt.close(fig)
    print(f"wrote leakage.png  (random {rmse['random']:.2f}, group {rmse['group']:.2f}, "
          f"honest/leaky {factor:.2f}x)")


def fig_splits() -> None:
    """Schematic: random row split versus per-unit grouped split.

    Six engines, each a row of cycle cells. Left: cells colored train/test at
    random, so every engine has both. Right: whole engines are train or test.
    """
    rng = np.random.default_rng(SEED)
    engines = [18, 14, 20, 12, 16, 15]      # cycle counts, just for the picture
    test_units = {2, 4}                      # which engines are held out on the right

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    for ax, mode in zip(axes, ["random", "grouped"]):
        for i, n in enumerate(engines):
            for c in range(n):
                if mode == "random":
                    is_test = rng.random() < 0.25
                else:
                    is_test = i in test_units
                ax.add_patch(mpatches.Rectangle(
                    (c, i), 0.9, 0.8,
                    facecolor=(CMU_RED if is_test else BLUE),
                    edgecolor="white", linewidth=0.5))
        ax.set_xlim(0, max(engines))
        ax.set_ylim(-0.4, len(engines))
        ax.set_yticks([i + 0.4 for i in range(len(engines))])
        ax.set_yticklabels([f"engine {i + 1}" for i in range(len(engines))], fontsize=10)
        ax.set_xlabel("cycle")
        ax.set_xticks([])
        for s in ["top", "right", "left", "bottom"]:
            ax.spines[s].set_visible(False)
        title = ("Random row split: every engine is in both"
                 if mode == "random" else
                 "Per-unit split: whole engines held out")
        ax.set_title(title, fontsize=12.5, pad=8)

    handles = [mpatches.Patch(color=BLUE, label="train"),
               mpatches.Patch(color=CMU_RED, label="test")]
    fig.legend(handles=handles, frameon=False, ncol=2, loc="lower center",
               fontsize=11, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("The same fleet, split two ways", fontsize=15, y=1.02)
    fig.savefig(HERE / "splits.png")
    plt.close(fig)
    print("wrote splits.png")


if __name__ == "__main__":
    train = load_train()
    print(f"loaded {len(train):,} rows, {train['unit'].nunique()} engines")
    X, y, groups, n_live = build_features(train)
    print(f"features: {X.shape[1]} columns from {n_live} live sensors; target clipped at {RUL_CAP}")
    rmse = leak_rmse(X, y, groups)
    fig_leakage(rmse)
    fig_splits()
