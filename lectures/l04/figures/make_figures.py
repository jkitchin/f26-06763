#!/usr/bin/env python3
"""Generate the L4 figures from the Intel Berkeley Lab sensor data.

Run with:
    uv run --with pandas --with numpy --with matplotlib --with pyarrow \
           --with duckdb python make_figures.py

L4 continues L3: the same Intel Lab readings, now stored columnar. Every figure
is generated from the real data (or, for the layout diagram, drawn as original
artwork) rather than copied, so the claims can be checked and recomputed. The
row-vs-column speedup and the compression ratio below are measured here, not
asserted, and the numbers this run prints are the ones the notes and slides cite.

Outputs (committed alongside this script):
    row-vs-column.png     how a row store and a column store lay bytes on disk
    columnar-scan.png      one-column aggregate: row store vs DuckDB/Parquet, and file size

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
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
# Byte-identical mirror of the Intel Lab data.txt (same file L3 uses); the
# canonical host (db.csail.mit.edu/labdata) is not always reachable from CI.
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
    """Fetch (once) and parse the Intel Lab data.txt. Same loader as L3."""
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


def fig_row_vs_column() -> None:
    """Draw how a row store and a column store lay the same table on disk.

    The whole L4 argument in one picture: a row store keeps each row's columns
    together, so a scan of one column still drags every other column off disk;
    a column store keeps each column together, so the same scan reads only what
    it needs, and each column (one type, similar values) compresses well.
    """
    fig, (axr, axc) = plt.subplots(1, 2, figsize=(11.5, 4.8))
    for ax in (axr, axc):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")

    cols = ["ts", "mote", "temp", "volt"]
    # one light shade per column, so the eye can track where each column's
    # bytes end up in the two layouts. temp is the one we will aggregate.
    face = {"ts": "#e6eef6", "mote": "#eeeeee", "temp": "#f6dfe4", "volt": "#e4efe6"}
    rows = [["08:00", "1", "19.9", "2.69"],
            ["08:00", "2", "20.1", "2.68"],
            ["08:01", "1", "19.8", "2.69"]]

    def cell(ax, x, y, w, h, text, fc, fg=INK, bold=False):
        ax.add_patch(patches.Rectangle((x, y), w, h, facecolor=fc,
                     edgecolor=MUTED, linewidth=1.0))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=10.5, color=fg, fontweight="bold" if bold else "normal")

    cw, ch = 2.0, 0.9

    # ---- Row store: rows stored together (one strip per row) -------------
    axr.set_title("Row store (PostgreSQL)", color=INK, pad=10)
    for r, vals in enumerate(rows):
        y = 7.2 - r * 1.2
        for c, (name, v) in enumerate(zip(cols, vals)):
            cell(axr, 0.4 + c * cw, y, cw, ch, v, face[name])
    axr.text(5.0, 2.4, "each row's columns sit together on disk",
             ha="center", fontsize=11, color=MUTED)
    axr.text(5.0, 1.4, "avg(temp) still reads every column of every row",
             ha="center", fontsize=11, color=CMU_RED, fontweight="bold")

    # ---- Column store: columns stored together (one strip per column) ----
    axc.set_title("Column store (Parquet / DuckDB)", color=INK, pad=10)
    for c, name in enumerate(cols):
        y = 7.2 - c * 1.2
        cell(axc, 0.4, y, 1.7, ch, name, "#e9e9ee", bold=True)
        for r in range(3):
            v = rows[r][c]
            hl = name == "temp"
            cell(axc, 2.3 + r * cw, y, cw, ch, v,
                 "#f2c9d2" if hl else face[name],
                 fg=CMU_RED if hl else INK, bold=hl)
    axc.text(5.0, 2.4, "each column sits together, and compresses well",
             ha="center", fontsize=11, color=MUTED)
    axc.text(5.0, 1.4, "avg(temp) reads only the temp block",
             ha="center", fontsize=11, color=CMU_RED, fontweight="bold")

    fig.suptitle("The same table, two layouts on disk", fontsize=15,
                 color=INK, y=1.02)
    fig.savefig(HERE / "row-vs-column.png")
    plt.close(fig)
    print("wrote row-vs-column.png")


def fig_scan_and_size(df: pd.DataFrame):
    """Measure the columnar payoff: one-column aggregate, and file size.

    Left: the same analytical query, avg(temperature) grouped by mote over the
    whole table, as the table grows, run against a row store (SQLite) and a
    column store (DuckDB reading a Parquet file). No index helps a full-column
    aggregate, so this isolates the layout, not the index.
    Right: the same readings written to CSV and to Parquet, bytes on disk.
    """
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq

    d = (df.dropna(subset=["temperature"]).sort_values("ts").reset_index(drop=True))
    d["epoch_s"] = (d.ts.astype("int64") // 10**9)
    keep = ["moteid", "epoch_s", "temperature", "humidity", "light", "voltage"]
    d = d[keep]

    sizes = [200_000, 600_000, 1_200_000, len(d)]
    sizes = sorted({s for s in sizes if s <= len(d)})
    Q_SQL = "SELECT moteid, avg(temperature) FROM readings GROUP BY moteid"
    Q_PARQ = "SELECT moteid, avg(temperature) FROM read_parquet(?) GROUP BY moteid"

    def median_ms(fn, n=25):
        fn()  # warm
        s = []
        for _ in range(n):
            t = time.perf_counter()
            fn()
            s.append((time.perf_counter() - t) * 1000.0)
        return float(np.median(s))

    row_ms, col_ms = [], []
    pq_path = CACHE / "_bench.parquet"
    for n in sizes:
        sub = d.iloc[:n]
        # row store: SQLite, no index (a full aggregate scans everything anyway)
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE readings (moteid INT, epoch_s INT, "
                    "temperature REAL, humidity REAL, light REAL, voltage REAL)")
        con.executemany("INSERT INTO readings VALUES (?,?,?,?,?,?)",
                        (tuple(r) for r in sub.to_numpy()))
        con.commit()
        row_ms.append(median_ms(lambda: con.execute(Q_SQL).fetchall()))
        con.close()
        # column store: Parquet queried by DuckDB, reads only 2 of 6 columns
        pq.write_table(pa.Table.from_pandas(sub, preserve_index=False), pq_path,
                       compression="snappy")
        dcon = duckdb.connect()
        col_ms.append(median_ms(lambda: dcon.execute(Q_PARQ, [str(pq_path)]).fetchall()))
        dcon.close()

    # file size at full scale: CSV vs Parquet
    csv_path = CACHE / "_bench.csv"
    d.to_csv(csv_path, index=False)
    pq.write_table(pa.Table.from_pandas(d, preserve_index=False), pq_path,
                   compression="snappy")
    csv_mb = csv_path.stat().st_size / 1e6
    parq_mb = pq_path.stat().st_size / 1e6

    fig, (axt, axs) = plt.subplots(1, 2, figsize=(11.5, 4.4),
                                   gridspec_kw={"width_ratios": [1.55, 1]})

    x = np.array(sizes) / 1e6
    axt.plot(x, row_ms, "-o", color=MUTED, lw=1.8, label="row store (SQLite)")
    axt.plot(x, col_ms, "-o", color=CMU_RED, lw=1.8, label="column store (DuckDB + Parquet)")
    axt.set_xlabel("Rows in table, millions")
    axt.set_ylabel("Query time, ms")
    axt.set_title("avg(temperature) by mote, whole table", pad=10)
    axt.legend(frameon=False, fontsize=10.5)
    speed = row_ms[-1] / col_ms[-1]
    axt.annotate(f"≈{speed:.0f}× faster\nat {sizes[-1] / 1e6:.1f}M rows",
                 xy=(x[-1], col_ms[-1]), xytext=(x[-1] * 0.5, max(row_ms) * 0.6),
                 fontsize=11, color=CMU_RED, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.3))

    bars = axs.bar(["CSV", "Parquet\n(snappy)"], [csv_mb, parq_mb],
                   color=[MUTED, CMU_RED], width=0.6)
    for b, v in zip(bars, [csv_mb, parq_mb]):
        axs.text(b.get_x() + b.get_width() / 2, v, f"{v:.0f} MB",
                 ha="center", va="bottom", fontsize=11, fontweight="bold")
    axs.set_ylabel("File size on disk, MB")
    axs.set_ylim(0, csv_mb * 1.18)
    axs.set_title(f"Same {len(d) / 1e6:.1f}M readings on disk", pad=10)

    fig.savefig(HERE / "columnar-scan.png")
    plt.close(fig)
    print(f"wrote columnar-scan.png  (scan {row_ms[-1]:.1f}ms row vs "
          f"{col_ms[-1]:.2f}ms columnar = {speed:.0f}x; "
          f"CSV {csv_mb:.0f}MB vs Parquet {parq_mb:.0f}MB = {csv_mb / parq_mb:.1f}x smaller)")
    print(f"  row ms by size: {[round(s, 1) for s in row_ms]}")
    print(f"  col ms by size: {[round(s, 2) for s in col_ms]}")
    return dict(speed=speed, csv_mb=csv_mb, parq_mb=parq_mb, rows=sizes[-1])


if __name__ == "__main__":
    data = load()
    print(f"loaded {len(data):,} rows, {data.moteid.nunique()} motes, "
          f"{data.ts.min().date()} to {data.ts.max().date()}")
    fig_row_vs_column()
    fig_scan_and_size(data)
