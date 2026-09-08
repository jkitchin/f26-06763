#!/usr/bin/env python3
"""Generate the L5 figure from the Tennessee Eastman process data.

Run with:
    uv run --with pandas --with polars --with pyreadr --with numpy \
           --with matplotlib --with pyarrow python make_figures.py

L5's pipeline is measured here, not asserted: the same load, drop, impute,
aggregate stages the demo notebook runs, timed on the real data as it grows in
rows and in columns. The numbers this run prints are the ones the notes and
slides cite.

Output (committed alongside this script):
    eager-vs-lazy.png     pandas eager vs Polars lazy, as the table grows wider
                          and taller

The raw .RData is cached in .cache/ and is gitignored; do not commit it.
"""
from __future__ import annotations

import time
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import pyreadr

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
# Faulty_Training: the only TEP file carrying more than one fault class.
URL = "https://dataverse.harvard.edu/api/access/datafile/3031242"

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
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

ID_COLS = ["faultNumber", "simulationRun", "sample"]
MISSING_MAX = 0.5


def load() -> pd.DataFrame:
    """Fetch (once) and parse Faulty_Training. Same source as the demo notebook."""
    CACHE.mkdir(exist_ok=True)
    raw = CACHE / "tep_faulty.RData"
    if not raw.exists():
        print(f"downloading {URL} (one time, ~494 MB)")
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(raw, "wb") as f:
            import shutil
            shutil.copyfileobj(r, f)
    df = pyreadr.read_r(str(raw))["faulty_training"]
    for c in ID_COLS:
        df[c] = df[c].astype(int)
    return df[(df["simulationRun"] <= 80) & (df["sample"] > 20)].reset_index(drop=True)


def inject_defects(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Same three defects as the demo notebook, on purpose: this data is clean."""
    rng = np.random.default_rng(seed)
    dirty = df.copy()
    dirty.loc[rng.random(len(dirty)) < 0.70, "xmeas_20"] = np.nan   # dropped
    dirty.loc[rng.random(len(dirty)) < 0.40, "xmeas_10"] = np.nan   # imputed
    dirty["xmv_5"] = 0.0                                             # dropped
    return dirty


def pipeline_pandas(path, sensor_cols) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=ID_COLS + sensor_cols)
    nunique = df[sensor_cols].nunique(dropna=True)
    null_frac = df[sensor_cols].isna().mean()
    keep = [c for c in sensor_cols if nunique[c] > 1 and null_frac[c] <= MISSING_MAX]
    df = df[ID_COLS + keep].copy()
    df[keep] = df[keep].fillna(df[keep].median())
    return df.groupby("faultNumber")[keep].mean().reset_index()


def pipeline_polars(path, sensor_cols) -> pl.DataFrame:
    lf = pl.scan_parquet(path).select(ID_COLS + sensor_cols)
    stats = (lf.select(
                 pl.len().alias("_n"),
                 pl.col(sensor_cols).n_unique().name.suffix("_nu"),
                 pl.col(sensor_cols).null_count().name.suffix("_nz"))
               .collect().row(0, named=True))
    n = stats["_n"]
    keep = [c for c in sensor_cols
            if stats[f"{c}_nu"] > 1 and stats[f"{c}_nz"] / n <= MISSING_MAX]
    plan = (lf.select(ID_COLS + keep)
              .with_columns(pl.col(keep).fill_null(pl.col(keep).median()))
              .group_by("faultNumber").agg(pl.col(keep).mean())
              .sort("faultNumber"))
    return plan.collect()


def median_ms(fn, n=5) -> float:
    fn()  # warm
    s = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        s.append((time.perf_counter() - t) * 1000.0)
    return float(np.median(s))


def fig_eager_vs_lazy(df: pd.DataFrame) -> dict:
    """Measure pandas eager vs Polars lazy, as the table grows taller and wider.

    Left: fixed 52 sensor columns, growing row counts (more simulation runs).
    Right: fixed row count, growing sensor-column counts (more of the table in
    scope). Both isolate one dimension of "wide, tall" so the two curves show
    what actually drives each engine's cost.
    """
    all_sensors = [c for c in df.columns if c not in ID_COLS]
    dirty = inject_defects(df)

    # ---- left: rows ----------------------------------------------------
    run_counts = [10, 30, 50, 80]
    row_sizes, pd_ms_rows, pl_ms_rows = [], [], []
    for runs in run_counts:
        sub = dirty[dirty["simulationRun"] <= runs]
        path = CACHE / f"_bench_r{runs}.parquet"
        sub.to_parquet(path, engine="pyarrow", compression="snappy")
        row_sizes.append(len(sub))
        pd_ms_rows.append(median_ms(lambda p=path: pipeline_pandas(p, all_sensors)))
        pl_ms_rows.append(median_ms(lambda p=path: pipeline_polars(p, all_sensors)))

    # ---- right: columns --------------------------------------------------
    col_counts = [10, 20, 35, 52]
    fixed = dirty[dirty["simulationRun"] <= 50]
    fixed_path = CACHE / "_bench_cols.parquet"
    fixed.to_parquet(fixed_path, engine="pyarrow", compression="snappy")
    pd_ms_cols, pl_ms_cols = [], []
    for k in col_counts:
        cols = all_sensors[:k]
        pd_ms_cols.append(median_ms(lambda c=cols: pipeline_pandas(fixed_path, c)))
        pl_ms_cols.append(median_ms(lambda c=cols: pipeline_polars(fixed_path, c)))

    fig, (axr, axc) = plt.subplots(1, 2, figsize=(11.5, 4.6))

    x = np.array(row_sizes) / 1e3
    axr.plot(x, pd_ms_rows, "-o", color=MUTED, lw=1.8, label="pandas (eager)")
    axr.plot(x, pl_ms_rows, "-o", color=CMU_RED, lw=1.8, label="Polars (lazy)")
    axr.set_xlabel("Rows, thousands")
    axr.set_ylabel("Pipeline time, ms")
    axr.set_title("Fixed 52 sensors, growing rows", pad=10)
    axr.legend(frameon=False, fontsize=10.5)
    speed_rows = pd_ms_rows[-1] / pl_ms_rows[-1]
    axr.annotate(f"≈{speed_rows:.1f}× faster\nat {row_sizes[-1] / 1e3:.0f}k rows",
                 xy=(x[-1], pl_ms_rows[-1]), xytext=(x[-1] * 0.45, max(pd_ms_rows) * 0.65),
                 fontsize=11, color=CMU_RED, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.3))

    axc.plot(col_counts, pd_ms_cols, "-o", color=MUTED, lw=1.8, label="pandas (eager)")
    axc.plot(col_counts, pl_ms_cols, "-o", color=CMU_RED, lw=1.8, label="Polars (lazy)")
    axc.set_xlabel("Sensor columns in scope")
    axc.set_ylabel("Pipeline time, ms")
    axc.set_title(f"Fixed {row_sizes[2] / 1e3:.0f}k rows, growing columns", pad=10)
    axc.legend(frameon=False, fontsize=10.5)
    speed_cols = pd_ms_cols[-1] / pl_ms_cols[-1]
    axc.annotate(f"≈{speed_cols:.1f}× faster\nat {col_counts[-1]} columns",
                 xy=(col_counts[-1], pl_ms_cols[-1]),
                 xytext=(col_counts[-1] * 0.5, max(pd_ms_cols) * 0.65),
                 fontsize=11, color=CMU_RED, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.3))

    fig.suptitle("The same 4-stage pipeline: pandas eager vs Polars lazy",
                 fontsize=15, color=INK, y=1.03)
    fig.savefig(HERE / "eager-vs-lazy.png")
    plt.close(fig)

    print(f"wrote eager-vs-lazy.png")
    print(f"  rows:    {row_sizes}")
    print(f"  pandas:  {[round(v, 1) for v in pd_ms_rows]} ms")
    print(f"  polars:  {[round(v, 1) for v in pl_ms_rows]} ms  ({speed_rows:.1f}x at largest)")
    print(f"  cols:    {col_counts}")
    print(f"  pandas:  {[round(v, 1) for v in pd_ms_cols]} ms")
    print(f"  polars:  {[round(v, 1) for v in pl_ms_cols]} ms  ({speed_cols:.1f}x at largest)")
    return dict(speed_rows=speed_rows, speed_cols=speed_cols, rows=row_sizes[-1])


if __name__ == "__main__":
    data = load()
    print(f"loaded {len(data):,} rows, {data.shape[1]} columns, "
          f"{data['faultNumber'].nunique()} fault classes")
    fig_eager_vs_lazy(data)
