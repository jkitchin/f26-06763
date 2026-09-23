#!/usr/bin/env python3
"""Generate lectures/l09/l09-regression.ipynb.

The last twenty minutes of the session, with questions. Two datasets, in five steps:

  1. concrete strength (Yeh 1998): load the data and count the mixes
  2. lock a test set of whole mixes
  3. fit the four model families with the same fit/predict, and score them under
     KFold and GroupKFold
  4. test the chosen model once
  5. NARX: Lecture 8's reactor-pressure table, from the miniproject's fault-free
     Tennessee Eastman file, fitted with a ridge ARX, an NN-NARX and a GP-NARX (on
     1,000 rows, because of the GP's O(N^3) cost)

The classification steps (the moons, the Tennessee Eastman fault classifier and the
faults it never saw) moved to Lecture 10 with that material: see
lectures/l10/build_classification_notebook.py.

Design notes:
  - Same data, splits, models and seeds as figures/make_figures.py, so the notebook
    reproduces the numbers in the notes (GroupKFold RMSE: linear, physics features 7.43, tree
    9.42, GP 7.17 MPa; GP test 5.39 MPa; NARX: ARX 4.71, NN-NARX 4.73, GP-NARX 4.76 kPa).
  - Only the fault-free Tennessee Eastman file is downloaded (25 MB): NARX needs no
    faulty runs.
  - pandas rather than Polars: the concrete file is .xls, and every step after the
    load is scikit-learn on NumPy arrays.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed
.ipynb carries no outputs and must run top to bottom.

    python3 lectures/l09/build_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l09-regression.ipynb"

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
# L9 demo: regression with scikit-learn

Two datasets, one interface.

1. **Concrete strength.** Predict the compressive strength of a concrete mix (MPa) from its
   recipe and its age, with four model families. Then score them two ways and see the
   ranking change.
2. **NARX.** Lecture 8's reactor-pressure forecast, with a network and a GP in place of the
   linear model.

Every model is used the same way: `model.fit(X_train, y_train)`, then `model.predict(X)`.
"""),

    code("""
import io, urllib.request, zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xlrd       # noqa: F401  pandas needs it to read the .xls file
import pyarrow    # noqa: F401  pandas needs it to read the Parquet file

from sklearn.model_selection import GroupShuffleSplit, KFold, GroupKFold, cross_val_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, FunctionTransformer
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.compose import TransformedTargetRegressor
from sklearn.tree import DecisionTreeRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
from sklearn.metrics import root_mean_squared_error, mean_absolute_error, r2_score

DATA = Path("data"); DATA.mkdir(exist_ok=True)
"""),

    md("""
## 1. Concrete: load the data

1,030 rows from Yeh (1998), on the UCI repository (CC BY 4.0). Seven ingredients in kg per
cubic metre, the age in days, and the strength in MPa. Downloaded once, 125 kB.
"""),

    code("""
XLS = DATA / "Concrete_Data.xls"
if not XLS.exists():
    url = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
    XLS.write_bytes(zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read()))
                    .read("Concrete_Data.xls"))

COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]      # MIX is the recipe; age varies within a mix

concrete = pd.read_excel(XLS)
concrete.columns = COLUMNS
concrete.describe().T[["mean", "std", "min", "max"]].round(1)
"""),

    md("""
**How many experiments is that?** Group the rows by their seven ingredients, ignoring the age.
"""),

    code("""
mix = concrete.groupby(MIX).ngroup().to_numpy()     # one integer per distinct mix
sizes = concrete.groupby(MIX).size()
print("rows:", len(concrete), "   distinct mixes:", mix.max() + 1)
print("mixes tested at more than one age:", (sizes > 1).sum(),
      f"holding {sizes[sizes > 1].sum() / len(concrete):.0%} of the rows")
print("rows that are exact copies of another row:", concrete.duplicated().sum())
"""),

    md("""
## 2. Lock the test set, by mix

20% of the mixes go into the test set and stay there until the very end. `GroupShuffleSplit`
keeps every row of a mix on one side.
"""),

    code("""
X = concrete[FEATURES].to_numpy()
y = concrete["strength_mpa"].to_numpy()

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.2,
    random_state=42,
)
train, test = next(splitter.split(X, y, groups=mix))
X_train, y_train, mix_train = X[train], y[train], mix[train]
X_test, y_test = X[test], y[test]
print(f"training: {len(train)} rows, {len(set(mix_train))} mixes")
print(f"test:     {len(test)} rows, {len(set(mix[test]))} mixes (not touched until step 4)")
"""),

    md("""
## 3. Four families, one interface

The same `fit` and `predict` for all of them. Two references first: the baseline that predicts
the mean, and a straight line. Then the line with two physics features, the log of the age and
the water/cement ratio (Abrams 1918). The network and the GP get a `StandardScaler` in a
`Pipeline`.
"""),

    code("""
import warnings
from sklearn.exceptions import ConvergenceWarning

# The network stops at its 5,000-iteration limit before L-BFGS declares convergence, and
# scikit-learn warns on every fit. Comment this line out to see the warning.
warnings.filterwarnings("ignore", category=ConvergenceWarning)

def engineered(X):
    \"\"\"The raw columns, plus log(age) and the water/cement ratio.\"\"\"
    X = np.asarray(X, float)
    return np.column_stack([X[:, :7], np.log(X[:, 7]), X[:, 3] / X[:, 0]])

kernel = ConstantKernel(1.0) * RBF(np.ones(8), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1))

models = {
    "Baseline: predict the mean": DummyRegressor(),
    "Linear": make_pipeline(StandardScaler(), LinearRegression()),
    "Linear, with physics features": make_pipeline(
        FunctionTransformer(engineered),
        StandardScaler(),
        LinearRegression(),
    ),
    "Decision tree": DecisionTreeRegressor(random_state=0),
    "Neural network": make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(16,),
            activation="tanh",
            solver="lbfgs",
            max_iter=5000,
            random_state=0,
        ),
    ),
    "Gaussian process": make_pipeline(
        StandardScaler(),
        GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=True,
            random_state=0,
            n_restarts_optimizer=2,
        ),
    ),
}
"""),

    md("""
Score every model by five-fold cross-validation, twice: folds of random rows (`KFold`) and
folds of whole mixes (`GroupKFold`). This cell takes a minute or two; the GP is most of it.
"""),

    code("""
def cv_rmse(model, cv, groups=None):
    scores = cross_val_score(
        model, X_train, y_train,
        cv=cv,
        groups=groups,
        scoring="neg_root_mean_squared_error",
    )
    return -scores.mean()

random_folds = KFold(
    n_splits=5,
    shuffle=True,
    random_state=0,
)
table = pd.DataFrame({
    "KFold": {name: cv_rmse(m, random_folds) for name, m in models.items()},
    "GroupKFold": {name: cv_rmse(m, GroupKFold(n_splits=5), mix_train) for name, m in models.items()},
}).round(2)
table
"""),

    md("""
**What to look for.** The baseline and the two linear models barely move between the columns:
they cannot memorize a mix. The tree, the network and the GP all get worse under `GroupKFold`, and
the tree most. Under `KFold` the tree beats the line with physics features. Under `GroupKFold` it loses
to it by 2 MPa.
"""),

    md("""
## 4. Test once

The GP has the lowest `GroupKFold` error, so it is the one we test. Fit it on all the training
rows, and score the held-out mixes once.
"""),

    code("""
gp = models["Gaussian process"].fit(X_train, y_train)
y_pred, y_std = gp.predict(X_test, return_std=True)
print(f"test RMSE {root_mean_squared_error(y_test, y_pred):.2f} MPa,"
      f" MAE {mean_absolute_error(y_test, y_pred):.2f},  R2 {r2_score(y_test, y_pred):.3f}")
print(f"test points within 2 predicted std: {np.mean(np.abs(y_test - y_pred) < 2 * y_std):.1%}")

plt.figure(figsize=(5, 4.5))
plt.errorbar(
    y_test, y_pred,
    yerr=2 * y_std,
    fmt="o",
    ms=4,
    ecolor="0.75",
    alpha=0.9,
)
plt.plot([0, 85], [0, 85], "k--", lw=1)
plt.xlabel("Measured strength (MPa)"); plt.ylabel("Predicted strength (MPa)")
plt.title("Parity plot, held-out mixes")
plt.tight_layout()
"""),

    md("""
The test RMSE comes out lower than the `GroupKFold` estimate. A test set of 86 mixes is one
random draw; with `random_state=0` to `9` in step 2 the same GP scores between 5.45 and 7.42 MPa.
"""),

    md("""
## 5. NARX: Lecture 8's table, three models

Reactor pressure `xmeas_7`, 30 minutes ahead (`H = 10` samples), from ten lags of pressure and
the eleven valve positions at time $t$. Train on fault-free runs 1 to 300, test on runs 401 to
500, exactly as in Lecture 8. The first time, the miniproject's fault-free plant file downloads
25 MB.
"""),

    code("""
HOST = "https://kitchin-services.cheme.cmu.edu/f26-06763/data/"
PLANT = DATA / "tep_fault_free_training.parquet"
if not PLANT.exists():
    urllib.request.urlretrieve(HOST + PLANT.name, PLANT)
fault_free = pd.read_parquet(PLANT)

XMV = [f"xmv_{i}" for i in range(1, 12)]
LAGS, H = 10, 10
runs = {r: g.sort_values("sample") for r, g in fault_free.groupby("simulationRun")}

def narx_table(run_ids):
    \"\"\"Rows [y[t], ..., y[t-9], u[t]] and the target y[t+10], built inside each run.\"\"\"
    A, b = [], []
    for r in run_ids:
        y = runs[r]["xmeas_7"].to_numpy()
        U = runs[r][XMV].to_numpy()
        t = np.arange(LAGS - 1, len(y) - H)
        A.append(np.column_stack([y[t - k] for k in range(LAGS)] + [U[t, j] for j in range(11)]))
        b.append(y[t + H])
    return np.vstack(A), np.concatenate(b)

A_train, b_train = narx_table(range(1, 301))
A_test, b_test = narx_table(range(401, 501))
print("training rows:", len(b_train), "  test rows:", len(b_test))
"""),

    md("""
The same `fit` and `predict` for all three. The network scales its **target** as well as its
inputs (pressure sits near 2,705 kPa with a spread of about 8 kPa). The GP gets 1,000 of the
144,300 training rows: its cost grows as $N^3$, and this cell takes about half a minute.
"""),

    code("""
arx = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
nn_narx = TransformedTargetRegressor(          # scale the target, not only the inputs
    regressor=make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(32,),
            activation="tanh",
            solver="adam",
            max_iter=500,
            early_stopping=True,
            random_state=0,
        ),
    ),
    transformer=StandardScaler(),
)
narx_kernel = ConstantKernel(1.0) * RBF(np.ones(21), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1))
gp_narx = make_pipeline(
    StandardScaler(),
    GaussianProcessRegressor(
        kernel=narx_kernel,
        normalize_y=True,
        random_state=0,
    ),
)

arx.fit(A_train, b_train)
nn_narx.fit(A_train, b_train)
subset = np.random.default_rng(0).choice(len(b_train), 1000, replace=False)
gp_narx.fit(A_train[subset], b_train[subset])

for name, m in [("ARX (ridge)", arx), ("NN-NARX", nn_narx), ("GP-NARX, 1,000 rows", gp_narx)]:
    print(f"{name:22s} test RMSE {root_mean_squared_error(b_test, m.predict(A_test)):.2f} kPa")
"""),

    md("""
**What to look for.** The three tie. Held at its operating point the plant is close to linear,
so the network and the GP have nothing extra to find. What the GP adds is a band. Try the network
without `TransformedTargetRegressor`, and watch it end up predicting the mean.
"""),

    code("""
A_run, b_run = narx_table([401])
hours = (np.arange(len(b_run)) + LAGS - 1 + H) * 3 / 60
mu, sd = gp_narx.predict(A_run, return_std=True)

plt.figure(figsize=(11, 3.8))
plt.fill_between(
    hours, mu - 2 * sd, mu + 2 * sd,
    alpha=0.2,
    label="GP-NARX, mean +/- 2 std",
)
plt.plot(hours, b_run, "k", label="Measured")
plt.plot(hours, arx.predict(A_run), "--", label="ARX")
plt.plot(hours, mu, label="GP-NARX mean")
plt.xlabel("Hours into test run 401"); plt.ylabel("Reactor pressure (kPa)")
plt.legend(
    ncol=2,
    fontsize=9,
)
plt.tight_layout()
"""),

    md("""
**Try it.**

1. In step 3, give the tree `max_depth=6`. Does it close the gap between `KFold` and `GroupKFold`?
2. In step 2, change `random_state`. How much does the test RMSE move?
3. In step 5, remove `TransformedTargetRegressor` from the network. What does it predict?
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
