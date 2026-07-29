#!/usr/bin/env python3
"""Generate the L13 figures: surrogates, sampling plans, physics, and uncertainty.

Run with:
    uv run --with numpy,scipy,pandas,scikit-learn,matplotlib,torch python make_figures.py

Every number quoted in notes.md and slides.md is printed by this script.

Six of these measurements changed what the lecture says.

  1. The Strouhal collapse was drafted as "the physics collapses the velocity
     sweeps onto one curve." It does, for large chords and high angles of attack
     (6.45 dB of spread becomes 1.55 dB), and it does not for small chords at low
     angle, where it makes things *worse*. A single dimensionless group cannot
     carry three noise mechanisms. The partial collapse is the honest figure.

  2. The physics-feature comparison was drafted expecting a uniform win. Feeding
     the GP log-Strouhal instead of raw frequency helps exactly where the physics
     involves the variable being extrapolated over (chord: 4.37 -> 2.15 dB RMSE)
     and hurts where it does not (angle of attack: 4.84 -> 5.31). Physics is not
     a free lunch; it is a claim, and a claim can be wrong.

  3. The dataset does not obey the U^5 trailing-edge scaling that the
     Brooks-Pope-Marcolini model predicts. At matched Strouhal number the level
     barely moves with velocity. The UCI column is documented as "scaled sound
     pressure level," which is the likely reason. Imposing a 50*log10(U) prior on
     this data would have been imposing a law the data does not contain. Check
     before you constrain.

  4. The deep ensemble was drafted as the well-calibrated alternative to a GP,
     on the strength of Lakshminarayanan et al.'s claims. On the honest split it
     covers 76% of a nominal 95% interval, against the GP's 91%. Five members is
     not enough on 1,200 rows, and "better than a single net" is not "calibrated."

  5. Split conformal was drafted as the method with a guarantee. It has one, and
     the guarantee is about exchangeability, not about the model. Under an i.i.d.
     row split it lands on its nominal coverage almost exactly. Under a grouped
     split it falls to 89%, and under a held-out velocity it falls to 68%. The
     guarantee did not fail; the assumption did.

  6. The soft PDE penalty was drafted to show physics rescuing a net from sparse
     data, which it does. It also shows the failure mode: give the same penalty a
     conductivity that is 30% wrong and it converges confidently to the wrong
     field, and more data does not fix it. A wrong prior is worse than no prior.

  7. Every held-out-configuration number in this file was originally produced by
     `GroupKFold(5)`, and had to be redone. scikit-learn 1.8 and 1.9 assign groups
     to folds by different rules, with the same signature and the same
     `shuffle=False`, so the figures and the demo notebook disagreed: 2.08 dB
     against 1.50 dB, 91% coverage against 94%, on what was supposed to be the
     same split. See `grouped_split` below, which pins it.

Outputs (committed alongside this script):
    surrogate-economics.png   what a solve costs, what a surrogate costs, break-even
    sampling-designs.png      grid vs random vs LHS vs Sobol, and why grid dies
    gp-vs-ensemble.png        two surrogates with uncertainty on a held-out sweep
    physics-features.png      the Strouhal collapse, and where physics features pay
    soft-physics.png          a PDE-residual penalty, hard constraints, wrong physics
    calibration.png           reliability, PICP and the aleatoric/epistemic split

The raw dataset is cached in .cache/ and is gitignored; do not commit it.
"""

from __future__ import annotations

import io
import time
import urllib.request
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import torch
from scipy.interpolate import interp1d
from scipy.stats import qmc
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from torch import nn

# These are small models on small tensors. Left to itself PyTorch opens one
# thread per core and then spends most of its time synchronising them: the
# PINN fits below run 10x faster on four threads than on all of them.
torch.set_num_threads(4)

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
AIRFOIL_URL = "https://archive.ics.uci.edu/static/public/291/airfoil+self+noise.zip"
SEED = 0

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
AMBER = "#b8860b"
PURPLE = "#6b3fa0"
TEAL = "#0f7d8c"

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
RAW = COLS[:5]


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def load_airfoil() -> tuple[pd.DataFrame, np.ndarray]:
    """NASA airfoil self-noise, plus a group id per wind-tunnel configuration.

    A configuration is one (angle of attack, chord, free-stream velocity)
    setting; the displacement thickness is determined by those three, and the
    frequency column is the sweep *within* a run. That matters: five feature
    columns, four independent knobs.
    """
    CACHE.mkdir(exist_ok=True)
    local = CACHE / "airfoil_self_noise.dat"
    if not local.exists():
        print(f"downloading {AIRFOIL_URL}")
        with urllib.request.urlopen(AIRFOIL_URL) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        local.write_bytes(archive.read("airfoil_self_noise.dat"))
    df = pd.read_csv(local, sep="\t", header=None, names=COLS)
    df["strouhal"] = df.freq_hz * df.thickness_m / df.velocity_ms
    groups = df.groupby(["aoa_deg", "chord_m", "velocity_ms"]).ngroup().to_numpy()
    return df, groups


def grouped_split(groups: np.ndarray, n_splits: int = 5, fold: int = 0):
    """Hold out every n_splits-th configuration, by sorted group id.

    Deliberately not `GroupKFold`. scikit-learn 1.8 and 1.9 assign groups to
    folds by different rules, with the same signature and the same
    `shuffle=False`, so the identical call returns different folds on different
    machines. On this dataset that moved the GP's held-out RMSE from 2.08 dB to
    1.50 dB and its coverage from 91% to 94%, which is larger than most of the
    effects this session measures, and nothing warned about it.

    This is L1's `np.trapz` lesson arriving in a new costume: a version-dependent
    default silently changed a number the lecture is built on. The fix is the same
    one, which is to pin the thing you depend on rather than to inherit it.
    """
    unique = np.unique(groups)
    held_out = unique[fold::n_splits]
    mask = np.isin(groups, held_out)
    return np.where(~mask)[0], np.where(mask)[0]


def raw_features(d: pd.DataFrame) -> np.ndarray:
    return d[RAW].to_numpy(float)


def physics_features(d: pd.DataFrame) -> np.ndarray:
    """The same information, re-expressed in the groups the physics uses.

    Trailing-edge noise scales on the Strouhal number St = f delta* / U, so the
    frequency, the boundary-layer thickness and the velocity are not three
    independent knobs but (mostly) one. Nothing is added here and nothing is
    thrown away; the coordinates change.
    """
    return np.column_stack([
        np.log10(d.freq_hz * d.thickness_m / d.velocity_ms),   # log Strouhal
        d.aoa_deg,
        np.log10(d.chord_m),
        np.log10(d.thickness_m),
        d.velocity_ms / 340.3,                                 # Mach
    ])


# --------------------------------------------------------------------------
# The "expensive simulation": 2D steady conduction with a variable conductivity
# --------------------------------------------------------------------------
def solve_heat(x0: float, y0: float, a: float, b: float, n: int = 129) -> np.ndarray:
    """-div(k grad T) = q on the unit square, T = 0 on the boundary.

    k(x, y) = exp(a x + b y) is a smoothly varying conductivity and q is a fixed
    Gaussian source at (x0, y0). Five-point finite volume with harmonic-mean face
    conductivities, solved directly. This stands in for a CFD or FEA run: it is
    milliseconds rather than hours, but the *ratio* to a surrogate evaluation is
    the quantity the argument depends on, and that transfers.
    """
    h = 1.0 / (n - 1)
    xs = np.linspace(0.0, 1.0, n)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    k = np.exp(a * X + b * Y)
    q = 100.0 * np.exp(-((X - x0) ** 2 + (Y - y0) ** 2) / (2 * 0.08 ** 2))

    m = n - 2
    idx = np.arange(m * m).reshape(m, m)
    kx = 2.0 / (1.0 / k[:-1, :] + 1.0 / k[1:, :])      # harmonic mean, x faces
    ky = 2.0 / (1.0 / k[:, :-1] + 1.0 / k[:, 1:])      # harmonic mean, y faces
    w, e = kx[:-1, 1:-1], kx[1:, 1:-1]                 # faces of each interior cell
    s, nn_ = ky[1:-1, :-1], ky[1:-1, 1:]
    diag = (w + e + s + nn_).ravel()

    rows = [idx.ravel()]
    cols = [idx.ravel()]
    vals = [diag]
    for face, shift, axis in ((w, 1, 0), (e, -1, 0), (s, 1, 1), (nn_, -1, 1)):
        keep = np.ones((m, m), dtype=bool)
        if axis == 0:
            keep[: max(shift, 0) or None, :] = shift <= 0
            keep[m + min(shift, 0):, :] = shift >= 0
        else:
            keep[:, : max(shift, 0) or None] = shift <= 0
            keep[:, m + min(shift, 0):] = shift >= 0
        src = idx[keep]
        dst = np.roll(idx, shift, axis=axis)[keep]
        rows.append(src)
        cols.append(dst)
        vals.append(-face[keep])

    A = sp.csr_matrix((np.concatenate(vals),
                       (np.concatenate(rows), np.concatenate(cols))),
                      shape=(m * m, m * m))
    T = np.zeros((n, n))
    T[1:-1, 1:-1] = spla.spsolve(A, (q[1:-1, 1:-1] * h * h).ravel()).reshape(m, m)
    return T


HEAT_BOUNDS = np.array([[0.2, 0.8], [0.2, 0.8], [-3.0, 3.0], [-3.0, 3.0]])
HEAT_NAMES = ["source $x_0$", "source $y_0$", "$\\ln k$ slope $a$", "$\\ln k$ slope $b$"]


def heat_qoi(design: np.ndarray, n: int = 129) -> np.ndarray:
    """log10 of the peak temperature, for each row of a design matrix.

    The quantity of interest is modelled in log space, which is the cheapest hard
    constraint there is: a surrogate trained on log T cannot predict a negative
    temperature, whatever it does elsewhere.
    """
    return np.array([np.log10(solve_heat(*row, n=n).max()) for row in design])


def scale_design(unit: np.ndarray) -> np.ndarray:
    lo, hi = HEAT_BOUNDS[:, 0], HEAT_BOUNDS[:, 1]
    return lo + unit * (hi - lo)


def fit_gp(X: np.ndarray, y: np.ndarray, restarts: int = 0) -> GaussianProcessRegressor:
    """A Matern-5/2 GP with a separate length scale per input (ARD) plus noise."""
    kernel = (ConstantKernel(1.0, (1e-3, 1e4))
              * Matern(length_scale=np.ones(X.shape[1]), nu=2.5,
                       length_scale_bounds=(1e-2, 1e3))
              + WhiteKernel(1e-2, (1e-6, 1e2)))
    return GaussianProcessRegressor(kernel=kernel, normalize_y=True, alpha=0.0,
                                    n_restarts_optimizer=restarts,
                                    random_state=SEED).fit(X, y)


# --------------------------------------------------------------------------
# Figure 1: what a solve costs, what a surrogate costs, and when it pays
# --------------------------------------------------------------------------
def fig_economics(test_design: np.ndarray, test_y: np.ndarray) -> dict:
    print("\nfig_economics")
    n_train = 128
    train_design = scale_design(qmc.LatinHypercube(4, seed=SEED).random(n_train))

    t0 = time.perf_counter()
    train_y = heat_qoi(train_design)
    train_seconds = time.perf_counter() - t0
    solve_ms = train_seconds / n_train * 1e3
    print(f"  {n_train} training solves in {train_seconds:.1f} s "
          f"= {solve_ms:.1f} ms per solve")

    scaler = StandardScaler().fit(train_design)
    t0 = time.perf_counter()
    gp = fit_gp(scaler.transform(train_design), train_y, restarts=2)
    fit_seconds = time.perf_counter() - t0

    Xte = scaler.transform(test_design)
    best = float("inf")
    for _ in range(7):
        t0 = time.perf_counter()
        mu = gp.predict(Xte)
        best = min(best, time.perf_counter() - t0)
    predict_ms = best / len(test_design) * 1e3
    rmse = float(np.sqrt(np.mean((test_y - mu) ** 2)))
    speedup = solve_ms / predict_ms
    print(f"  GP fit on {n_train} points in {fit_seconds:.1f} s; "
          f"prediction {predict_ms * 1e3:.1f} us per point ({speedup:,.0f}x faster)")
    print(f"  surrogate RMSE on {len(test_y)} held-out designs: {rmse:.4f} "
          f"decades of peak temperature (target range "
          f"{test_y.min():.2f} to {test_y.max():.2f})")

    # Break-even: N queries cost N * solve, or (n_train * solve + fit + N * predict).
    queries = np.logspace(0, 6, 200)
    direct = queries * solve_ms / 1e3
    surrogate = n_train * solve_ms / 1e3 + fit_seconds + queries * predict_ms / 1e3
    cross = queries[np.argmax(surrogate < direct)]
    print(f"  break-even at {cross:.0f} queries "
          f"(training budget {n_train} solves + {fit_seconds:.1f} s of fitting)")

    fig = plt.figure(figsize=(15.0, 5.4))
    gsp = fig.add_gridspec(1, 3, width_ratios=[0.85, 1, 1.15], wspace=0.45)

    ax0 = fig.add_subplot(gsp[0])
    field = solve_heat(0.35, 0.6, 2.0, -2.0)
    im = ax0.imshow(field.T, origin="lower", extent=(0, 1, 0, 1), cmap="magma")
    ax0.set_title("One evaluation", pad=10)
    ax0.set_xlabel("$x$")
    ax0.set_ylabel("$y$")
    fig.colorbar(im, ax=ax0, fraction=0.046, pad=0.04, label="$T$")
    ax0.text(0.03, 0.95, f"{solve_ms:.0f} ms", transform=ax0.transAxes, va="top",
             fontsize=15, color="white", fontweight="bold")

    ax1 = fig.add_subplot(gsp[1])
    ax1.scatter(test_y, mu, s=16, color=BLUE, alpha=0.55, edgecolor="none")
    lims = [min(test_y.min(), mu.min()) - 0.1, max(test_y.max(), mu.max()) + 0.1]
    ax1.plot(lims, lims, color=INK, lw=1.2)
    ax1.set_xlim(lims)
    ax1.set_ylim(lims)
    ax1.set_xlabel("solver $\\log_{10} T_{\\max}$")
    ax1.set_ylabel("surrogate $\\log_{10} T_{\\max}$")
    ax1.set_title(f"{n_train} training solves, RMSE {rmse:.3f}", pad=10)
    ax1.grid(True, color=RULE, lw=0.7)
    ax1.set_axisbelow(True)

    ax2 = fig.add_subplot(gsp[2])
    ax2.loglog(queries, direct, color=CMU_RED, lw=2.4, label="solve every time")
    ax2.loglog(queries, surrogate, color=BLUE, lw=2.4,
               label=f"train a surrogate ({n_train} solves), then predict")
    ax2.axvline(cross, color=MUTED, ls=":", lw=1.4)
    ax2.annotate(f"break-even\n{cross:.0f} queries", xy=(cross, direct[0] * 50),
                 xytext=(cross * 1.5, direct[0] * 20), fontsize=11, color=MUTED)
    ax2.set_xlabel("Number of design evaluations")
    ax2.set_ylabel("Total wall-clock, seconds")
    ax2.set_title(f"The surrogate is {speedup:,.0f}x cheaper per query", pad=10)
    ax2.legend(frameon=False, fontsize=10.5, loc="upper left")
    ax2.grid(True, which="both", color=RULE, lw=0.6)
    ax2.set_axisbelow(True)

    fig.suptitle("A surrogate is a fixed cost you pay once, to make every later "
                 "query nearly free", fontsize=15.5, y=1.03)
    fig.savefig(HERE / "surrogate-economics.png")
    plt.close(fig)
    print("wrote surrogate-economics.png")
    return {"solve_ms": solve_ms, "predict_ms": predict_ms, "speedup": speedup,
            "fit_seconds": fit_seconds, "rmse": rmse, "break_even": float(cross),
            "n_train": n_train}


# --------------------------------------------------------------------------
# Figure 2: how to spend a sampling budget
# --------------------------------------------------------------------------
def fig_sampling(test_design: np.ndarray, test_y: np.ndarray) -> dict:
    print("\nfig_sampling")
    budgets = [16, 81, 256]
    n_repeat = 3
    results = {d: {n: [] for n in budgets}
               for d in ("full grid", "uniform random", "Latin hypercube", "Sobol")}

    def evaluate(design):
        y = heat_qoi(design)
        scaler = StandardScaler().fit(design)
        gp = fit_gp(scaler.transform(design), y)
        pred = gp.predict(scaler.transform(test_design))
        return float(np.sqrt(np.mean((test_y - pred) ** 2)))

    for n in budgets:
        levels = int(round(n ** 0.25))
        axis = (np.arange(levels) + 0.5) / levels
        grid = np.stack(np.meshgrid(*[axis] * 4, indexing="ij"), -1).reshape(-1, 4)
        results["full grid"][n].append(evaluate(scale_design(grid)))
        print(f"  n={n:4d}  full grid ({levels} levels^4 = {len(grid)} points) "
              f"RMSE {results['full grid'][n][0]:.4f}")
        for rep in range(n_repeat):
            rng = np.random.default_rng(SEED + rep)
            results["uniform random"][n].append(
                evaluate(scale_design(rng.random((n, 4)))))
            results["Latin hypercube"][n].append(evaluate(scale_design(
                qmc.LatinHypercube(4, seed=SEED + rep).random(n))))
            results["Sobol"][n].append(evaluate(scale_design(
                qmc.Sobol(4, scramble=True, seed=SEED + rep).random(n))))
        for d in ("uniform random", "Latin hypercube", "Sobol"):
            a = np.array(results[d][n])
            print(f"  n={n:4d}  {d:16s} RMSE {a.mean():.4f} +/- {a.std():.4f}")

    # The Sobol power-of-two footgun, measured on discrepancy rather than asserted.
    disc = {}
    for n in (64, 81, 128, 100):
        vals = [qmc.discrepancy(qmc.Sobol(4, scramble=True, seed=s).random(n))
                for s in range(8)]
        disc[n] = float(np.mean(vals))
    print("  Sobol discrepancy (lower is better): "
          + ", ".join(f"n={n}: {v:.2e}" for n, v in disc.items()))

    fig = plt.figure(figsize=(15.0, 5.6))
    gsp = fig.add_gridspec(2, 4, width_ratios=[1, 1, 1.15, 1.35], wspace=0.38,
                           hspace=0.45)

    demo = {
        "full grid": np.stack(np.meshgrid(*[(np.arange(4) + .5) / 4] * 2,
                                          indexing="ij"), -1).reshape(-1, 2),
        "uniform random": np.random.default_rng(3).random((16, 2)),
        "Latin hypercube": qmc.LatinHypercube(2, seed=SEED).random(16),
        "Sobol": qmc.Sobol(2, scramble=True, seed=SEED).random(16),
    }
    for i, (name, pts) in enumerate(demo.items()):
        ax = fig.add_subplot(gsp[i // 2, i % 2])
        ax.scatter(pts[:, 0], pts[:, 1], s=26, color=BLUE, zorder=3)
        for v in np.linspace(0, 1, 5):
            ax.axhline(v, color=RULE, lw=0.6)
            ax.axvline(v, color=RULE, lw=0.6)
        ax.plot(pts[:, 0], np.full(len(pts), -0.09), "|", color=CMU_RED, ms=8,
                clip_on=False)
        occupied = len(np.unique(np.floor(pts[:, 0] * 16).astype(int)))
        ax.set_title(f"{name}\n{occupied}/16 bins in $x$", fontsize=11.5, pad=6)
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.02, 1.02)
        ax.set_xticks([])
        ax.set_yticks([])

    ax = fig.add_subplot(gsp[:, 2])
    dims = np.arange(1, 11)
    for budget, colour in ((100, BLUE), (1000, GREEN)):
        ax.plot(dims, np.floor(budget ** (1 / dims)), "o-", color=colour, lw=2.2,
                ms=6, label=f"budget of {budget:,} runs")
    ax.axhline(2, color=CMU_RED, ls="--", lw=1.4)
    ax.text(3.4, 2.4, "two levels: a plane,\nand nothing else",
            fontsize=10.5, color=CMU_RED)
    ax.set_xticks([2, 4, 6, 8, 10])
    ax.set_xlabel("Design variables $d$")
    ax.set_ylabel("Levels per variable a full grid affords")
    ax.set_title("Why grids die", pad=10)
    ax.legend(frameon=False, fontsize=10.5)
    ax.grid(True, color=RULE, lw=0.7)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 11)

    ax = fig.add_subplot(gsp[:, 3])
    styles = {"full grid": (CMU_RED, "o"), "uniform random": (MUTED, "s"),
              "Latin hypercube": (BLUE, "^"), "Sobol": (GREEN, "D")}
    for name, (colour, marker) in styles.items():
        means = [np.mean(results[name][n]) for n in budgets]
        errs = [np.std(results[name][n]) for n in budgets]
        ax.errorbar(budgets, means, yerr=errs, color=colour, marker=marker, lw=2.2,
                    ms=7, capsize=4, label=name)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(budgets)
    ax.set_xticklabels([str(b) for b in budgets])
    ax.set_xlabel("Simulation budget")
    ax.set_ylabel("Surrogate RMSE, decades of $T_{\\max}$")
    ax.set_title("4 design variables, same solver", pad=10)
    ax.legend(frameon=False, fontsize=10.5)
    ax.grid(True, which="both", color=RULE, lw=0.6)
    ax.set_axisbelow(True)

    fig.suptitle("Where the points go matters more than how many there are",
                 fontsize=15.5, y=1.02)
    fig.savefig(HERE / "sampling-designs.png")
    plt.close(fig)
    print("wrote sampling-designs.png")
    return {"results": {d: {n: [float(x) for x in v] for n, v in r.items()}
                        for d, r in results.items()},
            "discrepancy": disc, "budgets": budgets}


# --------------------------------------------------------------------------
# Neural surrogate: a mean-variance network, and an ensemble of them
# --------------------------------------------------------------------------
class MeanVariance(nn.Module):
    """Predicts a mean and a variance, trained by Gaussian negative log-likelihood.

    The variance head is the aleatoric part: what the network thinks the
    irreducible scatter is at this input. The spread *between* ensemble members
    is the epistemic part. Lakshminarayanan et al. (2017) is this, five times.
    """

    def __init__(self, d_in: int, width: int = 64, p_drop: float = 0.0):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(d_in, width), nn.ReLU(), nn.Dropout(p_drop),
            nn.Linear(width, width), nn.ReLU(), nn.Dropout(p_drop))
        self.head = nn.Linear(width, 2)

    def forward(self, x):
        out = self.head(self.body(x))
        return out[:, :1], nn.functional.softplus(out[:, 1:]) + 1e-3


def fit_member(X, z, seed, epochs=400, p_drop=0.0):
    torch.manual_seed(seed)
    model = MeanVariance(X.shape[1], p_drop=p_drop)
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    xt = torch.tensor(X, dtype=torch.float32)
    zt = torch.tensor(z, dtype=torch.float32)[:, None]
    gen = torch.Generator().manual_seed(seed)
    for _ in range(epochs):
        for idx in torch.randperm(len(xt), generator=gen).split(64):
            mu, var = model(xt[idx])
            loss = (torch.log(var) / 2 + (zt[idx] - mu) ** 2 / (2 * var)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    return model.eval()


def ensemble_predict(models, X, y_mean, y_std):
    """Mixture mean and the law-of-total-variance split, back in target units."""
    xt = torch.tensor(X, dtype=torch.float32)
    with torch.no_grad():
        out = [(m(xt)[0].numpy().ravel(), m(xt)[1].numpy().ravel()) for m in models]
    mus = np.array([o[0] for o in out])
    variances = np.array([o[1] for o in out])
    mean = mus.mean(0)
    epistemic = mus.var(0)
    aleatoric = variances.mean(0)
    return (mean * y_std + y_mean, np.sqrt(epistemic + aleatoric) * y_std,
            np.sqrt(epistemic) * y_std, np.sqrt(aleatoric) * y_std)


def fit_ensemble(Xtr, ytr, n_members=5, seed0=0, **kw):
    y_mean, y_std = ytr.mean(), ytr.std()
    z = (ytr - y_mean) / y_std
    models = [fit_member(Xtr, z, seed0 + i, **kw) for i in range(n_members)]
    return models, y_mean, y_std


def interval_metrics(y, mu, sd, alpha=0.05):
    from scipy.stats import norm
    zc = norm.ppf(1 - alpha / 2)
    return {
        "rmse": float(np.sqrt(np.mean((y - mu) ** 2))),
        "picp": float(np.mean(np.abs(y - mu) <= zc * sd)),
        "width": float(np.mean(2 * zc * sd)),
        "nll": float(np.mean(0.5 * np.log(2 * np.pi * sd ** 2)
                             + (y - mu) ** 2 / (2 * sd ** 2))),
    }


# --------------------------------------------------------------------------
# Figure 3: a GP and a deep ensemble on the same held-out sweep
# --------------------------------------------------------------------------
def fig_gp_vs_ensemble(df: pd.DataFrame, groups: np.ndarray) -> dict:
    print("\nfig_gp_vs_ensemble")
    X = raw_features(df)
    y = df.spl_db.to_numpy()
    out = {}

    def run(tr, te, label):
        scaler = StandardScaler().fit(X[tr])
        Xtr, Xte = scaler.transform(X[tr]), scaler.transform(X[te])
        gp = fit_gp(Xtr, y[tr])
        gmu, gsd = gp.predict(Xte, return_std=True)
        models, ym, ys = fit_ensemble(Xtr, y[tr])
        emu, esd, eep, eal = ensemble_predict(models, Xte, ym, ys)
        g = interval_metrics(y[te], gmu, gsd)
        e = interval_metrics(y[te], emu, esd)
        print(f"  {label:24s} GP   RMSE {g['rmse']:5.2f}  sd {gsd.mean():5.2f}  "
              f"PICP {g['picp']:5.1%}  width {g['width']:5.2f}")
        print(f"  {'':24s} ens  RMSE {e['rmse']:5.2f}  sd {esd.mean():5.2f}  "
              f"PICP {e['picp']:5.1%}  width {e['width']:5.2f}  "
              f"(epi {eep.mean():.2f} / ale {eal.mean():.2f})")
        return dict(gp=g, ens=e, gsd=float(gsd.mean()), esd=float(esd.mean()),
                    epi=float(eep.mean()), ale=float(eal.mean()),
                    gmu=gmu, gsd_v=gsd, emu=emu, esd_v=esd)

    tr, te = grouped_split(groups)
    out["interpolation"] = run(tr, te, "held-out configurations")
    fast = df.velocity_ms.to_numpy() == 71.3
    out["extrapolation"] = run(np.where(~fast)[0], np.where(fast)[0],
                               "held-out velocity 71.3")

    # A single held-out configuration to draw: the longest sweep in fold 0.
    sizes = pd.Series(groups[te]).value_counts()
    target = int(sizes.idxmax())
    mask = groups[te] == target
    order = np.argsort(df.freq_hz.to_numpy()[te][mask])
    freq = df.freq_hz.to_numpy()[te][mask][order]
    truth = y[te][mask][order]
    cfg = df.iloc[te[mask][0]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.6),
                                   gridspec_kw={"width_ratios": [1.25, 1]})
    inter = out["interpolation"]
    for key, colour, label in (("g", BLUE, "Gaussian process"),
                               ("e", CMU_RED, "deep ensemble (5 nets)")):
        mu = (inter["gmu"] if key == "g" else inter["emu"])[mask][order]
        sd = (inter["gsd_v"] if key == "g" else inter["esd_v"])[mask][order]
        ax1.plot(freq, mu, color=colour, lw=2.2, label=label)
        ax1.fill_between(freq, mu - 1.96 * sd, mu + 1.96 * sd, color=colour,
                         alpha=0.16, lw=0)
    ax1.plot(freq, truth, "o", color=INK, ms=6, label="wind tunnel", zorder=5)
    ax1.set_xscale("log")
    ax1.set_xlabel("Frequency, Hz")
    ax1.set_ylabel("Sound pressure level, dB")
    ax1.set_title(f"One configuration the models never saw\n"
                  f"({cfg.aoa_deg:g}$^\\circ$, chord {cfg.chord_m:g} m, "
                  f"{cfg.velocity_ms:g} m/s), 95% intervals", fontsize=13, pad=10)
    ax1.legend(frameon=False, fontsize=10.5, loc="lower left")
    ax1.grid(True, which="both", color=RULE, lw=0.6)
    ax1.set_axisbelow(True)

    labels = ["held-out\nconfigurations", "held-out\nvelocity (71.3 m/s)"]
    pos = np.arange(2)
    width = 0.35
    keys = ("interpolation", "extrapolation")
    gsd = [out[k]["gsd"] for k in keys]
    esd = [out[k]["esd"] for k in keys]
    gp_cov = [out[k]["gp"]["picp"] for k in keys]
    en_cov = [out[k]["ens"]["picp"] for k in keys]
    ax2.bar(pos - width / 2, gsd, width, color=BLUE, label="Gaussian process")
    ax2.bar(pos + width / 2, esd, width, color=CMU_RED, label="deep ensemble")
    for i in range(2):
        for offset, sd, cov in ((-width / 2, gsd[i], gp_cov[i]),
                                (width / 2, esd[i], en_cov[i])):
            ax2.annotate(f"$\\sigma$ = {sd:.2f}\n{cov:.0%} covered",
                         (i + offset, sd), xytext=(0, 6),
                         textcoords="offset points", ha="center", fontsize=10.5)
    growth_g = gsd[1] / gsd[0]
    growth_e = esd[1] / esd[0]
    ax2.set_xticks(pos)
    ax2.set_xticklabels(labels, fontsize=11)
    ax2.set_ylabel("Mean predicted $\\sigma$, dB")
    ax2.set_title("Wider is not the same as right\n"
                  "(nominal coverage is 95% in every bar)", fontsize=13, pad=10)
    ax2.legend(frameon=False, fontsize=11, loc="upper left")
    ax2.grid(True, axis="y", color=RULE, lw=0.7)
    ax2.set_axisbelow(True)
    ax2.set_ylim(0, max(gsd + esd) * 1.75)
    print(f"  sigma growth out of distribution: GP {growth_g:.2f}x, "
          f"ensemble {growth_e:.2f}x")

    fig.suptitle("NASA airfoil self-noise: two surrogates that both report an "
                 "uncertainty", fontsize=15.5, y=1.02)
    fig.savefig(HERE / "gp-vs-ensemble.png")
    plt.close(fig)
    print("wrote gp-vs-ensemble.png")
    for k in out:
        for drop in ("gmu", "gsd_v", "emu", "esd_v"):
            out[k].pop(drop)
    out["growth"] = {"gp": float(growth_g), "ensemble": float(growth_e)}
    return out


# --------------------------------------------------------------------------
# Figure 4: the Strouhal collapse, and where physics features actually pay
# --------------------------------------------------------------------------
def curve_spread(g: pd.DataFrame, xcol: str, npts: int = 25) -> float | None:
    """RMS pointwise spread, in dB, between the velocity curves of one setting."""
    curves = []
    for _, gv in g.groupby("velocity_ms"):
        gv = gv.sort_values(xcol)
        x = np.log10(gv[xcol].to_numpy())
        keep = np.concatenate([[True], np.diff(x) > 0])
        if keep.sum() >= 4:
            curves.append((x[keep], gv.spl_db.to_numpy()[keep]))
    if len(curves) < 2:
        return None
    lo = max(c[0].min() for c in curves)
    hi = min(c[0].max() for c in curves)
    if hi <= lo:
        return None
    grid = np.linspace(lo, hi, npts)
    stack = np.array([interp1d(x, y)(grid) for x, y in curves])
    return float(np.sqrt(np.mean(np.var(stack, axis=0, ddof=1))))


def fig_physics(df: pd.DataFrame, groups: np.ndarray) -> dict:
    print("\nfig_physics")
    freq_spread, st_spread, keys = [], [], []
    for key, g in df.groupby(["aoa_deg", "chord_m"]):
        if g.velocity_ms.nunique() < 2:
            continue
        a, b = curve_spread(g, "freq_hz"), curve_spread(g, "strouhal")
        if a is None or b is None:
            continue
        freq_spread.append(a)
        st_spread.append(b)
        keys.append(key)
    freq_spread, st_spread = np.array(freq_spread), np.array(st_spread)
    better = int((st_spread < freq_spread).sum())
    print(f"  {len(keys)} (aoa, chord) settings with more than one velocity")
    print(f"    spread against frequency: mean {freq_spread.mean():.2f} dB")
    print(f"    spread against Strouhal : mean {st_spread.mean():.2f} dB")
    print(f"    Strouhal is tighter in {better}/{len(keys)} settings")

    # Does the U^5 trailing-edge scaling hold here? Fit the exponent per setting.
    exps = []
    for _, g in df.groupby(["aoa_deg", "chord_m"]):
        oa = g.groupby("velocity_ms").apply(
            lambda h: 10 * np.log10(np.sum(10 ** (h.spl_db / 10))),
            include_groups=False)
        if len(oa) >= 3:
            exps.append(np.polyfit(np.log10(oa.index.to_numpy()),
                                   oa.to_numpy(), 1)[0] / 10)
    exps = np.array(exps)
    print(f"    overall-level exponent n in U^n: median {np.median(exps):.2f} "
          f"over {len(exps)} settings (Brooks-Pope-Marcolini predicts 5)")

    y = df.spl_db.to_numpy()
    regimes = {
        "held-out\nconfigurations": np.zeros(len(df), dtype=bool),
        "held-out velocity\n71.3 m/s": df.velocity_ms.to_numpy() == 71.3,
        "held-out chord\n0.3048 m": df.chord_m.to_numpy() == 0.3048,
        "held-out stall\n$\\alpha \\geq 15.4^\\circ$": df.aoa_deg.to_numpy() >= 15.4,
    }
    table = {}
    for name, mask in regimes.items():
        if not mask.any():
            tr, te = grouped_split(groups)
        else:
            tr, te = np.where(~mask)[0], np.where(mask)[0]
        row = {}
        for feat_name, featfn in (("raw", raw_features), ("physics", physics_features)):
            Xall = featfn(df)
            scaler = StandardScaler().fit(Xall[tr])
            gp = fit_gp(scaler.transform(Xall[tr]), y[tr])
            mu, sd = gp.predict(scaler.transform(Xall[te]), return_std=True)
            row[feat_name] = interval_metrics(y[te], mu, sd)
            row[feat_name]["sd"] = float(sd.mean())
        table[name] = row
        flat = name.replace("\n", " ")
        print(f"    {flat:38s} raw {row['raw']['rmse']:5.2f} -> "
              f"physics {row['physics']['rmse']:5.2f} dB "
              f"({'better' if row['physics']['rmse'] < row['raw']['rmse'] else 'WORSE'}),"
              f" n_test = {len(te)}")

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15.5, 5.2),
                                        gridspec_kw={"width_ratios": [1, 1, 1.3]})
    show = df[(df.aoa_deg == 0.0) & (df.chord_m == 0.3048)]
    palette = [BLUE, GREEN, AMBER, CMU_RED]
    for (v, gv), colour in zip(show.groupby("velocity_ms"), palette):
        gv = gv.sort_values("freq_hz")
        ax1.semilogx(gv.freq_hz, gv.spl_db, "o-", color=colour, ms=4, lw=1.8,
                     label=f"{v:g} m/s")
        ax2.semilogx(gv.strouhal, gv.spl_db, "o-", color=colour, ms=4, lw=1.8)
    a, b = curve_spread(show, "freq_hz"), curve_spread(show, "strouhal")
    ax1.set_xlabel("Frequency, Hz")
    ax1.set_ylabel("Sound pressure level, dB")
    ax1.set_title(f"Raw coordinates\nspread {a:.2f} dB", fontsize=13, pad=8)
    ax1.legend(frameon=False, fontsize=10, title="free stream")
    ax2.set_xlabel("Strouhal number $f\\,\\delta^*/U$")
    ax2.set_title(f"Physics coordinates\nspread {b:.2f} dB", fontsize=13, pad=8)
    for ax in (ax1, ax2):
        ax.grid(True, which="both", color=RULE, lw=0.6)
        ax.set_axisbelow(True)
        ax.set_ylim(104, 133)

    names = list(table)
    pos = np.arange(len(names))
    width = 0.36
    raw_v = [table[n]["raw"]["rmse"] for n in names]
    phy_v = [table[n]["physics"]["rmse"] for n in names]
    ax3.bar(pos - width / 2, raw_v, width, color=MUTED, label="raw columns")
    ax3.bar(pos + width / 2, phy_v, width, color=TEAL,
            label="Strouhal / Mach coordinates")
    for i, (r, p) in enumerate(zip(raw_v, phy_v)):
        colour = GREEN if p < r else CMU_RED
        ax3.annotate(f"{100 * (p - r) / r:+.0f}%", (i + width / 2, p),
                     xytext=(0, 5), textcoords="offset points", ha="center",
                     fontsize=11, fontweight="bold", color=colour)
    ax3.set_xticks(pos)
    ax3.set_xticklabels(names, fontsize=9)
    ax3.set_ylabel("GP RMSE, dB")
    ax3.set_title("Physics pays only where it applies", pad=8)
    ax3.legend(frameon=False, fontsize=10.5, loc="upper left")
    ax3.grid(True, axis="y", color=RULE, lw=0.7)
    ax3.set_axisbelow(True)
    ax3.set_ylim(0, max(raw_v + phy_v) * 1.35)

    fig.suptitle("The same five numbers, in two coordinate systems",
                 fontsize=15.5, y=1.02)
    fig.savefig(HERE / "physics-features.png")
    plt.close(fig)
    print("wrote physics-features.png")
    return {"freq_spread": float(freq_spread.mean()),
            "st_spread": float(st_spread.mean()),
            "better": better, "n_settings": len(keys),
            "exponent": float(np.median(exps)), "table": table,
            "showcase": {"freq": a, "strouhal": b},
            "best": {"key": keys[int(np.argmin(st_spread / freq_spread))],
                     "freq": float(freq_spread[int(np.argmin(st_spread / freq_spread))]),
                     "st": float(st_spread[int(np.argmin(st_spread / freq_spread))])},
            "worst": {"key": keys[int(np.argmax(st_spread / freq_spread))],
                      "freq": float(freq_spread[int(np.argmax(st_spread / freq_spread))]),
                      "st": float(st_spread[int(np.argmax(st_spread / freq_spread))])}}


# --------------------------------------------------------------------------
# Figure 5: a soft PDE penalty, a hard boundary condition, and wrong physics
# --------------------------------------------------------------------------
K_TRUE = 2.5           # the conductivity the "experiment" actually has


def source(x, complete=True):
    """The heat source. `complete=False` is an engineer who missed the hot spot."""
    q = 50.0 * np.sin(3 * np.pi * x)
    if complete:
        q = q + 300.0 * np.exp(-((x - 0.72) / 0.05) ** 2)
    return q


def reference_solution(n=4001, k=K_TRUE):
    """-k T'' = q on [0, 1], T(0) = T(1) = 0, by finite differences."""
    x = np.linspace(0, 1, n)
    h = x[1] - x[0]
    A = sp.diags([np.full(n - 3, -1.0), np.full(n - 2, 2.0), np.full(n - 3, -1.0)],
                 [-1, 0, 1], format="csc")
    T = np.zeros(n)
    T[1:-1] = spla.spsolve(A, source(x[1:-1]) * h * h / k)
    return x, T


class Field(nn.Module):
    """A tiny tanh net for T(x), plus the conductivity we are trying to identify.

    tanh rather than ReLU because the loss differentiates the network twice, and
    the second derivative of a ReLU network is zero almost everywhere. That is
    not a detail: a PINN built on ReLU has a PDE residual it cannot reduce.
    """

    def __init__(self, width=32, hard_bc=False, learn_k=True):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(1, width), nn.Tanh(),
                                 nn.Linear(width, width), nn.Tanh(),
                                 nn.Linear(width, 1))
        self.hard_bc = hard_bc
        self.log_k = nn.Parameter(torch.zeros(())) if learn_k else None

    def forward(self, x):
        out = self.net(x)
        # x(1-x)N(x) satisfies T(0) = T(1) = 0 exactly, for any weights at all.
        return x * (1 - x) * out if self.hard_bc else out

    @property
    def k(self):
        return torch.exp(self.log_k)


def fit_field(x_data, y_data, *, lam, complete_physics=True, hard_bc=False, seed=0,
              epochs=1500, n_collocation=200, scale=1.0):
    """Fit T(x), and (when lam > 0) the conductivity k, from sparse noisy data."""
    torch.manual_seed(seed)
    model = Field(hard_bc=hard_bc, learn_k=lam > 0)
    opt = torch.optim.Adam(model.parameters(), lr=5e-3)
    xd = torch.tensor(x_data, dtype=torch.float32)[:, None]
    yd = torch.tensor(y_data / scale, dtype=torch.float32)[:, None]
    xc = torch.linspace(0, 1, n_collocation, dtype=torch.float32)[:, None]
    q_np = source(xc.numpy().ravel(), complete=complete_physics) / scale
    qc = torch.tensor(q_np, dtype=torch.float32)[:, None]
    q_ref = float(np.abs(q_np).max())
    edges = torch.tensor([[0.0], [1.0]])
    for _ in range(epochs):
        opt.zero_grad()
        loss = ((model(xd) - yd) ** 2).mean()
        if lam > 0:
            xr = xc.clone().requires_grad_(True)
            T = model(xr)
            dT = torch.autograd.grad(T.sum(), xr, create_graph=True)[0]
            d2T = torch.autograd.grad(dT.sum(), xr, create_graph=True)[0]
            residual = (model.k * d2T + qc) / q_ref      # -k T'' = q
            loss = loss + lam * (residual ** 2).mean()
        if not hard_bc:
            loss = loss + (model(edges) ** 2).mean()     # boundary, softly
        loss.backward()
        opt.step()
    k_hat = float(model.k.detach()) if lam > 0 else float("nan")
    return model.eval(), k_hat


def evaluate_field(model, x_grid, scale):
    with torch.no_grad():
        return model(torch.tensor(x_grid, dtype=torch.float32)[:, None]
                     ).numpy().ravel() * scale


def fig_soft_physics() -> dict:
    """The forward problem needs no data at all, so this is the inverse one.

    If you know the PDE, the source and the boundary conditions, a PINN solves
    the problem with zero measurements and the comparison is vacuous. The
    engineering situation is the other one: the operator is known, a material
    property is not, and the measurements are few and noisy.
    """
    print("\nfig_soft_physics")
    x_ref, T_ref = reference_solution()
    truth = interp1d(x_ref, T_ref)
    scale = float(np.abs(T_ref).max())
    noise = 0.05 * scale
    print(f"  true k = {K_TRUE}, peak temperature {T_ref.max():.3f}, "
          f"measurement noise sd {noise:.3f}")

    variants = {
        "data only": dict(lam=0.0),
        "soft PDE penalty": dict(lam=1.0),
        "soft PDE + hard BC": dict(lam=1.0, hard_bc=True),
        "PDE penalty, source mis-specified": dict(lam=1.0, complete_physics=False),
    }
    sizes = [4, 8, 16, 32, 64]
    x_test = np.linspace(0, 1, 501)
    y_test = truth(x_test)
    curves = {name: {n: [] for n in sizes} for name in variants}
    ks = {name: {n: [] for n in sizes} for name in variants}
    bc_violation = {name: [] for name in variants}

    for n in sizes:
        for seed in range(5):
            rng = np.random.default_rng(100 + seed)
            xd = np.sort(rng.uniform(0.02, 0.98, n))
            yd = truth(xd) + rng.normal(0, noise, n)
            for name, kw in variants.items():
                model, k_hat = fit_field(xd, yd, seed=seed, scale=scale, **kw)
                pred = evaluate_field(model, x_test, scale)
                curves[name][n].append(float(np.sqrt(np.mean((y_test - pred) ** 2))))
                ks[name][n].append(k_hat)
                edges = evaluate_field(model, np.array([0.0, 1.0]), scale)
                bc_violation[name].append(float(np.abs(edges).max()))
        line = "   ".join(f"{name[:14]:14s} {np.mean(curves[name][n]):6.3f} "
                          f"(k {np.nanmean(ks[name][n]):5.2f})" for name in variants)
        print(f"  n={n:3d}  {line}")

    for name in variants:
        v = np.array(bc_violation[name])
        print(f"  boundary violation max|T(0)|,|T(1)|: {name:36s} "
              f"mean {v.mean():.2e}, worst {v.max():.2e}")

    rng = np.random.default_rng(100)
    xd8 = np.sort(rng.uniform(0.02, 0.98, 8))
    yd8 = truth(xd8) + rng.normal(0, noise, 8)
    drawn = {}
    for name, kw in variants.items():
        model, k_hat = fit_field(xd8, yd8, seed=0, scale=scale, **kw)
        drawn[name] = evaluate_field(model, x_test, scale)
        print(f"  n=8 shown: {name:36s} RMSE "
              f"{np.sqrt(np.mean((y_test - drawn[name]) ** 2)):6.3f}   "
              f"k_hat {k_hat:.3f}")

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15.8, 5.3),
                                        gridspec_kw={"width_ratios": [1.35, 1, 1],
                                                     "wspace": 0.32})
    styles = {"data only": (MUTED, "-"), "soft PDE penalty": (BLUE, "-"),
              "soft PDE + hard BC": (GREEN, "--"),
              "PDE penalty, source mis-specified": (CMU_RED, "--")}
    ax1.plot(x_test, y_test, color=INK, lw=3.2, alpha=0.30, label="true field")
    for name, pred in drawn.items():
        colour, ls = styles[name]
        ax1.plot(x_test, pred, color=colour, lw=2.0, ls=ls, label=name)
    ax1.plot(xd8, yd8, "o", color=CMU_RED, ms=8, mec="white", mew=1.2, zorder=6,
             label="8 noisy measurements")
    ax1.set_xlabel("$x$")
    ax1.set_ylabel("$T(x)$")
    ax1.set_title("Eight points, four ways", fontsize=13.5, pad=10)
    ax1.legend(frameon=False, fontsize=9.5, loc="upper left")
    ax1.grid(True, color=RULE, lw=0.7)
    ax1.set_axisbelow(True)

    for name in variants:
        colour, ls = styles[name]
        ax2.loglog(sizes, [np.mean(curves[name][n]) for n in sizes], "o-",
                   color=colour, ls=ls, lw=2.2, ms=6)
    ax2.set_xlabel("Measurements available")
    ax2.set_ylabel("RMSE against the true field")
    ax2.set_title("A wrong prior does not\nwash out", fontsize=13.5, pad=8)
    ax2.set_xticks(sizes)
    ax2.set_xticklabels([str(s) for s in sizes])
    ax2.grid(True, which="both", color=RULE, lw=0.6)
    ax2.set_axisbelow(True)

    for name in variants:
        if name == "data only":
            continue
        colour, ls = styles[name]
        ax3.semilogx(sizes, [np.nanmean(ks[name][n]) for n in sizes], "o-",
                     color=colour, ls=ls, lw=2.2, ms=6, label=name)
    ax3.axhline(K_TRUE, color=INK, lw=1.6, ls=":")
    ax3.text(sizes[0], K_TRUE * 1.04, f"true $k$ = {K_TRUE}", fontsize=10.5,
             color=INK)
    ax3.set_xlabel("Measurements available")
    ax3.set_ylabel("Recovered conductivity $\\hat{k}$")
    ax3.set_title("The penalty also identifies\na material property",
                  fontsize=13.5, pad=8)
    ax3.set_xticks(sizes)
    ax3.set_xticklabels([str(s) for s in sizes])
    ax3.grid(True, which="both", color=RULE, lw=0.6)
    ax3.set_axisbelow(True)

    fig.suptitle("Soft PDE residual penalties: what physics buys, and what it costs",
                 fontsize=15.5, y=1.02)
    fig.savefig(HERE / "soft-physics.png")
    plt.close(fig)
    print("wrote soft-physics.png")
    return {"curves": {k: {n: [float(x) for x in v] for n, v in d.items()}
                       for k, d in curves.items()},
            "k_hat": {k: {n: [float(x) for x in v] for n, v in d.items()}
                      for k, d in ks.items()},
            "bc_violation": {k: float(np.mean(v)) for k, v in bc_violation.items()},
            "sizes": sizes, "noise": noise, "peak": float(T_ref.max())}


# --------------------------------------------------------------------------
# Figure 6: is the uncertainty any good?
# --------------------------------------------------------------------------
def split_conformal(residuals_cal: np.ndarray, alpha: float = 0.05) -> float:
    """The (1-alpha) conformal quantile, with the finite-sample correction."""
    n = len(residuals_cal)
    level = min(np.ceil((n + 1) * (1 - alpha)) / n, 1.0)
    return float(np.quantile(residuals_cal, level, method="higher"))


def fig_calibration(df: pd.DataFrame, groups: np.ndarray) -> dict:
    print("\nfig_calibration")
    from scipy.stats import norm

    X = raw_features(df)
    y = df.spl_db.to_numpy()
    regimes = {}
    kf_tr, kf_te = next(iter(KFold(5, shuffle=True, random_state=SEED).split(X)))
    regimes["random rows"] = (kf_tr, kf_te)
    gk_tr, gk_te = grouped_split(groups)
    regimes["held-out configurations"] = (gk_tr, gk_te)
    fast = df.velocity_ms.to_numpy() == 71.3
    regimes["held-out velocity"] = (np.where(~fast)[0], np.where(fast)[0])

    nominal = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99])
    table, reliability = {}, {}

    for name, (tr, te) in regimes.items():
        scaler = StandardScaler().fit(X[tr])
        Xtr, Xte = scaler.transform(X[tr]), scaler.transform(X[te])
        row, rel = {}, {}

        gp = fit_gp(Xtr, y[tr])
        gmu, gsd = gp.predict(Xte, return_std=True)
        row["Gaussian process"] = interval_metrics(y[te], gmu, gsd)
        rel["Gaussian process"] = [float(np.mean(np.abs(y[te] - gmu)
                                                 <= norm.ppf(0.5 + p / 2) * gsd))
                                   for p in nominal]

        models, ym, ys = fit_ensemble(Xtr, y[tr])
        emu, esd, epi, ale = ensemble_predict(models, Xte, ym, ys)
        row["deep ensemble"] = interval_metrics(y[te], emu, esd)
        row["deep ensemble"]["epistemic"] = float(epi.mean())
        row["deep ensemble"]["aleatoric"] = float(ale.mean())
        rel["deep ensemble"] = [float(np.mean(np.abs(y[te] - emu)
                                              <= norm.ppf(0.5 + p / 2) * esd))
                                for p in nominal]

        drop_models, dym, dys = fit_ensemble(Xtr, y[tr], n_members=1, seed0=99,
                                             p_drop=0.1)
        net = drop_models[0].train()          # dropout stays on at prediction time
        xt = torch.tensor(Xte, dtype=torch.float32)
        with torch.no_grad():
            draws = np.array([net(xt)[0].numpy().ravel() for _ in range(50)])
        net.eval()
        with torch.no_grad():
            var = net(xt)[1].numpy().ravel()
        dmu = draws.mean(0) * dys + dym
        dsd = np.sqrt(draws.var(0) + var) * dys
        row["MC-dropout"] = interval_metrics(y[te], dmu, dsd)
        rel["MC-dropout"] = [float(np.mean(np.abs(y[te] - dmu)
                                           <= norm.ppf(0.5 + p / 2) * dsd))
                             for p in nominal]

        # Split conformal on top of the GP mean: a calibration set carved out of
        # the training rows at random, exactly as the recipe says.
        rng = np.random.default_rng(SEED)
        perm = rng.permutation(len(tr))
        n_cal = len(tr) // 4
        cal, sub = tr[perm[:n_cal]], tr[perm[n_cal:]]
        sc2 = StandardScaler().fit(X[sub])
        gp2 = fit_gp(sc2.transform(X[sub]), y[sub])
        res_cal = np.abs(y[cal] - gp2.predict(sc2.transform(X[cal])))
        mu2 = gp2.predict(sc2.transform(X[te]))
        row["split conformal"] = {
            "rmse": float(np.sqrt(np.mean((y[te] - mu2) ** 2))),
            "picp": float(np.mean(np.abs(y[te] - mu2)
                                  <= split_conformal(res_cal, 0.05))),
            "width": 2 * split_conformal(res_cal, 0.05), "nll": float("nan")}
        rel["split conformal"] = [
            float(np.mean(np.abs(y[te] - mu2) <= split_conformal(res_cal, 1 - p)))
            for p in nominal]

        lo = GradientBoostingRegressor(loss="quantile", alpha=0.025,
                                       random_state=SEED).fit(Xtr, y[tr]).predict(Xte)
        hi = GradientBoostingRegressor(loss="quantile", alpha=0.975,
                                       random_state=SEED).fit(Xtr, y[tr]).predict(Xte)
        row["quantile GBM"] = {
            "rmse": float("nan"),
            "picp": float(np.mean((y[te] >= lo) & (y[te] <= hi))),
            "width": float(np.mean(hi - lo)), "nll": float("nan")}

        table[name] = row
        reliability[name] = rel
        print(f"  {name} ({len(te)} test rows)")
        for method, m in row.items():
            print(f"    {method:20s} PICP95 {m['picp']:6.1%}  "
                  f"width {m['width']:6.2f} dB  RMSE {m['rmse']:6.2f}")

    # Aleatoric against epistemic, on a synthetic problem where the true noise
    # is known. It has to be synthetic: the airfoil file contains zero repeated
    # settings, so nothing in it can tell you how much of the scatter is noise.
    def truth(x):
        return np.sin(2 * x) + 0.3 * x ** 2

    sigma_bar = 0.15                       # the noise we put in, so we know it
    x_grid = np.linspace(-3, 3, 400)[:, None]
    decomposition = []
    for n in (16, 32, 64, 128, 256, 512, 1024):
        rng = np.random.default_rng(SEED)
        xs = rng.uniform(-3, 3, n)[:, None]
        ys = truth(xs.ravel()) + rng.normal(0, sigma_bar, n)
        model = fit_gp(xs, ys)
        _, total = model.predict(x_grid, return_std=True)
        noise = model.kernel_.k2.noise_level * np.var(ys)   # normalize_y=True
        epistemic = np.sqrt(np.maximum(total ** 2 - noise, 0.0))
        decomposition.append((n, float(epistemic.mean()), float(np.sqrt(noise))))
        print(f"  synthetic n={n:5d}  epistemic {epistemic.mean():.4f}   "
              f"aleatoric {np.sqrt(noise):.4f}   (true noise {sigma_bar:.3f})")

    # And the same split on the real data, where it is a statement about the
    # model rather than about the physics.
    tr, te = regimes["held-out configurations"]
    rng = np.random.default_rng(SEED)
    perm = rng.permutation(tr)
    for frac in (0.05, 0.2, 1.0):
        sub = perm[:max(30, int(frac * len(tr)))]
        scaler = StandardScaler().fit(X[sub])
        model = fit_gp(scaler.transform(X[sub]), y[sub])
        _, total = model.predict(scaler.transform(X[te]), return_std=True)
        noise = model.kernel_.k2.noise_level * np.var(y[sub])   # normalize_y=True
        epistemic = np.sqrt(np.maximum(total ** 2 - noise, 0.0))
        print(f"  airfoil GP, n_train {len(sub):5d}: epistemic "
              f"{epistemic.mean():.2f} dB, 'aleatoric' {np.sqrt(noise):.2f} dB")

    # The conformal guarantee is about the average over calibration/test draws,
    # not about one realisation. Fix the model, then resample the partition.
    tr, te = regimes["random rows"]
    pool = np.concatenate([tr[len(tr) // 2:], te])
    sub = tr[:len(tr) // 2]
    sc3 = StandardScaler().fit(X[sub])
    gp3 = fit_gp(sc3.transform(X[sub]), y[sub])
    residual_pool = np.abs(y[pool] - gp3.predict(sc3.transform(X[pool])))
    rng = np.random.default_rng(SEED)
    n_cal = len(pool) // 2
    coverages = []
    for _ in range(400):
        order = rng.permutation(len(pool))
        q = split_conformal(residual_pool[order[:n_cal]], 0.05)
        coverages.append(float(np.mean(residual_pool[order[n_cal:]] <= q)))
    conformal_mean = float(np.mean(coverages))
    print(f"  split conformal over 400 exchangeable calibration/test draws "
          f"(n_cal = {n_cal}): mean coverage {conformal_mean:.3%}, "
          f"guaranteed band 95.000% to {95 + 100 / (n_cal + 1):.3f}%")

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15.8, 5.2),
                                        gridspec_kw={"width_ratios": [1, 1.25, 1],
                                                     "wspace": 0.30})
    colours = {"Gaussian process": BLUE, "deep ensemble": CMU_RED,
               "MC-dropout": AMBER, "split conformal": GREEN}
    for method, colour in colours.items():
        ax1.plot(nominal, reliability["held-out configurations"][method], "o-",
                 color=colour, lw=2.0, ms=5, label=method)
    ax1.plot([0, 1], [0, 1], color=INK, lw=1.4, ls="--")
    ax1.text(0.70, 0.40, "perfect\ncalibration", fontsize=10.5, color=MUTED,
             ha="left")
    ax1.set_xlabel("Nominal coverage")
    ax1.set_ylabel("Empirical coverage")
    ax1.set_title("Reliability, held-out\nconfigurations", fontsize=13, pad=8)
    ax1.legend(frameon=False, fontsize=9.5, loc="upper left")
    ax1.grid(True, color=RULE, lw=0.7)
    ax1.set_axisbelow(True)
    ax1.set_xlim(0, 1.02)
    ax1.set_ylim(0, 1.02)

    methods = ["Gaussian process", "deep ensemble", "MC-dropout",
               "split conformal", "quantile GBM"]
    pos = np.arange(len(methods))
    width = 0.26
    for offset, (name, colour) in zip((-width, 0, width),
                                      zip(regimes, (GREEN, BLUE, CMU_RED))):
        vals = [table[name][m]["picp"] for m in methods]
        ax2.bar(pos + offset, vals, width, color=colour, label=name)
    ax2.axhline(0.95, color=INK, lw=1.6, ls="--")
    ax2.text(-0.45, 0.965, "nominal 95%", fontsize=10.5, color=INK, ha="left")
    ax2.set_xticks(pos)
    ax2.set_xticklabels([m.replace(" ", "\n") for m in methods], fontsize=9.5)
    ax2.set_ylabel("Coverage of the 95% interval")
    ax2.set_title("Nobody's guarantee survives\nleaving the training envelope",
                  fontsize=13, pad=8)
    ax2.legend(frameon=False, fontsize=9.5, loc="upper center", ncol=3,
               bbox_to_anchor=(0.5, 1.0), columnspacing=1.0, handlelength=1.2)
    ax2.grid(True, axis="y", color=RULE, lw=0.7)
    ax2.set_axisbelow(True)
    ax2.set_ylim(0, 1.38)

    n_sub = [d[0] for d in decomposition]
    ax3.loglog(n_sub, [d[1] for d in decomposition], "o-", color=PURPLE, lw=2.4,
               ms=7, label="epistemic (model ignorance)")
    ax3.loglog(n_sub, [d[2] for d in decomposition], "s-", color=TEAL, lw=2.4,
               ms=7, label="aleatoric (measurement noise)")
    ax3.axhline(sigma_bar, color=INK, ls=":", lw=1.6)
    ax3.text(n_sub[-1], sigma_bar * 1.18, "the noise actually there",
             fontsize=10, color=INK, ha="right")
    ax3.set_xlabel("Training points")
    ax3.set_ylabel("Mean predicted $\\sigma$")
    ax3.set_title("Only one of them is\nsomething data can fix", fontsize=13, pad=8)
    ax3.legend(frameon=False, fontsize=9.5, loc="lower left")
    ax3.grid(True, which="both", color=RULE, lw=0.6)
    ax3.set_axisbelow(True)

    fig.suptitle("An uncertainty you have not checked is a number, not a "
                 "measurement", fontsize=15.5, y=1.02)
    fig.savefig(HERE / "calibration.png")
    plt.close(fig)
    print("wrote calibration.png")
    return {"table": table, "reliability": reliability, "nominal": nominal.tolist(),
            "decomposition": decomposition, "conformal_mean": conformal_mean,
            "conformal_n_cal": n_cal, "true_sigma": sigma_bar}


# --------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"torch {torch.__version__} | numpy {np.__version__}")
    df, groups = load_airfoil()
    sizes = pd.Series(groups).value_counts()
    print(f"\nloaded {len(df)} rows in {sizes.size} wind-tunnel configurations; "
          f"median {int(sizes.median())} frequencies each")
    print(f"design levels: {df.freq_hz.nunique()} frequencies, "
          f"{df.aoa_deg.nunique()} angles, {df.chord_m.nunique()} chords, "
          f"{df.velocity_ms.nunique()} velocities; a full grid would be "
          f"{df.freq_hz.nunique() * df.aoa_deg.nunique() * df.chord_m.nunique() * df.velocity_ms.nunique():,} "
          f"runs and we have {len(df):,} ({len(df) / (df.freq_hz.nunique() * df.aoa_deg.nunique() * df.chord_m.nunique() * df.velocity_ms.nunique()):.1%})")
    thick = df.groupby(["aoa_deg", "chord_m", "velocity_ms"]).thickness_m.nunique()
    print(f"displacement thickness is determined by the other three in "
          f"{(thick == 1).sum()}/{len(thick)} configurations: "
          f"five columns, four knobs")

    print("\nbuilding the shared held-out design for the heat problem")
    t0 = time.perf_counter()
    test_design = scale_design(qmc.LatinHypercube(4, seed=999).random(300))
    test_y = heat_qoi(test_design)
    print(f"  300 reference solves in {time.perf_counter() - t0:.1f} s")

    economics = fig_economics(test_design, test_y)
    sampling = fig_sampling(test_design, test_y)
    surrogates = fig_gp_vs_ensemble(df, groups)
    physics = fig_physics(df, groups)
    soft = fig_soft_physics()
    calibration = fig_calibration(df, groups)

    print("\n--- numbers cited in notes.md and slides.md ---")
    print(f"solver {economics['solve_ms']:.0f} ms per evaluation, surrogate "
          f"{economics['predict_ms'] * 1e3:.0f} us: {economics['speedup']:,.0f}x, "
          f"break-even at {economics['break_even']:.0f} queries")
    for name in ("full grid", "uniform random", "Latin hypercube", "Sobol"):
        vals = ", ".join(f"n={n}: {np.mean(sampling['results'][name][n]):.3f}"
                         for n in sampling["budgets"])
        print(f"  {name:16s} {vals}")
    print(f"Strouhal collapse: {physics['freq_spread']:.2f} dB -> "
          f"{physics['st_spread']:.2f} dB, tighter in {physics['better']}/"
          f"{physics['n_settings']} settings; U^n exponent {physics['exponent']:.2f}")
    for name, row in physics["table"].items():
        print(f"  {name.replace(chr(10), ' '):40s} raw {row['raw']['rmse']:.2f} -> "
              f"physics {row['physics']['rmse']:.2f} dB")
    print(f"GP sigma grows {surrogates['growth']['gp']:.1f}x out of distribution, "
          f"ensemble {surrogates['growth']['ensemble']:.1f}x")
    for regime, row in calibration["table"].items():
        cov = ", ".join(f"{m} {row[m]['picp']:.0%}" for m in row)
        print(f"  {regime:26s} {cov}")
    n0, e0, a0 = calibration["decomposition"][0]
    n1, e1, a1 = calibration["decomposition"][-1]
    print(f"synthetic: epistemic {e0:.3f} -> {e1:.3f} from {n0} to {n1} points "
          f"({e0 / e1:.1f}x); aleatoric {a0:.3f} -> {a1:.3f} against a true "
          f"{calibration['true_sigma']:.3f}")
    print(f"conformal, averaged over 400 exchangeable draws: "
          f"{calibration['conformal_mean']:.2%} against a nominal 95%")
    for name, d in soft["curves"].items():
        vals = ", ".join(f"n={n}: {np.mean(v):.3f}" for n, v in d.items())
        print(f"  {name:28s} {vals}")
