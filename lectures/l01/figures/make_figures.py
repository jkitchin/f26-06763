#!/usr/bin/env python3
"""Generate the L1 figures from the UCI Air Quality dataset.

Run with:  uv run --with pandas,matplotlib,scikit-learn python make_figures.py

Every figure in this lecture is generated from real data by this script rather
than copied from a paper. That is partly a licensing matter, since the course
site is public, and partly the point: a figure you cannot regenerate is a figure
you cannot check.

Outputs (committed alongside this script):
    system-boxes.png            the "ML code is a small box" schematic, redrawn
    drift-calibration.png       calibration error growing over the deployment
    split-comparison.png        random split vs temporal split on the same data
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
URL = "https://archive.ics.uci.edu/static/public/360/air+quality.zip"

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"

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


def load() -> pd.DataFrame:
    """Fetch (once) and parse the UCI Air Quality CSV.

    The file is semicolon separated with comma decimals, carries two trailing
    empty columns, and codes missing values as -200. All four of those are
    normal for instrument exports and none of them are announced.
    """
    CACHE.mkdir(exist_ok=True)
    csv = CACHE / "AirQualityUCI.csv"
    if not csv.exists():
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as r:
            payload = r.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            csv.write_bytes(z.read("AirQualityUCI.csv"))

    df = (
        pd.read_csv(csv, sep=";", decimal=",")
        .dropna(axis=1, how="all")
        .dropna(how="all")
    )
    df["ts"] = pd.to_datetime(
        df["Date"] + " " + df["Time"].str.replace(".", ":", regex=False),
        format="%d/%m/%Y %H:%M:%S",
    )
    return df.replace(-200, np.nan)


def fig_system_boxes() -> None:
    """Redraw the 'ML code is a small box' schematic.

    Deliberately a redrawing, not a reproduction: the original figure is in a
    copyrighted paper and this site is public. Same argument, our own artwork.
    """
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 46)
    ax.axis("off")

    # Tiles the canvas exactly, so the area comparison is honest and there are
    # no stray gaps that read as a rendering bug.
    boxes = [
        ("Configuration", 0, 16, 14, 30),
        ("Process\nmanagement tools", 70, 16, 30, 30),
        ("Data collection", 14, 30, 22, 16),
        ("Feature\nextraction", 36, 30, 16, 16),
        ("Analysis tools", 52, 30, 18, 16),
        ("Machine resource\nmanagement", 14, 16, 26, 14),
        ("Monitoring", 52, 16, 18, 14),
        ("Data verification", 0, 0, 40, 16),
        ("Serving infrastructure", 40, 0, 60, 16),
    ]
    for label, x, y, w, h in boxes:
        ax.add_patch(patches.Rectangle(
            (x, y), w, h, facecolor="#f2f2f4", edgecolor=MUTED, linewidth=1.1))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center",
                fontsize=10.5, color=MUTED)

    # The point of the whole figure: 168 of 4600 units, about 3.7% of the area.
    ax.add_patch(patches.Rectangle(
        (40, 16), 12, 14, facecolor=CMU_RED, edgecolor=CMU_RED))
    ax.text(46, 23, "ML\ncode", ha="center", va="center",
            fontsize=11, color="white", fontweight="bold")

    ax.set_title("A production ML system, sized by the code each part requires",
                 color=INK, pad=14)
    fig.savefig(HERE / "system-boxes.png")
    plt.close(fig)
    print("wrote system-boxes.png")


def fig_drift(df: pd.DataFrame) -> None:
    """Calibrate on the first three months, then watch the error grow.

    This is the lecture's drift claim, computed rather than asserted.
    """
    d = df.dropna(subset=["PT08.S1(CO)", "CO(GT)"]).copy()
    train = d[d.ts < "2004-06-01"]
    model = LinearRegression().fit(train[["PT08.S1(CO)"]], train["CO(GT)"])

    d["pred"] = model.predict(d[["PT08.S1(CO)"]])
    d["month"] = d.ts.dt.to_period("M")
    monthly = d.groupby("month").apply(
        lambda g: mean_absolute_error(g["CO(GT)"], g["pred"]), include_groups=False)
    monthly = monthly[monthly.index.astype(str) < "2005-04"]  # drop 3-day stub

    fig, ax = plt.subplots(figsize=(10, 4.4))
    x = np.arange(len(monthly))
    colors = [MUTED if str(m) < "2004-06" else CMU_RED for m in monthly.index]
    ax.bar(x, monthly.values, color=colors, width=0.68)
    ax.set_xticks(x)
    ax.set_xticklabels([str(m)[2:] for m in monthly.index], rotation=45, ha="right")
    ax.set_ylabel("Mean absolute error, mg/m$^3$")
    ax.set_title("A calibration fit on three months, applied for a year", pad=12)

    span = len(monthly[monthly.index.astype(str) < "2004-06"])
    ax.axvspan(-0.5, span - 0.5, color=MUTED, alpha=0.10)
    ax.text(span / 2 - 0.5, ax.get_ylim()[1] * 0.94, "fitted here",
            ha="center", fontsize=11, color=MUTED)

    # The interesting result is not a monotonic drift. It is seasonal: the model
    # fitted in spring is best in late summer and worst in early winter. Report
    # the worst month, since an average over the tail hides exactly that.
    base = monthly.iloc[:span].mean()
    worst_i = int(np.argmax(monthly.values))
    worst = monthly.iloc[worst_i]
    ax.annotate(f"{worst / base:.1f}x the fitted-period error",
                xy=(worst_i, worst), xytext=(worst_i - 3.4, worst * 1.12),
                fontsize=11, color=CMU_RED, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.4))
    ax.set_ylim(0, worst * 1.32)
    fig.savefig(HERE / "drift-calibration.png")
    plt.close(fig)
    print(f"wrote drift-calibration.png  (worst month {worst / base:.2f}x baseline, "
          f"best {monthly.min() / base:.2f}x, seasonal not monotonic)")
    return base, worst


def fig_split(df: pd.DataFrame) -> None:
    """The same data and model, scored two ways.

    Random split shuffles future readings into the training set, so it reports a
    number the deployed model will never achieve.
    """
    d = df.dropna(subset=["PT08.S1(CO)", "CO(GT)"]).sort_values("ts")
    X, y = d[["PT08.S1(CO)"]], d["CO(GT)"]

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=0)
    r2_random = r2_score(yte, LinearRegression().fit(Xtr, ytr).predict(Xte))

    cut = int(len(d) * 0.75)
    r2_temporal = r2_score(
        y.iloc[cut:],
        LinearRegression().fit(X.iloc[:cut], y.iloc[:cut]).predict(X.iloc[cut:]),
    )

    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    bars = ax.bar(["Random split", "Temporal split"], [r2_random, r2_temporal],
                  color=[MUTED, CMU_RED], width=0.55)
    for b, v in zip(bars, [r2_random, r2_temporal]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                ha="center", fontsize=14, fontweight="bold")
    ax.set_ylabel("$R^2$ on held-out data")
    ax.set_ylim(0, max(r2_random, r2_temporal) * 1.25)
    ax.set_title("Same data, same model, two evaluation protocols", pad=12)
    fig.savefig(HERE / "split-comparison.png")
    plt.close(fig)
    print(f"wrote split-comparison.png  (random {r2_random:.3f}, temporal {r2_temporal:.3f})")
    return r2_random, r2_temporal


if __name__ == "__main__":
    data = load()
    print(f"loaded {len(data)} rows, {data.ts.min().date()} to {data.ts.max().date()}")
    fig_system_boxes()
    fig_drift(data)
    fig_split(data)
