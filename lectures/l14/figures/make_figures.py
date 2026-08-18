"""Figures for L14, Bayesian optimization and active learning for design.

Run from this directory with the course `sys_tools` environment:

    python make_figures.py

Everything is computed here rather than copied, for the reasons in CLAUDE.md
section 5b. The three teaching panels run on the Forrester one-dimensional test
function, f(x) = (6x - 2)^2 * sin(12x - 4), which is the worked example in
Forrester, Sobester & Keane (2008), the surrogate-modelling book already cited
in L13. Its global minimum on [0, 1] is near x = 0.7572, and it carries a second
local minimum near x = 0.15, so a myopic optimiser that only exploits is easy to
catch out. The convergence panel runs on the same NASA airfoil self-noise data
L13 uses, so the two sessions share one dataset: a gradient-boosted model fit to
all 1503 rows stands in for the expensive experiment, and Bayesian optimisation
and random search each get the same evaluation budget to find a quiet operating
point. The airfoil raw file is cached under .cache/ and gitignored; do not commit
it.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
AIRFOIL_URL = "https://archive.ics.uci.edu/static/public/291/airfoil+self+noise.zip"
SEED = 0

# Shared palette with L13, so the two decks look like one course.
CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
AMBER = "#b8860b"
PURPLE = "#6b3fa0"
TEAL = "#0f7d8c"
BAND = "#c9dbec"

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

COLS = ["freq_hz", "aoa_deg", "chord_m", "velocity_ms", "thickness_m", "spl_db"]


# --------------------------------------------------------------------------
# The 1-D test function and a small Gaussian-process helper
# --------------------------------------------------------------------------
def forrester(x: np.ndarray) -> np.ndarray:
    """Forrester et al. (2008). Global min ~ -6.02 at x ~ 0.7572 on [0, 1]."""
    return (6.0 * x - 2.0) ** 2 * np.sin(12.0 * x - 4.0)


def fit_gp(x: np.ndarray, y: np.ndarray, length_scale: float = 0.15,
           bounds: tuple = (0.05, 0.5)) -> GaussianProcessRegressor:
    """A Matern-5/2 GP with a fitted noise term, standardised target.

    The same shape the demo builds by hand, kept deliberately small so the
    posterior is legible: this is a teaching surrogate, not a production one.
    The length-scale prior is loose enough that the GP generalises across the
    gap to the global basin rather than reverting to the mean between points,
    which is what lets the loop below actually find the optimum.
    """
    kernel = (ConstantKernel(1.0, (1e-2, 1e2))
              * Matern(length_scale=length_scale, length_scale_bounds=bounds, nu=2.5)
              + WhiteKernel(1e-4, (1e-6, 1e-1)))
    gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True,
                                  n_restarts_optimizer=4, random_state=SEED)
    gp.fit(x.reshape(-1, 1), y)
    return gp


def expected_improvement(mu: np.ndarray, sigma: np.ndarray, best: float,
                         xi: float = 0.0) -> np.ndarray:
    """EI for MINIMISATION: how much we expect to beat the incumbent `best`."""
    sigma = np.maximum(sigma, 1e-9)
    imp = best - mu - xi
    z = imp / sigma
    return imp * norm.cdf(z) + sigma * norm.pdf(z)


def probability_of_improvement(mu: np.ndarray, sigma: np.ndarray, best: float,
                               xi: float = 0.0) -> np.ndarray:
    sigma = np.maximum(sigma, 1e-9)
    return norm.cdf((best - mu - xi) / sigma)


# --------------------------------------------------------------------------
# Figure 1 — the Bayesian-optimization loop over three iterations
# --------------------------------------------------------------------------
def fig_bo_loop() -> dict:
    grid = np.linspace(0, 1, 400)
    truth = forrester(grid)
    # A four-point space-filling start, none near the global optimum at 0.757.
    x = np.array([0.0, 0.33, 0.66, 1.0])
    y = forrester(x)

    fig, axes = plt.subplots(3, 2, figsize=(12, 10.5),
                             gridspec_kw={"width_ratios": [1, 1], "hspace": 0.42,
                                          "wspace": 0.22})
    picks = []
    for row in range(3):
        gp = fit_gp(x, y)
        mu, sigma = gp.predict(grid.reshape(-1, 1), return_std=True)
        best = y.min()
        ei = expected_improvement(mu, sigma, best, xi=0.01)
        x_next = grid[int(ei.argmax())]
        picks.append(x_next)

        ax = axes[row, 0]
        ax.plot(grid, truth, color=RULE, lw=2, zorder=1,
                label="true objective" if row == 0 else None)
        ax.fill_between(grid, mu - 1.96 * sigma, mu + 1.96 * sigma,
                        color=BAND, alpha=0.8, zorder=0,
                        label="GP 95% band" if row == 0 else None)
        ax.plot(grid, mu, color=BLUE, lw=2, zorder=2,
                label="GP mean" if row == 0 else None)
        ax.scatter(x, y, color=INK, s=45, zorder=4, label="evaluated" if row == 0 else None)
        ax.axvline(x_next, color=CMU_RED, ls="--", lw=1.6, zorder=3)
        ax.set_ylabel(f"iteration {row + 1}\n\nf(x)")
        ax.set_xlim(0, 1)
        if row == 0:
            ax.legend(loc="upper center", fontsize=9, ncol=2, frameon=False)

        axq = axes[row, 1]
        axq.plot(grid, ei, color=GREEN, lw=2)
        axq.fill_between(grid, 0, ei, color=GREEN, alpha=0.15)
        axq.axvline(x_next, color=CMU_RED, ls="--", lw=1.6)
        axq.set_ylabel("expected\nimprovement")
        axq.set_xlim(0, 1)
        axq.annotate("evaluate here next", xy=(x_next, ei.max()),
                     xytext=(x_next + (0.12 if x_next < 0.6 else -0.28), ei.max() * 0.9),
                     fontsize=9, color=CMU_RED,
                     arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))

        # evaluate the true objective and fold it in for the next row
        x = np.append(x, x_next)
        y = np.append(y, forrester(x_next))

    axes[2, 0].set_xlabel("design variable x")
    axes[2, 1].set_xlabel("design variable x")
    fig.suptitle("Bayesian optimization: the surrogate proposes, the acquisition decides",
                 fontsize=16, y=0.94)
    out = HERE / "bo-loop.png"
    fig.savefig(out)
    plt.close(fig)
    xbest = x[int(np.argmin(y))]
    return {"file": out.name, "picks": [round(p, 3) for p in picks],
            "final_best_x": round(float(xbest), 3),
            "final_best_f": round(float(y.min()), 3)}


# --------------------------------------------------------------------------
# Figure 2 — four acquisition functions, four different next points
# --------------------------------------------------------------------------
def fig_acquisitions() -> dict:
    grid = np.linspace(0, 1, 400)
    truth = forrester(grid)
    # Well into the campaign: the global basin near 0.757 is already sampled, so
    # the greedy rules cluster there and only a high kappa still explores.
    x = np.array([0.1, 0.35, 0.68, 0.78, 0.95])
    y = forrester(x)
    gp = fit_gp(x, y)
    mu, sigma = gp.predict(grid.reshape(-1, 1), return_std=True)
    best = y.min()

    ei = expected_improvement(mu, sigma, best)
    pi = probability_of_improvement(mu, sigma, best)
    ucb1 = mu - 1.0 * sigma          # low kappa: exploit
    ucb3 = mu - 3.0 * sigma          # high kappa: explore (lower is better here)

    proposals = {
        "EI": (GREEN, grid[int(ei.argmax())]),
        "PI": (AMBER, grid[int(pi.argmax())]),
        "LCB, kappa=1": (BLUE, grid[int(ucb1.argmin())]),
        "LCB, kappa=3": (PURPLE, grid[int(ucb3.argmin())]),
    }

    fig, (ax, axq) = plt.subplots(2, 1, figsize=(10, 8),
                                  gridspec_kw={"height_ratios": [1.3, 1], "hspace": 0.28})
    ax.plot(grid, truth, color=RULE, lw=2, label="true objective")
    ax.fill_between(grid, mu - 1.96 * sigma, mu + 1.96 * sigma, color=BAND, alpha=0.8)
    ax.plot(grid, mu, color=INK, lw=2, label="GP mean")
    ax.scatter(x, y, color=INK, s=45, zorder=4, label="evaluated")
    for name, (color, xp) in proposals.items():
        ax.axvline(xp, color=color, ls="--", lw=1.8)
    ax.set_ylabel("f(x)")
    ax.set_xlim(0, 1)
    ax.legend(loc="upper center", fontsize=10, ncol=3, frameon=False)
    ax.set_title("One surrogate, four acquisition rules, four different next experiments")

    # normalise each acquisition to [0,1] so they share an axis
    def unit(a, lower_is_better=False):
        a = -a if lower_is_better else a
        return (a - a.min()) / (a.max() - a.min() + 1e-12)
    axq.plot(grid, unit(ei), color=GREEN, lw=2, label="EI")
    axq.plot(grid, unit(pi), color=AMBER, lw=2, label="PI")
    axq.plot(grid, unit(ucb1, True), color=BLUE, lw=2, label="LCB kappa=1 (exploit)")
    axq.plot(grid, unit(ucb3, True), color=PURPLE, lw=2, label="LCB kappa=3 (explore)")
    for name, (color, xp) in proposals.items():
        axq.axvline(xp, color=color, ls="--", lw=1.4)
    axq.set_ylabel("acquisition\n(scaled)")
    axq.set_xlabel("design variable x")
    axq.set_xlim(0, 1)
    axq.legend(fontsize=9, ncol=2, frameon=False, loc="upper center")

    out = HERE / "acquisitions.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name,
            "proposals": {k: round(float(v[1]), 3) for k, v in proposals.items()}}


# --------------------------------------------------------------------------
# Figure 3 — Bayesian optimization vs random search on the airfoil oracle
# --------------------------------------------------------------------------
def load_airfoil() -> np.ndarray:
    CACHE.mkdir(exist_ok=True)
    local = CACHE / "airfoil_self_noise.dat"
    if not local.exists():
        print(f"downloading {AIRFOIL_URL}")
        with urllib.request.urlopen(AIRFOIL_URL) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        local.write_bytes(archive.read("airfoil_self_noise.dat"))
    import pandas as pd
    df = pd.read_csv(local, sep="\t", header=None, names=COLS)
    return df.values


def propose_by_ei(gp, lo, hi, best, rng, pool=800):
    """Optimise EI over a fresh random pool, the transparent way the demo does."""
    cand = rng.uniform(lo, hi, size=(pool, lo.size))
    mu, sigma = gp.predict(cand, return_std=True)
    ei = expected_improvement(mu, sigma, best)
    return cand[int(ei.argmax())]


def fig_bo_vs_random() -> dict:
    data = load_airfoil()
    X, y = data[:, :5], data[:, 5]
    # A fixed, deterministic stand-in for the expensive experiment: predict SPL
    # anywhere in the input box. This is the "oracle"; the optimisers never see it.
    oracle = GradientBoostingRegressor(random_state=SEED, n_estimators=400,
                                       max_depth=3, learning_rate=0.05)
    oracle.fit(X, y)
    lo, hi = X.min(axis=0), X.max(axis=0)

    def f(pt):
        return float(oracle.predict(pt.reshape(1, -1))[0])

    # A dense reference for "the best the oracle can do" over the box.
    ref_rng = np.random.default_rng(12345)
    ref = oracle.predict(ref_rng.uniform(lo, hi, size=(200_000, 5)))
    oracle_floor = float(ref.min())

    budget = 22
    n_init = 4
    n_seeds = 40
    kernel = (ConstantKernel(1.0, (1e-2, 1e3))
              * Matern(length_scale=np.ones(5), nu=2.5)
              + WhiteKernel(1.0, (1e-3, 1e3)))

    bo_curves, rs_curves = [], []
    for s in range(n_seeds):
        rng = np.random.default_rng(1000 + s)
        # shared initial design so the comparison is paired
        init = rng.uniform(lo, hi, size=(n_init, 5))
        yi = np.array([f(p) for p in init])

        # --- Bayesian optimization ---
        Xb, yb = init.copy(), yi.copy()
        best_bo = [yb.min()]
        for _ in range(budget - n_init):
            gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True,
                                          n_restarts_optimizer=0, random_state=s)
            # standardise inputs for a saner length scale
            mean, std = Xb.mean(0), Xb.std(0) + 1e-9
            gp.fit((Xb - mean) / std, yb)
            pool = rng.uniform(lo, hi, size=(1500, 5))
            mu, sigma = gp.predict((pool - mean) / std, return_std=True)
            ei = expected_improvement(mu, sigma, yb.min())
            x_next = pool[int(ei.argmax())]
            Xb = np.vstack([Xb, x_next])
            yb = np.append(yb, f(x_next))
            best_bo.append(yb.min())
        bo_curves.append(best_bo)

        # --- random search, same budget, same start ---
        Xr, yr = init.copy(), yi.copy()
        best_rs = [yr.min()]
        for _ in range(budget - n_init):
            x_next = rng.uniform(lo, hi, size=5)
            yr = np.append(yr, f(x_next))
            best_rs.append(yr.min())
        rs_curves.append(best_rs)

    bo = np.array(bo_curves)
    rs = np.array(rs_curves)
    evals = np.arange(n_init, budget + 1)  # best-so-far indexed from n_init eval
    # curves have length budget - n_init + 1, aligned to evals above
    xs = np.arange(n_init, n_init + bo.shape[1])

    fig, ax = plt.subplots(figsize=(9.5, 6))
    for curves, color, name in [(bo, CMU_RED, "Bayesian optimization (EI)"),
                                (rs, MUTED, "random search")]:
        med = np.median(curves, axis=0)
        q1, q3 = np.percentile(curves, [25, 75], axis=0)
        ax.plot(xs, med, color=color, lw=2.4, label=name)
        ax.fill_between(xs, q1, q3, color=color, alpha=0.15)
    ax.axhline(oracle_floor, color=INK, ls=":", lw=1.5)
    ax.annotate("best the emulator allows over the design box",
                xy=(xs[-1], oracle_floor), xytext=(xs[0] + 0.3, oracle_floor + 1.2),
                fontsize=9, color=INK)
    ax.set_xlabel("expensive evaluations spent")
    ax.set_ylabel("lowest sound pressure level found (dB)")
    ax.set_title("Same budget, two strategies: where the next experiment goes matters")
    ax.legend(frameon=False, fontsize=11)
    out = HERE / "bo-vs-random.png"
    fig.savefig(out)
    plt.close(fig)

    # honest summary numbers for the caption and notes
    def evals_to_reach(curves, target):
        outs = []
        for c in curves:
            hit = np.where(np.array(c) <= target)[0]
            outs.append(int(xs[hit[0]]) if hit.size else None)
        hit = [o for o in outs if o is not None]
        return hit
    target = oracle_floor + 1.0  # within 1 dB of the emulator floor
    bo_hits = evals_to_reach(bo, target)
    rs_hits = evals_to_reach(rs, target)
    return {
        "file": out.name,
        "oracle_floor_db": round(oracle_floor, 2),
        "target_db": round(target, 2),
        "bo_final_median_db": round(float(np.median(bo[:, -1])), 2),
        "rs_final_median_db": round(float(np.median(rs[:, -1])), 2),
        "bo_reached_target_frac": round(len(bo_hits) / n_seeds, 2),
        "rs_reached_target_frac": round(len(rs_hits) / n_seeds, 2),
        "bo_median_evals_to_target": int(np.median(bo_hits)) if bo_hits else None,
        "n_seeds": n_seeds, "budget": budget,
    }


# --------------------------------------------------------------------------
# Figure 4 — one active-learning step shrinks the uncertainty
# --------------------------------------------------------------------------
def fig_active_learning() -> dict:
    grid = np.linspace(0, 1, 400)
    truth = forrester(grid)
    x = np.array([0.08, 0.2, 0.32, 0.44, 0.9])   # a wide gap between 0.44 and 0.9
    y = forrester(x)

    gp = fit_gp(x, y)
    mu, sigma = gp.predict(grid.reshape(-1, 1), return_std=True)
    x_next = grid[int(sigma.argmax())]          # query where we are most ignorant
    before_total = float(np.trapezoid(sigma, grid))

    # Condition on the new point at the SAME hyperparameters (optimizer=None).
    # That isolates what active learning actually does: adding data reduces the
    # posterior variance everywhere. Refitting the length scale on a surprising
    # value is a separate effect that would muddy the picture, so we freeze it.
    x2 = np.append(x, x_next)
    y2 = np.append(y, forrester(x_next))
    gp2 = GaussianProcessRegressor(kernel=gp.kernel_, optimizer=None,
                                   normalize_y=True)
    gp2.fit(x2.reshape(-1, 1), y2)
    mu2, sigma2 = gp2.predict(grid.reshape(-1, 1), return_std=True)
    after_total = float(np.trapezoid(sigma2, grid))

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (m, sg, xs_, ys_, title, star) in zip(axes, [
        (mu, sigma, x, y, "before: the widest gap sits between x=0.44 and x=0.9", x_next),
        (mu2, sigma2, x2, y2, "after one query at the most uncertain point", None),
    ]):
        ax.plot(grid, truth, color=RULE, lw=2)
        ax.fill_between(grid, m - 1.96 * sg, m + 1.96 * sg, color=BAND, alpha=0.85)
        ax.plot(grid, m, color=BLUE, lw=2)
        ax.scatter(xs_, ys_, color=INK, s=42, zorder=4)
        if star is not None:
            ax.axvline(star, color=CMU_RED, ls="--", lw=1.6)
        ax.set_title(title, fontsize=12)
        ax.set_xlabel("design variable x")
        ax.set_xlim(0, 1)
    axes[0].set_ylabel("f(x)")
    fig.suptitle("Active learning: spend the query where the model is most uncertain",
                 fontsize=15, y=1.02)
    out = HERE / "active-learning.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name, "query_x": round(float(x_next), 3),
            "total_sd_before": round(before_total, 3),
            "total_sd_after": round(after_total, 3),
            "sd_drop_pct": round(100 * (before_total - after_total) / before_total, 1)}


def main() -> None:
    results = {}
    for fn in (fig_bo_loop, fig_acquisitions, fig_bo_vs_random, fig_active_learning):
        r = fn()
        results[fn.__name__] = r
        print(f"{fn.__name__}: {r}")
    print("\nwrote:", ", ".join(sorted(p.name for p in HERE.glob("*.png"))))


if __name__ == "__main__":
    main()
