#!/usr/bin/env python3
"""Generate lectures/l14a/l14a-uq.ipynb, the L14a worked example.

On the concrete strength dataset, with Lecture 9's network and two splits (grouped, and the
strongest mixes held out): a five-network ensemble and the coverage of its raw spread; one
scale factor fitted on calibration mixes; split conformal and CV+ written by hand, then the
same with MAPIE; and four pycse regressors on a toy problem, inside and beyond their data.

It follows figures/make_figures.py (groups concrete and pycse) with the same seeds and splits,
so the numbers it prints are the numbers the notes quote (pycse here runs one seed, there five).

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed copy
carries real output. After regenerating, execute it and refresh the Colab cell:

    python3 lectures/l14a/build_notebook.py
    cd lectures/l14a && uv run --no-project --python 3.12 --with numpy --with pandas --with xlrd \
        --with scikit-learn --with scipy --with matplotlib --with "mapie==1.5.0" \
        --with "pycse==2.11.1" --with nbclient --with nbformat --with ipykernel python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l14a-uq.ipynb', as_version=4)
NotebookClient(nb, timeout=1800, resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l14a-uq.ipynb')
"
    python3 tools/colab_setup.py --write "$PWD/lectures/l14a/l14a-uq.ipynb"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l14a-uq.ipynb"
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
# L14a worked example: checking and fixing prediction intervals

**scikit-learn** fits the networks, as in Lecture 9: https://scikit-learn.org.

**MAPIE** runs conformal prediction around any scikit-learn model:
https://mapie.readthedocs.io. This notebook uses its version 1 API (`SplitConformalRegressor`,
`CrossConformalRegressor`, `confidence_level`); most tutorials online still use the older
`MapieRegressor`.

**pycse** has regressors with uncertainty built in: https://github.com/jkitchin/pycse. Its
`DPOSE` and `LLPRRegressor` run on JAX, which Colab already has.

The plan:

1. Train a five-network ensemble on the concrete strength dataset and measure how often its
   spread covers the measured strength.
2. Rescale the spread by one number fitted on calibration mixes.
3. Split conformal and CV+ by hand, then with MAPIE.
4. Four pycse regressors on a toy problem, inside and beyond their training data.

> Companion notes: [`notes.md`](notes.md).
""")
md("""
## 1. Load the concrete strength dataset, and make two splits

One row per specimen. `groups` numbers the mixes, so every row of a mix stays on one side of a
split, as in Lecture 9.

- **Grouped split**: 20% of the mixes held out at random.
- **Extrapolation split**: the 20% of mixes with the lowest water/cement ratio held out. These
  are the strongest mixes, the ones a design loop would push toward.
""")
code("""
import io
import urllib.request
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
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

train_g, test_g = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
                       .split(X, y, groups))

wc = (concrete["water"] / concrete["cement"]).groupby(groups).mean()
held = wc[wc <= wc.quantile(0.2)].index
test_e = np.flatnonzero(np.isin(groups, held))
train_e = np.flatnonzero(~np.isin(groups, held))

SPLITS = {"grouped": (train_g, test_g), "extrapolation": (train_e, test_e)}
for name, (tr, te) in SPLITS.items():
    print(f"{name:13s}: {len(tr)} training rows, {len(te)} test rows, "
          f"mean test strength {y[te].mean():.1f} MPa")
""")
md("""
## 2. An ensemble, and how often its spread covers

Within each training set, a quarter of the mixes are set aside as **calibration** mixes. Five
copies of Lecture 9's network (one hidden layer of 16 tanh units), seeds 0 to 4, are trained on
the rest. The prediction is their mean, and the spread is their standard deviation.

A 90% interval is the mean ± 1.645 × spread.
""")
code("""
Z90 = norm.ppf(0.95)


def net(seed):
    return make_pipeline(StandardScaler(), MLPRegressor(
        hidden_layer_sizes=(16,), activation="tanh", solver="lbfgs", max_iter=5000,
        random_state=seed))


def ensemble(Xf, yf):
    return [net(s).fit(Xf, yf) for s in range(5)]


def predict(nets, Xq):
    P = np.array([m.predict(Xq) for m in nets])
    return P.mean(0), P.std(0, ddof=1)


def coverage(y_true, lo, hi):
    return np.mean((y_true >= lo) & (y_true <= hi))


R = {}
for name, (tr, te) in SPLITS.items():
    fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0)
                        .split(X[tr], y[tr], groups[tr]))
    fit_i, cal_i = tr[fit_i], tr[cal_i]
    nets = ensemble(X[fit_i], y[fit_i])
    mc, sc = predict(nets, X[cal_i])
    mt, st = predict(nets, X[te])
    R[name] = dict(tr=tr, te=te, fit=fit_i, cal=cal_i, nets=nets, mc=mc, sc=sc, mt=mt, st=st)
    cov = coverage(y[te], mt - Z90 * st, mt + Z90 * st)
    print(f"{name:13s}: RMSE {np.sqrt(np.mean((y[te] - mt) ** 2)):.2f} MPa, mean spread "
          f"{st.mean():.2f} MPa, 90% coverage from the spread alone {cov:.0%}")
""")
md("""
## 3. Rescale the spread by one number

With $z_i = (y_i - \\mu_i)/\\sigma_i$ on the calibration mixes, the scale factor that minimizes
the Gaussian negative log likelihood is $s = \\sqrt{\\overline{z^2}}$. A calibrated model has
$s = 1$.
""")
code("""
def nll(y_true, mu, sd):
    return np.mean(0.5 * np.log(2 * np.pi * sd**2) + 0.5 * ((y_true - mu) / sd) ** 2)


for name, r in R.items():
    te, cal = r["te"], r["cal"]
    z = (y[cal] - r["mc"]) / r["sc"]
    s = np.sqrt(np.mean(z**2))
    r["s"] = s
    for label, k in [("raw", 1.0), (f"x {s:.2f}", s)]:
        cov = coverage(y[te], r["mt"] - Z90 * k * r["st"], r["mt"] + Z90 * k * r["st"])
        print(f"{name:13s} {label:7s}: 90% coverage {cov:.0%}, mean width "
              f"{2 * Z90 * k * r['st'].mean():.1f} MPa, NLL {nll(y[te], r['mt'], k * r['st']):.2f}")
""")
md("""
## 4. Split conformal prediction, by hand

The score is the absolute residual on the calibration mixes. The width is the
$\\lceil (n+1)(1-\\alpha) \\rceil$-th smallest score. The guarantee, at least $1 - \\alpha$, needs the
calibration and test mixes to be exchangeable.

The normalized version divides each residual by the ensemble spread, so the width follows it.
""")
code("""
def qhat(scores, alpha=0.1):
    n = len(scores)
    k = int(np.ceil((n + 1) * (1 - alpha)))
    return np.inf if k > n else np.sort(scores)[k - 1]


for name, r in R.items():
    te, cal = r["te"], r["cal"]
    q = qhat(np.abs(y[cal] - r["mc"]))
    qn = qhat(np.abs(y[cal] - r["mc"]) / r["sc"])
    r["q"] = q
    print(f"{name:13s}: split conformal {coverage(y[te], r['mt'] - q, r['mt'] + q):.0%} "
          f"(width {2 * q:.1f} MPa); normalized "
          f"{coverage(y[te], r['mt'] - qn * r['st'], r['mt'] + qn * r['st']):.0%} "
          f"(mean width {2 * qn * r['st'].mean():.1f} MPa)")
""")
md("""
## 5. CV+, by hand

CV+ (Barber et al. 2021) uses every training mix. For each of ten folds, train the ensemble
without that fold, record the fold's residuals $R_i$, and predict the test mixes. The interval
runs from a low quantile of $\\hat\\mu_{-k(i)}(x) - R_i$ to a high quantile of
$\\hat\\mu_{-k(i)}(x) + R_i$. This takes 50 network fits per split, about a minute.
""")
code("""
def cv_plus(tr, te, alpha=0.1, K=10):
    lo_s, hi_s = [], []
    for k_tr, k_out in GroupKFold(n_splits=K).split(X[tr], y[tr], groups[tr]):
        nk = ensemble(X[tr][k_tr], y[tr][k_tr])
        R_out = np.abs(y[tr][k_out] - predict(nk, X[tr][k_out])[0])
        m_te = predict(nk, X[te])[0]
        lo_s.append(m_te[None, :] - R_out[:, None])
        hi_s.append(m_te[None, :] + R_out[:, None])
    lo_s, hi_s = np.vstack(lo_s), np.vstack(hi_s)
    n = lo_s.shape[0]
    lo = np.sort(lo_s, axis=0)[int(np.floor(alpha * (n + 1))) - 1]
    hi = np.sort(hi_s, axis=0)[min(int(np.ceil((1 - alpha) * (n + 1))), n) - 1]
    return lo, hi


for name, r in R.items():
    lo, hi = cv_plus(r["tr"], r["te"])
    print(f"{name:13s}: CV+ {coverage(y[r['te']], lo, hi):.0%} (mean width {np.mean(hi - lo):.1f} MPa)")
""")
md("""
## 6. The same with MAPIE

`VotingRegressor` averages its members' predictions, so it is the five-network ensemble as one
scikit-learn model. `SplitConformalRegressor` with `prefit=True` takes an already fitted model
and only conformalizes it. `CrossConformalRegressor` with `method="plus"` is CV+; passing `groups`
keeps each mix in one fold.

MAPIE's interval array has shape `(n, 2, 1)`: lower and upper bound for one confidence level.
""")
code("""
from mapie.regression import CrossConformalRegressor, SplitConformalRegressor
from sklearn.ensemble import VotingRegressor


def voting():
    return VotingRegressor([(f"net{s}", net(s)) for s in range(5)])


for name, r in R.items():
    model = voting().fit(X[r["fit"]], y[r["fit"]])
    split = SplitConformalRegressor(model, confidence_level=0.9, prefit=True)
    split.conformalize(X[r["cal"]], y[r["cal"]])
    _, y_int = split.predict_interval(X[r["te"]])
    print(f"{name:13s}: MAPIE split conformal "
          f"{coverage(y[r['te']], y_int[:, 0, 0], y_int[:, 1, 0]):.0%} "
          f"(width {np.mean(y_int[:, 1, 0] - y_int[:, 0, 0]):.1f} MPa)")

r = R["extrapolation"]
cvp = CrossConformalRegressor(voting(), confidence_level=0.9, method="plus", cv=GroupKFold(10))
cvp.fit_conformalize(X[r["tr"]], y[r["tr"]], groups=groups[r["tr"]])
_, y_int = cvp.predict_interval(X[r["te"]])
print(f"extrapolation: MAPIE CV+ {coverage(y[r['te']], y_int[:, 0, 0], y_int[:, 1, 0]):.0%} "
      f"(mean width {np.mean(y_int[:, 1, 0] - y_int[:, 0, 0]):.1f} MPa)")
""")
md("""
## 7. Uncertainty built into the model: pycse

A toy problem with a known answer: $\\sin(2\\pi x)$ plus noise of standard deviation 0.1, 120
training points and 40 validation points on $[0, 1]$. Because the truth and the noise are known,
coverage is computed exactly: the chance that $y$ lands in $[\\text{lo}, \\text{hi}]$ at $x$ is
$\\Phi((\\text{hi} - f)/0.1) - \\Phi((\\text{lo} - f)/0.1)$, averaged over a grid.

Every model returns `(mean, std)` from `predict(X, return_std=True)`. Import each from its module:
in pycse 2.11.1, `from pycse.sklearn import NNBR` raises `ImportError`.
""")
code("""
import flax.linen as fnn
from sklearn.linear_model import BayesianRidge
from pycse.sklearn.dpose import DPOSE
from pycse.sklearn.llpr_regressor import LLPRRegressor
from pycse.sklearn.lr_uq import LinearRegressionUQ
from pycse.sklearn.nnbr import NeuralNetworkBLR

rng = np.random.default_rng(0)
f = lambda x: np.sin(2 * np.pi * x)
xtr = rng.uniform(0, 1, 120)[:, None]
xva = rng.uniform(0, 1, 40)[:, None]
ytr = f(xtr.ravel()) + 0.1 * rng.normal(size=120)
yva = f(xva.ravel()) + 0.1 * rng.normal(size=40)

cubic = lambda X: np.hstack([X**k for k in range(4)])
lr = LinearRegressionUQ().fit(cubic(xtr), ytr)
nnbr = NeuralNetworkBLR(MLPRegressor(hidden_layer_sizes=(20, 20), activation="tanh",
                                     solver="lbfgs", max_iter=2000, random_state=0),
                        BayesianRidge(tol=1e-6, fit_intercept=False))
nnbr.fit(xtr, ytr, val_X=xva, val_y=yva)
dpose = DPOSE(layers=(1, 20, 32), activation=fnn.tanh, seed=19)
dpose.fit(xtr, ytr, val_X=xva, val_y=yva, maxiter=1500)
llpr = LLPRRegressor(hidden_dims=(32, 32), n_epochs=400, random_state=0)
llpr.fit(np.vstack([xtr, xva]), np.concatenate([ytr, yva]))

MODELS = {
    "LinearRegressionUQ (cubic)": lambda Xq: lr.predict(cubic(Xq), return_std=True),
    "NeuralNetworkBLR": lambda Xq: nnbr.predict(Xq, return_std=True),
    "DPOSE": lambda Xq: dpose.predict(Xq, return_std=True),
    "LLPRRegressor": lambda Xq: llpr.predict(Xq, return_std=True),
}
inside, beyond = np.linspace(0, 1, 201), np.linspace(1, 1.5, 101)[1:]
Z95 = norm.ppf(0.975)
for name, pred in MODELS.items():
    out = []
    for g in (inside, beyond):
        # .real: pycse 2.11.1's LinearRegressionUQ returns a complex dtype (zero imaginary
        # part), because it takes np.linalg.eigvals of the symmetric X'X matrix.
        m, s = (np.real(np.asarray(a)).ravel() for a in pred(g[:, None]))
        c = norm.cdf((m + Z95 * s - f(g)) / 0.1) - norm.cdf((m - Z95 * s - f(g)) / 0.1)
        out.append(f"{c.mean():.0%} (width {np.mean(2 * Z95 * s):.2f})")
    print(f"{name:27s} 95% coverage inside [0, 1]: {out[0]:17s} beyond, (1, 1.5]: {out[1]}")
""")
md("""
## Try it

- Change `alpha` in `qhat` to 0.2. Do the grouped-split intervals cover about 80%?
- Fit the scale factor $s$ on the **extrapolation** test mixes instead of the calibration mixes.
  How different is it, and what does that say about choosing calibration data?
- In section 7, train on $[0, 0.8]$ instead of $[0, 1]$ and ask about $(0.8, 1]$. Which model's
  coverage holds up?
""")

cells = with_colab_cell(cells, OUT)
nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT.name} ({len(cells)} cells)")
