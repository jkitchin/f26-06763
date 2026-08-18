#!/usr/bin/env python3
"""Generate the L12 figures for architectures on engineering data.

Run with the course env:
    /opt/anaconda3/envs/sys_tools/bin/python make_figures.py

L12 matches architecture to the structure of the input. Two figures:

    architecture_map.png   which architecture fits which input structure:
                           a vector -> MLP, a field/image -> 2D-CNN, a sensor
                           sequence -> 1D-CNN or RNN. Original schematic.
    cnn_vs_baseline.png    a real comparison on NASA C-MAPSS turbofan RUL: a
                           1D-CNN over sliding sensor windows against a tabular
                           gradient-boosting baseline on hand-crafted window
                           features, both evaluated on held-out engines
                           (GroupKFold-by-unit), plus the CNN's loss curve.

The comparison is run under a grouped split, because windows from one engine in
both train and test would leak (the L8 lesson). Numbers printed here are what the
notes and slides cite. C-MAPSS FD001 is cached under .cache/ (gitignored).
"""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import root_mean_squared_error
from sklearn.model_selection import GroupKFold

import torch
import torch.nn as nn

warnings.filterwarnings("ignore")
torch.manual_seed(0)
np.random.seed(0)

HERE = Path(__file__).parent
CACHE = HERE / ".cache" / "CMAPSS"
COLS = (["unit", "cycle"] + [f"setting{i+1}" for i in range(3)]
        + [f"sensor{i+1}" for i in range(21)])
WINDOW = 30
RUL_CAP = 125          # piecewise-linear RUL: constant, then linear
SEED = 0

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#1a7f37"

plt.rcParams.update({
    "font.size": 13, "axes.labelsize": 13, "axes.titlesize": 14,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "figure.dpi": 160, "savefig.bbox": "tight",
})


def load_train() -> pd.DataFrame:
    df = pd.read_csv(CACHE / "train_FD001.txt", sep=r"\s+", header=None, names=COLS)
    df[["unit", "cycle"]] = df[["unit", "cycle"]].astype(int)
    return df.sort_values(["unit", "cycle"]).reset_index(drop=True)


def make_windows(df, live, mu, sd):
    """Sliding windows of length WINDOW per engine, with piecewise-linear RUL.

    Returns X (n, channels, time), y (n,), groups (n,) = engine id.
    """
    Xs, ys, gs = [], [], []
    for unit, g in df.groupby("unit"):
        arr = ((g[live].to_numpy() - mu) / sd).astype(np.float32)
        life = g["cycle"].max()
        cyc = g["cycle"].to_numpy()
        for end in range(WINDOW, len(g) + 1):
            Xs.append(arr[end - WINDOW:end].T)                  # (channels, time)
            rul = min(life - cyc[end - 1], RUL_CAP)
            ys.append(float(rul))
            gs.append(unit)
    return np.stack(Xs), np.array(ys, dtype=np.float32), np.array(gs)


class TinyCNN(nn.Module):
    """A small 1D-CNN over a sensor window: conv over time, pool, regress RUL."""
    def __init__(self, channels):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(channels, 32, 5, padding=2), nn.ReLU(),
            nn.Conv1d(32, 32, 5, padding=2), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(32, 32), nn.ReLU(), nn.Dropout(0.2), nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def train_cnn(Xtr, ytr, Xva, yva, epochs=25):
    dev = "cpu"                     # debug and run on CPU: faster here than MPS
    model = TinyCNN(Xtr.shape[1]).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.MSELoss()
    Xtr_t = torch.tensor(Xtr); ytr_t = torch.tensor(ytr)
    Xva_t = torch.tensor(Xva); yva_t = torch.tensor(yva)
    n = len(Xtr_t); bs = 256
    tr_curve, va_curve = [], []
    for _ in range(epochs):
        model.train()
        perm = torch.randperm(n)
        for i in range(0, n, bs):
            idx = perm[i:i + bs]
            opt.zero_grad()
            loss = lossf(model(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            tr_curve.append(float(torch.sqrt(lossf(model(Xtr_t), ytr_t))))
            va_curve.append(float(torch.sqrt(lossf(model(Xva_t), yva_t))))
    return model, tr_curve, va_curve


def window_features(X):
    """Hand-crafted per-window summary features for the tabular baseline."""
    return np.concatenate([X.mean(axis=2), X.std(axis=2), X[:, :, -1]], axis=1)


def fig_architecture_map() -> None:
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.axis("off")
    rows = [
        ("Vector / tabular", "mix proportions, ambient readings", "MLP", BLUE),
        ("Field / image", "temperature or stress map from simulation", "2D-CNN", GREEN),
        ("Sequence", "multivariate sensor time series", "1D-CNN or RNN", CMU_RED),
    ]
    for i, (structure, example, arch, color) in enumerate(rows):
        y = 2 - i
        ax.add_patch(mpatches.FancyBboxPatch((0.2, y + 0.12), 3.0, 0.72,
                     boxstyle="round,pad=0.02", facecolor="#f6f6f7", edgecolor=color, lw=2))
        ax.text(1.7, y + 0.62, structure, ha="center", va="center", fontsize=13, fontweight="bold")
        ax.text(1.7, y + 0.32, example, ha="center", va="center", fontsize=9.5, color=MUTED)
        ax.annotate("", xy=(4.7, y + 0.48), xytext=(3.3, y + 0.48),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=2))
        ax.add_patch(mpatches.FancyBboxPatch((4.8, y + 0.12), 2.6, 0.72,
                     boxstyle="round,pad=0.02", facecolor=color, edgecolor="none", alpha=0.9))
        ax.text(6.1, y + 0.48, arch, ha="center", va="center", fontsize=13,
                fontweight="bold", color="white")
    ax.text(3.7, 3.15, "match the architecture to the structure of the input",
            ha="center", fontsize=13, style="italic", color=INK)
    ax.set_xlim(0, 7.6); ax.set_ylim(0, 3.4)
    fig.savefig(HERE / "architecture_map.png")
    plt.close(fig)
    print("wrote architecture_map.png")


def fig_cnn_vs_baseline(df) -> dict:
    live = [c for c in df.columns if c.startswith(("sensor", "setting"))
            and df[c].nunique() > 1]
    mu = df[live].mean().to_numpy(); sd = df[live].std().replace(0, 1).to_numpy()
    X, y, groups = make_windows(df, live, mu, sd)

    Xf = window_features(X)
    print(f"{X.shape[0]} windows, {X.shape[1]} channels x {X.shape[2]} cycles; "
          f"{len(set(groups))} engines")

    # Honest comparison: GroupKFold by engine, several folds, so the winner is not
    # a single-run accident (the module's insistence: one run is not evidence).
    gkf = GroupKFold(n_splits=4)
    cnn_rmses, base_rmses = [], []
    curve0 = None
    for fold, (tr, va) in enumerate(gkf.split(X, y, groups)):
        torch.manual_seed(fold)
        model, tr_c, va_c = train_cnn(X[tr], y[tr], X[va], y[va])
        with torch.no_grad():
            cnn_rmses.append(float(torch.sqrt(nn.MSELoss()(
                model(torch.tensor(X[va])), torch.tensor(y[va])))))
        base = HistGradientBoostingRegressor(random_state=SEED).fit(Xf[tr], y[tr])
        base_rmses.append(root_mean_squared_error(y[va], base.predict(Xf[va])))
        if fold == 0:
            curve0 = (tr_c, va_c)
    cnn_rmses, base_rmses = np.array(cnn_rmses), np.array(base_rmses)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.3),
                                 gridspec_kw={"width_ratios": [1.4, 1]})
    ep = range(1, len(curve0[0]) + 1)
    a1.plot(ep, curve0[0], color=BLUE, lw=2, label="train")
    a1.plot(ep, curve0[1], color=CMU_RED, lw=2, label="held-out engines")
    a1.set_xlabel("epoch"); a1.set_ylabel("RUL RMSE, cycles")
    a1.set_title("1D-CNN training curve (one fold)", fontsize=13)
    a1.legend(frameon=False)

    means = [cnn_rmses.mean(), base_rmses.mean()]
    errs = [cnn_rmses.std(), base_rmses.std()]
    bars = a2.bar(["1D-CNN\n(raw windows)", "gradient boosting\n(window features)"],
                  means, yerr=errs, capsize=6, color=[CMU_RED, MUTED], width=0.55)
    for b, m in zip(bars, means):
        a2.text(b.get_x() + b.get_width() / 2, m, f"{m:.1f}",
                ha="center", va="bottom", fontsize=12, fontweight="bold")
    a2.set_ylabel("RUL RMSE, cycles")
    a2.set_ylim(0, max(means) * 1.3)
    a2.set_title(f"{gkf.get_n_splits()}-fold GroupKFold by engine", fontsize=13)
    fig.suptitle("A sequence model on raw windows vs a tabular baseline",
                 fontsize=14, y=1.02)
    fig.savefig(HERE / "cnn_vs_baseline.png")
    plt.close(fig)
    print(f"wrote cnn_vs_baseline.png  (1D-CNN {cnn_rmses.mean():.2f}+/-{cnn_rmses.std():.2f}, "
          f"baseline {base_rmses.mean():.2f}+/-{base_rmses.std():.2f} cycles RMSE)")
    return {"cnn": float(cnn_rmses.mean()), "cnn_std": float(cnn_rmses.std()),
            "baseline": float(base_rmses.mean()), "baseline_std": float(base_rmses.std())}


if __name__ == "__main__":
    df = load_train()
    print(f"loaded C-MAPSS FD001: {len(df):,} rows, {df.unit.nunique()} engines")
    fig_architecture_map()
    fig_cnn_vs_baseline(df)
