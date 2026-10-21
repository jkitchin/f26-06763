#!/usr/bin/env python3
"""Generate the L15 figures and the data behind its interactive figures, and print every
number the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with botorch --with numpy --with scipy \
        --with matplotlib python make_figures.py

Name groups to regenerate only those; with no names, every group runs.

The example. Series reactions A -> B -> C in a continuous stirred tank. B is the product; it
keeps reacting into the waste C. Both steps follow Arrhenius kinetics, and the second needs
more heat (E2 > E1), so heat helps the first step and then the second. The yield of B at
steady state, for temperature T and residence time tau, is

    y = k1 tau / ((1 + k1 tau)(1 + k2 tau)),   ki = ki_ref exp(-Ei/R (1/T - 1/T_ref))

with k1_ref = 0.15 1/min, E1 = 60 kJ/mol, k2_ref = 0.03 1/min, E2 = 110 kJ/mol, T_ref = 80 C.
An experiment measures y with noise of standard deviation 0.01.

    problem     yield-curve.png, landscape.png: the true yield against temperature (tau = 10
                min) and over temperature and residence time; the optima. Also grid.png and
                random.png, reactor.png and reactor-pump.png, and the industry-*.png sketches.
    posterior   the "posterior" entry: a Gaussian process with fixed, printed settings
                conditioned on 0 to 5 experiments, with three sample curves that keep their
                random numbers from frame to frame; gp-schematic.png.
    loop        the "loop" entry and acquisitions.png: Bayesian optimization in BoTorch on the
                1-D problem (temperature, tau = 10 min) from two old runs at 30 and 50 C,
                exactly as the worked example; the GP, the expected improvement and the next
                point at every iteration; one GP state with PI, EI and UCB. Also final-gp.png,
                logei.png, ucb.png, pi-picture.png, ei-picture.png, terminology.png,
                ext-batch.png and the loop-*.png panels.
    race        the "race" entry and bo-vs-random.png: the 2-D problem (temperature and
                residence time) from three old runs, BO against Nelder-Mead, L-BFGS-B with
                finite-difference gradients, and random search; ten seeds each.
    schematics  race-*.png (seed 0 of each method, from the race cache), finite-diff.png,
                decision-map.png, and the four extension sketches (pareto, constraint, batch
                is in loop, fidelity).
    al          al-vs-bo.png: six more experiments chosen by expected improvement against six
                chosen where the GP is most uncertain (active learning).
    ego         ego.png: the idea of Jones, Schonlau and Welch (1998), Figs. 8 to 11, redrawn on a
                function of our own.

Results are cached under .cache/ (gitignored). problem and posterior take seconds, loop about
ten seconds, race a few minutes.
"""
import json
import shutil
import sys
import time
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from botorch.acquisition import LogExpectedImprovement
from botorch.fit import fit_gpytorch_mll
from botorch.models import SingleTaskGP
from botorch.models.transforms import Normalize, Standardize
from botorch.optim import optimize_acqf
from gpytorch.mlls import ExactMarginalLogLikelihood
from scipy.optimize import minimize
from scipy.stats import norm

warnings.filterwarnings("ignore")
torch.set_default_dtype(torch.float64)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)
WIDGET_JS = REPO / "_static" / "l15-widget-data.js"

RED, BLUE, GOLD, GREEN, GRAY = "#c41230", "#1f5c99", "#b07d12", "#2e7d32", "#8a8a8a"
plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 150, "savefig.bbox": "tight"})

# ------------------------------------------------------------------------ the reactor
R_GAS = 8.314                       # J/(mol K)
K1, E1 = 0.15, 60e3                 # 1/min at T_ref, J/mol: A -> B
K2, E2 = 0.03, 110e3                # 1/min at T_ref, J/mol: B -> C
T_REF = 80.0                        # C
TAU_1D = 10.0                       # min, the residence time of the 1-D problem
NOISE = 0.01                        # standard deviation of a yield measurement
T_LO, T_HI = 20.0, 140.0            # C
TAU_LO, TAU_HI = 1.0, 30.0          # min


def rate(T, k_ref, E):
    T = np.asarray(T, dtype=float) + 273.15
    return k_ref * np.exp(-E / R_GAS * (1 / T - 1 / (T_REF + 273.15)))


def yield_B(T, tau=TAU_1D):
    k1, k2 = rate(T, K1, E1), rate(T, K2, E2)
    return k1 * tau / ((1 + k1 * tau) * (1 + k2 * tau))


GRID_T = np.linspace(T_LO, T_HI, 241)
Y_1D = yield_B(GRID_T)
T_STAR = float(GRID_T[Y_1D.argmax()])
Y_STAR = float(Y_1D.max())


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def r(a, nd=4):
    return np.round(np.asarray(a, dtype=float), nd).tolist()


def cache_put(name, obj):
    (CACHE / f"{name}.json").write_text(json.dumps(obj))


def gp_fit(X, y, d):
    gp = SingleTaskGP(X, y, input_transform=Normalize(d=d), outcome_transform=Standardize(m=1))
    fit_gpytorch_mll(ExactMarginalLogLikelihood(gp.likelihood, gp))
    return gp


# ------------------------------------------------------------------------ problem
def group_problem():
    fine = np.linspace(T_LO, T_HI, 1201)
    yf = yield_B(fine)
    print(f"  1-D optimum (tau = {TAU_1D:g} min): T = {fine[yf.argmax()]:.1f} C, yield {yf.max():.3f}; "
          f"yield at 20 C {yf[0]:.3f}, at 140 C {yf[-1]:.3f}")
    TT, UU = np.meshgrid(np.linspace(T_LO, T_HI, 241), np.linspace(TAU_LO, TAU_HI, 233))
    Y = yield_B(TT, UU)
    j = np.unravel_index(Y.argmax(), Y.shape)
    print(f"  2-D optimum: T = {TT[j]:.1f} C, tau = {UU[j]:.1f} min, yield {Y.max():.3f}")

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.axvspan(T_LO, 50, color=BLUE, alpha=0.07)
    ax.axvspan(105, T_HI, color=RED, alpha=0.07)
    ax.plot(fine, yf, color="k", lw=2.5)
    ax.plot(fine[yf.argmax()], yf.max(), "o", color=GOLD, ms=11, zorder=3)
    ax.annotate(f"best: {fine[yf.argmax()]:.0f} °C,\nyield {yf.max():.2f}", (fine[yf.argmax()], yf.max()),
                xytext=(96, 0.47), fontsize=13, color=GOLD, arrowprops=dict(arrowstyle="->", color=GOLD))
    ax.text(35, 0.40, "too cold:\nA barely reacts", ha="center", fontsize=13, color=BLUE)
    ax.text(122, 0.40, "too hot:\nB burns into C", ha="center", fontsize=13, color=RED)
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("yield of B (fraction of A)")
    ax.set_ylim(0, 0.55)
    save(fig, "yield-curve.png")

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    cs = ax.contourf(TT, UU, Y, levels=np.linspace(0, 0.56, 15), cmap="Greys")
    ax.contour(TT, UU, Y, levels=[0.3, 0.4, 0.5, 0.54], colors="k", linewidths=0.8)
    ax.axhline(TAU_1D, color=BLUE, lw=2, ls="--")
    ax.text(124, TAU_1D + 0.8, "the 1-D problem", color=BLUE, fontsize=12, ha="center")
    ax.plot(TT[j], UU[j], "*", color=GOLD, ms=20, mec="k")
    ax.annotate(f"best: {TT[j]:.0f} °C, {UU[j]:.0f} min\nyield {Y.max():.2f}", (TT[j], UU[j]), xytext=(92, 24),
                fontsize=12, color="k", arrowprops=dict(arrowstyle="->"))
    fig.colorbar(cs, ax=ax, label="yield of B")
    ax.set_ylim(TAU_LO, TAU_HI + 1.5)
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("residence time (min)")
    save(fig, "landscape.png")

    # where a grid and random search spend six experiments
    rng = np.random.default_rng(4)
    pts_grid = np.linspace(T_LO, T_HI, 6)
    pts_rand = np.sort(rng.uniform(T_LO, T_HI, 6))
    print(f"  grid of 6 at {np.round(pts_grid).tolist()}: {int((yield_B(pts_grid) >= 0.9 * yf.max()).sum())} within 10% of the best; "
          f"random 6 at {np.round(pts_rand).tolist()}: {int((yield_B(pts_rand) >= 0.9 * yf.max()).sum())}")
    # a grid and random search, as two files, so the deck can show one, then the other
    for xs, title, name in [(pts_grid, "a grid, every 24 °C", "grid.png"), (pts_rand, "random search", "random.png")]:
        fig, ax = plt.subplots(figsize=(5.6, 3.6))
        ax.plot(fine, yf, color=GRAY, lw=2)
        good = yield_B(xs) >= 0.9 * yf.max()
        ax.vlines(xs, 0, yield_B(xs), color=np.where(good, GREEN, RED), lw=1.5)
        ax.plot(xs, yield_B(xs), "o", ms=9, color="k")
        ax.set_title(f"{title}: {good.sum()} of 6 within 10% of the best", fontsize=13)
        ax.set_xlabel("temperature (°C)")
        ax.set_ylabel("yield of B")
        ax.set_ylim(0, 0.52)
        save(fig, name)

    draw_reactor("reactor.png", pump=False)
    draw_reactor("reactor-pump.png", pump=True)

    # three industrial cases with the same shape: the product is made, then destroyed
    t = np.linspace(0, 6, 300)
    for name, (a, b, c), (k1, k2) in [("industry-eo.png", ("ethylene", "EO", "CO₂"), (1.2, 0.35)),
                                      ("industry-sugar.png", ("cellulose", "glucose", "waste"), (0.8, 0.5)),
                                      ("industry-drug.png", ("reagents", "drug", "impurities"), (1.5, 0.25))]:
        A = np.exp(-k1 * t)
        B = k1 / (k2 - k1) * (np.exp(-k1 * t) - np.exp(-k2 * t))
        C = 1 - A - B
        fig, ax = plt.subplots(figsize=(3.6, 2.5))
        ax.plot(t, A, color=BLUE, lw=2.5, label=a)
        ax.plot(t, B, color=GREEN, lw=3.5, label=b)
        ax.plot(t, C, color=GRAY, lw=2.5, label=c)
        j = int(B.argmax())
        ax.plot(t[j], B[j], "o", color=GOLD, ms=9, zorder=3)
        ax.text(t[j], B[j] + 0.1, "best", color=GOLD, fontsize=12, fontweight="bold", ha="center")
        ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=11, frameon=False,
                  handlelength=1.2, columnspacing=0.9, borderaxespad=0.1)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("time, or heat")
        ax.set_ylabel("amount")
        ax.set_ylim(0, 1.08)
        save(fig, name)


def draw_reactor(name, pump):
    # the stirred tank; with pump=True the feed pump, which sets the residence time, is highlighted
    from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.4)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((3, 1), 4, 4.6, boxstyle="round,pad=0.1,rounding_size=0.5", fc="#eef3f8", ec="k", lw=2))
    ax.plot([6.3, 6.3], [5.9, 1.6], color="k", lw=2)
    ax.plot([5.7, 6.9], [1.6, 1.6], color="k", lw=4)
    ax.add_patch(FancyArrowPatch((0.2, 5.0), (3.0, 5.0), arrowstyle="-|>", mutation_scale=22, lw=2.5, color=BLUE))
    if pump:
        ax.add_patch(Circle((1.3, 5.0), 0.45, fc="white", ec=RED, lw=3, zorder=3))
        ax.text(1.3, 5.0, "P", ha="center", va="center", fontsize=14, fontweight="bold", color=RED, zorder=4)
        ax.text(1.3, 5.65, "pump: flow q", ha="center", fontsize=13, color=RED, fontweight="bold")
        ax.text(5, 6.6, "time in the tank: τ = V / q", ha="center", fontsize=14, color=RED, fontweight="bold")
    else:
        ax.text(1.6, 5.35, "feed: A", ha="center", fontsize=15, color=BLUE)
        ax.text(5, 6.6, "time in the tank: τ", ha="center", fontsize=13)
    ax.add_patch(FancyArrowPatch((7.0, 1.8), (9.6, 1.8), arrowstyle="-|>", mutation_scale=22, lw=2.5, color=GOLD))
    ax.text(8.3, 2.15, "out: B, C,\nleft-over A", ha="center", va="bottom", fontsize=13, color=GOLD)
    ax.text(4.55, 4.3, "A → B → C", ha="center", fontsize=19, fontweight="bold")
    ax.text(4.55, 3.5, "B: product\nC: waste", ha="center", va="top", fontsize=12, color=GRAY)
    for x in (3.9, 5.0, 6.1):
        ax.annotate("", (x, 0.95), (x, 0.25), arrowprops=dict(arrowstyle="-|>", color=RED, lw=2))
    ax.text(5, 0.0, "heat: temperature T", ha="center", fontsize=13, color=RED)
    save(fig, name)


# ------------------------------------------------------------------------ posterior
# A GP with fixed settings, so the band shrinks only because data arrive.
POST_MEAN, POST_SD, POST_ELL = 0.25, 0.15, 20.0       # prior mean, prior sd, length scale (C)
POST_T = [30.0, 50.0, 110.0, 80.0, 65.0]               # the order the experiments arrive in


def gp_numpy(xt, yt, xs, mean, sd, ell, noise):
    k = lambda a, b: sd ** 2 * np.exp(-0.5 * ((a[:, None] - b[None, :]) / ell) ** 2)
    if len(xt) == 0:
        return np.full(len(xs), mean), k(xs, xs)
    K = k(xt, xt) + noise ** 2 * np.eye(len(xt))
    Ks = k(xs, xt)
    A = np.linalg.solve(K, Ks.T)
    return mean + A.T @ (yt - mean), k(xs, xs) - Ks @ A


def group_posterior():
    rng = np.random.default_rng(15)
    yt_all = yield_B(np.array(POST_T)) + NOISE * rng.standard_normal(len(POST_T))
    z = np.random.default_rng(7).standard_normal((3, len(GRID_T)))
    frames = []
    for n in range(len(POST_T) + 1):
        xt, yt = np.array(POST_T[:n]), yt_all[:n]
        mu, cov = gp_numpy(xt, yt, GRID_T, POST_MEAN, POST_SD, POST_ELL, NOISE)
        L = np.linalg.cholesky(cov + 1e-8 * np.eye(len(GRID_T)))
        samples = mu[None, :] + z @ L.T
        frames.append({"x": r(xt, 1), "y": r(yt), "mu": r(mu), "sd": r(np.sqrt(np.clip(np.diag(cov), 0, None))),
                       "samples": [r(s) for s in samples]})
        print(f"  {n} experiments: band half-width at 80 C {1.96 * np.sqrt(cov[GRID_T.searchsorted(80), GRID_T.searchsorted(80)]):.3f}")
    print(f"  prior: mean {POST_MEAN}, sd {POST_SD}, length scale {POST_ELL} C, noise sd {NOISE}")

    # the GP of Lecture 14 in one picture: before data, and after three experiments
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.9), sharey=True)
    for ax, n, title in [(axes[0], 0, "before any experiment: the prior"), (axes[1], 3, "after 3 experiments: the posterior")]:
        xt, yt = np.array(POST_T[:n]), yt_all[:n]
        mu, cov = gp_numpy(xt, yt, GRID_T, POST_MEAN, POST_SD, POST_ELL, NOISE)
        sd = np.sqrt(np.clip(np.diag(cov), 0, None))
        L = np.linalg.cholesky(cov + 1e-8 * np.eye(len(GRID_T)))
        ax.fill_between(GRID_T, mu - 2 * sd, mu + 2 * sd, color=BLUE, alpha=0.15)
        for k in range(3):
            ax.plot(GRID_T, mu + L @ z[k], color=[GOLD, GREEN, RED][k], lw=1, alpha=0.8)
        ax.plot(GRID_T, mu, color=BLUE, lw=2.5)
        if n:
            ax.plot(xt, yt, "ko", ms=8, zorder=4)
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("temperature (°C)")
    axes[0].set_ylabel("yield of B")
    axes[0].annotate("mean μ(x)", (125, POST_MEAN), xytext=(100, -0.12), color=BLUE, fontsize=12,
                     arrowprops=dict(arrowstyle="->", color=BLUE))
    axes[0].annotate("band μ ± 2σ(x)", (40, POST_MEAN + 2 * POST_SD), xytext=(22, 0.66), color=BLUE, fontsize=12,
                     arrowprops=dict(arrowstyle="->", color=BLUE))
    axes[1].annotate("pinched at an\nexperiment", (POST_T[0], yt_all[0]), xytext=(38, 0.55), fontsize=12,
                     arrowprops=dict(arrowstyle="->"))
    axes[1].annotate("thin lines: sample curves", (128, 0.05), xytext=(70, -0.2), fontsize=11, color=GRAY,
                     arrowprops=dict(arrowstyle="->", color=GRAY))
    axes[0].set_ylim(-0.3, 0.75)
    save(fig, "gp-schematic.png")
    cache_put("posterior", {"grid": r(GRID_T, 1), "truth": r(Y_1D), "frames": frames,
                            "prior": {"mean": POST_MEAN, "sd": POST_SD, "ell": POST_ELL}})


# ------------------------------------------------------------------------ loop
def run_experiment_1d(T, gen):
    # one experiment: the yield of B at temperature T (C), tau = 10 min, with measurement noise
    y = yield_B(T.numpy().ravel()) + NOISE * gen.standard_normal(T.shape[0])
    return torch.tensor(y).unsqueeze(-1)


def group_loop():
    torch.manual_seed(0)
    gen = np.random.default_rng(0)
    bounds = torch.tensor([[T_LO], [T_HI]])
    T = torch.tensor([[30.0], [50.0]])
    y = run_experiment_1d(T, gen)
    grid = torch.tensor(GRID_T).unsqueeze(-1)
    frames = []
    for i in range(10):
        gp = gp_fit(T, y, 1)
        acq = LogExpectedImprovement(gp, best_f=y.max())
        T_next, _ = optimize_acqf(acq, bounds=bounds, q=1, num_restarts=10, raw_samples=200)
        with torch.no_grad():
            post = gp.posterior(grid)
            mu = post.mean.squeeze().numpy()
            sd = post.variance.sqrt().squeeze().numpy()
            ei = acq(grid.unsqueeze(-2)).exp().numpy()
        frames.append({"x": r(T.numpy().ravel(), 1), "y": r(y.numpy().ravel()), "mu": r(mu), "sd": r(sd),
                       "acq": r(ei / ei.max()), "next": round(float(T_next), 1), "best": round(float(y.max()), 4)})
        if i == 1:
            state = {"x": r(T.numpy().ravel(), 1), "y": r(y.numpy().ravel()), "mu": r(mu), "sd": r(sd),
                     "best": round(float(y.max()), 4)}
            acq_state = (T.numpy().ravel(), y.numpy().ravel(), mu, sd, gp)
        y_next = run_experiment_1d(T_next, gen)
        T = torch.cat([T, T_next])
        y = torch.cat([y, y_next])
    picks = T.numpy().ravel()
    print("  picks (C):", np.round(picks, 1).tolist())
    print("  measured yields:", np.round(y.numpy().ravel(), 3).tolist())
    k = int(y.argmax())
    print(f"  best measured: T = {picks[k]:.1f} C, measured {float(y[k]):.3f}, true {yield_B(picks[k]):.3f} "
          f"(true optimum {T_STAR:.1f} C, {Y_STAR:.3f})")
    first = next(n for n in range(1, len(picks) + 1) if yield_B(picks[:n][np.argmax(y.numpy().ravel()[:n])]) >= 0.98 * Y_STAR)
    print(f"  evaluations to 98% of the best yield (two old runs included): {first}")
    # the answer: the GP after all twelve experiments, against the hidden truth
    gp = gp_fit(T, y, 1)
    with torch.no_grad():
        post = gp.posterior(grid)
        mu_f = post.mean.squeeze().numpy()
        sd_f = post.variance.sqrt().squeeze().numpy()
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    ax.fill_between(GRID_T, mu_f - 1.96 * sd_f, mu_f + 1.96 * sd_f, color=BLUE, alpha=0.15)
    ax.plot(GRID_T, Y_1D, color=GRAY, lw=2.5, ls="--", label="true yield (hidden)")
    ax.plot(GRID_T, mu_f, color=BLUE, lw=2, label="GP mean, 95% band")
    ax.plot(picks, y.numpy().ravel(), "ko", ms=7, label="experiments")
    ax.plot(picks[k], float(y[k]), "o", ms=13, mfc="none", mec=GOLD, mew=2.5, label=f"best: {picks[k]:.0f} °C")
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("yield of B")
    ax.legend(loc="upper right", fontsize=10, frameon=False)
    save(fig, "final-gp.png")

    cache_put("loop", {"grid": r(GRID_T, 1), "truth": r(Y_1D), "frames": frames, "t_star": T_STAR,
                       "y_star": round(Y_STAR, 4), "state": state})
    loop_pictures(frames, picks, y.numpy().ravel())

    # LogEI: on the final GP, plain EI underflows to exactly zero over most of the range
    with torch.no_grad():
        log_ei = LogExpectedImprovement(gp, best_f=y.max())(grid.unsqueeze(-2)).numpy()
    ei = np.exp(log_ei)
    zero = ei == 0.0
    print(f"  final GP: log EI from {log_ei.min():.0f} to {log_ei.max():.1f}; EI is exactly 0.0 in float64 at "
          f"{zero.sum()} of {len(ei)} grid points ({zero.mean():.0%}), between {GRID_T[zero].min():.0f} and "
          f"{GRID_T[zero].max():.0f} C" if zero.any() else f"  final GP: log EI from {log_ei.min():.0f}; EI never 0.0")
    fig, axes = plt.subplots(2, 1, figsize=(8.5, 5.2), sharex=True)
    axes[0].plot(GRID_T, ei, color=GREEN, lw=2.5)
    axes[0].plot(GRID_T[zero], ei[zero], "o", color=RED, ms=3)
    axes[0].set_ylabel("EI")
    axes[0].set_title("expected improvement after 12 experiments: red = exactly 0.0 in the computer", fontsize=12)
    axes[1].plot(GRID_T, log_ei, color=BLUE, lw=2.5)
    axes[1].set_ylabel("log EI")
    axes[1].set_title("log expected improvement: a finite number everywhere, with a slope", fontsize=12)
    axes[1].set_xlabel("temperature (°C)")
    save(fig, "logei.png")

    # one GP state, four acquisition functions
    xs, ys, mu, sd, gp = acq_state
    best = ys.max()
    z = (mu - best) / sd
    acqs = {
        "probability of improvement": norm.cdf(z),
        "expected improvement": (mu - best) * norm.cdf(z) + sd * norm.pdf(z),
        "upper confidence bound, κ = 2": mu + 2 * sd,
    }
    fig, axes = plt.subplots(4, 1, figsize=(8.5, 8.4), sharex=True, gridspec_kw={"height_ratios": [2.2, 1, 1, 1]})
    ax = axes[0]
    ax.fill_between(GRID_T, mu - 1.96 * sd, mu + 1.96 * sd, color=BLUE, alpha=0.15)
    ax.plot(GRID_T, Y_1D, color=GRAY, lw=2, label="true yield (hidden)")
    ax.plot(GRID_T, mu, color=BLUE, lw=2, label="GP mean, 95% band")
    ax.plot(xs, ys, "ko", ms=7, label="experiments")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=11, frameon=False)
    ax.set_ylabel("yield of B")
    colors = [GOLD, GREEN, BLUE]
    print(f"  one GP, {len(xs)} experiments:")
    for a, (name, v), c in zip(axes[1:], acqs.items(), colors):
        a.plot(GRID_T, v, color=c, lw=2)
        kx = GRID_T[np.argmax(v)]
        a.axvline(kx, color=c, ls="--")
        a.set_ylabel(name.split(",")[0].replace("probability of improvement", "PI").replace("expected improvement", "EI")
                     .replace("upper confidence bound", "UCB"), fontsize=11)
        a.set_yticks([])
        a.text(1.01, 0.5, f"{name.split(',')[0]}\nnext: {kx:.0f} °C", transform=a.transAxes, fontsize=11,
               color=c, va="center")
        ax.axvline(kx, color=c, ls="--", lw=1)
        print(f"    {name}: next T = {kx:.1f} C")
    axes[-1].set_xlabel("temperature (°C)")
    save(fig, "acquisitions.png")

    # UCB and LCB on the same GP
    kappa = 2.0
    ucb, lcb = mu + kappa * sd, mu - kappa * sd
    ku = int(np.argmax(ucb))
    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    ax.fill_between(GRID_T, lcb, ucb, color=BLUE, alpha=0.12)
    ax.plot(GRID_T, mu, color=BLUE, lw=2, label="GP mean μ(x)")
    ax.plot(GRID_T, ucb, color=RED, lw=2.5, label="UCB = μ + 2σ")
    ax.plot(GRID_T, lcb, color=GRAY, lw=2, ls="--", label="LCB = μ − 2σ")
    ax.plot(xs, ys, "ko", ms=7)
    ax.plot(GRID_T[ku], ucb[ku], "o", color=RED, ms=11)
    ax.axvline(GRID_T[ku], color=RED, ls=":", lw=1.5)
    ax.annotate(f"next: {GRID_T[ku]:.0f} °C", (GRID_T[ku], ucb[ku]), xytext=(78, 0.24),
                color=RED, fontsize=12, arrowprops=dict(arrowstyle="->", color=RED))
    x0 = int(np.searchsorted(GRID_T, 110))
    ax.annotate("", (GRID_T[x0], ucb[x0]), (GRID_T[x0], mu[x0]), arrowprops=dict(arrowstyle="<->", color="k"))
    ax.text(GRID_T[x0] + 2, (ucb[x0] + mu[x0]) / 2, "κσ(x)", fontsize=12, va="center")
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("yield of B")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=11, frameon=False)
    print(f"  UCB, kappa = {kappa:g}: next T = {GRID_T[ku]:.1f} C")
    save(fig, "ucb.png")


    # a batch of four experiments at once, with qLogEI
    from botorch.acquisition.logei import qLogExpectedImprovement
    torch.manual_seed(0)
    Xb, _ = optimize_acqf(qLogExpectedImprovement(gp, best_f=float(ys.max())), bounds=torch.tensor([[T_LO], [T_HI]]),
                          q=4, num_restarts=10, raw_samples=256)
    batch = np.sort(Xb.numpy().ravel())
    ei1 = (mu - best) * norm.cdf(z) + sd * norm.pdf(z)
    fig, ax = plt.subplots(figsize=(4.4, 2.8))
    ax.plot(GRID_T, ei1 / ei1.max(), color=GREEN, lw=2.5)
    for b in batch:
        ax.axvline(b, color=RED, lw=2)
    ax.set_yticks([])
    ax.set_ylabel("EI")
    ax.set_xlabel("temperature (°C)")
    ax.set_title("4 reactors: 4 experiments at once", fontsize=12)
    print("  qLogEI, q = 4: batch at", [round(float(b), 1) for b in batch], "C")
    save(fig, "ext-batch.png")

    # PI and EI as pictures: the GP's belief about the yield at one temperature
    T0 = 60.0
    m0, s0 = float(np.interp(T0, GRID_T, mu)), float(np.interp(T0, GRID_T, sd))
    fv = np.linspace(m0 - 4 * s0, m0 + 4 * s0, 400)
    dens = norm.pdf(fv, m0, s0)
    z0 = (m0 - best) / s0
    pi0 = norm.cdf(z0)
    ei0 = (m0 - best) * norm.cdf(z0) + s0 * norm.pdf(z0)
    print(f"  at {T0:g} C after {len(xs)} experiments: mu {m0:.3f}, sigma {s0:.3f}, f* {best:.3f}, z {z0:.2f}, "
          f"PI {pi0:.2f}, EI {ei0:.4f}")
    above = fv >= best
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    ax.plot(fv, dens, color=BLUE, lw=2.5)
    ax.fill_between(fv[above], 0, dens[above], color=GOLD, alpha=0.4)
    ax.axvline(best, color="k", lw=2)
    ax.text(best - 0.004, dens.max() * 1.12, f"best so far\nf* = {best:.3f}", fontsize=11, ha="right", va="top")
    ax.text(0.075, dens.max() * 0.75, f"the GP's bell\nat {T0:g} °C:\nmean {m0:.3f}\nsd {s0:.3f}", fontsize=11,
            color=BLUE, va="top")
    ax.annotate(f"{pi0:.0%} of the bell\nis above f*", (best + 0.05, dens.max() * 0.35), xytext=(0.33, dens.max() * 0.85),
                fontsize=12, color=GOLD, fontweight="bold", arrowprops=dict(arrowstyle="->", color=GOLD))
    ax.set_yticks([])
    ax.set_ylim(0, dens.max() * 1.15)
    ax.set_xlabel(f"possible yield at {T0:g} °C")
    ax.set_title(f"PI = shaded area = {pi0:.2f}", fontsize=13)
    save(fig, "pi-picture.png")

    # EI picture: the bell of possible yields on top, the gain for each possible yield below
    fig, axes = plt.subplots(2, 1, figsize=(6.6, 3.9), sharex=True, gridspec_kw={"height_ratios": [1.2, 1]})
    ax = axes[0]
    ax.plot(fv, dens, color=BLUE, lw=2.5)
    ax.fill_between(fv[above], 0, dens[above], color=GREEN, alpha=0.35)
    ax.axvline(best, color="k", lw=2)
    ax.text(best - 0.004, dens.max() * 1.1, "f*", fontsize=13, ha="right", va="top")
    ax.text(0.06, dens.max() * 0.75, "how likely\neach yield is", fontsize=11, color=BLUE, va="top")
    ax.set_yticks([])
    ax.set_ylim(0, dens.max() * 1.15)
    ax = axes[1]
    gain = np.maximum(fv - best, 0)
    ax.plot(fv, gain, color=RED, lw=2.5)
    ax.axvline(best, color="k", lw=2)
    y1 = 0.30
    ax.annotate("", (y1, y1 - best), (y1, 0), arrowprops=dict(arrowstyle="<->", color=RED, lw=1.5))
    ax.text(y1 + 0.005, (y1 - best) / 2, f"if the yield is {y1:.2f}:\ngain {y1 - best:.3f}", fontsize=10, color=RED,
            va="center")
    ax.text(0.075, 0.03, "below f*: gain 0", fontsize=11, color=RED)
    ax.set_ylabel("gain")
    ax.set_xticks([0.1, 0.2, 0.3, 0.4])
    ax.set_xlabel(f"possible yield at {T0:g} °C")
    axes[0].set_title(f"EI = the gain, averaged over the bell = {ei0:.3f}", fontsize=13)
    save(fig, "ei-picture.png")

    # how a lab-notebook view of the run looks: incumbent, budget and regret
    ys_all = y.numpy().ravel()
    inc = np.maximum.accumulate(ys_all)
    n = np.arange(1, len(ys_all) + 1)
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.step(n, inc, where="post", color=BLUE, lw=2.5, label="incumbent f*: best measured so far")
    ax.plot(n, ys_all, "o", color="k", ms=6, label="each experiment")
    ax.axhline(Y_STAR, color=GOLD, ls="--", lw=2, label=f"best possible: {Y_STAR:.2f}")
    k4 = 3
    ax.annotate("", (n[k4], Y_STAR), (n[k4], inc[k4]), arrowprops=dict(arrowstyle="<->", color=RED, lw=2))
    ax.text(n[k4] - 0.2, (Y_STAR + inc[k4]) / 2, "regret\nafter 4", color=RED, fontsize=12, va="center", ha="right")
    ax.annotate("", (1, -0.05), (len(n), -0.05), arrowprops=dict(arrowstyle="<->", color=GREEN, lw=2),
                annotation_clip=False)
    ax.text((1 + len(n)) / 2, -0.035, f"budget: {len(n)} experiments", color=GREEN, fontsize=12, ha="center")
    ax.set_xlabel("experiment")
    ax.set_ylabel("yield of B")
    ax.set_ylim(-0.08, 0.58)
    ax.set_xticks(n)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=10, frameon=False)
    print(f"  regret after 4 experiments: {Y_STAR - inc[k4]:.3f} (incumbent {inc[k4]:.3f})")
    save(fig, "terminology.png")


def loop_pictures(frames, picks, ys):
    # four small panels for the loop diagram: fit, score, run, add (the first pass of the worked example)
    f0, f1 = frames[0], frames[1]
    x0, y0 = np.array(f0["x"]), np.array(f0["y"])
    mu0, sd0, acq0 = np.array(f0["mu"]), np.array(f0["sd"]), np.array(f0["acq"])
    mu1, sd1 = np.array(f1["mu"]), np.array(f1["sd"])
    nxt, y_new = picks[2], ys[2]

    def mini():
        fig, ax = plt.subplots(figsize=(3.0, 1.9))
        ax.set_yticks([])
        ax.set_xticks([20, 80, 140])
        ax.tick_params(labelsize=10)
        return fig, ax

    fig, ax = mini()
    ax.fill_between(GRID_T, mu0 - 2 * sd0, mu0 + 2 * sd0, color=BLUE, alpha=0.18)
    ax.plot(GRID_T, mu0, color=BLUE, lw=2)
    ax.plot(x0, y0, "ko", ms=6)
    save(fig, "loop-fit.png")

    fig, ax = mini()
    ax.plot(GRID_T, acq0, color=GREEN, lw=2.5)
    ax.plot(f0["next"], 1.0, "o", color=RED, ms=8)
    ax.axvline(f0["next"], color=RED, ls="--", lw=1.5)
    save(fig, "loop-score.png")

    fig, ax = mini()
    ax.plot(GRID_T, Y_1D, color=GRAY, lw=1.5, ls=":")
    ax.plot(x0, y0, "o", color="#bbbbbb", ms=6)
    ax.annotate("", (nxt, y_new), (nxt, -0.02), arrowprops=dict(arrowstyle="-|>", color=RED, lw=2))
    ax.plot(nxt, y_new, "o", color=RED, ms=9)
    ax.set_ylim(-0.05, 0.5)
    save(fig, "loop-run.png")

    fig, ax = mini()
    ax.fill_between(GRID_T, mu1 - 2 * sd1, mu1 + 2 * sd1, color=BLUE, alpha=0.18)
    ax.plot(GRID_T, mu1, color=BLUE, lw=2)
    ax.plot(x0, y0, "ko", ms=6)
    ax.plot(nxt, y_new, "o", color=RED, ms=8)
    save(fig, "loop-add.png")


# ------------------------------------------------------------------------ race (2-D)
LO2, HI2 = np.array([T_LO, TAU_LO]), np.array([T_HI, TAU_HI])
INIT2 = ((30.0, 5.0), (50.0, 10.0), (40.0, 20.0))
START2 = (40.0, 10.0)
N_EVAL = 30
TT2, UU2 = np.meshgrid(np.linspace(T_LO, T_HI, 241), np.linspace(TAU_LO, TAU_HI, 233))
Y2 = yield_B(TT2, UU2)
Y2_STAR = float(Y2.max())


def measure2(x, gen):
    return float(yield_B(x[0], x[1]) + NOISE * gen.standard_normal())


def bo_2d(seed):
    torch.manual_seed(seed)
    gen = np.random.default_rng(seed)
    X = torch.tensor(INIT2)
    y = torch.tensor([[measure2(x, gen)] for x in X.numpy()])
    bounds = torch.tensor(np.array([LO2, HI2]))
    while X.shape[0] < N_EVAL:
        gp = gp_fit(X, y, 2)
        x_next, _ = optimize_acqf(LogExpectedImprovement(gp, best_f=y.max()), bounds=bounds, q=1,
                                  num_restarts=10, raw_samples=256)
        X = torch.cat([X, x_next])
        y = torch.cat([y, torch.tensor([[measure2(x_next.numpy()[0], gen)]])])
    return X.numpy(), y.numpy().ravel()


def local_2d(method, seed):
    gen = np.random.default_rng(1000 + seed)
    log = []

    def f(z):
        x = LO2 + np.clip(z, 0, 1) * (HI2 - LO2)
        v = measure2(x, gen)
        log.append((x[0], x[1], v))
        return -v

    z0 = (np.array(START2) - LO2) / (HI2 - LO2)
    if method == "Nelder-Mead":
        minimize(f, z0, method="Nelder-Mead", options={"maxfev": N_EVAL})
    else:
        minimize(f, z0, method="L-BFGS-B", bounds=[(0, 1), (0, 1)], options={"maxfun": N_EVAL, "eps": 0.01})
    a = np.array(log)[:N_EVAL]
    return a[:, :2], a[:, 2]


def random_2d(seed):
    gen = np.random.default_rng(2000 + seed)
    X = LO2 + gen.uniform(size=(N_EVAL, 2)) * (HI2 - LO2)
    return X, np.array([measure2(x, gen) for x in X])


def best_so_far(X, y):
    # the true yield of the experiment that looks best so far: what the lab would actually run
    out = []
    for n in range(1, len(y) + 1):
        k = int(np.argmax(y[:n]))
        out.append(float(yield_B(X[k, 0], X[k, 1])))
    return np.array(out)


def group_race():
    methods = {"Bayesian optimization": bo_2d, "Nelder-Mead": lambda s: local_2d("Nelder-Mead", s),
               "L-BFGS-B": lambda s: local_2d("L-BFGS-B", s), "random search": random_2d}
    curves, runs = {}, {}
    t0 = time.time()
    for name, fn in methods.items():
        curves[name] = []
        for seed in range(10):
            X, y = fn(seed)
            b = best_so_far(X, y)
            b = np.concatenate([b, np.full(N_EVAL - len(b), b[-1])])     # a method that stopped early keeps its best
            curves[name].append(b)
            if seed == 0:
                runs[name] = {"x": r(X, 2), "y": r(y)}
        curves[name] = np.array(curves[name])
    print(f"  ran in {time.time() - t0:.0f} s")
    stats = {}
    for name, c in curves.items():
        reach = [int(np.argmax(row >= 0.98 * Y2_STAR)) + 1 if (row >= 0.98 * Y2_STAR).any() else None for row in c]
        got = [v for v in reach if v is not None]
        final = c[:, -1] / Y2_STAR
        stats[name] = {"reached": len(got), "median": float(np.median(got)) if got else None,
                       "final_median": round(float(np.median(final)), 3),
                       "final_min": round(float(final.min()), 3)}
        print(f"  {name}: reached 98% of the best yield in {len(got)}/10 seeds"
              + (f", median {np.median(got):.0f} evaluations (range {min(got)} to {max(got)})" if got else "")
              + f"; after {N_EVAL}: median {np.median(final):.1%}, worst {final.min():.1%} of the best yield")

    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    for (name, c), col in zip(curves.items(), [BLUE, GOLD, GREEN, RED]):
        n = np.arange(1, N_EVAL + 1)
        ax.plot(n, np.median(c, axis=0), color=col, lw=2.5, label=name)
        ax.fill_between(n, c.min(axis=0), c.max(axis=0), color=col, alpha=0.12)
    ax.axhline(Y2_STAR, color="k", ls=":", lw=1)
    ax.text(N_EVAL, Y2_STAR + 0.008, f"best possible yield {Y2_STAR:.2f}", ha="right", fontsize=11)
    ax.set_xlabel("experiments run")
    ax.set_ylabel("true yield of the best experiment so far")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.02), ncol=4, fontsize=11, frameon=False)
    ax.set_ylim(0, 0.6)
    save(fig, "bo-vs-random.png")

    # contour lines for the widget background
    cs = plt.contour(TT2, UU2, Y2, levels=[0.1, 0.2, 0.3, 0.4, 0.5, 0.54])
    lines = []
    for lev, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) > 3:
                lines.append({"level": round(float(lev), 2), "pts": r(seg[::3], 2)})
    plt.close("all")
    j = np.unravel_index(Y2.argmax(), Y2.shape)
    cache_put("race", {"runs": runs, "contours": lines, "lo": LO2.tolist(), "hi": HI2.tolist(),
                       "star": [round(float(TT2[j]), 1), round(float(UU2[j]), 1)], "y_star": round(Y2_STAR, 4),
                       "curves": {k: r(np.median(v, axis=0)) for k, v in curves.items()},
                       "seed0": {k: r(best_so_far(np.array(v["x"]), np.array(v["y"]))) for k, v in runs.items()},
                       "stats": stats, "n_eval": N_EVAL})


# ------------------------------------------------------------------------ schematics
def group_schematics():
    race = json.loads((CACHE / "race.json").read_text())
    lines = race["contours"]
    star = race["star"]
    # one panel per method: where seed 0 ran its 30 experiments
    for name, fname, col in [("Bayesian optimization", "race-bo.png", BLUE), ("Nelder-Mead", "race-nm.png", GOLD),
                             ("L-BFGS-B", "race-lbfgs.png", GREEN), ("random search", "race-random.png", RED)]:
        X = np.array(race["runs"][name]["x"])
        fig, ax = plt.subplots(figsize=(3.4, 2.7))
        for ln in lines:
            pts = np.array(ln["pts"])
            ax.plot(pts[:, 0], pts[:, 1], color="#b8b8b8", lw=0.8)
        ax.plot(X[:, 0], X[:, 1], "o", color=col, ms=5, alpha=0.85)
        ax.plot(X[0, 0], X[0, 1], "s", color="k", ms=6)
        ax.plot(*star, "*", color=GOLD, ms=16, mec="k")
        ax.set_xlim(T_LO, T_HI)
        ax.set_ylim(TAU_LO, TAU_HI + 1)
        ax.set_xlabel("T (°C)", fontsize=11)
        ax.set_ylabel("τ (min)", fontsize=11)
        ax.tick_params(labelsize=9)
        save(fig, fname)

    # why a finite-difference gradient fails on the cold side: the change is smaller than the noise
    T0, tau0 = 40.0, 10.0
    h = 0.01 * (T_HI - T_LO)                   # the step L-BFGS-B took: 0.01 in scaled units
    dy = float(yield_B(T0 + h, tau0) - yield_B(T0, tau0))
    sd_diff = NOISE * np.sqrt(2)
    print(f"  finite difference at T = {T0:g} C, tau = {tau0:g} min, h = {h:.1f} C: true change {dy:.4f}, "
          f"noise sd of a difference {sd_diff:.4f} ({sd_diff / dy:.1f} times larger)")
    fine = np.linspace(25, 60, 300)
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(fine, yield_B(fine, tau0), color=GRAY, lw=2, label="true yield (τ = 10 min)")
    for x, c in [(T0, BLUE), (T0 + h, RED)]:
        ax.errorbar(x, yield_B(x, tau0), yerr=2 * NOISE, fmt="o", color=c, ms=7, capsize=5, lw=2)
    ax.annotate(f"two experiments {h:.1f} °C apart:\ntrue change {dy:.3f}\nnoise in the difference ±{2 * sd_diff:.3f}",
                (T0, yield_B(T0, tau0) + 2 * NOISE), xytext=(25.5, 0.2), fontsize=11,
                arrowprops=dict(arrowstyle="->"))
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("yield of B")
    ax.set_ylim(0, 0.3)
    ax.legend(loc="lower right", fontsize=10, frameon=False)
    save(fig, "finite-diff.png")

    # where each kind of optimizer fits: cost of one evaluation against the number of inputs (a sketch)
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1, 1e7)
    ax.set_ylim(1e-4, 3e6)
    regions = [((1, 60), 20, 3e6, BLUE, "Bayesian optimization: expensive,\nnoisy, no gradient, up to about 20 inputs"),
               ((1, 1e-4), 1e7, 1, GREEN, "gradient-based: cheap, with gradients,\nup to millions of inputs"),
               ((1, 1e-3), 300, 60, GOLD, "other derivative-free (Nelder–Mead,\nevolutionary): no gradient, cheap enough\nfor thousands of runs")]
    for (x0, y0), w, hgt, c, label in regions:
        ax.add_patch(Rectangle((x0, y0), w - x0, hgt - y0, fc=c, alpha=0.18, ec=c, lw=2, label=label))
    ax.plot(2, 3600 * 3, "*", color=RED, ms=18, mec="k", label="the reactor: 2 knobs, hours each", ls="none")
    ax.legend(loc="upper right", fontsize=10, frameon=False, labelspacing=0.9)
    ax.set_yticks([1e-3, 1, 60, 3600, 86400, 6e5])
    ax.set_yticklabels(["1 ms", "1 s", "1 min", "1 h", "1 day", "1 week"])
    ax.set_xticks([1, 10, 100, 1e4, 1e6])
    ax.set_xticklabels(["1", "10", "100", "10⁴", "10⁶"])
    ax.set_xlabel("number of inputs")
    ax.set_ylabel("cost of one evaluation")
    ax.set_title("a sketch: where each method fits", fontsize=12, color=GRAY)
    save(fig, "decision-map.png")

    # extensions, as small sketches on the reactor
    TT, UU = np.meshgrid(np.linspace(T_LO, T_HI, 121), np.linspace(TAU_LO, TAU_HI, 117))
    Y = yield_B(TT, UU)
    rate_b = Y / UU                              # production rate of B per unit volume and feed, relative
    pts = np.column_stack([Y.ravel(), rate_b.ravel()])
    order = np.argsort(-pts[:, 0])
    front, best_rate = [], -np.inf
    for k in order:
        if pts[k, 1] > best_rate:
            front.append(pts[k])
            best_rate = pts[k, 1]
    front = np.array(front)
    fig, ax = plt.subplots(figsize=(4.4, 2.8))
    ax.plot(pts[::7, 0], pts[::7, 1] / pts[:, 1].max(), ".", color="#c8c8c8", ms=2)
    ax.plot(front[:, 0], front[:, 1] / pts[:, 1].max(), color=RED, lw=3)
    ax.set_xlabel("yield of B")
    ax.set_ylabel("production rate")
    ax.set_yticks([])
    ax.set_title("yield and rate: the Pareto front", fontsize=12)
    save(fig, "ext-pareto.png")

    fine = np.linspace(T_LO, T_HI, 400)
    fig, ax = plt.subplots(figsize=(4.4, 2.8))
    ax.plot(fine, yield_B(fine), color="k", lw=2.5)
    ax.axvspan(70, T_HI, color=RED, alpha=0.15, hatch="//", ec=RED)
    ax.text(105, 0.42, "not allowed:\nT > 70 °C", color=RED, fontsize=11, ha="center")
    ax.plot(70, yield_B(70.0), "o", color=GOLD, ms=10, mec="k", zorder=4)
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("yield of B")
    ax.set_ylim(0, 0.55)
    ax.set_title("example limit: T ≤ 70 °C", fontsize=12)
    save(fig, "ext-constraint.png")

    def yield_rough(T):
        k1, k2 = rate(T, K1, E1), rate(T, K2, 95e3)
        return k1 * TAU_1D / ((1 + k1 * TAU_1D) * (1 + k2 * TAU_1D))

    fig, ax = plt.subplots(figsize=(4.4, 2.8))
    ax.plot(fine, yield_rough(fine), color=GRAY, lw=2, ls="--", label="cheap, rough model")
    ax.plot(fine, yield_B(fine), color="k", lw=2.5, label="lab experiment")
    xs_cheap = np.linspace(25, 135, 12)
    ax.plot(xs_cheap, yield_rough(xs_cheap), "o", color=GRAY, ms=5)
    ax.plot([60, 80, 95], yield_B(np.array([60.0, 80.0, 95.0])), "o", color=RED, ms=8)
    ax.set_xlabel("temperature (°C)")
    ax.set_ylabel("yield of B")
    ax.set_ylim(0, 0.55)
    ax.legend(fontsize=10, frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2,
              handlelength=1.5, columnspacing=1.0)
    save(fig, "ext-fidelity.png")


def group_ego():
    # The idea of Jones, Schonlau and Welch (1998), Figs. 8 to 11, redrawn on a function of our
    # own: five samples, three of them clustered; the kriging prediction alone would only refine
    # the local peak near the cluster, while expected improvement also points at the gap.
    x = np.linspace(0, 12, 600)
    f = lambda t: 1.0 * np.exp(-(t - 2.8) ** 2 / 0.8) + 1.25 * np.exp(-(t - 8.8) ** 2 / 1.2) + 0.15
    xt = np.array([1.6, 2.2, 3.0, 6.0, 11.5])
    yt = f(xt)
    mu, cov = gp_numpy(xt, yt, x, 0.5, 0.5, 1.0, 1e-3)
    sd = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    best = yt.max()
    zz = (mu - best) / sd
    ei = (mu - best) * norm.cdf(zz) + sd * norm.pdf(zz)
    peaks = [x[i] for i in range(1, len(x) - 1) if ei[i] > ei[i - 1] and ei[i] >= ei[i + 1] and ei[i] > 0.02 * ei.max()]
    print(f"  EGO sketch: GP mean peaks at x = {x[mu.argmax()]:.1f}; EI peaks at {[round(p, 1) for p in peaks]}; "
          f"largest at {x[ei.argmax()]:.1f}")
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax = axes[0]
    ax.fill_between(x, mu - 2 * sd, mu + 2 * sd, color=BLUE, alpha=0.15)
    ax.plot(x, f(x), color=GRAY, lw=2, ls="--", label="true function (hidden)")
    ax.plot(x, mu, color=BLUE, lw=2.5, label="kriging prediction, ± 2 standard errors")
    ax.plot(xt, yt, "ko", ms=8, label="samples")
    ax.annotate("prediction peaks here:\nonly a local peak", (x[mu.argmax()], mu.max()), xytext=(4.3, 1.45), fontsize=11,
                arrowprops=dict(arrowstyle="->"))
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=10, frameon=False)
    ax.set_yticks([])
    ax.set_ylim(-0.6, 1.9)
    axes[1].plot(x, ei / ei.max(), color=GREEN, lw=2.5)
    axes[1].set_yticks([])
    axes[1].set_ylabel("EI")
    axes[1].annotate("largest EI:\nthe unexplored gap", (x[ei.argmax()], 1.0), xytext=(4.8, 0.55), fontsize=11, color=GREEN,
                     arrowprops=dict(arrowstyle="->", color=GREEN))
    axes[1].set_xlabel("x")
    save(fig, "ego.png")


# ------------------------------------------------------------------------ active learning
def group_al():
    grid = torch.tensor(GRID_T).unsqueeze(-1)
    bounds = torch.tensor([[T_LO], [T_HI]])
    out = {}
    for mode in ("BO", "AL"):
        torch.manual_seed(0)
        gen = np.random.default_rng(0)
        T = torch.tensor([[30.0], [50.0]])
        y = run_experiment_1d(T, gen)
        for i in range(6):
            gp = gp_fit(T, y, 1)
            if mode == "BO":
                T_next, _ = optimize_acqf(LogExpectedImprovement(gp, best_f=y.max()), bounds=bounds, q=1,
                                          num_restarts=10, raw_samples=200)
            else:
                with torch.no_grad():
                    sd = gp.posterior(grid).variance.sqrt().squeeze()
                T_next = grid[int(torch.argmax(sd))].unsqueeze(0)
            T = torch.cat([T, T_next])
            y = torch.cat([y, run_experiment_1d(T_next, gen)])
        gp = gp_fit(T, y, 1)
        with torch.no_grad():
            post = gp.posterior(grid)
            out[mode] = (T.numpy().ravel(), y.numpy().ravel(), post.mean.squeeze().numpy(),
                         post.variance.sqrt().squeeze().numpy())
        print(f"  {mode}: picks", np.round(T.numpy().ravel()[2:], 1).tolist(),
              f"; mean band half-width {1.96 * out[mode][3].mean():.3f}")
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    for ax, mode, title in [(axes[0], "BO", "Bayesian optimization: find the best point"),
                            (axes[1], "AL", "active learning: a good model everywhere")]:
        xs, ys, mu, sd = out[mode]
        ax.fill_between(GRID_T, mu - 1.96 * sd, mu + 1.96 * sd, color=BLUE, alpha=0.15)
        ax.plot(GRID_T, Y_1D, color=GRAY, lw=2, ls="--")
        ax.plot(GRID_T, mu, color=BLUE, lw=2)
        ax.plot(xs[:2], ys[:2], "ko", ms=7)
        ax.plot(xs[2:], ys[2:], "o", color=RED, ms=8)
        ax.set_title(title, fontsize=13)
        ax.set_xlabel("temperature (°C)")
    axes[0].set_ylabel("yield of B")
    axes[0].set_ylim(-0.15, 0.6)
    save(fig, "al-vs-bo.png")


# ------------------------------------------------------------------------ widget data, extras
def copy_l13():
    for name in ("gen0.png", "gen1.png"):
        shutil.copy(REPO / "lectures" / "l13" / "figures" / name, HERE / name)
        print(f"  copied {name} from lectures/l13/figures")


def write_widget_data():
    data = {}
    for name in ("posterior", "loop", "race"):
        p = CACHE / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())
    text = ("/* Generated by lectures/l15/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l15 = " + json.dumps(data, separators=(",", ":")) + ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB)")


GROUPS = {"problem": group_problem, "posterior": group_posterior, "loop": group_loop, "race": group_race,
          "schematics": group_schematics, "al": group_al, "ego": group_ego, "l13": copy_l13}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(f"[{name}]")
        GROUPS[name]()
    write_widget_data()
