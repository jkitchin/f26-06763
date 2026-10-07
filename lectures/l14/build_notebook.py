#!/usr/bin/env python3
"""Generate lectures/l14/l14-uq-bayesopt.ipynb, the L14 worked example.

On the concrete strength dataset: Lecture 9's Gaussian process, a five-network ensemble and
split conformal prediction, with their coverage on the grouped test split and on an
extrapolation split; then Bayesian optimization of a mix design with expected improvement
written out by hand, against random search, and the same search with Optuna's GPSampler.

It follows figures/make_figures.py (groups uq and bench) with the same seeds and splits, so the
numbers it prints are the numbers the notes quote (the BO comparison uses 5 seeds here, 30 there).

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed copy
carries real output. After regenerating, execute it and refresh the Colab cell:

    python3 lectures/l14/build_notebook.py
    cd lectures/l14 && uv run --no-project --python 3.12 --with numpy --with pandas --with xlrd \
        --with scikit-learn --with scipy --with matplotlib --with optuna --with torch --with greenlet \
        --with ipywidgets --with nbclient --with nbformat --with ipykernel python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l14-uq-bayesopt.ipynb', as_version=4)
NotebookClient(nb, timeout=1200, resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l14-uq-bayesopt.ipynb')
"
    python3 tools/colab_setup.py --write "$PWD/lectures/l14/l14-uq-bayesopt.ipynb"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l14-uq-bayesopt.ipynb"
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells, n = [], 0


def md(text):
    global n
    n += 1
    cells.append({"cell_type": "markdown", "id": f"md-{n:02d}", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    global n
    n += 1
    cells.append({"cell_type": "code", "id": f"code-{n:02d}", "execution_count": None,
                  "metadata": {}, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


md("""
# L14 worked example: uncertainty and Bayesian optimization on the concrete strength dataset

**scikit-learn** fits the Gaussian process (GP) and the networks, as in Lecture 9:
https://scikit-learn.org.

**Optuna** runs the Bayesian optimization at the end, with its `GPSampler`:
https://optuna.readthedocs.io. Lecture 10 used Optuna with its default sampler; this sampler
also needs `torch`, which Colab already has.

The plan:

1. Three ways to get a 95% prediction interval for the strength of a mix.
2. Check how often each interval contains the measured strength, on two test sets.
3. Use the GP to choose which mixes to test, against choosing them at random.

> Companion notes: [`notes.md`](notes.md).
""")
md("""
## 1. Load the concrete strength dataset, and lock the split

One row per specimen. `groups` numbers the mixes, so that every row of a mix stays on the
same side of a split, exactly as in Lecture 9.
""")
code("""
import io
import urllib.request
import warnings
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern, WhiteKernel
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=ConvergenceWarning)

DATA = Path("data")
DATA.mkdir(exist_ok=True)
XLS = DATA / "Concrete_Data.xls"
if not XLS.exists():
    url = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
    XLS.write_bytes(
        zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read())).read("Concrete_Data.xls")
    )

COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]
concrete = pd.read_excel(XLS)
concrete.columns = COLUMNS
X = concrete[FEATURES].to_numpy()
y = concrete["strength_mpa"].to_numpy()
groups = concrete.groupby(MIX).ngroup().to_numpy()

splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.2,
    random_state=42,
)
train, test = next(splitter.split(X, y, groups))
print(f"{len(train)} training rows, {len(test)} test rows")
""")
md("""
## 2. The aleatoric floor: replicate specimens

Some settings (the same mix at the same age) were tested more than once. Their scatter is
noise no model can predict away.
""")
code("""
same = concrete.groupby(FEATURES)["strength_mpa"].agg(["size", "std"])
rep = same[same["size"] > 1]
pooled = np.sqrt((rep["std"] ** 2 * (rep["size"] - 1)).sum() / (rep["size"] - 1).sum())
print(f"{len(rep)} settings tested more than once ({int(rep['size'].sum())} rows): "
      f"pooled scatter {pooled:.2f} MPa")
""")
md("""
## 3. Three intervals

- `gp_model()` is Lecture 9's GP: a scaler, then a GP with one length scale per input and a
  noise term (`WhiteKernel`). `predict(X, return_std=True)` returns the mean and the standard
  deviation, which includes the noise.
- `net(seed)` is Lecture 9's network, one hidden layer of 16 tanh units, started from `seed`.
- `intervals(train, test)` fits all three methods on the training rows and returns, for each, the
  centre and the half-width of the 95% interval on the test rows. For split conformal it first
  sets aside a quarter of the training mixes to calibrate the width.
""")
code("""
def gp_model():
    return make_pipeline(
        StandardScaler(),
        GaussianProcessRegressor(
            kernel=ConstantKernel(1.0) * RBF(np.ones(8), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1)),
            normalize_y=True,
            random_state=0,
            n_restarts_optimizer=2,
        ),
    )


def net(seed):
    return make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(16,),
            activation="tanh",
            solver="lbfgs",
            max_iter=5000,
            random_state=seed,
        ),
    )


def intervals(tr, te, alpha=0.05):
    out = {}
    gp = gp_model().fit(X[tr], y[tr])
    mu, sd = gp.predict(X[te], return_std=True)
    out["Gaussian process"] = (mu, 1.96 * sd)

    preds = np.array([net(s).fit(X[tr], y[tr]).predict(X[te]) for s in range(5)])
    out["ensemble spread"] = (preds.mean(0), 1.96 * preds.std(0))

    fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0)
                        .split(X[tr], y[tr], groups[tr]))
    fit_i, cal_i = tr[fit_i], tr[cal_i]
    nets = [net(s).fit(X[fit_i], y[fit_i]) for s in range(5)]
    scores = np.abs(y[cal_i] - np.mean([m.predict(X[cal_i]) for m in nets], 0))
    k = len(scores)
    q = np.quantile(scores, min(1.0, np.ceil((k + 1) * (1 - alpha)) / k), method="higher")
    out["split conformal"] = (np.mean([m.predict(X[te]) for m in nets], 0), np.full(len(te), q))
    noise = np.sqrt(gp[-1].kernel_.k2.noise_level) * gp[-1]._y_train_std
    print(f"  GP noise term {noise:.2f} MPa; conformal calibration rows {k}, q = {q:.2f} MPa")
    return out


def report(tr, te, name):
    print(name)
    for method, (centre, half) in intervals(tr, te).items():
        picp = np.mean(np.abs(y[te] - centre) < half)
        print(f"  {method:18s} coverage {picp:5.0%}   mean width {2 * half.mean():5.1f} MPa")
""")
md("""
## 4. Coverage on two test sets

The **grouped split** is Lecture 9's. The **extrapolation split** holds out the 20% of mixes
with the lowest water/cement ratio: the strongest mixes, where a design loop will push.
""")
code("""
report(train, test, "grouped split")

wc = (concrete["water"] / concrete["cement"]).groupby(groups).mean()
held = wc[wc <= wc.quantile(0.2)].index
te2 = np.flatnonzero(np.isin(groups, held))
tr2 = np.flatnonzero(~np.isin(groups, held))
print(f"\\nheld out: mean strength {y[te2].mean():.1f} MPa; kept: {y[tr2].mean():.1f} MPa")
report(tr2, te2, "extrapolation split")
""")
md("""
**What to read in the output**

- On the grouped split the GP and conformal intervals cover about 95%. The ensemble's spread
  covers far less: it is the epistemic part only.
- On the strongest mixes every method covers less than it claims. Conformal falls furthest: the
  strong mixes are not exchangeable with its calibration mixes.

## 5. Bayesian optimization of a mix

The "lab" is Lecture 9's GP fitted to all 1,030 rows, standing in for the 28-day test.
`lab(u)` takes designs scaled to $[0, 1]$ for cement, slag, water and superplasticizer, between
the 5th and 95th percentiles of the 28-day mixes, with the other ingredients at their medians.
""")
code("""
emulator = gp_model().fit(X, y)
d28 = concrete[concrete.age_days == 28]
fixed = d28[FEATURES].median().to_numpy()
DESIGN = ["cement", "slag", "water", "superplasticizer"]
idx = [FEATURES.index(c) for c in DESIGN]
lo = d28[DESIGN].quantile(0.05).to_numpy()
hi = d28[DESIGN].quantile(0.95).to_numpy()


def lab(u):
    rows = np.tile(fixed, (len(u), 1))
    rows[:, idx] = lo + u * (hi - lo)
    return emulator.predict(rows)


print({c: (round(a), round(b)) for c, a, b in zip(DESIGN, lo, hi)})
""")
md("""
**Expected improvement**, for maximization, with $f^*$ the best strength so far:

$$
\\text{EI}(x) = \\big(\\mu(x) - f^*\\big)\\,\\Phi(z) + \\sigma(x)\\,\\phi(z), \\qquad z = \\frac{\\mu(x) - f^*}{\\sigma(x)}
$$

`bo(seed)` starts from 5 random mixes, then 20 times: fits a GP to the mixes tested so far,
scores 4,000 random candidates by EI, and tests the best one. `random_search(seed)` tests 25
random mixes. Both return the best strength found after each test.
""")
code("""
def expected_improvement(mu, sd, best):
    sd = np.maximum(sd, 1e-9)
    z = (mu - best) / sd
    return (mu - best) * norm.cdf(z) + sd * norm.pdf(z)


def bo(seed, n_init=5, budget=25):
    rng = np.random.default_rng(seed)
    U = rng.random((n_init, 4))
    Y = lab(U)
    for _ in range(budget - n_init):
        gp = GaussianProcessRegressor(
            kernel=ConstantKernel(1.0) * Matern(np.ones(4), (1e-2, 1e2), nu=2.5)
            + WhiteKernel(1e-3, (1e-6, 1e-1)),
            normalize_y=True,
            random_state=seed,
        ).fit(U, Y)
        candidates = rng.random((4000, 4))
        mu, sd = gp.predict(candidates, return_std=True)
        best_candidate = candidates[expected_improvement(mu, sd, Y.max()).argmax()]
        U = np.vstack([U, best_candidate])
        Y = np.append(Y, lab(best_candidate[None, :]))
    return np.maximum.accumulate(Y), U[Y.argmax()]


def random_search(seed, budget=25):
    rng = np.random.default_rng(seed)
    return np.maximum.accumulate(lab(rng.random((budget, 4))))


runs_bo = [bo(s) for s in range(5)]
runs_rand = [random_search(s) for s in range(5)]
for s in range(5):
    print(f"seed {s}: BO best {runs_bo[s][0][-1]:.1f} MPa, random best {runs_rand[s][-1]:.1f} MPa")

fig, ax = plt.subplots(figsize=(8, 4))
for s in range(5):
    ax.plot(range(1, 26), runs_bo[s][0], color="C0", alpha=0.7, label="BO (EI)" if s == 0 else None)
    ax.plot(range(1, 26), runs_rand[s], color="0.6", alpha=0.7, label="random search" if s == 0 else None)
ax.set_xlabel("mixes tested")
ax.set_ylabel("best strength so far (MPa)")
ax.legend()
plt.show()
""")
md("""
## 6. Check the answer with the uncertainty

The best mix BO found, back in kilograms per cubic meter, with the emulator's 95% interval.
""")
code("""
u_best = runs_bo[0][1]
row = fixed.copy()
row[idx] = lo + u_best * (hi - lo)
mean, sd = emulator.predict(row[None, :], return_std=True)
print({c: round(v) for c, v in zip(DESIGN, row[idx])})
print(f"predicted {mean[0]:.1f} +/- {1.96 * sd[0]:.1f} MPa; strongest specimen ever tested {y.max():.1f} MPa")
""")
md("""
The optimizer found where the emulator is most optimistic, far from any tested mix, and the
wide interval says so. In a real campaign the next step is to cast that mix and add the result.

## 7. The same search in Optuna

- `trial.suggest_float(name, low, high)` lets the sampler choose a value in the range.
- `optuna.samplers.GPSampler(n_startup_trials=5)` samples 5 mixes at random, then lets a GP with
  an acquisition function choose.
""")
code("""
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)


def objective(trial):
    u = np.array([
        (trial.suggest_float(c, a, b) - a) / (b - a) for c, a, b in zip(DESIGN, lo, hi)
    ])
    return float(lab(u[None, :])[0])


study = optuna.create_study(
    direction="maximize",
    sampler=optuna.samplers.GPSampler(
        seed=0,
        n_startup_trials=5,
    ),
)
study.optimize(
    objective,
    n_trials=25,
)
print(f"Optuna GPSampler, 25 trials: best {study.best_value:.1f} MPa")
print({k: round(v) for k, v in study.best_params.items()})
""")
md("""
## Try it

- Change `alpha` in `intervals` to 0.2 and check that the 80% intervals cover about 80% on the
  grouped split.
- Restrict the design box to the middle of the data (25th to 75th percentile). Does BO still
  land on a mix the emulator is unsure about?
- Replace expected improvement with $\\mu + 3\\sigma$ (an upper confidence bound) in `bo`. Does it
  find the best mix in fewer or more tests?
""")

cells = with_colab_cell(cells, OUT)
nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT.name} ({len(cells)} cells)")
