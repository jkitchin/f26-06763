#!/usr/bin/env python3
"""Figures for L16, generative AI.

Every figure is computed here from engineering models with known answers, so every number
in it can be checked: y = |x| with the middle removed, and the Peng-Robinson equation of
state for propane at 300 K and 10 bar. The widget-*.png files are static stand-ins for the
interactive figures in _static/widgets.js (gmm-condition, inverse-cdf, flow-condition,
prob-path), shown by a deck when scripts do not run. They use the same data recipe and the
same mathematics as the browser versions, so they double as a check on that code.

    cd lectures/l16/figures
    uv run --no-project --python 3.12 --with numpy --with scipy --with scikit-learn \
        --with matplotlib --with torch python make_figures.py [group ...]

Groups: intro, gmm, opt, flows, pr, families. With no argument, all of them.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402

HERE = Path(__file__).parent
BLUE, ORANGE, GREEN, GRAY = "#1f6fb2", "#c2410c", "#2b8a3e", "#777777"
plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 150, "savefig.bbox": "tight"})


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print("wrote", name)


# ----------------------------------------------------------------- shared models

def abs_data(n=240, seed=16):
    """y = |x| + N(0, 0.03^2), x uniform on [-1.2, 1.2] with |x| < 0.5 removed."""
    rng = np.random.default_rng(seed)
    x = rng.uniform(-1.2, 1.2, 4 * n)
    x = x[np.abs(x) >= 0.5][:n]
    return x, np.abs(x) + 0.03 * rng.standard_normal(n)


# Peng-Robinson for propane: Tc = 369.8 K, Pc = 42.48 bar, acentric factor 0.152.
R_GAS, TC, PC, OMEGA = 8.314, 369.8, 42.48e5, 0.152


def pr_coeffs(T=300.0, P=10e5):
    kappa = 0.37464 + 1.54226 * OMEGA - 0.26992 * OMEGA**2
    alpha = (1 + kappa * (1 - np.sqrt(T / TC))) ** 2
    a = 0.45724 * R_GAS**2 * TC**2 / PC * alpha
    b = 0.07780 * R_GAS * TC / PC
    A, B = a * P / (R_GAS * T) ** 2, b * P / (R_GAS * T)
    return np.array([1.0, -(1 - B), A - 3 * B**2 - 2 * B, -(A * B - B**2 - B**3)])


PR = pr_coeffs()
PR_ROOTS = np.sort(np.roots(PR).real)  # 0.0348, 0.1280, 0.8147


def condition_gmm(g, cols_known, values, rng, n=4000):
    """Sample p(unknown | known = values) from a fitted sklearn GaussianMixture.

    Each component's conditional is Gaussian (Schur complement), and the components are
    reweighted by the density each one gives the known values."""
    d = g.means_.shape[1]
    kn = list(cols_known)
    un = [j for j in range(d) if j not in kn]
    v = np.asarray(values, float)
    logw, means, covs = [], [], []
    for w, m, S in zip(g.weights_, g.means_, g.covariances_):
        Skk = S[np.ix_(kn, kn)]
        Suk = S[np.ix_(un, kn)]
        Suu = S[np.ix_(un, un)]
        sol = np.linalg.solve(Skk, v - m[kn])
        means.append(m[un] + Suk @ sol)
        covs.append(Suu - Suk @ np.linalg.solve(Skk, Suk.T))
        diff = v - m[kn]
        logw.append(np.log(w) - 0.5 * diff @ sol - 0.5 * np.linalg.slogdet(2 * np.pi * Skk)[1])
    logw = np.array(logw)
    w = np.exp(logw - logw.max())
    w /= w.sum()
    ks = rng.choice(len(w), size=n, p=w)
    return np.array([rng.multivariate_normal(means[k], covs[k]) for k in ks]), w, means, covs


def fm_velocity(data, cw, z, t, smin=0.02):
    """Exact minimizer of the conditional flow-matching loss for a finite data set.

    data (N, d), cw (N,) sample weights, z (M, d) query points, scalar t. Matches
    fmVelocity in _static/widgets.js."""
    st = 1 - (1 - smin) * t
    q = ((z[:, None, :] - t * data[None, :, :]) ** 2).sum(-1)
    with np.errstate(divide="ignore"):
        lw = np.log(cw)[None, :] - 0.5 * q / st**2
    lw -= lw.max(1, keepdims=True)
    w = np.exp(lw)
    w /= w.sum(1, keepdims=True)
    return (w[:, :, None] * (data[None, :, :] - (1 - smin) * z[:, None, :])).sum(1) / st


# ----------------------------------------------------------------- intro

def fig_data():
    """The |x| data alone, posed as the question, for the slide before the clicker."""
    x, y = abs_data()
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.axvspan(-0.5, 0.5, color=GRAY, alpha=0.08)
    ax.text(0, 0.1, "no measurements\nfor −0.5 < x < 0.5", ha="center", fontsize=10, color=GRAY)
    ax.scatter(x, y, s=10, color="k", alpha=0.55, label=f"{len(x)} measurements, y = |x| + noise (sd 0.03)")
    ax.axhline(0.75, color=GREEN, ls="--", lw=1.5)
    ax.text(0, 0.78, "y = 0.75: which x?", ha="center", va="bottom", color=GREEN, fontsize=12)
    ax.set(xlabel="setting x", ylabel="measured y", xlim=(-1.3, 1.3), ylim=(-0.05, 1.3))
    ax.legend(loc="upper center", frameon=False, fontsize=10)
    save(fig, "abs-data.png")


def fig_intro():
    fig_data()
    x, y = abs_data()
    b, a = np.polyfit(y, x, 1)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax1.axvspan(-0.5, 0.5, color=GRAY, alpha=0.08)
    ax1.scatter(x, y, s=8, color="k", alpha=0.5, label="data, y = |x| + noise")
    yy = np.linspace(0, 1.3, 2)
    ax1.plot(a + b * yy, yy, color=ORANGE, lw=2, label="least-squares fit of x on y")
    ax1.axhline(0.75, color=GREEN, ls="--", lw=1.5)
    ax1.plot([a + b * 0.75], [0.75], "o", color=ORANGE, ms=8)
    ax1.plot([-0.75, 0.75], [0.75, 0.75], "o", mfc="none", mec=GREEN, ms=10, mew=2, label="true answers, x = ±0.75")
    ax1.set(xlabel="x", ylabel="y", xlim=(-1.3, 1.3), ylim=(-0.05, 1.3),
            title=f"Which x gives y = 0.75? Regression says {a + b * 0.75:+.2f}")
    ax1.legend(loc="lower left", fontsize=9, frameon=False)

    # Newton's method from 400 starting guesses: which root does each one reach?
    p, dp = np.poly1d(PR), np.poly1d(PR).deriv()
    z0 = np.linspace(0.0, 1.0, 400)
    z = z0.copy()
    for _ in range(60):
        z = z - p(z) / dp(z)
    reached = np.array([np.argmin(np.abs(PR_ROOTS - v)) if np.isfinite(v) else -1 for v in z])
    Z = np.linspace(0.0, 1.0, 500)
    ax2.plot(Z, p(Z), color="k", lw=1.8)
    ax2.axhline(0, color=GRAY, lw=0.8)
    colors = [BLUE, GRAY, ORANGE]
    names = ["liquid", "unstable", "vapor"]
    for j, r in enumerate(PR_ROOTS):
        ax2.plot(r, 0, "o", color=colors[j], ms=9, zorder=3,
                 label=f"{names[j]} {r:.4f}: {np.mean(reached == j):.0%} of starts")
        ax2.scatter(z0[reached == j], np.full((reached == j).sum(), -0.0175), marker="|", color=colors[j], s=60)
    ax2.text(0.5, -0.0152, "Newton start Z₀, colored by root reached", ha="center", fontsize=9)
    ax2.set(xlabel="compressibility factor Z", ylabel="cubic residual r(Z)", ylim=(-0.02, 0.045),
            title="Peng-Robinson, propane at 300 K and 10 bar")
    ax2.legend(fontsize=9, frameon=False, loc="upper left")
    save(fig, "regression-failure.png")


# ----------------------------------------------------------------- gmm

def fig_gmm():
    from matplotlib.patches import Ellipse
    x, y = abs_data()
    D = np.c_[x, y]
    rng = np.random.default_rng(0)
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.2), gridspec_kw={"height_ratios": [2.2, 1]}, sharex=True)
    for col, K in enumerate([1, 2, 4]):
        g = GaussianMixture(K, covariance_type="full", random_state=0, n_init=5).fit(D)
        ax = axes[0, col]
        ax.axvspan(-0.5, 0.5, color=GRAY, alpha=0.08)
        ax.scatter(x, y, s=5, color="k", alpha=0.4)
        for w, m, S in zip(g.weights_, g.means_, g.covariances_):
            vals, vecs = np.linalg.eigh(S)
            ang = np.degrees(np.arctan2(vecs[1, 1], vecs[0, 1]))
            ax.add_patch(Ellipse(m, 4 * np.sqrt(vals[1]), 4 * np.sqrt(vals[0]), angle=ang,
                                 fc=BLUE, alpha=0.1 + 0.4 * w, ec=BLUE, lw=1.3))
        ax.axhline(0.75, color=GREEN, ls="--", lw=1.3)
        ax.set(ylim=(-0.1, 1.35), title=f"K = {K}, BIC = {g.bic(D):.0f}")
        if col == 0:
            ax.set_ylabel("y")
        s, *_ = condition_gmm(g, [1], [0.75], rng)
        ax = axes[1, col]
        ax.hist(s[:, 0], bins=np.linspace(-1.3, 1.3, 105), density=True, color=BLUE, alpha=0.6)
        for v in (-0.75, 0.75):
            ax.axvline(v, color="k", ls=":", lw=1)
        ax.set(xlabel="x", xlim=(-1.3, 1.3))
        if col == 0:
            ax.set_ylabel("p(x | y = 0.75)")
    fig.suptitle("Fit p(x, y) with K Gaussians, then condition on y = 0.75 (dotted: the true answers ±0.75)", y=1.0)
    save(fig, "widget-gmm-condition.png")


# ----------------------------------------------------------------- flows

def fig_flows():
    from scipy.stats import norm
    x, y = abs_data()
    # Inverse CDF, the bimodal target of the inverse-cdf widget.
    comps = [(0.35, -1.2, 0.35), (0.65, 1.0, 0.5)]
    grid = np.linspace(-3, 3, 601)
    pdf = sum(w * norm.pdf(grid, m, s) for w, m, s in comps)
    cdf = np.cumsum(pdf) * (grid[1] - grid[0])
    cdf /= cdf[-1]
    u = np.random.default_rng(5).uniform(size=2000)
    xs = np.interp(u, cdf, grid)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.2), sharex=True, gridspec_kw={"height_ratios": [1, 1]})
    a1.plot(grid, cdf, color=BLUE, lw=2)
    for uu in (0.2, 0.5, 0.8):
        xx = np.interp(uu, cdf, grid)
        a1.plot([-3, xx, xx], [uu, uu, 0], color=ORANGE, lw=1.4)
    a1.set(ylabel="u = F(x)", title="Uniform u through the inverse CDF gives samples of the target")
    a2.hist(xs, bins=60, density=True, color=ORANGE, alpha=0.4, label="2000 mapped samples")
    a2.plot(grid, pdf, color="k", lw=2, label="target density")
    a2.set(xlabel="x", ylabel="density")
    a2.legend(frameon=False, fontsize=9)
    save(fig, "widget-inverse-cdf.png")

    # Conditional flow, 1-D, with the exact field (same recipe as the widget).
    data = x[:, None]
    z = np.random.default_rng(3).standard_normal((60, 1))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    for ax, ystar in zip(axes, (0.75, 0.3)):
        cw = np.exp(-0.5 * ((y - ystar) / 0.04) ** 2)
        path = [z.copy()]
        zz = z.copy()
        for k in range(100):
            zz = zz + fm_velocity(data, cw, zz, k / 100) / 100
            path.append(zz.copy())
        path = np.array(path)[:, :, 0]
        ax.plot(np.linspace(0, 1, 101), path, color=BLUE, lw=0.8, alpha=0.6)
        for v in (-ystar, ystar):
            ax.axhline(v, color=GREEN, ls="--", lw=1.2)
        end = path[-1]
        ax.set(xlabel="time t", title=f"y* = {ystar}: {np.mean(end > 0):.0%} end at x > 0, "
                                       f"means {end[end > 0].mean() if (end > 0).any() else np.nan:+.2f} / "
                                       f"{end[end <= 0].mean():+.2f}")
    axes[0].set_ylabel("x")
    fig.suptitle("Noise at t = 0 flows to p(x | y*) at t = 1 (dashed: the true answers ±y*)", y=1.02)
    save(fig, "widget-flow-condition.png")

    # Probability path in 2-D: straight training lines against integrated paths.
    data2 = np.c_[x, y]
    r = np.random.default_rng(21)
    z0 = r.standard_normal((120, 2))
    x1 = data2[r.integers(0, len(data2), 120)]
    ts = np.linspace(0, 1, 61)
    lines = np.array([(1 - 0.98 * t) * z0 + t * x1 for t in ts])
    zz, ode = z0.copy(), [z0.copy()]
    for k in range(60):
        zz = zz + fm_velocity(data2, np.ones(len(data2)), zz, k / 60) / 60
        ode.append(zz.copy())
    ode = np.array(ode)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, paths, title in zip(axes, (lines, ode), ("training pairs: straight lines", "sampling: integrate the field")):
        ax.scatter(x, y, s=3, color="k", alpha=0.2)
        ax.plot(paths[:, :, 0], paths[:, :, 1], color=BLUE, lw=0.6, alpha=0.35)
        ax.scatter(paths[-1, :, 0], paths[-1, :, 1], s=10, color=ORANGE, zorder=3)
        ax.set(xlim=(-3, 3), ylim=(-2.6, 3), title=title, xlabel="x")
        ax.set_aspect("equal")
    axes[0].set_ylabel("y")
    save(fig, "widget-prob-path.png")


# ----------------------------------------------------------------- pr

def train_cfm(X, C, steps=4000, seed=0):
    """Conditional flow matching: v(x_t, c, t) regressed onto x1 - x0 on straight paths."""
    import torch
    torch.manual_seed(seed)
    X = torch.tensor(X, dtype=torch.float32)
    C = torch.tensor(C, dtype=torch.float32)
    dx, dc = X.shape[1], C.shape[1]
    net = torch.nn.Sequential(torch.nn.Linear(dx + dc + 1, 64), torch.nn.SiLU(), torch.nn.Linear(64, 64),
                              torch.nn.SiLU(), torch.nn.Linear(64, 64), torch.nn.SiLU(), torch.nn.Linear(64, dx))
    opt = torch.optim.Adam(net.parameters(), 1e-3)
    for _ in range(steps):
        i = torch.randint(0, len(X), (256,))
        x1, c = X[i], C[i]
        x0 = torch.randn_like(x1)
        t = torch.rand(len(i), 1)
        xt = (1 - t) * x0 + t * x1
        loss = ((net(torch.cat([xt, c, t], 1)) - (x1 - x0)) ** 2).mean()
        opt.zero_grad()
        loss.backward()
        opt.step()

    def sample(c, n=4000, nsteps=100):
        with torch.no_grad():
            z = torch.randn(n, dx)
            cc = torch.tensor(c, dtype=torch.float32).expand(n, dc)
            for k in range(nsteps):
                t = torch.full((n, 1), k / nsteps)
                z = z + net(torch.cat([z, cc, t], 1)) / nsteps
        return z.numpy()
    return sample


def fig_pr():
    rng = np.random.default_rng(0)
    Z = rng.uniform(0.01, 0.99, 2000)
    r = np.polyval(PR, Z)
    results = {}
    for label, feat, inv in (("GMM on (Z, r)", Z, lambda v: v), ("GMM on (log Z, r)", np.log(Z), np.exp)):
        D = np.c_[feat, r]
        mu, sd = D.mean(0), D.std(0)
        g = GaussianMixture(12, covariance_type="full", random_state=0, n_init=3).fit((D - mu) / sd)
        s, *_ = condition_gmm(g, [1], [(0 - mu[1]) / sd[1]], np.random.default_rng(0))
        results[label] = inv(s[:, 0] * sd[0] + mu[0])
    mu, sd = np.array([Z.mean(), r.mean()]), np.array([Z.std(), r.std()])
    sample = train_cfm(((Z - mu[0]) / sd[0])[:, None], ((r - mu[1]) / sd[1])[:, None])
    results["flow matching on (Z, r)"] = sample([[(0 - mu[1]) / sd[1]]])[:, 0] * sd[0] + mu[0]
    lz = np.log(Z)
    sample = train_cfm(((lz - lz.mean()) / lz.std())[:, None], ((r - mu[1]) / sd[1])[:, None])
    results["flow matching on (log Z, r)"] = np.exp(sample([[(0 - mu[1]) / sd[1]]])[:, 0] * lz.std() + lz.mean())

    fig, axes = plt.subplots(5, 1, figsize=(9, 11), sharex=True, gridspec_kw={"height_ratios": [1.3, 1, 1, 1, 1]})
    Zg = np.linspace(0, 1, 500)
    axes[0].plot(Zg, np.polyval(PR, Zg), color="k")
    axes[0].axhline(0, color=GRAY, lw=0.8)
    axes[0].plot(PR_ROOTS, 0 * PR_ROOTS, "o", color=GREEN)
    axes[0].set(ylim=(-0.02, 0.04), ylabel="r(Z)", title="Condition on r = 0 and sample Z (dashed: numpy.roots)")
    lines = []
    for ax, (label, s) in zip(axes[1:], results.items()):
        ax.hist(s, bins=np.linspace(0, 1, 401), density=True, color=BLUE, alpha=0.7)
        for v in PR_ROOTS:
            ax.axvline(v, color="k", ls="--", lw=0.8)
        near = [s[np.abs(s - v) < 0.03] for v in PR_ROOTS]
        found = ", ".join(f"{m.mean():.4f}" if len(m) else "none" for m in near)
        ax.set(ylabel="density", title=f"{label}: cluster means {found}")
        ax.set_yscale("log")
        lines.append(f"{label}: {found}")
    axes[-1].set_xlabel("compressibility factor Z")
    save(fig, "pr-roots.png")
    print("true roots", ", ".join(f"{v:.4f}" for v in PR_ROOTS))
    print("\n".join(lines))


# ----------------------------------------------------------------- families

def fig_families():
    """Three ways to make p(x) learnable, as three small panels."""
    x, y = abs_data()
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
    g = GaussianMixture(4, random_state=0, n_init=5).fit(np.c_[x, y])
    s = g.sample(400)[0]
    axes[0].scatter(s[:, 0], s[:, 1], s=5, color=BLUE, alpha=0.6)
    axes[0].set(title="1. Fit a density, then condition it\n" + r"$p(x, y) = \sum_k \pi_k\,\mathcal{N}(\mu_k, \Sigma_k)$",
                xlabel="x", ylabel="y")
    r = np.random.default_rng(2)
    z0 = r.standard_normal((300, 2))
    zz = z0.copy()
    for k in range(40):
        zz = zz + fm_velocity(np.c_[x, y], np.ones(len(x)), zz, k / 40) / 40
    axes[1].scatter(z0[:, 0], z0[:, 1], s=4, color=GRAY, alpha=0.4, label="noise, t = 0")
    axes[1].scatter(zz[:, 0], zz[:, 1], s=5, color=ORANGE, alpha=0.7, label="data, t = 1")
    axes[1].legend(frameon=False, fontsize=9, loc="lower left")
    axes[1].set(title="2. Learn a map from noise to data\n" + r"$dx/dt = v_\theta(x, t)$", xlabel="x", xlim=(-3, 3), ylim=(-3, 3))
    words = ["the", "reactor", "outlet", "temperature", "is"]
    probs = [0.42, 0.31, 0.12, 0.08, 0.07]
    cands = ["rising", "stable", "350", "high", "too"]
    axes[2].barh(cands[::-1], probs[::-1], color=GREEN, alpha=0.7)
    axes[2].set(title="3. Factor with the chain rule\n" + r"$p(x_1, \ldots, x_n) = \prod_i p(x_i \mid x_{<i})$",
                xlabel=f"p(next | \"{' '.join(words)}\")  (illustrative numbers)")
    save(fig, "families.png")


def fig_opt():
    """A -> B -> C in a batch reactor: find the residence time that maximizes C_B by
    conditioning a GMM of (tau, dC_B/dtau) on the derivative being zero. Same data, model
    and seeds as section 5 of the notebook."""
    k1, k2, ca0 = 0.5, 0.2, 1.0
    tau = np.random.default_rng(1).uniform(0, 20, 2000)

    def cb(t):
        return ca0 * k1 / (k2 - k1) * (np.exp(-k1 * t) - np.exp(-k2 * t))

    def dcb(t):
        return ca0 * k1 / (k2 - k1) * (-k1 * np.exp(-k1 * t) + k2 * np.exp(-k2 * t))
    X = np.c_[tau, dcb(tau)]
    mu, sd = X.mean(0), X.std(0)
    g = GaussianMixture(8, covariance_type="full", n_init=3, random_state=0).fit((X - mu) / sd)
    s, *_ = condition_gmm(g, [1], [(0 - mu[1]) / sd[1]], np.random.default_rng(0))
    ts = s[:, 0] * sd[0] + mu[0]
    t_star = np.log(k1 / k2) / (k1 - k2)
    tg = np.linspace(0, 20, 400)
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    axes[0].plot(tg, cb(tg), color="k")
    axes[0].axvline(t_star, color=GREEN, ls="--")
    axes[0].set(xlabel="residence time τ (min)", ylabel="C_B (mol/L)", title="the objective: maximize C_B(τ)")
    axes[1].scatter(tau[::4], dcb(tau[::4]), s=4, color=BLUE, alpha=0.5, label="training rows")
    axes[1].axhline(0, color=ORANGE, lw=1.5, label="condition: dC_B/dτ = 0")
    axes[1].axvline(t_star, color=GREEN, ls="--")
    axes[1].set(xlabel="residence time τ (min)", ylabel="dC_B/dτ", title="the data the GMM learns")
    axes[1].legend(frameon=False, fontsize=9)
    axes[2].hist(ts, bins=np.linspace(0, 8, 81), density=True, color=BLUE, alpha=0.7)
    axes[2].axvline(t_star, color=GREEN, ls="--", label=f"analytical τ* = {t_star:.2f}")
    axes[2].set(xlabel="residence time τ (min)", title=f"p(τ | dC_B/dτ = 0): median {np.median(ts):.2f} min")
    axes[2].legend(frameon=False, fontsize=9)
    save(fig, "opt-batch.png")
    print(f"tau* {t_star:.3f}, GMM median {np.median(ts):.3f}, 90% [{np.quantile(ts, .05):.2f}, {np.quantile(ts, .95):.2f}]")


GROUPS = {"intro": fig_intro, "opt": fig_opt, "gmm": fig_gmm, "flows": fig_flows, "pr": fig_pr, "families": fig_families}

if __name__ == "__main__":
    for name in sys.argv[1:] or GROUPS:
        GROUPS[name]()
