#!/usr/bin/env python3
"""Generate the L14a figures and the data behind its interactive figures, and print every
number the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with numpy --with pandas --with xlrd \
        --with scikit-learn --with scipy --with matplotlib python make_figures.py

The pycse group needs pycse and its JAX stack, so it runs separately:
    uv run --no-project --python 3.12 --with "pycse==2.11.1" --with xlrd --with matplotlib \
        python make_figures.py pycse

Name groups to regenerate only those; with no names, every group except pycse runs (pycse
reads its cached result if present). The groups, and what each writes:
    gp          gp-prior-posterior.png, gp-failures.png, gp-hetero-fix.png,
                gp-lengthscale.png, and the "gp" entry of the widget data. Gaussian processes
                on one-dimensional toy problems with a known truth, so coverage is computed
                exactly rather than sampled: a smooth function, heteroscedastic noise (and
                the fix of Kersting et al. 2007), a step, and five points.
    ens         ensemble-members.png and the "ens" entry. Ten networks from different seeds
                and ten from bootstrap resamples, on sin(2 pi x) plus noise, trained on
                [0, 1] and asked about [1, 1.5].
    concrete    recalibration.png, conformal-concrete.png and the "scale" entry. On the
                concrete strength dataset (Yeh 1998), with Lecture 9's network and the two
                splits of Lecture 14 (grouped, and the strongest mixes held out): a
                five-network ensemble, recalibrated by one scale factor; split conformal,
                normalized conformal and CV+; and the climatological forecaster.
    conformal   conformal-toy.png and the "conf" entry. Split conformal on a toy problem
                whose noise grows with x: constant width against normalized scores, and
                coverage as the test inputs move out of the calibration range.
    pycse       pycse-compare.png and the "pycse" entry. Four pycse regressors, five seeds,
                in-domain and out-of-domain coverage.

Toy problems use exact coverage: with the truth f(x) and the noise standard deviation s(x)
known, the probability that y falls in [lo, hi] at x is Phi((hi - f)/s) - Phi((lo - f)/s),
averaged over a fine grid. The concrete workbook is cached under .cache/ (copied from
Lecture 14's or Lecture 9's cache when present) and gitignored.
"""
import io
import json
import shutil
import sys
import time
import urllib.request
import warnings
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import digamma
from scipy.stats import norm, spearmanr
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", message=".*close to the specified")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CACHE = HERE / ".cache"
OTHER_CACHES = [HERE.parent.parent / "l14" / "figures" / ".cache",
                HERE.parent.parent / "l09" / "figures" / ".cache"]
WIDGET_JS = REPO / "_static" / "l14a-widget-data.js"
UCI_CONCRETE = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
SEED = 0

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
ORANGE = "#c2410c"
GREEN = "#2e7d32"
GOLD = "#b07d12"
GRAY = "#8a8a8a"
BAND = "#c9dbec"

STYLE = {
    "font.size": 14, "axes.labelsize": 14, "axes.titlesize": 15,
    "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 12,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "savefig.dpi": 150, "savefig.bbox": "tight",
}

COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]
LEVELS = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
Z95 = norm.ppf(0.975)
Z90 = norm.ppf(0.95)
LOG_CHI2_1 = float(digamma(0.5) + np.log(2))  # E[log chi2_1] = -1.27


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def cache_put(name, obj):
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps(obj))


def r(a, nd=3):
    return [round(float(v), nd) for v in np.asarray(a).ravel()]


# --------------------------------------------------------------------------------------
# toy problems: truth, noise, exact coverage
# --------------------------------------------------------------------------------------
def f_sin(x):
    return np.sin(2 * np.pi * x)


def f_step(x):
    return np.where(x < 0.5, -0.5, 0.5) + 0.2 * np.sin(2 * np.pi * x)


# Each scenario: truth, noise sd = a + b x, number of training points, the data range.
SCEN = {
    "smooth": dict(truth="sin", a=0.1, b=0.0, n=12),
    "hetero": dict(truth="sin", a=0.02, b=0.3, n=60),
    "step": dict(truth="step", a=0.05, b=0.0, n=40),
    "few": dict(truth="sin", a=0.1, b=0.0, n=5),
}
TRUTH = {"sin": f_sin, "step": f_step}


def noise_sd(sc, x):
    return sc["a"] + sc["b"] * np.clip(x, 0, None)


def draw(sc, n, rng, lo=0.0, hi=1.0):
    x = np.sort(rng.uniform(lo, hi, n))
    return x, TRUTH[sc["truth"]](x) + noise_sd(sc, x) * rng.normal(size=n)


def exact_cov(lo, hi, f, s):
    """Probability that y = f + s * eps lands in [lo, hi], pointwise."""
    return norm.cdf((hi - f) / s) - norm.cdf((lo - f) / s)


def gp_toy(restarts=5, noise=True):
    k = ConstantKernel(1.0, (1e-2, 1e2)) * RBF(0.2, (1e-3, 1e1))
    if noise:
        k = k + WhiteKernel(1e-2, (1e-6, 1e0))
    return GaussianProcessRegressor(k, normalize_y=False, n_restarts_optimizer=restarts,
                                    random_state=SEED)


def gp_parts(gp):
    """Fitted length scale, signal sd and noise sd of a C * RBF + White GP."""
    k = gp.kernel_
    return dict(ell=float(k.k1.k2.length_scale), sf=float(np.sqrt(k.k1.k1.constant_value)),
                sn=float(np.sqrt(k.k2.noise_level)))


# --------------------------------------------------------------------------------------
# gp
# --------------------------------------------------------------------------------------
GRID = np.linspace(-0.1, 1.4, 301)
IN = (GRID >= 0) & (GRID <= 1)
OUT = GRID > 1


def gp_cov(gp, sc, grid=GRID, extra_var=None):
    mu, sd = gp.predict(grid[:, None], return_std=True)
    if extra_var is not None:
        sd = np.sqrt(sd**2 + extra_var)
    f, s = TRUTH[sc["truth"]](grid), noise_sd(sc, grid)
    return mu, sd, exact_cov(mu - Z95 * sd, mu + Z95 * sd, f, s)


def mlhgp(x, y, iters=3):
    """A heteroscedastic GP in the spirit of Kersting et al. (2007): fit a GP, regress the log
    squared residuals on x with a second GP, refit the first with that noise at each point,
    repeat. Two departures from their step 2, both found by checking the learned noise against
    the true one: the latent variance is left out (with it the noise came out 1.4 to 2.9 times
    too large), and the log is corrected for its bias, since for Gaussian noise
    E[log eps^2] = log sigma^2 + psi(1/2) + log 2 = log sigma^2 - 1.27 (without the correction
    the noise came out about 0.7 times too small)."""
    g1 = gp_toy().fit(x[:, None], y)
    for _ in range(iters):
        mu = g1.predict(x[:, None])
        z = np.log((y - mu) ** 2 + 1e-12) - LOG_CHI2_1
        gn = GaussianProcessRegressor(ConstantKernel(1.0) * RBF(0.3, (5e-2, 1e1)) + WhiteKernel(0.5),
                                      normalize_y=True, n_restarts_optimizer=3,
                                      random_state=SEED).fit(x[:, None], z)
        g1 = GaussianProcessRegressor(ConstantKernel(1.0, (1e-2, 1e2)) * RBF(0.2, (1e-3, 1e1)),
                                      alpha=np.exp(gn.predict(x[:, None])), n_restarts_optimizer=5,
                                      random_state=SEED).fit(x[:, None], y)
    return g1, gn


def group_gp():
    out = {"grid": r(GRID, 3), "scenarios": {}}
    rng = np.random.default_rng(SEED)
    fits = {}
    for name, sc in SCEN.items():
        x, y = draw(sc, sc["n"], np.random.default_rng({"smooth": 1, "hetero": 2, "step": 3, "few": 4}[name]))
        gp = gp_toy().fit(x[:, None], y)
        p = gp_parts(gp)
        mu, sd, cv = gp_cov(gp, sc)
        fits[name] = (x, y, gp, mu, sd, cv)
        rec = dict(truth=sc["truth"], a=sc["a"], b=sc["b"], x=r(x), y=r(y), fit=r(list(p.values()), 4),
                   cov_in=float(cv[IN].mean()), cov_out=float(cv[OUT].mean()))
        print(f"  {name:6s} n={sc['n']:3d}: ell {p['ell']:.3f}, sf {p['sf']:.2f}, sn {p['sn']:.3f};"
              f" 95% coverage in [0,1] {cv[IN].mean():.2f}, beyond 1 {cv[OUT].mean():.2f};"
              f" mean sd in {sd[IN].mean():.3f}, beyond {sd[OUT].mean():.3f}")
        out["scenarios"][name] = rec

    # Heteroscedastic: coverage by thirds, homoscedastic against the MLHGP fix.
    sc = SCEN["hetero"]
    x, y, gp, mu, sd, cv = fits["hetero"]
    thirds = [(0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1)]
    def by_third(c):
        return [float(c[(GRID >= a) & (GRID <= b)].mean()) for a, b in thirds]
    g1, gn = mlhgp(x, y)
    mu2, sdf2 = g1.predict(GRID[:, None], return_std=True)
    rvar = np.exp(gn.predict(GRID[:, None]))
    sd2 = np.sqrt(sdf2**2 + rvar)
    f, s = f_sin(GRID), noise_sd(sc, GRID)
    cv2 = exact_cov(mu2 - Z95 * sd2, mu2 + Z95 * sd2, f, s)
    h_homo, h_fix = by_third(cv), by_third(cv2)
    print(f"  hetero 95% coverage by thirds of [0,1]: homoscedastic GP "
          + ", ".join(f"{c:.2f}" for c in h_homo) + "; heteroscedastic GP (Kersting) "
          + ", ".join(f"{c:.2f}" for c in h_fix))
    print(f"    true noise sd 0.02 to 0.32; fitted constant noise sd {gp_parts(gp)['sn']:.3f};"
          f" learned noise sd at x=0.1 {np.sqrt(np.exp(gn.predict([[0.1]])))[0]:.3f},"
          f" at x=0.9 {np.sqrt(np.exp(gn.predict([[0.9]])))[0]:.3f}")
    out["hetero"] = dict(thirds_homo=r(h_homo), thirds_fix=r(h_fix))

    # Step: coverage near the step against away from it.
    x, y, gp, mu, sd, cv = fits["step"]
    near = (np.abs(GRID - 0.5) < 0.1) & IN
    far = (np.abs(GRID - 0.5) >= 0.1) & IN
    print(f"  step: 95% coverage within 0.1 of the step {cv[near].mean():.2f}, elsewhere in [0,1]"
          f" {cv[far].mean():.2f}")
    out["step"] = dict(near=float(cv[near].mean()), far=float(cv[far].mean()))

    # Length scale as n grows: smooth against step (Duvenaud's misspecification signal).
    ns = [10, 20, 40, 80, 160, 320]
    ells = {}
    for name in ("smooth", "step"):
        sc = SCEN[name]
        ells[name] = []
        for n in ns:
            vals = []
            for rep in range(5):
                xx, yy = draw(sc, n, np.random.default_rng(1000 + 17 * n + rep))
                vals.append(gp_parts(gp_toy(restarts=3).fit(xx[:, None], yy))["ell"])
            ells[name].append(float(np.median(vals)))
        print(f"  fitted length scale (median of 5) for n = {ns}: {name} "
              + ", ".join(f"{v:.3f}" for v in ells[name]))
    out["ell_vs_n"] = dict(n=ns, **{k: r(v, 4) for k, v in ells.items()})

    # Few points: the distribution of coverage over many five-point data sets.
    covs = {}
    for n in (5, 12, 40):
        sc = SCEN["smooth"]
        cs = []
        for rep in range(200):
            xx, yy = draw(sc, n, np.random.default_rng(5000 + 1000 * n + rep))
            g = gp_toy(restarts=3).fit(xx[:, None], yy)
            _, _, c = gp_cov(g, sc)
            cs.append(c[IN].mean())
        cs = np.array(cs)
        covs[n] = cs
        print(f"  n={n:2d}, 200 data sets: 95% coverage on [0,1] median {np.median(cs):.2f},"
              f" mean {cs.mean():.2f}; below 0.80 in {np.mean(cs < 0.8):.0%}, below 0.50 in"
              f" {np.mean(cs < 0.5):.0%}")
    out["few"] = {str(k): dict(median=float(np.median(v)), mean=float(v.mean()),
                               below80=float(np.mean(v < 0.8)), below50=float(np.mean(v < 0.5)))
                  for k, v in covs.items()}
    cache_put("gp", out)

    with plt.rc_context(STYLE):
        # ---- prior and posterior draws
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.2), sharey=True)
        g = GaussianProcessRegressor(ConstantKernel(1.0, "fixed") * RBF(0.15, "fixed"),
                                     alpha=0.01, optimizer=None)
        gx = np.linspace(0, 1, 200)
        prior = g.sample_y(gx[:, None], 4, random_state=3)
        axes[0].plot(gx, prior, lw=1.6)
        axes[0].fill_between(gx, -1.96, 1.96, color=BAND, alpha=0.6, zorder=0)
        axes[0].set_title("prior: four functions drawn before any data")
        xd = np.array([0.1, 0.3, 0.45, 0.8, 0.9])
        yd = f_sin(xd)
        g.fit(xd[:, None], yd)
        m, s = g.predict(gx[:, None], return_std=True)
        post = g.sample_y(gx[:, None], 4, random_state=3)
        axes[1].fill_between(gx, m - 1.96 * s, m + 1.96 * s, color=BAND, alpha=0.8, zorder=0)
        axes[1].plot(gx, post, lw=1.4, alpha=0.9)
        axes[1].plot(gx, m, color=INK, lw=2.2)
        axes[1].plot(xd, yd, "o", color=INK, ms=7)
        axes[1].set_title("posterior: the same prior, conditioned on five points")
        for ax in axes:
            ax.set_xlabel("x")
        axes[0].set_ylabel("f(x)")
        save(fig, "gp-prior-posterior.png")

        # ---- three failures
        fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))
        titles = {
            "hetero": "noise grows with x\n" + ", ".join(f"{c:.0%}" for c in h_homo) + " by third",
            "step": f"a step at x = 0.5\n{out['step']['near']:.0%} within 0.1 of it",
            "few": f"five points\n{fits['few'][5][IN].mean():.0%} in [0, 1]",
        }
        for ax, name in zip(axes, ["hetero", "step", "few"]):
            title = titles[name]
            x, y, gp, mu, sd, cv = fits[name]
            sc = SCEN[name]
            f = TRUTH[sc["truth"]](GRID)
            ax.fill_between(GRID, mu - Z95 * sd, mu + Z95 * sd, color=BAND, alpha=0.9, zorder=0)
            ax.plot(GRID, f, color=GRAY, lw=2.5, label="truth")
            ax.plot(GRID, mu, color=BLUE, lw=2, label="GP mean, 95% band")
            ax.plot(x, y, "o", color=INK, ms=4)
            ax.axvline(1, color=MUTED, ls=":", lw=1)
            ax.set_title(title)
            ax.set_xlabel("x")
            ax.set_ylim(-2.2, 2.2)
        axes[0].legend(loc="lower left")
        save(fig, "gp-failures.png")

        # ---- heteroscedastic fix
        sc = SCEN["hetero"]
        x, y, gp, mu, sd, cv = fits["hetero"]
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.4), sharey=True)
        for ax, m_, s_, t_, c_ in [(axes[0], mu, sd, "one noise level (homoscedastic GP)", h_homo),
                                   (axes[1], mu2, sd2, "noise modeled by a second GP", h_fix)]:
            ax.fill_between(GRID, m_ - Z95 * s_, m_ + Z95 * s_, color=BAND, alpha=0.9, zorder=0)
            ax.plot(GRID, f_sin(GRID), color=GRAY, lw=2.5)
            ax.plot(GRID, m_, color=BLUE, lw=2)
            ax.plot(x, y, "o", color=INK, ms=3.5)
            ax.set_xlim(0, 1)
            ax.set_title(t_)
            ax.set_xlabel("x")
            for (a, b), c in zip(thirds, c_):
                ax.text((a + b) / 2, -1.85, f"{c:.0%}", ha="center", fontsize=13,
                        color=CMU_RED if abs(c - 0.95) > 0.04 else GREEN)
        axes[0].set_ylabel("y")
        axes[0].text(0.01, -2.15, "95% coverage by third:", fontsize=11, color=MUTED)
        axes[0].set_ylim(-2.3, 2.0)
        save(fig, "gp-hetero-fix.png")

        # ---- length scale against n
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        ax.plot(ns, ells["smooth"], "o-", color=BLUE, lw=2, label="smooth truth, sin(2πx)")
        ax.plot(ns, ells["step"], "s-", color=CMU_RED, lw=2, label="truth with a step")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("training points")
        ax.set_ylabel("fitted RBF length scale")
        ax.legend()
        save(fig, "gp-lengthscale.png")


# --------------------------------------------------------------------------------------
# ens
# --------------------------------------------------------------------------------------
EGRID = np.linspace(0, 1.5, 151)
EIN, EOUT = EGRID <= 1, EGRID > 1


def toy_net(seed):
    return MLPRegressor(hidden_layer_sizes=(32, 32), activation="relu", solver="lbfgs",
                        max_iter=3000, alpha=1e-4, random_state=seed)


def group_ens():
    rng = np.random.default_rng(SEED)
    sc = dict(truth="sin", a=0.1, b=0.0)
    x, y = draw(sc, 120, rng)
    K = 10
    seeds = np.array([toy_net(s).fit(x[:, None], y).predict(EGRID[:, None]) for s in range(K)])
    boots = []
    for s in range(K):
        idx = np.random.default_rng(100 + s).integers(0, len(x), len(x))
        boots.append(toy_net(s).fit(x[idx, None], y[idx]).predict(EGRID[:, None]))
    boots = np.array(boots)
    f, s_true = f_sin(EGRID), noise_sd(sc, EGRID)
    res = {}
    for name, P in [("seeds", seeds), ("bootstrap", boots)]:
        mu, sp = P.mean(0), P.std(0, ddof=1)
        mtr = np.interp(x, EGRID, mu)
        sn = float(np.std(y - mtr, ddof=1))
        c_sp = exact_cov(mu - Z95 * sp, mu + Z95 * sp, f, s_true)
        tot = np.sqrt(sp**2 + sn**2)
        c_tot = exact_cov(mu - Z95 * tot, mu + Z95 * tot, f, s_true)
        err = np.abs(mu - f)
        res[name] = dict(sn=sn, cov_sp_in=float(c_sp[EIN].mean()), cov_sp_out=float(c_sp[EOUT].mean()),
                         cov_tot_in=float(c_tot[EIN].mean()), cov_tot_out=float(c_tot[EOUT].mean()),
                         sp_in=float(sp[EIN].mean()), sp_out=float(sp[EOUT].mean()),
                         err_in=float(err[EIN].mean()), err_out=float(err[EOUT].mean()))
        d = res[name]
        print(f"  {name:9s}: spread in [0,1] {d['sp_in']:.3f}, beyond {d['sp_out']:.3f};"
              f" |error| of the mean in {d['err_in']:.3f}, beyond {d['err_out']:.3f};"
              f" fitted noise {sn:.3f}")
        print(f"             95% coverage, spread only: in {d['cov_sp_in']:.2f}, beyond"
              f" {d['cov_sp_out']:.2f}; spread + noise: in {d['cov_tot_in']:.2f}, beyond"
              f" {d['cov_tot_out']:.2f}")
    cache_put("ens", dict(grid=r(EGRID), x=r(x), y=r(y), noise=0.1,
                          seeds=[r(p) for p in seeds], bootstrap=[r(p) for p in boots],
                          summary=res))
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.4), sharey=True)
        for ax, P, t in [(axes[0], seeds, "ten seeds, all the data"),
                         (axes[1], boots, "ten bootstrap resamples")]:
            mu, sp = P.mean(0), P.std(0, ddof=1)
            ax.axvspan(1, 1.5, color=GRAY, alpha=0.1)
            ax.plot(EGRID, P.T, color=BLUE, lw=1, alpha=0.5)
            ax.plot(EGRID, f, color=GRAY, lw=3, label="truth")
            ax.plot(x, y, "o", color=INK, ms=2.5)
            ax.set_ylim(-3, 2)
            ax.set_xlabel("x")
            ax.set_title(t)
            ax.text(1.25, 1.6, "no data", ha="center", color=MUTED)
        axes[0].set_ylabel("y")
        save(fig, "ensemble-members.png")


# --------------------------------------------------------------------------------------
# concrete
# --------------------------------------------------------------------------------------
def load_concrete():
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "Concrete_Data.xls"
    for other in OTHER_CACHES:
        if not path.exists() and (other / "Concrete_Data.xls").exists():
            shutil.copy(other / "Concrete_Data.xls", path)
    if not path.exists():
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI_CONCRETE).read()))
        path.write_bytes(z.read("Concrete_Data.xls"))
    df = pd.read_excel(path)
    df.columns = COLUMNS
    return df


def l09_net(seed):
    """Lecture 9's network for the concrete strength dataset, with a seed."""
    return make_pipeline(StandardScaler(), MLPRegressor(
        hidden_layer_sizes=(16,), activation="tanh", solver="lbfgs", max_iter=5000,
        random_state=seed))


def ens5(X, y):
    return [l09_net(s).fit(X, y) for s in range(5)]


def ens_predict(nets, X):
    P = np.array([n.predict(X) for n in nets])
    return P.mean(0), P.std(0, ddof=1)


def nll(y, mu, sd):
    return float(np.mean(0.5 * np.log(2 * np.pi * sd**2) + 0.5 * ((y - mu) / sd) ** 2))


def concrete_split(X, y, groups, tr, te, label):
    fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
                        .split(X[tr], y[tr], groups[tr]))
    fit_i, cal_i = tr[fit_i], tr[cal_i]
    nets = ens5(X[fit_i], y[fit_i])
    mc, sc_ = ens_predict(nets, X[cal_i])
    mt, st = ens_predict(nets, X[te])

    # Recalibration: one scale factor, fitted on the calibration mixes.
    zc = (y[cal_i] - mc) / sc_
    s = float(np.sqrt(np.mean(zc**2)))

    def cov(mu, sd, zz):
        return float(np.mean(np.abs(y[te] - mu) <= zz * sd))
    rec = dict(label=label, n_fit=len(fit_i), n_cal=len(cal_i), n_test=len(te), s=s,
               rmse=float(np.sqrt(np.mean((y[te] - mt) ** 2))),
               spread=float(st.mean()),
               cov90_raw=cov(mt, st, Z90), cov90_cal=cov(mt, s * st, Z90),
               width90_raw=float(2 * Z90 * st.mean()), width90_cal=float(2 * Z90 * s * st.mean()),
               nll_raw=nll(y[te], mt, st), nll_cal=nll(y[te], mt, s * st),
               cal_cov90_raw=float(np.mean(np.abs(zc) <= Z90)),
               cal_cov90_cal=float(np.mean(np.abs(zc / s) <= Z90)),
               rel_raw=[cov(mt, st, norm.ppf(0.5 + l / 2)) for l in LEVELS],
               rel_cal=[cov(mt, s * st, norm.ppf(0.5 + l / 2)) for l in LEVELS],
               spearman=float(spearmanr(np.abs(y[te] - mt), st).correlation))

    # Split conformal (absolute residual) and normalized conformal (residual / spread).
    def qhat(scores, alpha):
        n = len(scores)
        k = int(np.ceil((n + 1) * (1 - alpha)))
        return np.inf if k > n else float(np.sort(scores)[k - 1])
    q = qhat(np.abs(y[cal_i] - mc), 0.1)
    qn = qhat(np.abs(y[cal_i] - mc) / sc_, 0.1)
    rec.update(conf_cov90=cov(mt, np.full_like(mt, q), 1.0), conf_width90=2 * q,
               nconf_cov90=cov(mt, qn * st, 1.0), nconf_width90=float(2 * qn * st.mean()))

    # CV+ (Barber et al. 2021), ten folds by mix, on all the training mixes.
    K = 10
    lo_s, hi_s = [], []
    for k_tr, k_out in GroupKFold(n_splits=K).split(X[tr], y[tr], groups[tr]):
        nk = ens5(X[tr][k_tr], y[tr][k_tr])
        mk_out, _ = ens_predict(nk, X[tr][k_out])
        R = np.abs(y[tr][k_out] - mk_out)
        mk_te, _ = ens_predict(nk, X[te])
        lo_s.append(mk_te[None, :] - R[:, None])
        hi_s.append(mk_te[None, :] + R[:, None])
    lo_s, hi_s = np.vstack(lo_s), np.vstack(hi_s)
    n = lo_s.shape[0]
    a = 0.1
    k_lo = int(np.floor(a * (n + 1)))
    k_hi = int(np.ceil((1 - a) * (n + 1)))
    lo = np.sort(lo_s, axis=0)[k_lo - 1]
    hi = np.sort(hi_s, axis=0)[min(k_hi, n) - 1]
    rec.update(cvplus_cov90=float(np.mean((y[te] >= lo) & (y[te] <= hi))),
               cvplus_width90=float(np.mean(hi - lo)), cvplus_n=int(n))

    # Climatology: the training strengths' own 5% and 95% quantiles, for every mix.
    clo, chi = np.quantile(y[tr], [0.05, 0.95])
    rec.update(clim_cov90=float(np.mean((y[te] >= clo) & (y[te] <= chi))),
               clim_width90=float(chi - clo))

    print(f"  {label}: {len(fit_i)} fitting, {len(cal_i)} calibration, {len(te)} test rows;"
          f" ensemble RMSE {rec['rmse']:.2f} MPa, mean spread {rec['spread']:.2f} MPa")
    print(f"    scale factor s = {s:.2f}; 90% coverage raw {rec['cov90_raw']:.2f} -> scaled"
          f" {rec['cov90_cal']:.2f} (calibration set {rec['cal_cov90_raw']:.2f} ->"
          f" {rec['cal_cov90_cal']:.2f}); width {rec['width90_raw']:.1f} -> {rec['width90_cal']:.1f} MPa;"
          f" NLL {rec['nll_raw']:.2f} -> {rec['nll_cal']:.2f}")
    print(f"    Spearman(|error|, spread) {rec['spearman']:.2f}")
    print(f"    90%: split conformal {rec['conf_cov90']:.2f} ({rec['conf_width90']:.1f} MPa),"
          f" normalized {rec['nconf_cov90']:.2f} ({rec['nconf_width90']:.1f} MPa),"
          f" CV+ {rec['cvplus_cov90']:.2f} ({rec['cvplus_width90']:.1f} MPa),"
          f" climatology {rec['clim_cov90']:.2f} ({rec['clim_width90']:.1f} MPa)")
    # Strengths carry two decimals in the workbook; keep them, and enough digits in mu and sd
    # that the widget's coverage matches the numbers printed here mix for mix.
    widget = dict(label=label, s=s, cal=dict(y=r(y[cal_i], 2), mu=r(mc, 4), sd=r(sc_, 4)),
                  test=dict(y=r(y[te], 2), mu=r(mt, 4), sd=r(st, 4)))
    return rec, widget


def group_concrete():
    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df["strength_mpa"].to_numpy()
    groups = df.groupby(MIX).ngroup().to_numpy()
    same = df.groupby(FEATURES)["strength_mpa"].agg(["size", "std"])
    rep = same[same["size"] > 1]
    pooled = float(np.sqrt((rep["std"] ** 2 * (rep["size"] - 1)).sum() / (rep["size"] - 1).sum()))
    print(f"  replicates: {len(rep)} settings (same mix and age) tested more than once, "
          f"{int(rep['size'].sum())} rows; pooled scatter {pooled:.2f} MPa")
    t0 = time.time()
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
    g_rec, g_w = concrete_split(X, y, groups, tr, te, "grouped split")
    wc = (df["water"] / df["cement"]).groupby(groups).mean()
    cut = float(wc.quantile(0.2))
    held = set(wc[wc <= cut].index)
    te2 = np.flatnonzero(np.isin(groups, list(held)))
    tr2 = np.flatnonzero(~np.isin(groups, list(held)))
    e_rec, e_w = concrete_split(X, y, groups, tr2, te2, "extrapolation split")
    print(f"  ({time.time() - t0:.0f} s)")
    cache_put("concrete", dict(grouped=g_rec, extrap=e_rec))
    cache_put("scale", dict(levels=r(LEVELS, 2), splits=[g_w, e_w]))

    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
        for ax, rec, t in [(axes[0], g_rec, "grouped split"), (axes[1], e_rec, "extrapolation split")]:
            ax.plot([0, 1], [0, 1], "--", color=MUTED, lw=1)
            ax.plot(LEVELS, rec["rel_raw"], "o-", color=CMU_RED, lw=2, label="ensemble spread")
            ax.plot(LEVELS, rec["rel_cal"], "s-", color=BLUE, lw=2,
                    label=f"spread × {rec['s']:.2f}")
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_xlabel("nominal coverage")
            ax.set_title(t)
            ax.set_aspect("equal")
        axes[0].set_ylabel("observed coverage")
        axes[0].legend(loc="upper left")
        save(fig, "recalibration.png")

        fig, ax = plt.subplots(figsize=(11, 4.6))
        meths = [("ensemble\nspread", "cov90_raw", "width90_raw"),
                 ("spread,\nrescaled", "cov90_cal", "width90_cal"),
                 ("split\nconformal", "conf_cov90", "conf_width90"),
                 ("normalized\nconformal", "nconf_cov90", "nconf_width90"),
                 ("CV+", "cvplus_cov90", "cvplus_width90"),
                 ("climatology", "clim_cov90", "clim_width90")]
        xs = np.arange(len(meths))
        for off, rec, col, lab in [(-0.2, g_rec, BLUE, "grouped split"),
                                   (0.2, e_rec, CMU_RED, "extrapolation split")]:
            vals = [rec[c] for _, c, _ in meths]
            ax.bar(xs + off, vals, 0.38, color=col, label=lab)
            for xx, v, (_, _, w) in zip(xs + off, vals, meths):
                ax.text(xx, v + 0.015, f"{v:.0%}\n{rec[w]:.0f}", ha="center", fontsize=10)
        ax.axhline(0.9, color=INK, ls="--", lw=1)
        ax.set_xticks(xs, [m[0] for m in meths])
        ax.set_ylim(0, 1.18)
        ax.set_ylabel("coverage of the 90% interval")
        ax.legend(loc="upper left", ncol=2)
        ax.text(len(meths) - 0.5, 1.12, "labels: coverage, mean width in MPa", ha="right",
                fontsize=11, color=MUTED)
        save(fig, "conformal-concrete.png")


# --------------------------------------------------------------------------------------
# conformal (toy)
# --------------------------------------------------------------------------------------
CGRID = np.linspace(0, 1.5, 151)


def group_conformal():
    sc = dict(truth="sin", a=0.05, b=0.25)
    rng = np.random.default_rng(SEED + 7)
    xf, yf = draw(sc, 300, rng)
    xc, yc = draw(sc, 500, rng)
    perm = rng.permutation(len(xc))
    xc, yc = xc[perm], yc[perm]
    nets = [MLPRegressor(hidden_layer_sizes=(32, 32), activation="tanh", solver="lbfgs",
                         max_iter=3000, alpha=1e-3, random_state=s).fit(xf[:, None], yf)
            for s in range(5)]
    mu = lambda x: np.mean([n.predict(np.atleast_1d(x)[:, None]) for n in nets], 0)
    # rho(x): a small network fitted to the absolute residuals on the fitting set (Lei et al.
    # 2018, section 5.2, locally weighted conformal).
    rf = np.abs(yf - mu(xf))
    rho_net = MLPRegressor(hidden_layer_sizes=(8,), activation="tanh", solver="lbfgs",
                           max_iter=3000, alpha=1e-2, random_state=0).fit(xf[:, None], rf)
    rho = lambda x: np.maximum(rho_net.predict(np.atleast_1d(x)[:, None]), 0.02)
    mg, rg = mu(CGRID), rho(CGRID)
    f, s = f_sin(CGRID), noise_sd(sc, CGRID)
    mc, rc = mu(xc), rho(xc)

    def q(scores, alpha):
        n = len(scores)
        k = int(np.ceil((n + 1) * (1 - alpha)))
        return np.inf if k > n else np.sort(scores)[k - 1]
    q_abs = q(np.abs(yc - mc), 0.1)
    q_nrm = q(np.abs(yc - mc) / rc, 0.1)
    c_abs = exact_cov(mg - q_abs, mg + q_abs, f, s)
    c_nrm = exact_cov(mg - q_nrm * rg, mg + q_nrm * rg, f, s)
    IN_ = CGRID <= 1
    thirds = [(0, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 1)]
    bt = lambda c: [float(c[(CGRID >= a) & (CGRID <= b)].mean()) for a, b in thirds]
    print(f"  90% split conformal on noise sd 0.05 + 0.25 x: in [0,1] constant width"
          f" {c_abs[IN_].mean():.3f} (by third " + ", ".join(f"{v:.2f}" for v in bt(c_abs))
          + f"), normalized {c_nrm[IN_].mean():.3f} (by third "
          + ", ".join(f"{v:.2f}" for v in bt(c_nrm)) + ")")
    print(f"    beyond 1: constant {c_abs[~IN_].mean():.2f}, normalized {c_nrm[~IN_].mean():.2f};"
          f" |error| of the model at x=1.4: {abs(mu(1.4)[0] - f_sin(1.4)):.2f}")
    for a in (0.0, 0.25, 0.5, 0.75, 1.0):
        w = (CGRID >= a) & (CGRID <= a + 0.5)
        print(f"    test window [{a:.2f}, {a + 0.5:.2f}]: constant {c_abs[w].mean():.2f},"
              f" normalized {c_nrm[w].mean():.2f}")
    cache_put("conf", dict(grid=r(CGRID), mu=r(mg), rho=r(rg), truth=r(f), noise=r(s),
                           cal=dict(x=r(xc), y=r(yc), mu=r(mc), rho=r(rc)),
                           thirds_abs=r(bt(c_abs)), thirds_nrm=r(bt(c_nrm))))

    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(14, 4.6), sharey=True)
        for ax, lo, hi, cc, t in [(axes[0], mg - q_abs, mg + q_abs, c_abs, "absolute residual: one width"),
                                  (axes[1], mg - q_nrm * rg, mg + q_nrm * rg, c_nrm,
                                   "residual / ρ(x): width follows the noise")]:
            ax.axvspan(1, 1.5, color=GRAY, alpha=0.1)
            ax.fill_between(CGRID, lo, hi, color=BAND, alpha=0.9, zorder=0)
            ax.plot(CGRID, f, color=GRAY, lw=2.5)
            ax.plot(CGRID, mg, color=BLUE, lw=2)
            ax.plot(xc[:200], yc[:200], "o", color=INK, ms=2, alpha=0.6)
            for (a, b), c in zip(thirds, bt(cc)):
                ax.text((a + b) / 2, -2.6, f"{c:.0%}", ha="center", fontsize=13,
                        color=CMU_RED if abs(c - 0.9) > 0.04 else GREEN)
            ax.text(1.25, -2.6, f"{cc[~IN_].mean():.0%}", ha="center", fontsize=13, color=CMU_RED)
            ax.set_title(t)
            ax.set_xlabel("x")
            ax.set_ylim(-3, 2.5)
        axes[0].set_ylabel("y")
        save(fig, "conformal-toy.png")


# --------------------------------------------------------------------------------------
# pycse
# --------------------------------------------------------------------------------------
def group_pycse():
    import flax.linen as fnn
    from sklearn.linear_model import BayesianRidge
    from pycse.sklearn.dpose import DPOSE
    from pycse.sklearn.llpr_regressor import LLPRRegressor
    from pycse.sklearn.lr_uq import LinearRegressionUQ
    from pycse.sklearn.nnbr import NeuralNetworkBLR

    def data(seed):
        rng = np.random.default_rng(seed)
        xtr = rng.uniform(0, 1, 120)[:, None]
        xva = rng.uniform(0, 1, 40)[:, None]
        noise = lambda n: 0.1 * rng.normal(size=n)
        return xtr, f_sin(xtr.ravel()) + noise(120), xva, f_sin(xva.ravel()) + noise(40)

    feats = lambda X: np.hstack([X**k for k in range(4)])
    builders = {
        "LinearRegressionUQ (cubic)": lambda s, xtr, ytr, xva, yva: (
            lambda m: (lambda X: m.predict(feats(X), return_std=True)))(
            LinearRegressionUQ().fit(feats(xtr), ytr)),
        "NeuralNetworkBLR": lambda s, xtr, ytr, xva, yva: (
            lambda m: (m.fit(xtr, ytr, val_X=xva, val_y=yva), lambda X: m.predict(X, return_std=True))[1])(
            NeuralNetworkBLR(MLPRegressor(hidden_layer_sizes=(20, 20), activation="tanh",
                                          solver="lbfgs", max_iter=2000, random_state=s),
                             BayesianRidge(tol=1e-6, fit_intercept=False))),
        "DPOSE": lambda s, xtr, ytr, xva, yva: (
            lambda m: (m.fit(xtr, ytr, val_X=xva, val_y=yva, maxiter=1500),
                       lambda X: m.predict(X, return_std=True))[1])(
            DPOSE(layers=(1, 20, 32), activation=fnn.tanh, seed=19 + s)),
        "LLPRRegressor": lambda s, xtr, ytr, xva, yva: (
            lambda m: (m.fit(np.vstack([xtr, xva]), np.concatenate([ytr, yva])),
                       lambda X: m.predict(X, return_std=True))[1])(
            LLPRRegressor(hidden_dims=(32, 32), n_epochs=400, random_state=s)),
    }
    gin = np.linspace(0, 1, 201)
    gout = np.linspace(1, 1.5, 101)[1:]
    res = {}
    for name, b in builders.items():
        rows = []
        t0 = time.time()
        for s in range(5):
            pred = b(s, *data(s))
            row = []
            for g in (gin, gout):
                m, sd = pred(g[:, None])
                # np.real: LinearRegressionUQ (pycse 2.11.1) returns a complex dtype with zero
                # imaginary part, from np.linalg.eigvals on a symmetric matrix.
                m, sd = np.real(np.asarray(m)).ravel(), np.real(np.asarray(sd)).ravel()
                c = exact_cov(m - Z95 * sd, m + Z95 * sd, f_sin(g), 0.1)
                row += [float(c.mean()), float(np.mean(2 * Z95 * sd))]
            rows.append(row)
        rows = np.array(rows)
        res[name] = dict(cov_in=r(rows[:, 0]), w_in=r(rows[:, 1]), cov_out=r(rows[:, 2]),
                         w_out=r(rows[:, 3]))
        print(f"  {name:27s} ({time.time() - t0:.0f} s): 95% coverage in [0,1] mean"
              f" {rows[:, 0].mean():.2f} (range {rows[:, 0].min():.2f} to {rows[:, 0].max():.2f}),"
              f" width {rows[:, 1].mean():.2f}; in (1,1.5] mean {rows[:, 2].mean():.2f}"
              f" (range {rows[:, 2].min():.2f} to {rows[:, 2].max():.2f}), width {rows[:, 3].mean():.2f}")
    cache_put("pycse", res)
    plot_pycse(res)


def plot_pycse(res):
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(11, 4.4))
        names = list(res)
        xs = np.arange(len(names))
        for off, key, col, lab in [(-0.2, "cov_in", BLUE, "inside the data, [0, 1]"),
                                   (0.2, "cov_out", CMU_RED, "beyond the data, (1, 1.5]")]:
            vals = np.array([res[n][key] for n in names])
            ax.bar(xs + off, vals.mean(1), 0.38, color=col, label=lab)
            for i, v in enumerate(vals):
                ax.plot(np.full(len(v), xs[i] + off), v, "o", color=INK, ms=3.5)
        ax.axhline(0.95, color=INK, ls="--", lw=1)
        ax.set_xticks(xs, [n.replace(" (", "\n(") for n in names])
        ax.set_ylim(0, 1.12)
        ax.set_ylabel("coverage of the 95% interval")
        ax.legend(loc="upper right", ncol=2)
        save(fig, "pycse-compare.png")


# --------------------------------------------------------------------------------------
def write_widget_data():
    data = {}
    for name in ("gp", "ens", "scale", "conf"):
        p = CACHE / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())
    text = ("/* Generated by lectures/l14a/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l14a = " + json.dumps(data, separators=(",", ":")) + ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB)")


GROUPS = {"gp": group_gp, "ens": group_ens,
          "concrete": group_concrete, "conformal": group_conformal, "pycse": group_pycse}

if __name__ == "__main__":
    names = sys.argv[1:] or [g for g in GROUPS if g != "pycse"]
    for name in names:
        print(f"[{name}]")
        GROUPS[name]()
    if "pycse" not in names and (CACHE / "pycse.json").exists():
        plot_pycse(json.loads((CACHE / "pycse.json").read_text()))
    write_widget_data()
