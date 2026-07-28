#!/usr/bin/env python3
"""Generate the L7 figures from NASA's C-MAPSS turbofan degradation data.

Run with:
    uv run --with pandas,numpy,scikit-learn,matplotlib python make_figures.py

Every figure is measured from the real FD001 subset rather than copied from a
paper, for the licensing reason (this course site is public) and the pedagogical
one (a figure you can regenerate is a figure you can check).

Two of these figures changed what the lecture claims. The leakage figure was
drafted expecting the leaky pipeline to score visibly worse; it does not, for
`Ridge`, and the honest version of the plot is now a comparison across four
models showing that the gap depends entirely on which model you measure with,
and can even favour the leaky pipeline. And the sensor panel was drafted to show
"a few flat channels" and turned up four that are exactly constant plus several
more that are effectively so.

Outputs (committed alongside this script):
    sensor-degradation.png   which channels carry a degradation signal, and which are flat
    grouped-vs-not.png       what a rolling window does when you forget to group by unit
    leakage-by-model.png     one leak, four models, four different verdicts

The raw archive is cached in .cache/ and is gitignored; do not commit it.
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
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_squared_error
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
URL = ("https://phm-datasets.s3.amazonaws.com/NASA/"
       "6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip")

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

N_SETTINGS, N_SENSORS = 3, 21
COLUMNS = (["unit", "cycle"]
           + [f"setting{i + 1}" for i in range(N_SETTINGS)]
           + [f"sensor{i + 1}" for i in range(N_SENSORS)])
SENSORS = [f"sensor{i + 1}" for i in range(N_SENSORS)]
MAX_RUL = 125
WINDOW = 5


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Fetch (once) and parse FD001 train, test, and the true test RUL."""
    CACHE.mkdir(exist_ok=True)
    needed = ["train_FD001.txt", "test_FD001.txt", "RUL_FD001.txt"]
    if not all((CACHE / f).exists() for f in needed):
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as response:
            payload = response.read()
        outer = zipfile.ZipFile(io.BytesIO(payload))
        inner_name = next(n for n in outer.namelist() if n.lower().endswith(".zip"))
        inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))
        for name in needed:
            (CACHE / name).write_bytes(inner.read(name))

    def read(path):
        df = pd.read_csv(path, sep=r"\s+", header=None, names=COLUMNS)
        df[["unit", "cycle"]] = df[["unit", "cycle"]].astype(int)
        return df

    train = read(CACHE / "train_FD001.txt")
    test = read(CACHE / "test_FD001.txt")
    train["rul"] = (train.groupby("unit")["cycle"].transform("max")
                    - train["cycle"]).clip(upper=MAX_RUL)
    rul_true = pd.read_csv(CACHE / "RUL_FD001.txt", header=None, names=["rul"])["rul"]
    rul_true.index = np.arange(1, len(rul_true) + 1)
    return train, test, rul_true


def engineer(df, sensors, window=WINDOW):
    """Per-unit rolling/delta/rate features, selected by exact name."""
    df = df.sort_values(["unit", "cycle"]).copy()
    g = df.groupby("unit", group_keys=False)
    names = []
    for s in sensors:
        built = {
            f"{s}_roll_mean": lambda x: x.rolling(window, min_periods=1).mean(),
            f"{s}_roll_std": lambda x: x.rolling(window, min_periods=1).std().fillna(0),
            f"{s}_delta0": lambda x: x - x.iloc[0],
            f"{s}_roc": lambda x: x.diff().fillna(0),
        }
        for name, fn in built.items():
            df[name] = g[s].transform(fn)
        names.extend(built)
        names.append(s)
    return df, names


# --------------------------------------------------------------------------
# Figure 1: which channels actually carry a signal
# --------------------------------------------------------------------------
def fig_sensor_degradation(train: pd.DataFrame) -> dict:
    """Rank all 21 channels by |corr| with RUL, and show three trajectories.

    Constant channels are found with nunique(), not std() == 0. Six FD001
    channels hold a single value, but two of them (sensors 5 and 16) return a
    standard deviation of 5e-15 and 3e-18 rather than exactly zero, because the
    variance of a column of 14.62s is computed, not looked up. Testing std == 0
    silently misses them. See the note in notes.md; L5's "constant iff std is
    zero" shortcut needs a tolerance in floating point.
    """
    constant = [s for s in SENSORS if train[s].nunique(dropna=True) <= 1]
    fp_residue = {s: train[s].std() for s in constant if train[s].std() != 0}
    corr = train[SENSORS].corrwith(train["rul"])
    order = corr.abs().fillna(0).sort_values(ascending=False)

    fig = plt.figure(figsize=(13.5, 6.0))
    gs = fig.add_gridspec(3, 2, width_ratios=[1.15, 1], hspace=0.35, wspace=0.25)
    ax1 = fig.add_subplot(gs[:, 0])

    labels = [s.replace("sensor", "") for s in order.index]
    colours = [CMU_RED if s in constant else BLUE for s in order.index]
    ax1.barh(range(len(order)), order.values, color=colours)
    ax1.set_yticks(range(len(order)))
    ax1.set_yticklabels(labels, fontsize=10)
    ax1.invert_yaxis()
    ax1.set_xlabel("|correlation| with clipped RUL")
    ax1.set_ylabel("Sensor channel")
    ax1.set_title("Not every channel is a signal", pad=10)
    ax1.grid(True, axis="x", color=RULE, lw=0.7)
    ax1.set_axisbelow(True)
    ax1.text(0.97, 0.03,
             f"{len(constant)} channels hold one value\n"
             f"(sensors {', '.join(s.replace('sensor', '') for s in constant)})\n"
             f"but only {len(constant) - len(fp_residue)} of them\nreturn std == 0 exactly",
             transform=ax1.transAxes, ha="right", va="bottom", fontsize=10.5,
             color=CMU_RED, fontweight="bold")

    # Each channel gets its own y-scale. Sharing one axis across readings that
    # span 47 to 1400 makes the informative channels look as flat as the dead one,
    # which is the opposite of the point.
    best = list(order.index[:2])
    dead = constant[0] if constant else order.index[-1]
    for row, (s, colour) in enumerate([(best[0], BLUE), (best[1], GREEN),
                                       (dead, CMU_RED)]):
        ax = fig.add_subplot(gs[row, 1])
        for unit in (1, 2, 3):
            traj = train[train["unit"] == unit]
            ax.plot(traj["cycle"], traj[s], "-", color=colour, lw=1.0, alpha=0.8)
        ax.set_ylabel(s, fontsize=11)
        ax.grid(True, color=RULE, lw=0.7)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=10)
        if row == 0:
            ax.set_title("Three engines, own scale each", pad=8)
        if row == 2:
            ax.set_xlabel("Cycle")
            ax.set_ylim(train[s].iloc[0] - 1, train[s].iloc[0] + 1.6)
            ax.text(0.5, 0.82, "one value, every engine, every cycle",
                    transform=ax.transAxes, ha="center", va="center",
                    fontsize=10.5, color=CMU_RED, fontweight="bold")
        else:
            ax.set_xticklabels([])

    fig.savefig(HERE / "sensor-degradation.png")
    plt.close(fig)
    print(f"wrote sensor-degradation.png  ({len(constant)} single-valued: {constant}; "
          f"{len(fp_residue)} with float residue "
          f"{ {k: f'{v:.1e}' for k, v in fp_residue.items()} }; "
          f"strongest {order.index[0]} at {order.iloc[0]:.3f})")
    return {"constant": constant, "top": list(order.index[:3]),
            "top_corr": float(order.iloc[0]), "fp_residue": fp_residue}


# --------------------------------------------------------------------------
# Figure 2: the grouping bug, drawn
# --------------------------------------------------------------------------
def fig_grouped_vs_not(train: pd.DataFrame, sensor: str) -> dict:
    """A rolling mean computed with and without groupby('unit'), at a boundary."""
    pair = train[train["unit"].isin([1, 2])].sort_values(["unit", "cycle"]).copy()
    pair["row"] = np.arange(len(pair))

    pair["right"] = (pair.groupby("unit", group_keys=False)[sensor]
                     .transform(lambda x: x.rolling(WINDOW, min_periods=1).mean()))
    pair["wrong"] = pair[sensor].rolling(WINDOW, min_periods=1).mean()

    boundary = int(pair[pair["unit"] == 1]["row"].max()) + 1
    window = pair[(pair["row"] > boundary - 22) & (pair["row"] < boundary + 22)]
    err = (window["wrong"] - window["right"]).abs()

    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    ax.plot(window["row"], window[sensor], "o", color=RULE, ms=3.5,
            label=f"{sensor}, raw")
    ax.plot(window["row"], window["right"], "-", color=BLUE, lw=2.1,
            label="rolling mean, grouped by unit")
    ax.plot(window["row"], window["wrong"], "-", color=CMU_RED, lw=2.1,
            label="rolling mean, forgot to group")
    ax.axvline(boundary - 0.5, color=INK, lw=1.2, ls="--")
    ax.text(boundary - 0.5, ax.get_ylim()[1], "  engine 1 ends,\n  engine 2 begins",
            va="top", fontsize=11, color=INK)

    ax.set_xlabel("Row index, as the dataframe is sorted")
    ax.set_ylabel(f"{sensor}")
    ax.set_title("The same feature, one missing groupby", pad=10)
    ax.legend(frameon=False, fontsize=11, loc="lower left")
    ax.grid(True, color=RULE, lw=0.7)
    ax.set_axisbelow(True)
    ax.annotate(f"engine 2's first {WINDOW - 1} cycles are\n"
                f"contaminated by engine 1\n(peak error {err.max():.3f})",
                xy=(boundary + 1, window["wrong"].iloc[len(window) // 2]),
                xytext=(boundary + 6, window[sensor].min()),
                fontsize=11, color=CMU_RED, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.3))

    fig.savefig(HERE / "grouped-vs-not.png")
    plt.close(fig)
    print(f"wrote grouped-vs-not.png  (peak contamination {err.max():.4f} "
          f"on {sensor}, {WINDOW - 1} rows affected per engine boundary)")
    return {"peak_error": float(err.max()), "rows_affected": WINDOW - 1}


# --------------------------------------------------------------------------
# Figure 3: one leak, four models
# --------------------------------------------------------------------------
def fig_leakage_by_model(train: pd.DataFrame, test: pd.DataFrame,
                         rul_true: pd.Series, sensors: list[str]) -> dict:
    """The identical scaler leak, scored by four models of differing scale-sensitivity."""
    train_fe, cols = engineer(train, sensors)
    test_fe, _ = engineer(test, sensors)
    last = test_fe.sort_values("cycle").groupby("unit").tail(1).sort_values("unit")
    y_true = rul_true.loc[last["unit"]].to_numpy()

    honest = StandardScaler().fit(train_fe[cols])
    leaky = StandardScaler().fit(pd.concat([train_fe[cols], test_fe[cols]], axis=0))
    rel_mean = (np.abs(honest.mean_ - leaky.mean_)
                / (np.abs(honest.mean_) + 1e-12)).max()
    rel_scale = (np.abs(honest.scale_ - leaky.scale_) / honest.scale_).max()

    def rmse(scaler, factory):
        model = factory().fit(scaler.transform(train_fe[cols]), train_fe["rul"])
        return mean_squared_error(
            y_true, model.predict(scaler.transform(last[cols]))) ** 0.5

    candidates = [
        ("LinearRegression", LinearRegression),
        ("Ridge\n(alpha=10)", lambda: Ridge(alpha=10.0)),
        ("Ridge\n(alpha=1e4)", lambda: Ridge(alpha=1e4)),
        ("KNeighbors\n(k=5)", lambda: KNeighborsRegressor(5)),
    ]
    names, gaps = [], []
    for name, factory in candidates:
        gap = rmse(leaky, factory) - rmse(honest, factory)
        names.append(name)
        gaps.append(gap)
        print(f"  {name.replace(chr(10), ' '):22s} gap {gap:+.4f}")

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    colours = [CMU_RED if g > 0.05 else (AMBER if g < -0.05 else MUTED) for g in gaps]
    bars = ax.bar(range(len(gaps)), gaps, color=colours, width=0.62)
    ax.axhline(0, color=INK, lw=1.1)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=11)
    ax.set_ylabel("RMSE penalty from the leak, cycles\n(positive = leaky is worse)")
    ax.set_title("One leak, four models, four verdicts", pad=10)
    ax.grid(True, axis="y", color=RULE, lw=0.7)
    ax.set_axisbelow(True)

    pad = max(abs(min(gaps)), abs(max(gaps))) * 0.12
    for bar, g in zip(bars, gaps):
        ax.text(bar.get_x() + bar.get_width() / 2,
                g + (pad * 0.35 if g >= 0 else -pad * 0.35),
                f"{g:+.3f}", ha="center",
                va="bottom" if g >= 0 else "top",
                fontsize=11.5, fontweight="bold",
                color=CMU_RED if g > 0.05 else (AMBER if g < -0.05 else MUTED))
    # Generous headroom: the two caption lines sit above the tallest bar.
    ax.set_ylim(min(gaps) - pad * 2.4, max(gaps) + pad * 6.5)

    ax.text(0.5, 0.97,
            f"The leak shifted feature centres by up to {rel_mean:.0%} "
            f"and spreads by up to {rel_scale:.0%} in every case.",
            transform=ax.transAxes, ha="center", va="top", fontsize=11.5,
            color=INK)
    ax.text(0.5, 0.895,
            "Only the model changes. Your metric is not a leak detector.",
            transform=ax.transAxes, ha="center", va="top", fontsize=11.5,
            color=CMU_RED, fontweight="bold")

    fig.savefig(HERE / "leakage-by-model.png")
    plt.close(fig)
    print(f"wrote leakage-by-model.png  (scaler differs by {rel_mean:.1%} in centre, "
          f"{rel_scale:.1%} in spread; gaps {[round(g, 4) for g in gaps]})")
    return {"gaps": dict(zip([n.replace("\n", " ") for n in names], gaps)),
            "rel_mean": float(rel_mean), "rel_scale": float(rel_scale)}


if __name__ == "__main__":
    train, test, rul_true = load()
    print(f"loaded FD001: {len(train):,} train rows / {train.unit.nunique()} engines, "
          f"{len(test):,} test rows / {test.unit.nunique()} engines, "
          f"median life {train.groupby('unit').cycle.max().median():.0f} cycles")

    print("\nfig_sensor_degradation")
    sensor_info = fig_sensor_degradation(train)
    key = sensor_info["top"]

    print("\nfig_grouped_vs_not")
    grouping = fig_grouped_vs_not(train, key[0])

    print("\nfig_leakage_by_model")
    leak = fig_leakage_by_model(train, test, rul_true, key)

    print("\n--- numbers cited in notes.md and slides.md ---")
    print(f"constant channels: {sensor_info['constant']}")
    print(f"  of which std() != 0 from float error: "
          f"{ {k: f'{v:.2e}' for k, v in sensor_info['fp_residue'].items()} }")
    print(f"strongest channels: {key} (top |corr| {sensor_info['top_corr']:.3f})")
    print(f"grouping bug: {grouping['rows_affected']} rows per boundary, "
          f"peak error {grouping['peak_error']:.4f}")
    print(f"scaler leak shifts centres up to {leak['rel_mean']:.1%}, "
          f"spreads up to {leak['rel_scale']:.1%}")
    for name, gap in leak["gaps"].items():
        print(f"  {name:22s} {gap:+.4f}")
