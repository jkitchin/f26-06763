#!/usr/bin/env python3
"""Generate lectures/l05/l05-pipelines.ipynb.

The L5 demo builds one four-stage batch pipeline (load, drop constant/high-missing
columns, impute, aggregate by fault) twice, once in pandas eager and once in Polars
lazy, on the Tennessee Eastman process data, then times them and prints the Polars
query plan.

Design notes so the demo stays honest:
  - Tennessee Eastman is clean by construction (no gaps, no dead channels). The
    cleaning stages would be no-ops on the raw file, so a single clearly-labeled
    cell injects the defects on purpose (a heavy dropout that gets a column
    dropped, a light dropout that gets imputed, and a stuck channel), and says so.
  - The multi-fault label lives only in the 494 MB Faulty_Training file. We fetch
    it once, keep a slice of the runs, and cache a compact Parquet. FAULT_FREE
    swaps in the 24.7 MB fault-free file for a bandwidth-limited run.
  - Live timings vary with hardware; the controlled figure in the notes
    (figures/make_figures.py) is the cited measurement. The demo shows the shape.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The
committed .ipynb carries no outputs and must run top to bottom.

    python3 lectures/l05/build_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l05-pipelines.ipynb"

_n = 0


def _next_id(kind):
    global _n
    _n += 1
    return f"{kind}-{_n:02d}"


def _src(text):
    lines = text.strip("\n").split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


def md(text):
    return {"cell_type": "markdown", "id": _next_id("md"),
            "metadata": {}, "source": _src(text)}


def code(text):
    return {"cell_type": "code", "id": _next_id("code"), "execution_count": None,
            "metadata": {}, "outputs": [], "source": _src(text)}


cells = [
    md("""
# L5 demo: the same pipeline, two ways

We take the Tennessee Eastman process readings and build one four-stage batch
pipeline, **load, drop bad columns, impute, aggregate by fault**, and write it
twice: once in **pandas** (eager) and once in **Polars** (lazy). Then we time
them and read the Polars query plan.

The data is clean by construction, so one clearly-labeled cell injects the
defects on purpose, the kind a real sensor log carries, so the cleaning stages
have real work to do.

> Data: [Tennessee Eastman process simulation data](https://doi.org/10.7910/DVN/6C3JR1)
> (Rieth et al. 2017, Harvard Dataverse, CC0). 52 process variables, fault-free
> operation plus faults 1 to 20.
"""),

    md("""
## 1. Load the readings

The multi-fault label lives only in the 494 MB `Faulty_Training` file, so we
fetch it once, keep every fault but a slice of the 500 simulation runs, drop the
nominal start of each run (the fault is injected after sample 20), and cache a
compact Parquet. Later runs read the Parquet and download nothing. Set
`FAULT_FREE = True` to use the 24.7 MB fault-free file instead, at the cost of a
single fault class.
"""),

    code("""
import shutil
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pyreadr

FAULT_FREE = False          # True -> 24.7 MB fault-free file (one class only)
RUNS_KEPT = 50              # of 500 runs per fault; 20 x 50 x 480 samples ~ 480k rows
DATA = Path("data")
DATA.mkdir(exist_ok=True)
PARQUET = DATA / ("tep_faultfree.parquet" if FAULT_FREE else "tep_faulty.parquet")

# (direct-download url, R object name inside the .RData)
SOURCE = {
    False: ("https://dataverse.harvard.edu/api/access/datafile/3031242", "faulty_training"),
    True:  ("https://dataverse.harvard.edu/api/access/datafile/3031241", "fault_free_training"),
}


def load_tep() -> pd.DataFrame:
    if PARQUET.exists():
        return pd.read_parquet(PARQUET)
    url, obj = SOURCE[FAULT_FREE]
    raw = DATA / (PARQUET.stem + ".RData")
    if not raw.exists():
        print(f"fetching {url} (one time, ~{'25' if FAULT_FREE else '494'} MB)")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(raw, "wb") as f:
            shutil.copyfileobj(r, f)   # stream; Dataverse 403s the default urllib agent
    df = pyreadr.read_r(str(raw))[obj]              # pyreadr needs no R install
    for c in ("faultNumber", "simulationRun", "sample"):
        df[c] = df[c].astype(int)                   # R numerics come back as float
    if not FAULT_FREE:
        df = df[(df["simulationRun"] <= RUNS_KEPT) & (df["sample"] > 20)]
    df = df.reset_index(drop=True)
    df.to_parquet(PARQUET, engine="pyarrow", compression="snappy")
    return df


readings = load_tep()
print(f"{len(readings):,} rows, {readings.shape[1]} columns, "
      f"{readings.faultNumber.nunique()} fault classes")
readings.head(3)
"""),

    md("""
## 2. Inject the defects, on purpose

Tennessee Eastman ships clean: no missing values, no dead channels. To give the
cleaning stages something real to do, we damage a **copy** and say exactly what
we did. These are the defects a real sensor log carries: a channel that dropped
out heavily, one that dropped out lightly, and one that stuck at a constant.
"""),

    code("""
rng = np.random.default_rng(0)
dirty = readings.copy()

# heavy dropout (> 50% missing): this column should be DROPPED as unusable
dirty.loc[rng.random(len(dirty)) < 0.70, "xmeas_20"] = np.nan
# light dropout (< 50% missing): this column should be KEPT and IMPUTED
dirty.loc[rng.random(len(dirty)) < 0.40, "xmeas_10"] = np.nan
# a stuck sensor frozen at one value: DROPPED as constant
dirty["xmv_5"] = 0.0

print(f"xmeas_20: {dirty['xmeas_20'].isna().mean():.0%} missing  (expect dropped)")
print(f"xmeas_10: {dirty['xmeas_10'].isna().mean():.0%} missing  (expect imputed)")
print(f"xmv_5:    {dirty['xmv_5'].nunique()} distinct value  (expect dropped)")
dirty.to_parquet("data/tep_dirty.parquet", engine="pyarrow", compression="snappy")
"""),

    md("""
## 3. The pipeline in pandas (eager)

Four stages: load, drop the columns that are constant or more than half missing,
impute the rest with each column's median, and aggregate to the mean of every
surviving sensor per fault. pandas runs each stage immediately and holds the
result in memory before the next one starts.
"""),

    code("""
ID_COLS = ["faultNumber", "simulationRun", "sample"]
MISSING_MAX = 0.5


def pipeline_pandas(path):
    df = pd.read_parquet(path)                                    # 1. load
    sensors = [c for c in df.columns if c not in ID_COLS]
    nunique = df[sensors].nunique(dropna=True)
    null_frac = df[sensors].isna().mean()
    keep = [c for c in sensors
            if nunique[c] > 1 and null_frac[c] <= MISSING_MAX]    # 2. drop
    df = df[ID_COLS + keep].copy()
    df[keep] = df[keep].fillna(df[keep].median())                 # 3. impute
    return (df.groupby("faultNumber")[keep].mean()                # 4. aggregate
              .reset_index().sort_values("faultNumber"))


result_pd = pipeline_pandas("data/tep_dirty.parquet")
print(f"kept {result_pd.shape[1] - 1} of 52 sensors after cleaning")
result_pd.iloc[:3, :6]
"""),

    md("""
## 4. The same pipeline in Polars (lazy)

`scan_parquet` reads nothing; it builds a plan. The drop stage needs one cheap
pass to learn which columns are constant or too sparse, then the rest of the
plan, select, impute, group-by, stays lazy until `.collect()` runs it in a
single optimized pass.
"""),

    code("""
def pipeline_polars(path):
    lf = pl.scan_parquet(path)                                    # 1. load (lazy)
    stats = (lf.select(
                 pl.len().alias("_n"),
                 pl.exclude(ID_COLS).n_unique().name.suffix("_nu"),
                 pl.exclude(ID_COLS).null_count().name.suffix("_nz"))
               .collect().row(0, named=True))                     # one small pass
    n = stats["_n"]
    sensors = [c for c in lf.collect_schema().names() if c not in ID_COLS]
    keep = [c for c in sensors
            if stats[f"{c}_nu"] > 1 and stats[f"{c}_nz"] / n <= MISSING_MAX]
    plan = (lf.select(ID_COLS + keep)                             # 2. drop
              .with_columns(pl.col(keep).fill_null(pl.col(keep).median()))  # 3. impute
              .group_by("faultNumber").agg(pl.col(keep).mean())   # 4. aggregate
              .sort("faultNumber"))
    return plan.collect(), plan


result_pl, plan = pipeline_polars("data/tep_dirty.parquet")
result_pl.select(result_pl.columns[:6]).head(3)
"""),

    md("""
Both engines return the same table, one row per fault. A quick check:
"""),

    code("""
a = result_pd.set_index("faultNumber").sort_index()
b = result_pl.to_pandas().set_index("faultNumber").sort_index()
print("max abs difference between pandas and Polars:",
      float(np.abs(a[b.columns.drop(["simulationRun", "sample"], errors="ignore")]
                   .sub(b[b.columns.drop(["simulationRun", "sample"], errors="ignore")]))
            .to_numpy().max()))
"""),

    md("""
## 5. Read the query plan

The optimized plan shows the work Polars will actually do. Compare it with the
unoptimized plan and you can see the column selection pushed down into the
Parquet scan, so only the columns the pipeline uses are read off disk.
"""),

    code("""
print(plan.explain(format="tree"))
"""),

    md("""
## 6. Time them

Warm each pipeline once, then take the best of a few runs, so we compare
steady-state work rather than first-call overhead.
"""),

    code("""
def bench(fn, n=3):
    fn()                                             # warm up
    best = float("inf")
    for _ in range(n):
        s = time.perf_counter()
        fn()
        best = min(best, (time.perf_counter() - s) * 1000)
    return best


pd_ms = bench(lambda: pipeline_pandas("data/tep_dirty.parquet"))
pl_ms = bench(lambda: pipeline_polars("data/tep_dirty.parquet")[0])
print(f"pandas eager   {pd_ms:8.0f} ms")
print(f"Polars lazy    {pl_ms:8.0f} ms   ({pd_ms / pl_ms:.1f}x)")
"""),

    md("""
Both pipelines produce the same per-fault signatures. Polars is usually faster
here because it fuses the middle stages and reads only the columns it needs,
across every core at once, while pandas materializes a new table after each
stage. The exact ratio is a property of this workload and this machine, so the
habit to carry is measuring your own pipeline, not the number on this slide.

---

## Takeaway

A pipeline is load, clean, transform, aggregate, and how you write it decides
whether it is fast, correct, and safe to re-run. Vectorized dataframe operations
replace slow Python loops; Polars adds multithreading and a query optimizer on
top of that; and building the work from small, pure stages that cache to Parquet
is what makes it survivable. pandas or Polars, the durable skills are the same:
vectorize, stage the work honestly, and measure before you optimize.
"""),
]

# The Colab bootstrap cell, injected from the notebook's own imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells = with_colab_cell(cells, OUT)

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT} ({len(cells)} cells)")
