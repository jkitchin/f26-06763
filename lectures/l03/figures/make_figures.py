#!/usr/bin/env python3
"""Generate the L3 figures from the Intel Berkeley Lab sensor data.

Run with:  uv run --with pandas,matplotlib,numpy python make_figures.py

Every figure in this lecture is generated from the real dataset (or, for the
schema diagram, drawn as original artwork) rather than copied from a paper.
That is partly a licensing matter, since the course site is public, and partly
the point of the course: a figure you cannot regenerate is a figure you cannot
check, and computing a claim rather than asserting it routinely changes it.

Outputs (committed alongside this script):
    schema-long-vs-wide.png   the wide vs long/tidy table argument, redrawn
    voltage-quality.png       dying batteries corrupting temperature readings
    index-scan.png            sequential scan vs B-tree index, measured

The raw data.txt is cached in .cache/ and is gitignored; do not commit it.
"""

from __future__ import annotations

import io
import sqlite3
import time
import urllib.request
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
# The canonical host (db.csail.mit.edu/labdata/data.txt.gz) is the dataset home.
# This is a byte-identical mirror of the same data.txt, used because the
# canonical host is not always reachable from a CI runner.
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
    """Fetch (once) and parse the Intel Lab data.txt.

    The file is whitespace separated with eight columns and no header. Rows are
    NOT in time order (they arrive in collection/epoch order per mote), missing
    values show up as short rows, and the timestamps carry sub-second precision.
    All three are normal for a sensor-network export and none are announced.
    """
    CACHE.mkdir(exist_ok=True)
    txt = CACHE / "data.txt"
    if not txt.exists():
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as r:
            payload = r.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            txt.write_bytes(z.read("data.txt"))

    df = pd.read_csv(
        txt, sep=r"\s+", names=COLS, header=None,
        engine="c", na_values=[], on_bad_lines="skip",
    )
    df["ts"] = pd.to_datetime(
        df["date"] + " " + df["time"], format="mixed", errors="coerce")
    df = df.dropna(subset=["ts", "moteid"])
    df["moteid"] = df["moteid"].astype(int)
    return df


def fig_schema() -> None:
    """Redraw the wide vs long/tidy schema argument as original artwork.

    The single most common mistake students make with sensor data is a wide
    table with one column per sensor. This figure is the counter-argument: the
    same readings in long form plus a sensors dimension, where adding a mote is
    an INSERT rather than a schema migration.
    """
    fig, (axw, axl) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for ax in (axw, axl):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")

    def cell(ax, x, y, w, h, text, face="#f2f2f4", fg=MUTED, weight="normal",
             fs=10.5):
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=face,
                                       edgecolor=MUTED, linewidth=1.0))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=fg, fontweight=weight)

    # ---- Wide table -----------------------------------------------------
    axw.set_title("Wide: one column per sensor", color=INK, pad=10)
    head = ["ts", "m1", "m2", "m3", "…", "m54"]
    xs = [0.3, 2.3, 3.5, 4.7, 5.9, 7.1]
    ws = [2.0, 1.2, 1.2, 1.2, 1.2, 1.2]
    for x, w, h in zip(xs, ws, head):
        cell(axw, x, 7.6, w, 1.0, h, face="#e9e9ee", fg=INK, weight="bold")
    rows = [
        ["08:00", "19.9", "20.1", "NULL", "…", "18.7"],
        ["08:01", "19.8", "20.0", "NULL", "…", "18.6"],
        ["08:02", "20.0", "NULL", "NULL", "…", "18.7"],
    ]
    for r, vals in enumerate(rows):
        y = 6.4 - r * 1.0
        for x, w, v in zip(xs, ws, vals):
            fg = CMU_RED if v == "NULL" else MUTED
            cell(axw, x, y, w, 0.95, v, fg=fg)
    # the new-sensor box, in red: it is a schema change
    axw.add_patch(patches.Rectangle((8.5, 7.6), 1.2, 1.0, facecolor="white",
                  edgecolor=CMU_RED, linewidth=1.6, linestyle="--"))
    axw.text(9.1, 8.1, "m55?", ha="center", va="center", fontsize=10.5,
             color=CMU_RED, fontweight="bold")
    axw.annotate("a new mote =\nALTER TABLE", xy=(9.1, 7.6), xytext=(6.8, 2.9),
                 fontsize=11, color=CMU_RED, ha="center",
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.4))
    axw.text(5.0, 1.3, "NULLs for every offline sensor · cannot ask\n"
             "“which sensors exceeded 30°C?” in one query",
             ha="center", va="center", fontsize=10.5, color=MUTED)

    # ---- Long table -----------------------------------------------------
    axl.set_title("Long / tidy: one row per reading", color=INK, pad=10)
    # sensors dimension
    sw, w0 = 3.9, 2.3
    cell(axl, 0.3, 7.6, sw, 1.0, "sensors", face="#e9e9ee", fg=INK,
         weight="bold")
    for r, (a, b) in enumerate([("sensor_id (PK)", "x, y, unit"),
                                ("1", "…"), ("2", "…")]):
        y = 6.5 - r * 1.0
        face = "#e9e9ee" if r == 0 else "#f2f2f4"
        fg = INK if r == 0 else MUTED
        cell(axl, 0.3, y, w0, 0.95, a, face=face, fg=fg,
             weight="bold" if r == 0 else "normal", fs=8.0)
        cell(axl, 0.3 + w0, y, sw - w0, 0.95, b, face=face, fg=fg, fs=8.0)
    # readings fact table
    cell(axl, 5.0, 7.6, 4.6, 1.0, "readings", face="#e9e9ee", fg=INK,
         weight="bold")
    rhead = ["sensor_id", "ts", "value"]
    rxs, rws = [5.0, 6.9, 8.3], [1.9, 1.4, 1.3]
    for x, w, hh in zip(rxs, rws, rhead):
        cell(axl, x, 6.5, w, 1.0, hh, face="#e9e9ee", fg=INK, weight="bold",
             fs=9.5)
    rdata = [["1", "08:00", "19.9"], ["2", "08:00", "20.1"],
             ["1", "08:01", "19.8"], ["55", "08:01", "21.3"]]
    for r, vals in enumerate(rdata):
        y = 5.4 - r * 0.95
        newrow = vals[0] == "55"
        for x, w, v in zip(rxs, rws, vals):
            fg = CMU_RED if newrow else MUTED
            cell(axl, x, y, w, 0.9, v, fg=fg, fs=9.5)
    # FK arrow
    axl.annotate("", xy=(4.2, 6.0), xytext=(5.0, 6.0),
                 arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=1.6))
    axl.text(4.6, 6.25, "FK", ha="center", fontsize=9.5, color=BLUE)
    axl.text(7.3, 1.3, "a new mote = one INSERT · types and ranges\n"
             "checked once · every question is a WHERE clause",
             ha="center", va="center", fontsize=10.5, color=MUTED)

    fig.suptitle("The same sensor readings, stored two ways", fontsize=15,
                 color=INK, y=1.02)
    fig.savefig(HERE / "schema-long-vs-wide.png")
    plt.close(fig)
    print("wrote schema-long-vs-wide.png")


def fig_voltage(df: pd.DataFrame):
    """Dying batteries, and the temperature readings they corrupt.

    The voltage column is not just telemetry: it is a data-quality signal.
    As a mote's battery drains toward ~2.3 V, its temperature channel stops
    being trustworthy and reports physically impossible values. This is the
    lecture's argument for storing units/calibration context and for range
    checks, computed rather than asserted.
    """
    d = df.dropna(subset=["temperature", "voltage"]).copy()

    # Physically implausible indoor-lab temperatures. 0-50 C is generous.
    LO, HI = 0.0, 50.0
    bad = (d.temperature < LO) | (d.temperature > HI)
    lowv = d.voltage < 2.4
    frac_low = lowv.mean()
    frac_bad = bad.mean()
    # Of the impossible readings, how many came from a low battery?
    share = (bad & lowv).sum() / max(bad.sum(), 1)
    tmax = d.temperature.max()

    fig, (axv, axs) = plt.subplots(1, 2, figsize=(11.5, 4.4))

    # Left: daily mean voltage for a handful of motes over the deployment.
    d["day"] = d.ts.dt.floor("D")
    counts = d.groupby("moteid").size()
    # pick motes with long coverage so the decline is visible
    motes = counts[counts > counts.median()].index[:5]
    for m in motes:
        s = d[d.moteid == m].groupby("day").voltage.mean()
        axv.plot(s.index, s.values, lw=1.4, alpha=0.85)
    axv.axhline(2.4, color=CMU_RED, lw=1.3, ls="--")
    axv.text(axv.get_xlim()[0], 2.4, " 2.4 V", va="bottom", ha="left",
             color=CMU_RED, fontsize=10.5)
    axv.set_ylabel("Battery voltage, V (daily mean)")
    axv.set_title("Batteries drain over the month", pad=10)
    axv.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
    axv.xaxis.set_major_formatter(
        mdates.ConciseDateFormatter(axv.xaxis.get_major_locator()))

    # Right: temperature vs voltage, showing the explosion at low voltage.
    samp = d.sample(n=min(60000, len(d)), random_state=0)
    axs.scatter(samp.voltage, samp.temperature, s=3, alpha=0.15,
                color=MUTED, edgecolors="none")
    axs.axhspan(LO, HI, color=BLUE, alpha=0.08)
    axs.axvline(2.4, color=CMU_RED, lw=1.3, ls="--")
    axs.set_xlim(1.8, 3.2)
    axs.set_ylim(-5, 130)
    axs.set_xlabel("Battery voltage, V")
    axs.set_ylabel("Reported temperature, °C")
    axs.set_title("Low voltage → impossible temperatures", pad=10)
    share_lbl = "nearly every" if share > 0.99 else f"{share:.0%} of"
    axs.annotate(f"{share_lbl} impossible\nreading comes from\na mote below 2.4 V",
                 xy=(2.33, 95), xytext=(2.74, 78), fontsize=10.5,
                 color=CMU_RED, fontweight="bold", ha="center",
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))

    fig.savefig(HERE / "voltage-quality.png")
    plt.close(fig)
    print(f"wrote voltage-quality.png  (low-voltage rows {frac_low:.1%}, "
          f"impossible temps {frac_bad:.2%}, of which {share:.4f} are low-voltage, "
          f"max temp {tmax:.0f}C)")
    return dict(frac_low=frac_low, frac_bad=frac_bad, share=share, tmax=tmax)


def fig_index(df: pd.DataFrame):
    """Sequential scan vs a B-tree index, measured on the real readings.

    Loaded into SQLite (server-free, ships with Python) so the figure needs no
    running database. A B-tree range lookup behaves the same way in SQLite and
    PostgreSQL; the demo reproduces this live in PostgreSQL with EXPLAIN ANALYZE.
    The point is the SHAPE: the scan cost grows with the table, the index cost
    barely moves.
    """
    d = (df.dropna(subset=["temperature"])
           .sort_values("ts")
           .reset_index(drop=True))
    d["epoch_s"] = (d.ts.astype("int64") // 10**9)  # integer seconds for SQLite
    full = d[["moteid", "epoch_s", "temperature"]].to_numpy()

    sizes = [200_000, 600_000, 1_200_000, len(full)]
    sizes = [s for s in sizes if s <= len(full)]
    # a representative per-mote, one-day window
    mote = int(d.moteid.mode().iloc[0])
    t0 = int(d.epoch_s.iloc[len(d) // 2])
    t1 = t0 + 3600  # a one-hour window, the shape of a typical range query
    # "how many readings did this sensor report in this hour?" — a dropout
    # check, and a query the (moteid, ts) index can answer without the heap.
    q = ("SELECT count(*) FROM readings "
         "WHERE moteid=? AND epoch_s BETWEEN ? AND ?")

    def bench(rows, indexed):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE readings (moteid INT, epoch_s INT, temperature REAL)")
        con.executemany("INSERT INTO readings VALUES (?,?,?)",
                        (tuple(r) for r in rows))
        if indexed:
            con.execute("CREATE INDEX idx ON readings (moteid, epoch_s)")
            con.execute("ANALYZE")  # let the planner commit to the index
        con.commit()
        con.execute(q, (mote, t0, t1)).fetchall()  # warm the cache
        samples = []
        for _ in range(51):
            start = time.perf_counter()
            con.execute(q, (mote, t0, t1)).fetchall()
            samples.append((time.perf_counter() - start) * 1000.0)  # ms
        con.close()
        return float(np.median(samples))

    scan, idx = [], []
    for n in sizes:
        rows = full[:n]
        scan.append(bench(rows, False))
        idx.append(bench(rows, True))

    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    x = np.array(sizes) / 1e6
    ax.plot(x, scan, "-o", color=MUTED, lw=1.8, label="no index (sequential scan)")
    ax.plot(x, idx, "-o", color=CMU_RED, lw=1.8, label="B-tree on (moteid, ts)")
    ax.set_xlabel("Rows in table, millions")
    ax.set_ylabel("Query time, ms (per range query)")
    ax.set_title("One per-sensor time window, as the table grows", pad=10)
    ax.legend(frameon=False, fontsize=11)
    speedup = scan[-1] / idx[-1]
    ax.annotate(f"≈{speedup:.0f}× faster\nat {sizes[-1]/1e6:.1f}M rows",
                xy=(x[-1], idx[-1]), xytext=(x[-1] * 0.62, max(scan) * 0.55),
                fontsize=11, color=CMU_RED, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.3))
    fig.savefig(HERE / "index-scan.png")
    plt.close(fig)
    print(f"wrote index-scan.png  (scan {scan[-1]:.2f}ms vs index {idx[-1]:.3f}ms "
          f"at {sizes[-1]} rows, {speedup:.0f}x)")
    print(f"  scan ms by size: {[round(s,2) for s in scan]}")
    print(f"  idx  ms by size: {[round(s,3) for s in idx]}")
    return dict(scan_ms=scan[-1], idx_ms=idx[-1], speedup=speedup, rows=sizes[-1])


if __name__ == "__main__":
    data = load()
    print(f"loaded {len(data):,} rows, {data.moteid.nunique()} motes, "
          f"{data.ts.min().date()} to {data.ts.max().date()}")
    fig_schema()
    fig_voltage(data)
    fig_index(data)
