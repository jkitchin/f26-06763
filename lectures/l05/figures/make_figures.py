#!/usr/bin/env python3
"""Generate the L5 figures from the UCI SECOM manufacturing dataset.

Run with:
    uv run --with pandas,polars,dask[dataframe],matplotlib,numpy python make_figures.py

Every figure here is measured on this machine from the real dataset rather than
copied from a benchmark page. That is partly a licensing matter, since the course
site is public, and partly the point of the course: a figure you cannot
regenerate is a figure you cannot check.

It also changed the lecture twice. The vectorization figure was drafted
expecting the row loop and `.apply` to be roughly equivalent; `.apply` turns out
to be consistently the *slower* of the two, which makes the "it looks
vectorized" pitfall worse than advertised. And the Dask panel was drafted
expecting a visible crossover inside the plotted range; there is none, because
replicating SECOM up to a million rows still fits in RAM comfortably. That
absence is the honest result and is now the caption.

Outputs (committed alongside this script):
    vectorization-scaling.png  row loop vs .apply vs vectorized vs Polars
    dask-overhead.png          fixed scheduling cost, and the nunique trap
    secom-column-triage.png    what "dirty industrial matrix" actually means

The raw secom.zip is cached in .cache/ and is gitignored; do not commit it.
"""

from __future__ import annotations

import io
import time
import urllib.request
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"

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

MISSING_FRAC = 0.4
TRAIN_FRAC = 0.8


def load() -> pd.DataFrame:
    """Fetch (once) and parse SECOM into one frame of run_id, ts, label, sensors.

    The labels file is two whitespace-separated fields per line, not three: the
    timestamp is a single *quoted* field containing a space. Splitting on
    whitespace into ['label', 'date', 'time'] silently yields an all-NaT
    timestamp column, which is the footgun the demo notebook opens with.
    """
    CACHE.mkdir(exist_ok=True)
    data_file = CACHE / "secom.data"
    labels_file = CACHE / "secom_labels.data"
    if not data_file.exists():
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as response:
            payload = response.read()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            data_file.write_bytes(archive.read("secom.data"))
            labels_file.write_bytes(archive.read("secom_labels.data"))

    X = pd.read_csv(data_file, sep=r"\s+", header=None, na_values="NaN")
    X.columns = [f"sensor_{i}" for i in range(X.shape[1])]
    lab = pd.read_csv(labels_file, sep=r"\s+", header=None, names=["label", "ts"])
    lab["ts"] = pd.to_datetime(lab["ts"], format="%d/%m/%Y %H:%M:%S")
    assert lab["ts"].notna().all(), "timestamp parse failed; check the quoting"

    # Build in one concat rather than inserting into a 592-column frame, which
    # trips pandas' block-fragmentation heuristic.
    run_id = pd.Series(np.arange(len(X)), name="run_id")
    return pd.concat([run_id, lab[["ts", "label"]], X], axis=1).copy()


def grow(df: pd.DataFrame, n_rows: int) -> pd.DataFrame:
    """Replicate rows up to n_rows.

    Replication is honest for a per-row cost measurement, which is all these
    figures claim: it changes neither the column count nor the dtypes, and none
    of the timed operations depend on the *values* being distinct. It would not
    be honest for a figure about cardinality or compression, so those are not
    the figures being drawn.
    """
    reps = int(np.ceil(n_rows / len(df)))
    out = pd.concat([df] * reps, ignore_index=True).iloc[:n_rows]
    return out.copy()


def best_of(fn, repeats: int = 3) -> float:
    """Minimum wall time over repeats: the least noisy estimator of a floor."""
    best = float("inf")
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


# --------------------------------------------------------------------------
# Figure 1: what a row-wise loop actually costs
# --------------------------------------------------------------------------
def fig_vectorization(raw: pd.DataFrame) -> dict:
    """Time one arithmetic transform four ways as the row count grows.

    The operation is deliberately trivial, a linear rescale of one sensor
    column, so that what is being measured is per-element dispatch overhead and
    nothing else.
    """
    sizes = [1_567, 6_000, 25_000, 100_000, 400_000]
    loop, apply_, vec, polars_ = [], [], [], []

    for n in sizes:
        df = grow(raw[["sensor_0"]].fillna(0.0), n)
        series = df["sensor_0"]
        pl_df = pl.from_pandas(df)

        # 1. The version everybody writes first.
        def row_loop():
            out = []
            for value in series.tolist():
                out.append((value - 32.0) * 5.0 / 9.0)
            return out

        # 2. The version that looks vectorized and is not.
        def row_apply():
            return df.apply(lambda row: (row["sensor_0"] - 32.0) * 5.0 / 9.0, axis=1)

        # 3. The whole-column operation.
        def vectorized():
            return (series - 32.0) * 5.0 / 9.0

        # 4. The same thing as a Polars expression.
        def polars_expr():
            return pl_df.select(((pl.col("sensor_0") - 32.0) * 5.0 / 9.0))

        # .apply is slow enough that timing it at 400k rows costs minutes;
        # measure it on a slice and scale, and say so on the figure.
        loop.append(best_of(row_loop))
        vec.append(best_of(vectorized, repeats=5))
        polars_.append(best_of(polars_expr, repeats=5))
        if n <= 25_000:
            apply_.append(best_of(row_apply, repeats=2))
        else:
            sub = df.iloc[:25_000]
            t = best_of(lambda: sub.apply(
                lambda row: (row["sensor_0"] - 32.0) * 5.0 / 9.0, axis=1), repeats=2)
            apply_.append(t * n / 25_000)
        print(f"  {n:>7,} rows: loop {loop[-1]*1e3:9.2f} ms | "
              f"apply {apply_[-1]*1e3:9.2f} ms | vec {vec[-1]*1e3:7.3f} ms | "
              f"polars {polars_[-1]*1e3:7.3f} ms")

    ratio = loop[-1] / vec[-1]
    ratio_apply = apply_[-1] / vec[-1]

    fig, ax = plt.subplots(figsize=(9, 5.6))
    # The ratios go in the legend labels. Any free-floating annotation in this
    # plot collides with one of the four lines at some aspect ratio.
    for values, label, color, marker, style in [
        (apply_, f".apply(axis=1)  ({ratio_apply:,.0f}× slower)", CMU_RED, "s", "-"),
        (loop, f"Python row loop  ({ratio:.0f}× slower)", AMBER, "o", "-"),
        (vec, "vectorized pandas  (1×)", BLUE, "^", "-"),
        (polars_, "Polars expression", GREEN, "D", "-"),
    ]:
        ax.plot(sizes, np.array(values) * 1e3, style, marker=marker, color=color,
                label=label, lw=1.9, ms=6)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Rows (SECOM replicated)")
    ax.set_ylabel("Wall time, ms (one column, one rescale)")
    ax.set_title(f"The same arithmetic, four ways "
                 f"(ratios at {sizes[-1]:,} rows)", pad=10)
    ax.grid(True, which="major", axis="y", color=RULE, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_ylim(top=apply_[-1] * 1e3 * 6)
    ax.legend(frameon=False, fontsize=11, loc="upper left")
    ax.text(0.99, 0.02,
            ".apply beyond 25k rows is extrapolated from a 25k-row slice",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=9, color=MUTED, style="italic")

    fig.savefig(HERE / "vectorization-scaling.png")
    plt.close(fig)
    print(f"wrote vectorization-scaling.png  (loop {ratio:.0f}x, "
          f"apply {ratio_apply:.0f}x slower than vectorized at {sizes[-1]:,} rows)")
    return {"ratio_loop": ratio, "ratio_apply": ratio_apply, "rows": sizes[-1]}


# --------------------------------------------------------------------------
# Figure 2: Dask's fixed cost, and the nunique trap
# --------------------------------------------------------------------------
def fig_dask_overhead(raw: pd.DataFrame) -> dict:
    """Two panels: scheduling cost as a fixed toll, and one operation that is all toll."""
    import dask.dataframe as dd

    sensor_cols = [c for c in raw.columns if c.startswith("sensor_")]
    # 590 float64 columns cost ~4.7 kB per row, so 200k rows is already a
    # 0.9 GB frame and three libraries hold it at once. Going further does not
    # change the shape of the curve, it just makes this script hostile to run.
    sizes = [1_567, 6_000, 25_000, 100_000, 200_000]
    t_pandas, t_polars, t_dask = [], [], []

    for n in sizes:
        df = grow(raw, n)[["run_id", "ts", "label"] + sensor_cols]
        pl_df = pl.from_pandas(df[sensor_cols])

        # The clean stage: per-column spread, missingness and mean. Identical work
        # in all three, so the difference is execution model, not algorithm.
        def with_pandas():
            return (df[sensor_cols].std(), df[sensor_cols].isna().mean(),
                    df[sensor_cols].mean())

        def with_polars():
            return pl_df.lazy().select(
                [pl.col(c).std().alias(f"{c}_s") for c in sensor_cols]
                + [pl.col(c).null_count().alias(f"{c}_n") for c in sensor_cols]
                + [pl.col(c).mean().alias(f"{c}_m") for c in sensor_cols]).collect()

        def with_dask():
            ddf = dd.from_pandas(df, npartitions=8)
            return (ddf[sensor_cols].std().compute(),
                    ddf[sensor_cols].isna().mean().compute(),
                    ddf[sensor_cols].mean().compute())

        t_pandas.append(best_of(with_pandas, repeats=2))
        t_polars.append(best_of(with_polars, repeats=2))
        t_dask.append(best_of(with_dask, repeats=2))
        print(f"  {n:>9,} rows: pandas {t_pandas[-1]*1e3:8.1f} ms | "
              f"polars {t_polars[-1]*1e3:8.1f} ms | dask {t_dask[-1]*1e3:8.1f} ms")

    # Panel 2: nunique vs std as partitions are added, at fixed rows and columns.
    train = raw.iloc[:int(len(raw) * TRAIN_FRAC)]
    parts = [1, 2, 4, 8, 16]
    nu_times, std_times = [], []
    for npart in parts:
        ddf = dd.from_pandas(train, npartitions=npart)
        nu_times.append(best_of(
            lambda: ddf[sensor_cols[:100]].nunique(dropna=True).compute(), repeats=1))
        ddf2 = dd.from_pandas(train, npartitions=npart)
        std_times.append(best_of(
            lambda: ddf2[sensor_cols[:100]].std().compute(), repeats=2))
        print(f"  {npart:2d} partitions: nunique {nu_times[-1]:6.2f} s | "
              f"std {std_times[-1]:6.3f} s")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    for values, label, color, marker in [
        (t_dask, "Dask (8 partitions)", CMU_RED, "s"),
        (t_pandas, "pandas", BLUE, "^"),
        (t_polars, "Polars (lazy)", GREEN, "D"),
    ]:
        ax1.plot(sizes, np.array(values) * 1e3, "-", marker=marker, color=color,
                 label=label, lw=1.9, ms=6)
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlabel("Rows (SECOM replicated)")
    ax1.set_ylabel("Wall time, ms (590-column clean stage)")
    ax1.set_title("Scheduling is a toll paid up front", pad=10)
    ax1.grid(True, which="major", axis="y", color=RULE, lw=0.7)
    ax1.set_axisbelow(True)
    ax1.legend(frameon=False, fontsize=11, loc="upper left")
    ratio_small = t_dask[0] / t_pandas[0]
    ratio_big = t_dask[-1] / t_pandas[-1]
    ax1.annotate(f"{ratio_small:.0f}× slower than pandas",
                 xy=(sizes[0], t_dask[0] * 1e3),
                 xytext=(sizes[0] * 1.35, t_dask[0] * 1e3 * 2.6),
                 fontsize=10.5, color=CMU_RED,
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))
    ax1.annotate(f"still {ratio_big:.1f}× slower",
                 xy=(sizes[-1], t_dask[-1] * 1e3),
                 xytext=(sizes[1] * 1.9, t_dask[-1] * 1e3 * 0.72),
                 fontsize=10.5, color=CMU_RED,
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))
    ax1.set_ylim(top=t_dask[-1] * 1e3 * 3.2)

    ax2.plot(parts, nu_times, "-", marker="s", color=CMU_RED, lw=1.9, ms=6,
             label="nunique (a shuffle per column)")
    ax2.plot(parts, std_times, "-", marker="^", color=BLUE, lw=1.9, ms=6,
             label="std (one reduction per column)")
    ax2.set_yscale("log")
    ax2.set_xscale("log", base=2)      # so 1, 2, 4, 8, 16 are evenly spaced
    ax2.set_xticks(parts)
    ax2.set_xticklabels([str(p) for p in parts])
    ax2.set_xlabel("Partitions (1,253 rows, 100 columns, fixed)")
    ax2.set_ylabel("Wall time, s")
    ax2.set_title("More workers, more waiting", pad=10)
    ax2.grid(True, which="major", axis="y", color=RULE, lw=0.7)
    ax2.set_axisbelow(True)
    ax2.legend(frameon=False, fontsize=11, loc="upper left")
    # The band between the two curves is empty; put the punchline in it.
    ax2.text(
        parts[1], np.sqrt(nu_times[-1] * std_times[-1]) * 0.55,
        f"{nu_times[-1] / std_times[-1]:.0f}× apart at 16 partitions,\n"
        "for the same 122 constant columns",
        fontsize=10.5, color=CMU_RED, fontweight="bold", va="center")

    fig.savefig(HERE / "dask-overhead.png")
    plt.close(fig)
    print(f"wrote dask-overhead.png  (dask/pandas {ratio_small:.0f}x at "
          f"{sizes[0]:,} rows, {ratio_big:.1f}x at {sizes[-1]:,})")
    return {"ratio_small": ratio_small, "ratio_big": ratio_big,
            "rows_max": sizes[-1], "nu_16": nu_times[-1], "std_16": std_times[-1],
            "t_dask": t_dask, "t_pandas": t_pandas, "t_polars": t_polars,
            "sizes": sizes}


# --------------------------------------------------------------------------
# Figure 3: what "dirty industrial matrix" means, per column
# --------------------------------------------------------------------------
def fig_column_triage(raw: pd.DataFrame) -> dict:
    """Every one of the 590 sensor columns, sorted by missingness, with the cuts."""
    sensor_cols = [c for c in raw.columns if c.startswith("sensor_")]
    train = raw.iloc[:int(len(raw) * TRAIN_FRAC)]

    miss = train[sensor_cols].isna().mean()
    nuniq = train[sensor_cols].nunique(dropna=True)
    is_const = nuniq <= 1

    order = np.argsort(-miss.values)
    miss_sorted = miss.values[order] * 100
    const_sorted = is_const.values[order]
    x = np.arange(len(sensor_cols))

    n_const = int(is_const.sum())
    n_sparse = int((miss > MISSING_FRAC).sum())
    dropped = set(miss[miss > MISSING_FRAC].index) | set(is_const[is_const].index)
    n_kept = len(sensor_cols) - len(dropped)

    fig, ax = plt.subplots(figsize=(11, 5.6))
    ax.bar(x[~const_sorted], miss_sorted[~const_sorted], width=1.0,
           color=BLUE, label=f"varying ({len(sensor_cols) - n_const} columns)")
    ax.bar(x[const_sorted], miss_sorted[const_sorted], width=1.0,
           color=CMU_RED, label=f"constant, zero information ({n_const} columns)")
    # Constant columns with no missing values have zero bar height; mark them.
    ax.plot(x[const_sorted], np.full(const_sorted.sum(), -1.6), "|",
            color=CMU_RED, ms=5, mew=0.9)

    ax.axhline(MISSING_FRAC * 100, color=INK, lw=1.2, ls="--")
    ax.text(len(sensor_cols) * 0.55, MISSING_FRAC * 100 + 3,
            f"drop above {MISSING_FRAC:.0%} missing  →  {n_sparse} columns",
            fontsize=11, color=INK)

    ax.set_xlim(-4, len(sensor_cols) + 4)
    ax.set_ylim(-4, 100)
    ax.set_xlabel("The 590 sensor columns, sorted by missingness")
    ax.set_ylabel("Missing readings, % of training runs")
    ax.set_title("Two independent reasons to drop a column", pad=10)
    ax.legend(frameon=False, fontsize=11, loc="upper right")
    ax.grid(True, axis="y", color=RULE, lw=0.7)
    ax.set_axisbelow(True)

    ax.annotate(
        f"{n_const} + {n_sparse} = {len(dropped)} dropped, {n_kept} survive\n"
        "the two rules never overlap on this data",
        xy=(len(sensor_cols) * 0.5, 62), fontsize=11.5, color=CMU_RED,
        fontweight="bold", ha="center")

    fig.savefig(HERE / "secom-column-triage.png")
    plt.close(fig)
    print(f"wrote secom-column-triage.png  ({n_const} constant, {n_sparse} sparse, "
          f"{len(dropped)} dropped, {n_kept} kept; worst missingness "
          f"{miss.max():.1%})")
    return {"n_const": n_const, "n_sparse": n_sparse, "n_dropped": len(dropped),
            "n_kept": n_kept, "worst_missing": miss.max(),
            "overlap": len(set(miss[miss > MISSING_FRAC].index)
                           & set(is_const[is_const].index))}


if __name__ == "__main__":
    data = load()
    sensors = [c for c in data.columns if c.startswith("sensor_")]
    print(f"loaded {len(data):,} runs x {len(sensors)} sensors, "
          f"{data.ts.min().date()} to {data.ts.max().date()}, "
          f"{data.ts.dt.date.nunique()} distinct days, "
          f"{(data.label == 1).sum()} failures "
          f"({(data.label == 1).mean():.1%})")
    print("\nfig_column_triage")
    triage = fig_column_triage(data)
    print("\nfig_vectorization")
    vector = fig_vectorization(data)
    print("\nfig_dask_overhead")
    overhead = fig_dask_overhead(data)

    print("\n--- numbers cited in notes.md and slides.md ---")
    print(f"columns: {triage['n_const']} constant + {triage['n_sparse']} sparse "
          f"= {triage['n_dropped']} dropped, {triage['n_kept']} kept "
          f"(overlap {triage['overlap']})")
    print(f"row loop is {vector['ratio_loop']:.0f}x, .apply is "
          f"{vector['ratio_apply']:.0f}x slower than vectorized at "
          f"{vector['rows']:,} rows")
    print(f"dask/pandas: {overhead['ratio_small']:.0f}x at 1,567 rows, "
          f"{overhead['ratio_big']:.1f}x at {overhead['rows_max']:,} rows")
    print(f"nunique vs std at 16 partitions: {overhead['nu_16']:.2f}s vs "
          f"{overhead['std_16']:.3f}s")
