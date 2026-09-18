#!/usr/bin/env python3
"""Generate lectures/l08/l08-forecasting.ipynb.

The last twenty minutes of the session, with questions, after the lecture. It does
four things on reactor pressure (`xmeas_7`) from the Rieth et al. (2017) fault-free
training file, and stops:

  1. build the horizon table: L7's `build_arx`, extended with `h` and `.over(RUN)`
  2. score persistence and the mean across horizons on held-out runs
  3. fit direct and recursive ridge models and plot error against horizon
  4. on single runs, shuffled KFold against TimeSeriesSplit(gap=h) for a random
     forest, where the shuffled score beats persistence and the honest one does not

Design notes:
  - Self-contained. L7 no longer writes a Parquet file, and a student who missed L7
    should still be able to run this. The fault-free file is 25 MB.
  - Same channel, lags, split and model settings as figures/make_figures.py, so the
    notebook reproduces the numbers in the notes (persistence 5.82, mean 7.57,
    direct 5.02, recursive 5.19 kPa at h = 10; forest 4.3 shuffled against 6.9
    time-ordered on runs 1-10). The notebook uses scikit-learn's Ridge with
    alpha = 1.0 on standardized columns, which is the same model as the figure
    script's hand-written ridge to the second decimal.
  - The residual detector is notes-only: the faulty file is 500 MB.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed
.ipynb carries no outputs and must run top to bottom.

    python3 lectures/l08/build_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l08-forecasting.ipynb"

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
# L8 demo: forecasting reactor pressure, and scoring it honestly

We do four things.

1. Build a table whose target is `h` samples in the future.
2. Score two free forecasts, **persistence** and **the mean**, at several horizons.
3. Fit **direct** and **recursive** models and see which holds up further out.
4. Score one model two ways, with a **shuffled** split and a **time-ordered** split.

One channel throughout: reactor pressure `xmeas_7`, in kPa, from the Tennessee Eastman
fault-free simulations. Samples are 3 minutes apart, so `h = 10` is thirty minutes.
"""),

    code("""
import numpy as np
import polars as pl
import matplotlib.pyplot as plt

DT = 3.0                 # minutes between samples
Y = "xmeas_7"            # reactor pressure, kPa
RUN = "simulationRun"
XMV = [f"xmv_{i}" for i in range(1, 12)]
"""),

    md("""
## 1. Load the data

The fault-free training file holds 500 independent simulation runs of 500 samples each
(25 hours per run). It is downloaded once, about 25 MB.
"""),

    code("""
from pathlib import Path
import urllib.request, shutil

DATA = Path("data"); DATA.mkdir(exist_ok=True)
PARQUET = DATA / "tep_fault_free.parquet"

def load_fault_free():
    \"\"\"Read the fault-free Tennessee Eastman file, downloading it the first time.\"\"\"
    if PARQUET.exists():
        return pl.read_parquet(PARQUET)
    import pyreadr
    raw = DATA / "tep_fault_free.RData"
    if not raw.exists():
        url = "https://dataverse.harvard.edu/api/access/datafile/3031241"
        print(f"fetching {url} (one time, ~25 MB)")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as r, open(raw, "wb") as f:
            shutil.copyfileobj(r, f)
    pdf = pyreadr.read_r(str(raw))["fault_free_training"]
    for c in ("faultNumber", "simulationRun", "sample"):
        pdf[c] = pdf[c].astype(int)
    out = pl.from_pandas(pdf).sort(RUN, "sample")
    out.write_parquet(PARQUET)
    return out


tep = load_fault_free()
tep.select(RUN, "sample", Y, "xmv_1").head()
"""),

    code("""
print(tep.height, "rows,", tep[RUN].n_unique(), "runs")
print(f"pressure: mean {tep[Y].mean():.1f} kPa, standard deviation {tep[Y].std():.2f} kPa")
"""),

    md("""
## 2. The horizon table

This is Lecture 7's `build_arx` with two changes. The target is `y[t+h]` instead of
`y[t+1]`, and every shift runs `.over(RUN)` so no row reaches into another run.

Everything in a row is known at time `t`. The valve positions are the ones at `t`,
because the future valve positions are not known when the forecast is made.
"""),

    code("""
def build_table(df, h, n_lags=10, valves=False):
    \"\"\"Features known at time t, and the target y[t+h], built inside each run.\"\"\"
    cols = {f"y[t-{k}]" if k else "y[t]": pl.col(Y).shift(k).over(RUN)
            for k in range(n_lags)}
    if valves:
        cols |= {v: pl.col(v) for v in XMV}
    cols["target"] = pl.col(Y).shift(-h).over(RUN)
    table = df.select(RUN, **cols).drop_nulls()
    names = [c for c in cols if c != "target"]
    return table, names


table, names = build_table(tep, h=10)
table.head()
"""),

    md("""
Split **by run**: train on runs 1 to 300, test on runs 401 to 500. No test run
contributes anything to the fit.
"""),

    code("""
def split(table, names):
    train = table.filter(pl.col(RUN) <= 300)
    test = table.filter(pl.col(RUN) > 400)
    return (train.select(names).to_numpy(), train["target"].to_numpy(),
            test.select(names).to_numpy(), test["target"].to_numpy())


def rmse(e):
    return float(np.sqrt(np.mean(np.square(e))))
"""),

    md("""
## 3. Two free forecasts

- **Persistence**: `y[t+h] = y[t]`, the first feature column.
- **The mean**: the average pressure in the training runs.

Neither needs fitting. Watch which one wins as `h` grows.
"""),

    code("""
HORIZONS = [1, 2, 5, 10, 15, 20, 30, 40]
rows = []
for h in HORIZONS:
    Xtr, ytr, Xte, yte = split(*build_table(tep, h))
    rows.append({"h": h, "minutes": h * DT,
                 "persistence": rmse(yte - Xte[:, 0]),
                 "mean": rmse(yte - ytr.mean())})
baselines = pl.DataFrame(rows)
baselines
"""),

    md("""
**Stop and predict.** Persistence starts about four times better than the mean. Where do
they cross? For a stationary series the answer is where the autocorrelation drops below
one half.
"""),

    md("""
## 4. Direct and recursive models

Both use the same ten lags and the same ridge regression inside a `Pipeline`, so the
scaler is fitted on training rows only.

- **Direct**: one model per horizon, trained on `y[t+h]`.
- **Recursive**: one model for `y[t+1]`, applied `h` times, feeding each prediction back in.
"""),

    code("""
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge


def ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=1.0))


# the one-step model the recursive forecaster reuses
Xtr1, ytr1, _, _ = split(*build_table(tep, 1))
one_step = ridge().fit(Xtr1, ytr1)


def recursive(X, h):
    \"\"\"Apply the one-step model h times, shifting each prediction into y[t].\"\"\"
    Z = X.copy()
    for _ in range(h):
        nxt = one_step.predict(Z)
        Z = np.column_stack([nxt, Z[:, :-1]])
    return nxt
"""),

    code("""
direct_err, recursive_err = [], []
for h in HORIZONS:
    Xtr, ytr, Xte, yte = split(*build_table(tep, h))
    direct_err.append(rmse(yte - ridge().fit(Xtr, ytr).predict(Xte)))
    recursive_err.append(rmse(yte - recursive(Xte, h)))

results = baselines.with_columns(direct=pl.Series(direct_err),
                                 recursive=pl.Series(recursive_err))
results.with_columns(
    skill=1 - pl.col("direct") / pl.min_horizontal("persistence", "mean"))
"""),

    code("""
m = results["minutes"]
fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(m, results["persistence"], "o-", label="persistence")
ax.plot(m, results["mean"], "s--", label="mean")
ax.plot(m, results["recursive"], "^-", label="recursive")
ax.plot(m, results["direct"], "o-", lw=2.5, label="direct")
ax.set_xlabel("horizon, minutes")
ax.set_ylabel("test RMSE, kPa")
ax.set_ylim(0, None)
ax.legend();
"""),

    md("""
Read the plot from left to right.

- At 3 minutes, the model barely beats persistence. That small gap is the honest version
  of an R-squared near 0.99.
- In the middle, neither free forecast is good, and the model earns the most.
- Far out, the recursive model has compounded its own errors past the mean.
"""),

    md("""
### Does knowing the valves help?

Add the eleven valve positions at time `t` to the direct model, at thirty minutes.
"""),

    code("""
Xtr, ytr, Xte, yte = split(*build_table(tep, 10, valves=True))
print(f"direct, pressure lags only : {direct_err[HORIZONS.index(10)]:.2f} kPa")
print(f"direct, lags and valves    : {rmse(yte - ridge().fit(Xtr, ytr).predict(Xte)):.2f} kPa")
"""),

    md("""
## 5. Shuffle, then don't

Now a single run, the situation of one stock, one meter or one plant historian. Score a
random forest two ways at `h = 10`:

- `KFold(shuffle=True)`: rows go to train and test at random.
- `TimeSeriesSplit(gap=h)`: train on the past, skip `h` samples, test on what follows.

Persistence is scored on the same test folds.
"""),

    code("""
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import KFold, TimeSeriesSplit

h = 10
schemes = {"shuffled KFold": KFold(5, shuffle=True, random_state=0),
           f"TimeSeriesSplit(gap={h})": TimeSeriesSplit(5, gap=h)}


def cv_scores(run):
    table, names = build_table(tep.filter(pl.col(RUN) == run), h, valves=True)
    X, y = table.select(names).to_numpy(), table["target"].to_numpy()
    out = {}
    for name, cv in schemes.items():
        forest, pers = [], []
        for tr, te in cv.split(X):
            model = RandomForestRegressor(100, n_jobs=-1, random_state=0).fit(X[tr], y[tr])
            forest.append(rmse(y[te] - model.predict(X[te])))
            pers.append(rmse(y[te] - X[te, 0]))
        out[name] = (np.mean(forest), np.mean(pers))
    return out
"""),

    code("""
rows = []
for run in range(1, 6):
    for name, (forest, pers) in cv_scores(run).items():
        rows.append({"run": run, "split": name, "forest": forest, "persistence": pers})

pl.DataFrame(rows).group_by("split").agg(pl.col("forest", "persistence").mean())
"""),

    md("""
**What happened.** Under the shuffled split, every test row has its neighbours from a few
minutes before *and after* in the training set, and the forest recalls them. The forest
looks far better than persistence. Under the time-ordered split, it is worse than
persistence, which is the number you would see in use.

**Try it.**

1. Replace the forest with `ridge()`. Does the shuffled score still flatter it?
2. Set `gap=0`. How much does the score change at `h = 10`? At `h = 40`?
3. Pick a white-noise channel, `xmeas_12`. What do persistence and the mean score there,
   and can any model beat the mean?
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
