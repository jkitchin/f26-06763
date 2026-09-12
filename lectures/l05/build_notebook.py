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

We build one pipeline twice, once in **pandas** and once in **Polars**, then
time both.

Four stages: **load, drop bad columns, fill gaps, average by fault.**

The simulator's data is clean, so cell 2 breaks it on purpose. Otherwise the
cleaning stages would have nothing to do.

> Data: [Tennessee Eastman process](https://doi.org/10.7910/DVN/6C3JR1)
> (Rieth et al. 2017, CC0). 52 sensors, normal operation plus faults 1 to 20.
"""),

    md("""
## 1. Load the readings

Downloads once, then caches a Parquet file. Every later run reads the cache and
downloads nothing.

We keep 50 of the 500 runs per fault, and drop each run's first 20 samples
because the fault has not been injected yet.
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
    # 1. Already cached? Then we are done.
    if PARQUET.exists():
        return pd.read_parquet(PARQUET)

    # 2. Download the .RData file, once. (Dataverse rejects urllib's default
    #    user agent, so we set a browser one and stream it to disk.)
    url, obj = SOURCE[FAULT_FREE]
    raw = DATA / (PARQUET.stem + ".RData")
    if not raw.exists():
        print(f"fetching {url} (one time, ~{'25' if FAULT_FREE else '494'} MB)")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(raw, "wb") as f:
            shutil.copyfileobj(r, f)

    # 3. Read it into a dataframe. pyreadr reads R files without installing R.
    df = pyreadr.read_r(str(raw))[obj]

    # 4. R stores all numbers as floats, so put the three ID columns back to int.
    for c in ("faultNumber", "simulationRun", "sample"):
        df[c] = df[c].astype(int)

    # 5. Shrink it: keep 50 runs per fault, and drop each run's first 20
    #    samples, where the fault has not started yet.
    if not FAULT_FREE:
        df = df[(df["simulationRun"] <= RUNS_KEPT) & (df["sample"] > 20)]
    df = df.reset_index(drop=True)

    # 6. Save as Parquet so the next run skips steps 2 to 5.
    df.to_parquet(PARQUET, engine="pyarrow", compression="snappy")
    return df


readings = load_tep()
print(f"{len(readings):,} rows, {readings.shape[1]} columns, "
      f"{readings.faultNumber.nunique()} fault classes")
readings.head(3)
"""),

    md("""
## 2. Break the data, on purpose

The simulator has no missing values and no dead sensors, so we damage a **copy**
and say exactly how. All three defects are ones real sensor logs have:
a sensor that mostly stopped reporting, one that dropped a few readings, and one
stuck at a single value.
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
## 3. The pipeline in pandas

pandas runs each line as it reaches it, and holds the whole table in memory
between stages.
"""),

    code("""
ID_COLS = ["faultNumber", "simulationRun", "sample"]
MISSING_MAX = 0.5


def pipeline_pandas(path):
    # 1. LOAD: read the whole file into memory.
    df = pd.read_parquet(path)

    # 2. DROP: keep a sensor only if it changes at all, and is less than half
    #    missing. A frozen sensor tells us nothing; a mostly-empty one is guesswork.
    sensors = [c for c in df.columns if c not in ID_COLS]
    nunique = df[sensors].nunique(dropna=True)
    null_frac = df[sensors].isna().mean()
    keep = [c for c in sensors
            if nunique[c] > 1 and null_frac[c] <= MISSING_MAX]
    df = df[ID_COLS + keep].copy()

    # 3. FILL: put each surviving column's median into its remaining gaps.
    df[keep] = df[keep].fillna(df[keep].median())

    # 4. AVERAGE: one row per fault, each sensor averaged over that fault.
    return (df.groupby("faultNumber")[keep].mean()
              .reset_index().sort_values("faultNumber"))


result_pd = pipeline_pandas("data/tep_dirty.parquet")
print(f"kept {result_pd.shape[1] - 1} of 52 sensors after cleaning")
result_pd.iloc[:3, :6]
"""),

    md("""
## 4. The same pipeline in Polars

Same four stages. The difference: `scan_parquet` reads nothing, it builds a
plan, and nothing runs until `.collect()`.

We do need one small pass up front to find out which columns to drop. Everything
after that stays a plan.
"""),

    code("""
def pipeline_polars(path):
    # 1. LOAD: builds a plan. Reads nothing yet.
    lf = pl.scan_parquet(path)

    # 2a. To decide what to drop we need real numbers, so run one small pass:
    #     how many rows, and per sensor, how many distinct values and nulls.
    stats = (lf.select(
                 pl.len().alias("_n"),
                 pl.exclude(ID_COLS).n_unique().name.suffix("_nu"),
                 pl.exclude(ID_COLS).null_count().name.suffix("_nz"))
               .collect().row(0, named=True))
    n = stats["_n"]

    # 2b. DROP: same rule as pandas. Changes at all, less than half missing.
    sensors = [c for c in lf.collect_schema().names() if c not in ID_COLS]
    keep = [c for c in sensors
            if stats[f"{c}_nu"] > 1 and stats[f"{c}_nz"] / n <= MISSING_MAX]

    # 3 and 4. FILL and AVERAGE, added to the plan. Still nothing has run.
    plan = (lf.select(ID_COLS + keep)
              .with_columns(pl.col(keep).fill_null(pl.col(keep).median()))
              .group_by("faultNumber").agg(pl.col(keep).mean())
              .sort("faultNumber"))

    # 5. RUN: now the whole plan executes, in one pass, using every core.
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

This prints what Polars actually decided to do. Look for the column list
appearing on the scan line: the selection moved down into the read, so the
columns we dropped are never loaded at all.
"""),

    code("""
print(plan.explain(format="tree"))
"""),

    md("""
## 6. Time them

Run each once to warm up, then take the best of three, so we are not timing
one-off startup costs.
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
Same answer from both. Polars is usually faster here because it reads only the
columns it needs, runs the middle stages together, and uses every core, while
pandas builds a fresh table after each stage.

The ratio you just measured belongs to this machine and this data. Measure your
own pipeline before rewriting it.

---

## Takeaway

Work on whole columns, not one row at a time. Build the pipeline from small
stages that each read a file and write a file, so a crash costs you one stage
instead of the whole run.
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
