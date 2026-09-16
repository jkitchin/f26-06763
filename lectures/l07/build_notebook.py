#!/usr/bin/env python3
"""Generate lectures/l07/l07-timeseries.ipynb.

DELIBERATELY SHORT. An earlier version ran 63 cells across two datasets and every
data-preparation topic in the notes, and it did not fit the session. This one does
four things and stops:

  1. load one run of Tennessee Eastman and build the clock
  2. build an ARX regressor matrix, twice, at two different lag depths
  3. recover a and b with lstsq, and convert them to a time constant and a gain
  4. show the one failure the method cannot fix: an input that never moved

Everything else (resampling, fill policy, rolling windows, the channel screen, the
group key) stays in the notes, where a student can read it at their own pace. The
demo's job is to make the regressor matrix concrete, because that is the idea the
room cannot get from prose.

Design notes:
  - The matrix is printed as a table before it is fitted. Seeing phi(t) laid out with
    its columns labelled is the whole point of running this live.
  - Numbers measured on 2026-09-16: one lag gives tau = 10.6 min, K = +0.1304 on
    fault 1 run 1; the deeper model gives a different tau, which is the honest answer
    and the reason lag depth needs a held-out score to choose.
  - The excitation failure uses a CONSTANT input, not a step. A step recovers the time
    constant fine, so "a step is not enough" would have been a false claim.
  - L7 fits, never scores. The output of every fit here is minutes and a gain.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed
.ipynb carries no outputs and must run top to bottom.

    python3 lectures/l07/build_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l07-timeseries.ipynb"

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
# L7 demo: building an ARX regressor matrix

We do four things.

1. Load the data and build a clock.
2. Build the **regressor matrix**, twice, with different numbers of past values.
3. Solve for the coefficients with `lstsq`, and turn them into a time constant.
4. Look at the one thing this method cannot recover from.

One loop throughout: the **A and C feed** of the Tennessee Eastman plant.
`xmv_4` is the valve. `xmeas_4` is the flow it sets. Samples are 3 minutes apart.
"""),

    code("""
import numpy as np
import polars as pl

DT = 3.0    # minutes between samples
"""),

    md("""
## 1. Load the data

Same file as Lecture 5. We take one run so there are no run boundaries to worry about.
"""),

    code("""
from pathlib import Path
import urllib.request, shutil

DATA = Path("data"); DATA.mkdir(exist_ok=True)
PARQUET = DATA / "tep.parquet"

def load_tep():
    \"\"\"Read the Tennessee Eastman file, downloading it the first time.\"\"\"
    if PARQUET.exists():
        return pl.read_parquet(PARQUET)
    import pyreadr
    raw = DATA / "tep.RData"
    if not raw.exists():
        url = "https://dataverse.harvard.edu/api/access/datafile/3031242"
        print(f"fetching {url} (one time, ~494 MB)")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(raw, "wb") as f:
            shutil.copyfileobj(r, f)
    pdf = pyreadr.read_r(str(raw))["faulty_training"]
    for c in ("faultNumber", "simulationRun", "sample"):
        pdf[c] = pdf[c].astype(int)
    pdf = pdf[(pdf.simulationRun <= 20) & (pdf["sample"] > 20)]
    out = pl.from_pandas(pdf.reset_index(drop=True))
    out.write_parquet(PARQUET)
    return out


tep = load_tep()

# one run, sorted in time
run = (tep.filter((pl.col("faultNumber") == 1) & (pl.col("simulationRun") == 1))
          .sort("sample")
          .select("sample", "xmv_4", "xmeas_4"))

print(f"{run.height} rows")
print(run.head(5))
"""),

    md("""
The file has no timestamps, only a counter. Build the clock so the spacing is explicit.
"""),

    code("""
run = run.with_columns(
    ts = pl.datetime(2026, 3, 16, 0, 0) + pl.duration(minutes=pl.col("sample") * DT)
)

# are the rows really 3 minutes apart?
print(run.select(pl.col("ts").diff().value_counts(sort=True)))
"""),

    md("""
## 2. The regressor matrix

An ARX model predicts the next flow from **past flows** and **past valve positions**:

$$y[t+1] = a_1 y[t] + a_2 y[t-1] + \\dots + b_1 u[t] + b_2 u[t-1] + \\dots$$

Each row of the **regressor matrix** holds the values on the right-hand side, for one
moment in time. Each column is one feature: one lag of `y`, or one lag of `u`.

We build it with `shift`. `shift(1)` copies a value down onto the next row, so it
becomes "the value one sample ago".
"""),

    code("""
def build_arx(df, n_a, n_b):
    \"\"\"Build an ARX regressor matrix.

    n_a = how many past flows to use
    n_b = how many past valve positions to use

    Returns (Phi, y, names) where each row of Phi lines up with one value in y.
    \"\"\"
    cols = {}

    # past flows:  y[t], y[t-1], ...
    for k in range(n_a):
        cols["y[t]" if k == 0 else f"y[t-{k}]"] = pl.col("xmeas_4").shift(k)

    # past valve positions:  u[t], u[t-1], ...
    for k in range(n_b):
        cols["u[t]" if k == 0 else f"u[t-{k}]"] = pl.col("xmv_4").shift(k)

    # what we are predicting: the NEXT flow
    cols["y[t+1]"] = pl.col("xmeas_4").shift(-1)

    table = df.with_columns(**cols).drop_nulls()

    names = [c for c in cols if c != "y[t+1]"]
    Phi = table.select(names).to_numpy()
    y = table["y[t+1]"].to_numpy()
    return Phi, y, names
"""),

    md("""
### Example A: one past flow, one past valve position

This is the simplest ARX model, and the one the notes derive from the ODE.
"""),

    code("""
Phi_A, y_A, names_A = build_arx(run, n_a=1, n_b=1)

print("columns:", names_A)
print(f"shape:   {Phi_A.shape}   ({Phi_A.shape[0]} rows, {Phi_A.shape[1]} features)")
print()

# look at the actual matrix, first 5 rows
print(pl.DataFrame(Phi_A[:5], schema=names_A).with_columns(
    pl.Series("-> y[t+1]", y_A[:5])
))
"""),

    md("""
Read one row across: *these were the flow and the valve at this moment, and that is what
the flow did next.* That is all a regressor matrix is.

### Example B: three past flows, two past valve positions

Same function, bigger numbers. The matrix gets wider.
"""),

    code("""
Phi_B, y_B, names_B = build_arx(run, n_a=3, n_b=2)

print("columns:", names_B)
print(f"shape:   {Phi_B.shape}   ({Phi_B.shape[0]} rows, {Phi_B.shape[1]} features)")
print()
print(pl.DataFrame(Phi_B[:5], schema=names_B).with_columns(
    pl.Series("-> y[t+1]", y_B[:5])
))
"""),

    md("""
Two things to notice.

**The matrix lost rows.** 480 rows went in. Example A came back with 479, example B with
477. A row needs all of its past *and* its answer, so the deeper the model, the more of
the record you throw away at each end.

**The columns look alike.** `y[t]` and `y[t-1]` are consecutive samples of a smooth
signal, so they are nearly the same column. We check that next.
"""),

    md("""
## 3. Solve for the coefficients

`lstsq` finds the coefficients that make the prediction error as small as possible.

One thing first: subtract the mean from every column. The flow sits around 8.8 and the
valve around 57.6, so most of each column is just the operating point. In process
control this is called working in **deviation variables**.
"""),

    code("""
def fit(Phi, y):
    \"\"\"Least-squares solve, in deviation variables. Returns the coefficients.\"\"\"
    Phi = Phi - Phi.mean(axis=0)
    y = y - y.mean()
    # rcond tells lstsq what counts as zero. Without it, a column that never
    # changes gets divided by rounding dust and returns nonsense.
    coef, *_ = np.linalg.lstsq(Phi, y, rcond=1e-8)
    return coef


coef_A = fit(Phi_A, y_A)
for name, c in zip(names_A, coef_A):
    print(f"  {name:>8s}  {c:+.4f}")
"""),

    md("""
Those two numbers are `a` and `b`. Now convert them into physics:

$$\\tau = \\frac{-\\Delta t}{\\ln a}, \\qquad K = \\frac{b}{1 - a}$$
"""),

    code("""
a, b = coef_A
tau = -DT / np.log(a)
K = b / (1 - a)

print(f"a = {a:.4f}   b = {b:.4f}")
print(f"time constant = {tau:.1f} minutes")
print(f"gain          = {K:+.4f} kscmh per % of valve")
"""),

    md("""
**Ten and a half minutes.** That is a number you can take to someone who knows that feed
line and ask whether it is believable. You cannot do that with an R-squared.
"""),

    md("""
### What the bigger model gives
"""),

    code("""
coef_B = fit(Phi_B, y_B)
for name, c in zip(names_B, coef_B):
    print(f"  {name:>8s}  {c:+.4f}")

# how alike are those lag columns?
C = np.corrcoef(Phi_B[:, :3].T)
print(f"\\ncorrelation between y[t] and y[t-1]: {C[0, 1]:+.3f}")
print(f"correlation between y[t] and y[t-2]: {C[0, 2]:+.3f}")
"""),

    md("""
Compare the first coefficient with the one-lag model. It was **0.753**. Now it is
**0.417**, and the memory it used to carry has been spread across `y[t-1]` and `y[t-2]`
instead. The three of them add up to about the same number.

That is what nearly-identical columns do. Each one can stand in for the others, so least
squares has no strong reason to prefer one split over another.

And notice what we lost: with one lag, the coefficient **was** the time constant. With
three, no single coefficient converts to anything. You traded a number you could check
against the plant for a slightly better fit.

More lags is not automatically better. Choosing how many needs a held-out score, which we
do not have today.
"""),

    md("""
## 4. The one thing this cannot fix

Everything above worked because the valve **moved**. Here is the same code on a stretch
where it did not.
"""),

    code("""
# freeze the valve at its average and see what the fit makes of it
frozen = run.with_columns(xmv_4 = pl.lit(run["xmv_4"].mean()))

Phi_f, y_f, names_f = build_arx(frozen, n_a=1, n_b=1)
coef_f = fit(Phi_f, y_f)

a_f, b_f = coef_f
print(f"a = {a_f:.4f}   b = {b_f:+.4f}")
print(f"gain = {b_f / (1 - a_f):+.4f}    (it was {K:+.4f} when the valve moved)")
"""),

    md("""
The gain comes back as zero. The model says the valve does nothing.

It is right about this data. The valve never moved, so nothing in the file says what
would have happened if it had. No extra features and no bigger model recover that,
because the information was never collected.

The fix is an experiment, not an algorithm.
"""),

    md("""
---

## Takeaway

A regressor matrix is just a table: **past values in the columns, the next value on the
right.** `shift` builds it and `lstsq` solves it.

The hard parts are not the solve. They are deciding which columns are allowed in
(leakage), how many to use (lag depth), and whether the data ever contained the answer
(did the input move).
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
