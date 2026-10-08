#!/usr/bin/env python3
"""Generate the L15 figures and the data behind its interactive figures, and print every
number the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with numpy --with pandas --with xlrd \
        --with scikit-learn --with scipy --with matplotlib python make_figures.py

Name groups to regenerate only those; with no names, every group runs. The groups, and
what each writes:
    uq          aleatoric-epistemic.png, intervals.png, calibration.png, and the "uq" entry
                of the widget data. On the concrete strength dataset (Yeh 1998), split by
                mix exactly as in Lecture 9, three ways to get a prediction interval: the
                Gaussian process (GP) of Lecture 9, a deep ensemble of five of Lecture 9's
                networks, and split conformal prediction. Each is checked for coverage on
                the grouped test split and on an extrapolation split that holds out the
                strongest mixes (the 20% of mixes with the lowest water/cement ratio). Also
                the replicate scatter: rows that share a mix and an age.
    bo          bo-loop.png, acquisitions.png, and the "bo" entry: Bayesian optimization
                on the Forrester et al. (2008) test function, flipped to a maximization,
                g(x) = -(6x - 2)^2 sin(12x - 4) on [0, 1], with expected improvement,
                probability of improvement and an upper confidence bound.
    bench       bo-vs-random.png: Bayesian optimization against random search on a mix
                design problem, maximizing the 28-day strength predicted by a GP emulator
                fitted to all 1,030 rows, over cement, slag, water and superplasticizer
                within the range the data cover; 30 seeds each.
    al          active-learning.png: active learning on the grouped training pool,
                querying the mix the GP is least sure of against querying at random.

The concrete workbook is cached under .cache/ (copied from Lecture 9's cache when present)
and gitignored. uq takes about a minute, bo seconds, bench about a minute, al a few minutes.
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
from scipy.stats import norm
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern, WhiteKernel
from sklearn.metrics import root_mean_squared_error
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=ConvergenceWarning)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CACHE = HERE / ".cache"
L09_CACHE = HERE.parent.parent / "l09" / "figures" / ".cache"
WIDGET_JS = REPO / "_static" / "l15-widget-data.js"
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
    "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 13,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "savefig.dpi": 150, "savefig.bbox": "tight",
}

COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]
LEVELS = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def cache_put(name, obj):
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps(obj))


def r(a, nd=2):
    return [round(float(v), nd) for v in np.asarray(a).ravel()]


def load_concrete():
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "Concrete_Data.xls"
    if not path.exists() and (L09_CACHE / "Concrete_Data.xls").exists():
        shutil.copy(L09_CACHE / "Concrete_Data.xls", path)
    if not path.exists():
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI_CONCRETE).read()))
        path.write_bytes(z.read("Concrete_Data.xls"))
    df = pd.read_excel(path)
    df.columns = COLUMNS
    return df


def l09_gp(restarts=2):
    """Lecture 9's Gaussian process for the concrete strength dataset, unchanged."""
    return make_pipeline(StandardScaler(), GaussianProcessRegressor(
        kernel=ConstantKernel(1.0) * RBF(np.ones(8), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1)),
        normalize_y=True, random_state=0, n_restarts_optimizer=restarts))


def l09_net(seed):
    """Lecture 9's network for the concrete strength dataset, with a seed."""
    return make_pipeline(StandardScaler(), MLPRegressor(
        hidden_layer_sizes=(16,), activation="tanh", solver="lbfgs", max_iter=5000,
        random_state=seed))


# --------------------------------------------------------------------------------------
# uq
# --------------------------------------------------------------------------------------
def coverage_study(X, y, groups, tr, te, label):
    """GP, deep ensemble and split conformal on one split. Returns the record."""
    gp = l09_gp().fit(X[tr], y[tr])
    mu, sd = gp.predict(X[te], return_std=True)
    kern = gp[-1].kernel_
    noise = float(np.sqrt(kern.k2.noise_level) * gp[-1]._y_train_std)
    epi = np.sqrt(np.maximum(sd**2 - noise**2, 0))

    nets = [l09_net(s).fit(X[tr], y[tr]) for s in range(5)]
    P = np.array([n.predict(X[te]) for n in nets])
    emu, esd = P.mean(0), P.std(0)

    # Split conformal: a quarter of the training mixes calibrate the residuals.
    fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED)
                        .split(X[tr], y[tr], groups[tr]))
    fit_i, cal_i = tr[fit_i], tr[cal_i]
    cnets = [l09_net(s).fit(X[fit_i], y[fit_i]) for s in range(5)]
    cal_res = np.abs(y[cal_i] - np.mean([n.predict(X[cal_i]) for n in cnets], 0))
    cpred = np.mean([n.predict(X[te]) for n in cnets], 0)
    n_cal = len(cal_res)
    qs = np.array([np.quantile(cal_res, min(1.0, np.ceil((n_cal + 1) * a) / n_cal), method="higher")
                   for a in LEVELS])

    z = norm.ppf(0.5 + LEVELS / 2)
    cov = {
        "GP": [float(np.mean(np.abs(y[te] - mu) < zz * sd)) for zz in z],
        "ensemble": [float(np.mean(np.abs(y[te] - emu) < zz * esd)) for zz in z],
        "conformal": [float(np.mean(np.abs(y[te] - cpred) < q)) for q in qs],
    }
    width95 = {"GP": float(2 * 1.96 * sd.mean()), "ensemble": float(2 * 1.96 * esd.mean()),
               "conformal": float(2 * qs[-1])}
    rec = dict(
        label=label, n_train=int(len(tr)), n_test=int(len(te)), n_cal=int(n_cal),
        rmse=dict(GP=float(root_mean_squared_error(y[te], mu)),
                  ensemble=float(root_mean_squared_error(y[te], emu)),
                  conformal=float(root_mean_squared_error(y[te], cpred))),
        gp_noise=noise, gp_sd=float(sd.mean()), gp_epi=float(epi.mean()), ens_sd=float(esd.mean()),
        coverage=cov, width95=width95, q=r(qs),
        y=r(y[te], 1), gp_mu=r(mu, 1), gp_sd_pts=r(sd, 2), ens_mu=r(emu, 1), ens_sd_pts=r(esd, 2),
        conf_mu=r(cpred, 1), kernel=str(kern))
    print(f"  {label}: {len(tr)} training rows, {len(te)} test rows ({n_cal} calibration rows)")
    print(f"    RMSE: GP {rec['rmse']['GP']:.2f}, ensemble {rec['rmse']['ensemble']:.2f},"
          f" conformal's model {rec['rmse']['conformal']:.2f} MPa")
    print(f"    GP noise term {noise:.2f} MPa; mean predictive SD {sd.mean():.2f}; mean epistemic"
          f" SD {epi.mean():.2f}; ensemble mean spread {esd.mean():.2f} MPa")
    for k, v in cov.items():
        print(f"    coverage {k:10s}", " ".join(f"{c:.2f}" for c in v),
              f"   (95% interval width {width95[k]:.1f} MPa)")
    return rec


def group_uq():
    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df["strength_mpa"].to_numpy()
    groups = df.groupby(MIX).ngroup().to_numpy()

    same = df.groupby(FEATURES)["strength_mpa"].agg(["size", "std"])
    rep = same[same["size"] > 1]
    pooled = float(np.sqrt((rep["std"] ** 2 * (rep["size"] - 1)).sum() / (rep["size"] - 1).sum()))
    print(f"  replicates: {len(rep)} settings (same mix and age) tested more than once, "
          f"{int(rep['size'].sum())} rows; pooled scatter {pooled:.2f} MPa")

    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
    t0 = time.time()
    grouped = coverage_study(X, y, groups, tr, te, "grouped split, as in Lecture 9")

    wc = (df["water"] / df["cement"]).groupby(groups).mean()
    cut = float(wc.quantile(0.2))
    held = set(wc[wc <= cut].index)
    te2 = np.flatnonzero(np.isin(groups, list(held)))
    tr2 = np.flatnonzero(~np.isin(groups, list(held)))
    print(f"  extrapolation split: mixes with water/cement <= {cut:.3f} held out; mean strength"
          f" {y[te2].mean():.1f} MPa held out against {y[tr2].mean():.1f} kept")
    extrap = coverage_study(X, y, groups, tr2, te2, "extrapolation: strongest mixes held out")
    print(f"  ({time.time() - t0:.0f} s)")

    cache_put("uq", dict(levels=r(LEVELS), replicate_sd=round(pooled, 2), wc_cut=round(cut, 3),
                         splits=[grouped, extrap]))

    with plt.rc_context(STYLE):
        # ---- aleatoric and epistemic on a 1-D toy problem with a gap in the data
        rng = np.random.default_rng(SEED)
        xs = np.concatenate([rng.uniform(0, 0.35, 18), rng.uniform(0.7, 1.0, 14)])
        ftrue = lambda x: np.sin(6 * x) + 0.5 * x
        ys = ftrue(xs) + rng.normal(0, 0.15, xs.size)
        g = GaussianProcessRegressor(ConstantKernel(1.0) * RBF(0.2) + WhiteKernel(0.02),
                                     normalize_y=True, random_state=0).fit(xs[:, None], ys)
        grid = np.linspace(0, 1, 300)
        m, s_tot = g.predict(grid[:, None], return_std=True)
        nz = float(np.sqrt(g.kernel_.k2.noise_level) * g._y_train_std)
        s_epi = np.sqrt(np.maximum(s_tot**2 - nz**2, 0))
        fig, ax = plt.subplots(figsize=(10, 4.4))
        ax.fill_between(grid, m - 2 * s_tot, m + 2 * s_tot, color=BAND, lw=0,
                        label="total: aleatoric + epistemic")
        ax.fill_between(grid, m - 2 * s_epi, m + 2 * s_epi, color=ORANGE, alpha=0.35, lw=0,
                        label="epistemic only")
        ax.plot(grid, m, color=BLUE, lw=2, label="GP mean")
        ax.plot(xs, ys, "o", color=INK, ms=5, label="noisy data")
        ax.annotate("no data: epistemic\nuncertainty grows", xy=(0.52, m[156] + 2 * s_epi[156]),
                    xytext=(0.42, 2.6), color=ORANGE, ha="center",
                    arrowprops=dict(arrowstyle="->", color=ORANGE))
        ax.annotate("near data: the noise\n(aleatoric) remains", xy=(0.17, m[51] - 2 * s_tot[51]),
                    xytext=(0.12, -2.3), color=BLUE, ha="center",
                    arrowprops=dict(arrowstyle="->", color=BLUE))
        ax.set_xlabel("input $x$")
        ax.set_ylabel("output $y$")
        ax.set_ylim(-2.8, 3.2)
        ax.legend(loc="upper right", fontsize=12)
        save(fig, "aleatoric-epistemic.png")

        # ---- GP intervals on the test mixes, both splits
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), sharey=True)
        for ax, rec in zip(axes, (grouped, extrap)):
            yy, mu_, sd_ = (np.array(rec[k]) for k in ("y", "gp_mu", "gp_sd_pts"))
            miss = np.abs(yy - mu_) >= 1.96 * sd_
            ax.errorbar(yy[~miss], mu_[~miss], yerr=1.96 * sd_[~miss], fmt="o", ms=3.5,
                        color=BLUE, ecolor="#b9cde3", elinewidth=1, label="interval covers the truth")
            ax.errorbar(yy[miss], mu_[miss], yerr=1.96 * sd_[miss], fmt="o", ms=4.5,
                        color=CMU_RED, ecolor="#f0b3bd", elinewidth=1.2, label="interval misses")
            ax.plot([0, 90], [0, 90], "k--", lw=1)
            cov95 = rec["coverage"]["GP"][-1]
            ax.set_title(f"{rec['label'].split(':')[0].split(',')[0]}: {cov95:.0%} covered",
                         color=INK)
            ax.set_xlabel("measured strength (MPa)")
        axes[0].set_ylabel("predicted strength, 95% interval (MPa)")
        axes[0].legend(loc="upper left", fontsize=12)
        save(fig, "intervals.png")

        # ---- reliability diagrams
        fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
        cols = {"GP": BLUE, "ensemble": GOLD, "conformal": GREEN}
        names = {"GP": "Gaussian process", "ensemble": "ensemble spread", "conformal": "split conformal"}
        for ax, rec in zip(axes, (grouped, extrap)):
            ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect calibration")
            for k, c in cols.items():
                ax.plot(LEVELS, rec["coverage"][k], "o-", color=c, lw=2, ms=5, label=names[k])
            ax.set_title(rec["label"].split(":")[0].split(",")[0])
            ax.set_xlabel("nominal coverage")
            ax.text(0.95, 0.05, "below the line:\noverconfident", ha="right", color=CMU_RED,
                    fontsize=12)
        axes[0].set_ylabel("observed coverage on the test mixes")
        axes[1].legend(loc="upper left", fontsize=12)
        save(fig, "calibration.png")


# --------------------------------------------------------------------------------------
# bo: the loop on a 1-D test function
# --------------------------------------------------------------------------------------
def g_test(x):
    """The Forrester et al. (2008) function, negated so that we maximize it."""
    return -((6 * x - 2) ** 2) * np.sin(12 * x - 4)


def fit_1d(x, y):
    gp = GaussianProcessRegressor(
        ConstantKernel(1.0, (1e-2, 1e2)) * Matern(0.15, (0.05, 0.5), nu=2.5) + WhiteKernel(1e-4, (1e-6, 1e-1)),
        normalize_y=True, n_restarts_optimizer=4, random_state=SEED)
    return gp.fit(x[:, None], y)


def acquisition(kind, mu, sd, best):
    sd = np.maximum(sd, 1e-9)
    if kind == "EI":
        imp = mu - best
        z = imp / sd
        return imp * norm.cdf(z) + sd * norm.pdf(z)
    if kind == "PI":
        return norm.cdf((mu - best) / sd)
    if kind == "UCB":
        return mu + 3.0 * sd
    raise ValueError(kind)


def group_bo():
    grid = np.linspace(0, 1, 121)
    truth = g_test(grid)
    x0 = np.array([0.0, 0.33, 0.66, 1.0])
    print(f"  g(x) on [0, 1]: global maximum {truth.max():.2f} at x = {grid[truth.argmax()]:.3f}; "
          f"start points {x0.tolist()}, best start value {g_test(x0).max():.2f}")
    runs = {}
    for kind in ("EI", "PI", "UCB"):
        x = x0.copy()
        frames = []
        for it in range(8):
            y = g_test(x)
            gp = fit_1d(x, y)
            mu, sd = gp.predict(grid[:, None], return_std=True)
            acq = acquisition(kind, mu, sd, y.max())
            nxt = float(grid[int(acq.argmax())])
            frames.append(dict(x=r(x, 3), y=r(y, 3), mu=r(mu, 3), sd=r(sd, 3),
                               acq=r(acq / (acq.max() or 1), 3), next=round(nxt, 3)))
            x = np.append(x, nxt)
        best = g_test(x).max()
        print(f"  {kind}: picks {[f['next'] for f in frames]}; best after 8 picks {best:.2f}")
        runs[kind] = frames
    cache_put("bo", dict(grid=r(grid, 3), truth=r(truth, 3), runs=runs))

    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(3, 2, figsize=(13, 9.6), sharex=True,
                                 gridspec_kw={"hspace": 0.45, "wspace": 0.2})
        for row in range(3):
            fr = runs["EI"][row]
            mu, sd = np.array(fr["mu"]), np.array(fr["sd"])
            ax = axes[row, 0]
            ax.plot(grid, truth, color=GRAY, lw=2, label="true objective" if row == 0 else None)
            ax.fill_between(grid, mu - 1.96 * sd, mu + 1.96 * sd, color=BAND, lw=0,
                            label="GP 95% band" if row == 0 else None)
            ax.plot(grid, mu, color=BLUE, lw=2, label="GP mean" if row == 0 else None)
            ax.plot(fr["x"], fr["y"], "o", color=INK, ms=6, label="evaluated" if row == 0 else None)
            ax.axvline(fr["next"], color=CMU_RED, ls="--", lw=1.5)
            ax.set_title(f"iteration {row + 1}: fit the GP to {len(fr['x'])} points")
            ax = axes[row, 1]
            ax.plot(grid, fr["acq"], color=GREEN, lw=2)
            ax.axvline(fr["next"], color=CMU_RED, ls="--", lw=1.5)
            ax.set_title(f"expected improvement: next x = {fr['next']:.2f}")
            ax.set_yticks([])
        axes[0, 0].legend(loc="lower left", fontsize=11)
        axes[2, 0].set_xlabel("design variable $x$")
        axes[2, 1].set_xlabel("design variable $x$")
        save(fig, "bo-loop.png")

        # one GP state, three acquisitions
        x = np.append(x0, runs["EI"][0]["next"])       # the state after one EI pick
        y = g_test(x)
        gp = fit_1d(x, y)
        mu, sd = gp.predict(grid[:, None], return_std=True)
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                                 gridspec_kw={"height_ratios": [1.3, 1], "hspace": 0.12})
        ax = axes[0]
        ax.plot(grid, truth, color=GRAY, lw=2, label="true objective")
        ax.fill_between(grid, mu - 1.96 * sd, mu + 1.96 * sd, color=BAND, lw=0, label="GP 95% band")
        ax.plot(grid, mu, color=BLUE, lw=2, label="GP mean")
        ax.plot(x, y, "o", color=INK, ms=6, label="evaluated")
        ax.legend(loc="lower left", fontsize=11, ncol=2)
        picks = {}
        for kind, col, lab in (("EI", GREEN, "expected improvement"), ("PI", GOLD, "probability of improvement"),
                               ("UCB", ORANGE, "upper confidence bound, $\\kappa$ = 3")):
            a = acquisition(kind, mu, sd, y.max())
            a = (a - a.min()) / ((a.max() - a.min()) or 1)
            nxt = grid[int(a.argmax())]
            picks[kind] = float(nxt)
            axes[1].plot(grid, a, color=col, lw=2, label=f"{lab}: next x = {nxt:.2f}")
            axes[0].axvline(nxt, color=col, ls="--", lw=1.4)
        axes[1].set_yticks([])
        axes[1].set_ylabel("acquisition\n(scaled)")
        axes[1].set_xlabel("design variable $x$")
        axes[1].legend(loc="upper left", fontsize=11)
        save(fig, "acquisitions.png")
        print(f"  acquisitions from one GP state: {picks}")


# --------------------------------------------------------------------------------------
# bench: Bayesian optimization against random search on a mix design
# --------------------------------------------------------------------------------------
DESIGN = ["cement", "slag", "water", "superplasticizer"]


def group_bench():
    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df["strength_mpa"].to_numpy()
    emulator = l09_gp().fit(X, y)
    d28 = df[df.age_days == 28]
    fixed = d28[FEATURES].median()
    lo = d28[DESIGN].quantile(0.05).to_numpy()
    hi = d28[DESIGN].quantile(0.95).to_numpy()
    idx = [FEATURES.index(c) for c in DESIGN]

    def lab(u):
        """Cast and test a mix at 28 days: here, the emulator's prediction."""
        rows = np.tile(fixed.to_numpy(), (len(u), 1))
        rows[:, idx] = lo + u * (hi - lo)
        return emulator.predict(rows)

    rng = np.random.default_rng(SEED)
    dense = lab(rng.random((200_000, 4)))
    best_possible = float(dense.max())
    print(f"  design bounds (5th to 95th percentile of the 28-day mixes): "
          + ", ".join(f"{c} {a:.0f} to {b:.0f}" for c, a, b in zip(DESIGN, lo, hi)) + " kg/m3")
    print(f"  best emulated 28-day strength in the box (200,000 random mixes): {best_possible:.1f} MPa")
    u_best = rng.random((200_000, 4))
    u_best = u_best[int(lab(u_best).argmax())]
    row = fixed.to_numpy().copy()
    row[idx] = lo + u_best * (hi - lo)
    m_b, s_b = emulator.predict(row[None, :], return_std=True)
    print("  that mix: " + ", ".join(f"{c} {v:.0f}" for c, v in zip(DESIGN, row[idx])) +
          f" kg/m3; emulator {m_b[0]:.1f} +/- {1.96 * s_b[0]:.1f} MPa (95%); strongest specimen in"
          f" the data {y.max():.1f} MPa; strongest at 28 days {d28.strength_mpa.max():.1f} MPa")

    budget, n_init, n_seeds = 25, 5, 30
    curves = {"BO": [], "random": []}
    t0 = time.time()
    for seed in range(n_seeds):
        r_ = np.random.default_rng(seed)
        u = r_.random((budget, 4))
        curves["random"].append(np.maximum.accumulate(lab(u)))
        U = r_.random((n_init, 4))
        Y = lab(U)
        for _ in range(budget - n_init):
            gp = GaussianProcessRegressor(
                ConstantKernel(1.0) * Matern(np.ones(4), (1e-2, 1e2), nu=2.5) + WhiteKernel(1e-3, (1e-6, 1e-1)),
                normalize_y=True, random_state=seed).fit(U, Y)
            cand = r_.random((4000, 4))
            mu, sd = gp.predict(cand, return_std=True)
            nxt = cand[int(acquisition("EI", mu, sd, Y.max()).argmax())]
            U = np.vstack([U, nxt])
            Y = np.append(Y, lab(nxt[None, :]))
        curves["BO"].append(np.maximum.accumulate(Y))
    print(f"  {n_seeds} seeds x {budget} evaluations each ({time.time() - t0:.0f} s)")
    out = {}
    for k, c in curves.items():
        c = np.array(c)
        gap = best_possible - c
        within = [int(np.argmax(g <= 1.0)) + 1 if (g <= 1.0).any() else None for g in gap]
        hit = [w for w in within if w is not None]
        out[k] = dict(median=r(np.median(c, 0), 2), q25=r(np.quantile(c, 0.25, 0), 2),
                      q75=r(np.quantile(c, 0.75, 0), 2))
        print(f"  {k:6s}: median best after 10 evaluations {np.median(c[:, 9]):.1f} MPa, after 25 "
              f"{np.median(c[:, -1]):.1f}; within 1 MPa of the best in {len(hit)} of {n_seeds} seeds"
              + (f", median {int(np.median(hit))} evaluations" if hit else ""))

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(10, 4.8))
        n = np.arange(1, budget + 1)
        for k, col in (("random", GRAY), ("BO", BLUE)):
            ax.fill_between(n, out[k]["q25"], out[k]["q75"], color=col, alpha=0.2, lw=0)
            ax.plot(n, out[k]["median"], color=col, lw=2.5,
                    label="Bayesian optimization (EI)" if k == "BO" else "random search")
        ax.axhline(best_possible, color=CMU_RED, ls="--", lw=1.4)
        ax.text(budget, best_possible + 0.4, f"the emulator's best: {best_possible:.1f} MPa", ha="right",
                color=CMU_RED)
        ax.axvline(n_init + 0.5, color=MUTED, ls=":", lw=1)
        ax.text(n_init + 0.8, ax.get_ylim()[0] + 1, "5 random mixes to start", color=MUTED, fontsize=12)
        ax.set_xlabel("mixes cast and tested (28 days each)")
        ax.set_ylabel("best strength so far (MPa)")
        ax.legend(loc="lower right")
        save(fig, "bo-vs-random.png")


# --------------------------------------------------------------------------------------
# al: active learning on the grouped training pool
# --------------------------------------------------------------------------------------
def group_al():
    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df["strength_mpa"].to_numpy()
    groups = df.groupby(MIX).ngroup().to_numpy()
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
    n_start, n_query, n_seeds = 20, 40, 8
    sc = StandardScaler().fit(X[tr])
    Xp, yp, Xt, yt = sc.transform(X[tr]), y[tr], sc.transform(X[te]), y[te]
    res = {"uncertainty": [], "random": []}
    picked = {"uncertainty": [], "random": []}
    t0 = time.time()
    for seed in range(n_seeds):
        r_ = np.random.default_rng(seed)
        start = list(r_.choice(len(Xp), n_start, replace=False))
        for strat in res:
            lab_ = list(start)
            curve = []
            for q in range(n_query + 1):
                gp = GaussianProcessRegressor(
                    ConstantKernel(1.0) * RBF(np.ones(8), (1e-2, 1e3)) + WhiteKernel(1e-1, (1e-5, 1e1)),
                    normalize_y=True, random_state=0).fit(Xp[lab_], yp[lab_])
                curve.append(root_mean_squared_error(yt, gp.predict(Xt)))
                if q == n_query:
                    picked[strat].extend(lab_[n_start:])
                    break
                pool = np.setdiff1d(np.arange(len(Xp)), lab_)
                if strat == "uncertainty":
                    _, sd = gp.predict(Xp[pool], return_std=True)
                    lab_.append(int(pool[int(sd.argmax())]))
                else:
                    lab_.append(int(r_.choice(pool)))
            res[strat].append(curve)
    print(f"  {n_seeds} seeds, start with {n_start} rows, {n_query} queries ({time.time() - t0:.0f} s)")
    edge = lambda rows: float(np.mean(np.max(np.abs(rows), axis=1)))
    print(f"  how extreme the queried mixes are (mean of each row's largest |standardized input|): "
          f"uncertainty {edge(Xp[picked['uncertainty']]):.2f}, random {edge(Xp[picked['random']]):.2f}, "
          f"test mixes {edge(Xt):.2f}")
    ages = X[tr][:, FEATURES.index("age_days")]
    for k in picked:
        a = ages[picked[k]]
        print(f"  {k:12s}: {np.mean((a <= 3) | (a >= 180)):.0%} of queries at age 3 days or 180 days and"
              f" over (pool: {np.mean((ages <= 3) | (ages >= 180)):.0%})")
    out = {}
    for k, c in res.items():
        c = np.array(c)
        out[k] = np.median(c, 0)
        print(f"  {k:12s}: median test RMSE {out[k][0]:.2f} MPa at {n_start} rows, "
              f"{out[k][20]:.2f} at {n_start + 20}, {out[k][-1]:.2f} at {n_start + n_query}")

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(10, 4.6))
        n = np.arange(n_start, n_start + n_query + 1)
        ax.plot(n, out["random"], color=GRAY, lw=2.5, label="query at random")
        ax.plot(n, out["uncertainty"], color=BLUE, lw=2.5, label="query where the GP is least sure")
        ax.annotate("least-sure queries go to\nextreme mixes at the edges", xy=(n[18], out["uncertainty"][18]),
                    xytext=(n[22], out["uncertainty"][18] + 2.2), color=BLUE,
                    arrowprops=dict(arrowstyle="->", color=BLUE))
        ax.set_xlabel("labeled rows (tested specimens)")
        ax.set_ylabel("test RMSE (MPa)")
        ax.legend(loc="lower left")
        save(fig, "active-learning.png")


# --------------------------------------------------------------------------------------
def write_widget_data():
    data = {}
    for name in ("uq", "bo"):
        p = CACHE / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())
    if "uq" in data:
        for s in data["uq"]["splits"]:
            s.pop("kernel", None)
    text = ("/* Generated by lectures/l15/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l15 = " + json.dumps(data, separators=(",", ":")) + ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB)")


GROUPS = {"uq": group_uq, "bo": group_bo, "bench": group_bench, "al": group_al}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(f"[{name}]")
        GROUPS[name]()
    write_widget_data()
