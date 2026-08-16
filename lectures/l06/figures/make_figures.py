#!/usr/bin/env python3
"""Generate the L6 figures from the Intel Berkeley Lab sensor data.

Run with:
    uv run --with pandas --with numpy --with matplotlib python make_figures.py
or with the course env:
    /opt/anaconda3/envs/sys_tools/bin/python make_figures.py

L6 is streaming concepts + data validation. Both figures are built from the real
Intel Lab readings (carried from L3/L4), computed rather than asserted:

    windowing.png     tumbling vs sliding windows over one mote's temperature
    validation.png    how many rows fail plausibility checks, and why

The validation figure continues L3's finding: the impossible temperatures come
from motes whose batteries have drained, so a range check and a voltage check
reject the same rows. Numbers printed here are the ones the notes/slides cite.

The raw data.txt is cached in .cache/ and is gitignored; do not commit it.
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

# pandas 2.3 + numpy 2.5 emit a DeprecationWarning on Timestamp + Timedelta arithmetic
# (the "generic" timedelta unit). It does not affect the figures; silence it for a clean run.
import warnings
warnings.filterwarnings("ignore", message="The 'generic' unit for NumPy timedelta")

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
URL = "https://raw.githubusercontent.com/linsea423/Intel_Lab_Data/master/data.zip"

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"

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

COLS = ["date", "time", "epoch", "moteid",
        "temperature", "humidity", "light", "voltage"]


def load() -> pd.DataFrame:
    """Fetch (once) and parse the Intel Lab data.txt. Same loader as L3/L4."""
    CACHE.mkdir(exist_ok=True)
    txt = CACHE / "data.txt"
    if not txt.exists():
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as r:
            payload = r.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            txt.write_bytes(z.read("data.txt"))
    df = pd.read_csv(txt, sep=r"\s+", names=COLS, header=None,
                     engine="c", on_bad_lines="skip")
    df["ts"] = pd.to_datetime(df["date"] + " " + df["time"],
                              format="mixed", errors="coerce")
    df = df.dropna(subset=["ts", "moteid"])
    df["moteid"] = df["moteid"].astype(int)
    return df


def fig_windowing(df: pd.DataFrame) -> None:
    """Tumbling vs sliding windows over one mote's temperature.

    The same unbounded stream, aggregated two ways. Tumbling windows are fixed
    and non-overlapping; sliding windows overlap and update more often. This is
    the core of turning an endless sensor feed into numbers you can act on.
    """
    d = df.dropna(subset=["temperature"])
    d = d[(d.temperature > 0) & (d.temperature < 50)]  # plausible, for a clean picture
    mote = int(d.moteid.value_counts().idxmax())
    s = (d[d.moteid == mote].sort_values("ts").set_index("ts")["temperature"])
    # a readable slice: the first 8 hours this mote reported
    start = s.index.min()
    s = s[(s.index >= start) & (s.index < start + pd.Timedelta(hours=8))]

    tumbling = s.resample("1h").mean()                       # fixed, non-overlapping
    sliding = s.resample("15min").mean().rolling(4, min_periods=1).mean()  # 1h window, 15min hop

    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.plot(s.index, s.values, ".", ms=3, color=RULE, label="raw readings (~31 s)")
    # tumbling windows: shade alternate hours, draw the window mean as a flat step
    for i, (t, v) in enumerate(tumbling.items()):
        if np.isnan(v):
            continue
        left, right = t.to_pydatetime(), (t + pd.Timedelta(hours=1)).to_pydatetime()
        if i % 2 == 0:
            ax.axvspan(left, right, color=MUTED, alpha=0.06)
        ax.hlines(v, left, right, color=CMU_RED, lw=3)
    ax.plot([], [], color=CMU_RED, lw=3, label="tumbling 1 h mean")
    ax.plot(sliding.index, sliding.values, color=BLUE, lw=1.8,
            label="sliding 1 h mean, 15 min hop")

    ax.set_ylabel("Temperature, °C")
    ax.set_title(f"One stream, two windows (mote {mote}, first 8 hours)", pad=10)
    ax.legend(frameon=False, fontsize=10.5, loc="best")
    for lab in ax.get_xticklabels():
        lab.set_rotation(0)
    fig.savefig(HERE / "windowing.png")
    plt.close(fig)
    print(f"wrote windowing.png  (mote {mote}, {len(s)} readings over 8 h, "
          f"{tumbling.notna().sum()} tumbling windows)")


def fig_validation(df: pd.DataFrame):
    """Two plausibility checks and how many rows each rejects.

    Temperature outside an instrument range, and battery voltage below the
    trustworthy floor. Continuing L3: the impossible temperatures come from
    low-voltage motes, so the two checks reject nearly the same rows. The
    out-of-order-arrival fraction is computed too, but it belongs to the
    streaming story (it motivates watermarks), not to row rejection, so it is
    only printed for the notes to cite.
    """
    d = df.copy()
    n = len(d)

    temp_bad = (d.temperature < 0) | (d.temperature > 50)
    volt_bad = d.voltage < 2.4
    share = (temp_bad & volt_bad).sum() / max(temp_bad.sum(), 1)

    # arrival vs event order: a STREAMING property, printed for the notes, not plotted here
    order_bad = (df.groupby("moteid")["ts"]
                 .apply(lambda x: x < x.cummax()).reset_index(level=0, drop=True))
    out_of_order = float(order_bad.mean())

    checks = {"temperature\noutside 0–50 °C": int(temp_bad.sum()),
              "battery voltage\nbelow 2.4 V": int(volt_bad.sum())}
    labels = list(checks)
    vals = [checks[k] / n * 100 for k in labels]

    fig, ax = plt.subplots(figsize=(7.4, 4.6))
    bars = ax.bar(labels, vals, color=[CMU_RED, MUTED], width=0.5)
    for b, v, k in zip(bars, vals, labels):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}%\n({checks[k]:,})",
                ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylabel("Share of all readings that fail")
    ax.set_ylim(0, max(vals) * 1.35)
    ax.set_title("A schema check rejects the physically impossible rows", pad=10)
    ax.text(0.5, -0.32,
            f"{share:.0%} of the impossible-temperature rows come from a mote already below 2.4 V:\n"
            "the range check and the voltage check catch the same failure.",
            transform=ax.transAxes, ha="center", va="top", fontsize=10.5, color=MUTED)
    fig.savefig(HERE / "validation.png")
    plt.close(fig)
    print(f"wrote validation.png  (n={n:,}; temp_bad {checks[labels[0]]:,}={temp_bad.mean():.1%}, "
          f"volt_bad {checks[labels[1]]:,}={volt_bad.mean():.1%}, share {share:.3f}; "
          f"out-of-order arrival {out_of_order:.1%})")
    return dict(n=n, share=share, out_of_order=out_of_order)


if __name__ == "__main__":
    data = load()
    print(f"loaded {len(data):,} rows, {data.moteid.nunique()} motes, "
          f"{data.ts.min().date()} to {data.ts.max().date()}")
    fig_windowing(data)
    fig_validation(data)
