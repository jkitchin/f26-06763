#!/usr/bin/env python3
"""Generate the L11 figures: autodiff, training pathologies, DL vs trees, devices.

Run with:
    uv run --with pandas,numpy,scikit-learn,matplotlib,torch,jax,xlrd \
        python make_figures.py

Every number quoted in notes.md and slides.md is printed by this script. The
`xlrd` dependency is not an oversight: the canonical UCI concrete file is a
1997-vintage .xls that pandas cannot open without it, which is worth knowing
before you spend ten minutes on the traceback.

Four of these figures changed what the lecture says.

  1. The autodiff figure was drafted to show "autodiff agrees with the analytic
     gradient to machine precision." PyTorch did not: it disagreed at 5e-8 while
     JAX agreed at 3e-16. The cause was not PyTorch. It was two Python floats
     (`torch.tensor(1.234)` and a bare `rng.normal()` scalar) silently becoming
     float32, at a relative error of 1.25e-7, which is exactly float32 epsilon.
     Nothing warned, because float32 promotes to float64 on contact and every
     dtype downstream reads float64. That bug is now the point of the figure.

  2. The DL-vs-trees figure was drafted expecting the module's stated result,
     that gradient boosting beats an MLP on small tabular data. On a random
     k-fold it does, by 0.51 MPa. Under a mix-grouped split the gap collapses to
     0.13 +/- 0.18 MPa, a tie. The tree's advantage here is substantially its
     greater ability to exploit a leaky split. A single-seed run of the same
     comparison showed the MLP *winning*; five seeds show a tie. Do not report
     single-seed deep-learning results.

  3. The pathology figure was drafted around the module's claim that
     unnormalized inputs cause NaNs. With SGD they do, immediately. With Adam
     they do not: training merely degrades from 5.5 to ~9.5 MPa. Adam's
     per-parameter scaling hides a scaling bug as mediocrity rather than a crash,
     which is worse.

  4. The device figure was drafted expecting "GPU faster." For this model the
     accelerator is 7x *slower*, and it only wins past ~256 hidden units. The
     crossover, not the speedup, is the lesson.

Outputs (committed alongside this script):
    autodiff-vs-fd.png        exact gradients, the finite-difference V, and the dtype trap
    training-pathologies.png  zero_grad, learning rate, and input scaling
    dl-vs-trees.png           the honest tabular comparison, and what the leak was worth
    device-crossover.png      where an accelerator starts to pay for itself

The raw archive is cached in .cache/ and is gitignored; do not commit it.
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
import torch
from jax import config as jax_config

jax_config.update("jax_enable_x64", True)
import jax
import jax.numpy as jnp
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import GroupKFold, KFold
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
URL = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
SEED = 0

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
AMBER = "#b8860b"
PURPLE = "#6b3fa0"

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

COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES = COLUMNS[:8]
MIX = COLUMNS[:7]          # the seven mix components; age is the within-mix variable
DEVICES = ["cpu"] + (["mps"] if torch.backends.mps.is_available() else [])


def load() -> tuple[pd.DataFrame, np.ndarray]:
    """Fetch (once) the UCI concrete set and derive the mix-level group id."""
    CACHE.mkdir(exist_ok=True)
    local = CACHE / "Concrete_Data.xls"
    if not local.exists():
        print(f"downloading {URL}")
        with urllib.request.urlopen(URL) as response:
            archive = zipfile.ZipFile(io.BytesIO(response.read()))
        local.write_bytes(archive.read("Concrete_Data.xls"))
    df = pd.read_excel(local)
    df.columns = COLUMNS
    groups = df.groupby(MIX, sort=False).ngroup().to_numpy()
    return df, groups


def mlp(width: int = 64, depth: int = 2, d_in: int = 8) -> nn.Module:
    layers, d = [], d_in
    for _ in range(depth):
        layers += [nn.Linear(d, width), nn.ReLU()]
        d = width
    return nn.Sequential(*layers, nn.Linear(d, 1))


def train(X_tr, y_tr, X_va, y_va, *, width=64, depth=2, lr=1e-3, epochs=400,
          batch=64, zero_grad=True, scale=True, device="cpu", seed=SEED,
          optimizer="adam", record=False):
    """A hand-written training loop, deliberately breakable.

    `zero_grad=False` and `scale=False` exist so the pathologies can be measured
    rather than asserted. Everything else is the loop the notes describe.
    """
    torch.manual_seed(seed)
    if scale:
        scaler = StandardScaler().fit(X_tr)
        X_tr = scaler.transform(X_tr).astype(np.float32)
        X_va = scaler.transform(X_va).astype(np.float32)
    y_mean, y_std = y_tr.mean(), y_tr.std()

    dev = torch.device(device)
    # The same Dataset/DataLoader path the demo notebook uses, so the numbers in
    # these figures and the numbers a student sees in the notebook agree. An
    # earlier version indexed a permutation by hand and the two disagreed about
    # whether SGD at lr=1 produced NaN.
    loader = DataLoader(
        TensorDataset(torch.tensor(X_tr, device=dev),
                      torch.tensor((y_tr - y_mean) / y_std, device=dev)[:, None]),
        batch_size=batch, shuffle=True)
    xv = torch.tensor(X_va, device=dev)
    yv = torch.tensor(y_va, device=dev)[:, None]

    model = mlp(width, depth, X_tr.shape[1]).to(dev)
    opt = (torch.optim.Adam(model.parameters(), lr=lr) if optimizer == "adam"
           else torch.optim.SGD(model.parameters(), lr=lr))
    loss_fn = nn.MSELoss()
    history = []

    for _ in range(epochs):
        model.train()
        for xb, yb in loader:
            loss = loss_fn(model(xb), yb)
            if zero_grad:                       # the line everyone forgets once
                opt.zero_grad()
            loss.backward()
            opt.step()
        if record:
            model.eval()
            with torch.no_grad():
                history.append(float(torch.sqrt(torch.mean(
                    (model(xv) * y_std + y_mean - yv) ** 2))))
    model.eval()
    with torch.no_grad():
        rmse = float(torch.sqrt(torch.mean((model(xv) * y_std + y_mean - yv) ** 2)))
    return rmse, history


# --------------------------------------------------------------------------
# Figure 1: what a gradient costs, and the dtype that quietly ruins it
# --------------------------------------------------------------------------
def fig_autodiff() -> dict:
    """Analytic vs PyTorch vs JAX vs central differences, on one hidden layer.

    The model is small enough to differentiate by hand:
        z = W x + b,  a = tanh(z),  yhat = v . a + c,  L = (yhat - y)^2
    so there is a ground truth to compare against, which is the whole point.
    """
    rng = np.random.default_rng(SEED)
    d_in, hidden = 4, 3
    W = rng.normal(size=(hidden, d_in))
    b = rng.normal(size=hidden)
    v = rng.normal(size=hidden)
    c = np.float64(rng.normal())
    x = rng.normal(size=d_in)
    y = np.float64(1.234)

    def forward(W, b, v, c):
        return float((v @ np.tanh(W @ x + b) + c - y) ** 2)

    def analytic():
        a = np.tanh(W @ x + b)
        err = 2.0 * (v @ a + c - y)
        dz = (err * v) * (1.0 - a ** 2)
        return {"W": np.outer(dz, x), "b": dz, "v": err * a, "c": np.array(err)}

    reference = analytic()

    def torch_grad(careful: bool):
        """careful=False reproduces the bug this figure exists to show."""
        cast = (lambda t: torch.tensor(t, dtype=torch.float64)) if careful else torch.tensor
        tW = torch.tensor(W, requires_grad=True)
        tb = torch.tensor(b, requires_grad=True)
        tv = torch.tensor(v, requires_grad=True)
        # float(c) makes it a *Python* float, which torch.tensor stores as float32.
        tc = torch.tensor(c if careful else float(c), requires_grad=True)
        loss = (tv @ torch.tanh(tW @ cast(x) + tb) + tc
                - cast(y if careful else float(y))) ** 2
        loss.backward()
        return {"W": tW.grad.numpy(), "b": tb.grad.numpy(),
                "v": tv.grad.numpy(), "c": tc.grad.numpy()}

    def jax_grad():
        def loss(p):
            return (p["v"] @ jnp.tanh(p["W"] @ x + p["b"]) + p["c"] - y) ** 2
        g = jax.grad(loss)({"W": jnp.array(W), "b": jnp.array(b),
                            "v": jnp.array(v), "c": jnp.array(c)})
        return {k: np.asarray(val) for k, val in g.items()}

    def worst(g):
        return max(np.max(np.abs(g[k] - reference[k])) for k in reference)

    careful, careless, jaxg = torch_grad(True), torch_grad(False), jax_grad()
    err_careful, err_careless, err_jax = worst(careful), worst(careless), worst(jaxg)
    agree = max(np.max(np.abs(careful[k] - jaxg[k])) for k in reference)
    print(f"  torch, all float64      max|error| {err_careful:.3e}")
    print(f"  torch, two Python floats max|error| {err_careless:.3e}")
    print(f"  jax, x64 enabled        max|error| {err_jax:.3e}")
    print(f"  torch vs jax agree to {agree:.3e}; float64 eps {np.finfo(np.float64).eps:.3e}")

    steps = np.logspace(-1, -13, 40)
    target = reference["W"][0, 0]
    fd_err = []
    for h in steps:
        up, down = W.copy(), W.copy()
        up[0, 0] += h
        down[0, 0] -= h
        fd_err.append(abs((forward(up, b, v, c) - forward(down, b, v, c)) / (2 * h)
                          - target))
    fd_err = np.array(fd_err)
    best = int(fd_err.argmin())
    print(f"  best central difference {fd_err[best]:.3e} at h={steps[best]:.1e}")

    n_params = W.size + b.size + v.size + 1
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.6),
                                   gridspec_kw={"width_ratios": [1.15, 1]})

    ax1.loglog(steps, np.maximum(fd_err, 1e-20), "o-", color=MUTED, ms=4, lw=1.6,
               label="central finite difference")
    ax1.axhline(max(err_careful, 1e-18), color=BLUE, lw=2.4,
                label=f"PyTorch autograd, all float64 ({err_careful:.0e})")
    ax1.axhline(err_jax, color=GREEN, lw=2.4, ls="--",
                label=f"jax.grad, x64 enabled ({err_jax:.0e})")
    ax1.axhline(err_careless, color=CMU_RED, lw=2.4,
                label=f"PyTorch, two stray Python floats ({err_careless:.0e})")
    ax1.set_xlabel("finite-difference step $h$")
    ax1.set_ylabel(r"$|\hat{g} - g_{\mathrm{analytic}}|$")
    ax1.set_title("Autodiff is exact. Differencing is a compromise.", pad=10)
    ax1.invert_xaxis()
    ax1.legend(frameon=False, fontsize=9.5, loc="center left", bbox_to_anchor=(0.0, 0.42))
    ax1.grid(True, which="both", color=RULE, lw=0.6)
    ax1.set_axisbelow(True)
    ax1.text(0.14, 0.80, "truncation\nerror dominates", transform=ax1.transAxes,
             fontsize=10.5, color=MUTED, ha="center")
    ax1.text(0.86, 0.80, "round-off\nerror dominates", transform=ax1.transAxes,
             fontsize=10.5, color=MUTED, ha="center")

    params = np.logspace(1, 7, 50)
    ax2.loglog(params, 2 * params, color=MUTED, lw=2.4,
               label="finite differences: $2P$ forward passes")
    ax2.loglog(params, np.full_like(params, 2.0), color=BLUE, lw=2.4,
               label="backpropagation: 1 forward + 1 backward")
    ax2.axvline(n_params, color=CMU_RED, lw=1.2, ls=":")
    ax2.annotate(f"this toy model\n({n_params} parameters)", xy=(n_params, 3e5),
                 xytext=(n_params * 1.6, 3e5), fontsize=10.5, color=CMU_RED)
    ax2.axvline(4801, color=GREEN, lw=1.2, ls=":")
    ax2.annotate("the concrete MLP\n(4,801 parameters)", xy=(4801, 30),
                 xytext=(6200, 12), fontsize=10.5, color=GREEN)
    ax2.set_xlabel("Number of parameters $P$")
    ax2.set_ylabel("Model evaluations per gradient")
    ax2.set_title("And it is the only one that scales", pad=10)
    ax2.legend(frameon=False, fontsize=10.5, loc="upper left")
    ax2.grid(True, which="both", color=RULE, lw=0.6)
    ax2.set_axisbelow(True)

    fig.savefig(HERE / "autodiff-vs-fd.png")
    plt.close(fig)
    print("wrote autodiff-vs-fd.png")
    return {"torch": err_careful, "torch_careless": err_careless, "jax": err_jax,
            "agree": float(agree), "fd_best": float(fd_err[best]),
            "fd_best_h": float(steps[best]), "n_params": int(n_params)}


# --------------------------------------------------------------------------
# Figure 2: the three ways a first training loop dies
# --------------------------------------------------------------------------
def fig_pathologies(df: pd.DataFrame, groups: np.ndarray) -> dict:
    X = df[FEATURES].to_numpy(np.float32)
    y = df["strength_mpa"].to_numpy(np.float32)
    tr, va = next(iter(GroupKFold(5).split(X, y, groups)))
    args = dict(epochs=120, record=True)
    baseline = float(np.sqrt(np.mean((y[va] - y[tr].mean()) ** 2)))
    print(f"  fold-0 predict-the-training-mean baseline: {baseline:.3f} MPa")

    fig, axes = plt.subplots(1, 3, figsize=(15.0, 5.0))
    out = {}

    ax = axes[0]
    for flag, colour, label in ((True, BLUE, "opt.zero_grad() every step"),
                                (False, CMU_RED, "zero_grad() omitted")):
        rmse, hist = train(X[tr], y[tr], X[va], y[va], zero_grad=flag, **args)
        ax.plot(hist, color=colour, lw=2.0, label=label)
        out[f"zero_grad={flag}"] = rmse
        print(f"  zero_grad={str(flag):5s} final validation RMSE {rmse:8.3f} MPa")
    ax.axhline(baseline, color=MUTED, ls="--", lw=1.2)
    ax.text(0.02, baseline + 0.6, "predict the mean", transform=ax.get_yaxis_transform(),
            va="bottom", ha="left", fontsize=10, color=MUTED)
    ax.set_title("Gradients accumulate", pad=10)
    ax.set_ylim(0, 30)

    ax = axes[1]
    # 1.0 sits on the stability boundary: it produced NaN in 3 of 6 seed/loop
    # combinations tested, and diverged to ~100 MPa in the others. 2.0 blows up
    # every time, which is the reproducible version of the same lesson.
    lrs = [1e-3, 1e-2, 1e-1, 1.0, 2.0]
    dead = []
    for lr, colour in zip(lrs, [BLUE, GREEN, AMBER, PURPLE, CMU_RED]):
        rmse, hist = train(X[tr], y[tr], X[va], y[va], lr=lr, optimizer="sgd", **args)
        finite = np.isfinite(hist)
        if finite.any():
            offscale = np.nanmax(np.where(finite, hist, np.nan)) > 30
            ax.plot(np.where(finite, hist, np.nan), color=colour, lw=2.0,
                    label=f"lr = {lr:g}" + (" (off scale)" if offscale else ""))
        else:
            dead.append(lr)
        out[f"sgd_lr={lr}"] = rmse
        print(f"  SGD lr={lr:<6g} final {rmse:12.3f}   non-finite epochs "
              f"{int((~finite).sum()):3d}/{len(hist)}")
    if dead:
        ax.text(0.5, 0.03, "lr = " + ", ".join(f"{d:g}" for d in dead)
                + ": NaN from the first\nepoch. Nothing to plot.",
                transform=ax.transAxes, ha="center", fontsize=10.5,
                color=CMU_RED, fontweight="bold")
    else:
        ax.text(0.5, 0.62, "every rate here stayed finite\non this seed",
                transform=ax.transAxes, ha="center", fontsize=11,
                color=MUTED)
    ax.set_title("Learning rate, with plain SGD", pad=10)
    ax.set_ylim(0, 30)

    ax = axes[2]
    offscale = []
    for optimizer, colour in (("adam", BLUE), ("sgd", CMU_RED)):
        pretty = "Adam" if optimizer == "adam" else "SGD"
        for scale, style in ((True, "-"), (False, ":")):
            rmse, hist = train(X[tr], y[tr], X[va], y[va], optimizer=optimizer,
                               scale=scale, lr=1e-3, **args)
            hist = np.asarray(hist)
            visible = np.isfinite(hist) & (hist < 30)
            label = f"{pretty}, " + ("scaled" if scale else "raw inputs")
            if visible.any():
                ax.plot(np.where(np.isfinite(hist), hist, np.nan), color=colour,
                        lw=2.0, ls=style, label=label)
            else:
                offscale.append((label, rmse))
            out[f"{optimizer}_scale={scale}"] = rmse
            print(f"  {optimizer:4s} scale={str(scale):5s} final {rmse:12.3f}   "
                  f"non-finite {int((~np.isfinite(hist)).sum()):3d}/{len(hist)}")
    if offscale:
        ax.text(0.5, 0.03, "\n".join(
            f"{lab}:\n" + ("NaN inside the first epoch."
                           if not np.isfinite(val)
                           else f"diverged to {val:.1e} MPa, off scale.")
            for lab, val in offscale), transform=ax.transAxes, ha="center",
            fontsize=10.5, color=CMU_RED, fontweight="bold")
    ax.set_title("Unscaled inputs, two optimizers", pad=10)
    ax.set_ylim(0, 30)

    for ax, where in zip(axes, ("upper right", "center right", "upper right")):
        ax.set_xlabel("Epoch")
        ax.grid(True, color=RULE, lw=0.7)
        ax.set_axisbelow(True)
        ax.legend(frameon=False, fontsize=9.5, loc=where)
    axes[0].set_ylabel("Validation RMSE, MPa")

    fig.suptitle("Three ways a first training loop dies, measured on the same fold",
                 fontsize=15.5, y=1.02)
    fig.savefig(HERE / "training-pathologies.png")
    plt.close(fig)
    print("wrote training-pathologies.png")
    return out


# --------------------------------------------------------------------------
# Figure 3: does the net actually beat the tree?
# --------------------------------------------------------------------------
def fig_dl_vs_trees(df: pd.DataFrame, groups: np.ndarray) -> dict:
    """Five seeds x five folds, under an honest split and a leaky one.

    One seed is not enough. A single-seed version of this comparison showed the
    MLP beating gradient boosting under the grouped split; five seeds show a tie.
    """
    X = df[FEATURES].to_numpy(np.float32)
    y = df["strength_mpa"].to_numpy(np.float32)
    schemes = {
        "GroupKFold\nby mix (honest)": list(GroupKFold(5).split(X, y, groups)),
        "KFold\nrandom rows (leaky)": list(KFold(5, shuffle=True,
                                                 random_state=SEED).split(X)),
    }
    models = ["predict the mean", "random forest", "gradient boosting", "MLP (PyTorch)"]
    results = {s: {m: [] for m in models} for s in schemes}

    for scheme, folds in schemes.items():
        for seed in range(5):
            for tr, va in folds:
                def rmse(pred):
                    return float(np.sqrt(np.mean((y[va] - pred) ** 2)))
                results[scheme]["predict the mean"].append(
                    rmse(np.full(len(va), y[tr].mean())))
                results[scheme]["random forest"].append(rmse(
                    RandomForestRegressor(300, random_state=seed, n_jobs=-1)
                    .fit(X[tr], y[tr]).predict(X[va])))
                results[scheme]["gradient boosting"].append(rmse(
                    HistGradientBoostingRegressor(random_state=seed)
                    .fit(X[tr], y[tr]).predict(X[va])))
                results[scheme]["MLP (PyTorch)"].append(
                    train(X[tr], y[tr], X[va], y[va], seed=seed)[0])
        print(f"  {scheme.replace(chr(10), ' ')}")
        for m in models:
            a = np.array(results[scheme][m])
            print(f"    {m:20s} {a.mean():6.3f} +/- {a.std():.3f}  (n={len(a)})")

    # Repeatability of the 28-day crush test, from the duplicated settings.
    dup = df[df.duplicated(subset=FEATURES, keep=False)]
    diffs = [abs(g["strength_mpa"].iloc[0] - g["strength_mpa"].iloc[1])
             for _, g in dup.groupby(FEATURES)
             if len(g) == 2 and g["strength_mpa"].nunique() == 2]
    repeat = float(np.sqrt(np.mean(np.square(diffs)) / 2))
    print(f"  repeatability from {len(diffs)} duplicated settings: {repeat:.3f} MPa")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8),
                                   gridspec_kw={"width_ratios": [1.35, 1]})

    pos = np.arange(len(models))
    width = 0.36
    for offset, (scheme, colour) in zip((-width / 2, width / 2),
                                        zip(schemes, (BLUE, CMU_RED))):
        means = [np.mean(results[scheme][m]) for m in models]
        errs = [np.std(results[scheme][m]) for m in models]
        ax1.bar(pos + offset, means, width, yerr=errs, color=colour,
                label=scheme.replace("\n", " "),
                error_kw=dict(ecolor=INK, lw=1.1, capsize=3))
    ax1.axhspan(0, repeat, color=GREEN, alpha=0.16)
    ax1.axhline(repeat, color=GREEN, lw=1.8, ls="--",
                label=f"repeatability of the crush test itself ({repeat:.1f} MPa)")
    ax1.set_xticks(pos)
    ax1.set_xticklabels(models, fontsize=11)
    ax1.set_ylabel("CV RMSE, MPa")
    ax1.set_title("5 seeds x 5 folds on 1,030 concrete mixes", pad=10)
    ax1.legend(frameon=False, fontsize=11, loc="upper right")
    ax1.grid(True, axis="y", color=RULE, lw=0.7)
    ax1.set_axisbelow(True)

    gaps = {}
    for scheme in schemes:
        tree = np.array(results[scheme]["gradient boosting"])
        net = np.array(results[scheme]["MLP (PyTorch)"])
        d = net - tree
        gaps[scheme] = (d.mean(), d.std() / np.sqrt(len(d)))
    labels = list(gaps)
    values = [gaps[s][0] for s in labels]
    errors = [gaps[s][1] for s in labels]
    colours = [CMU_RED if abs(m) > 2 * e else MUTED for m, e in zip(values, errors)]
    ax2.bar(range(2), values, 0.5, yerr=errors, color=colours,
            error_kw=dict(ecolor=INK, lw=1.3, capsize=5))
    ax2.axhline(0, color=INK, lw=1.1)
    ax2.set_xticks(range(2))
    ax2.set_xticklabels([s.replace("\n", "\n") for s in labels], fontsize=11)
    ax2.set_ylabel("MLP RMSE minus tree RMSE, MPa\n(positive = the tree wins)")
    ax2.set_title("Is the tree really better?", pad=10)
    ax2.grid(True, axis="y", color=RULE, lw=0.7)
    ax2.set_axisbelow(True)
    for i, (m, e) in enumerate(zip(values, errors)):
        ax2.annotate(f"{m:+.2f} $\\pm$ {e:.2f}", xy=(i, m), xytext=(0, 16 if m > 0 else -26),
                     textcoords="offset points", ha="center", fontsize=11.5,
                     fontweight="bold", color=colours[i])
    ax2.set_ylim(0, max(v + e for v, e in zip(values, errors)) * 1.75)
    ax2.text(0.03, 0.97,
             "Honest split: the gap is smaller than its own\n"
             "standard error. The two models tie.",
             transform=ax2.transAxes, ha="left", va="top", fontsize=11,
             color=INK)

    fig.savefig(HERE / "dl-vs-trees.png")
    plt.close(fig)
    print(f"wrote dl-vs-trees.png  (gaps {gaps})")
    return {"results": {s: {m: [float(x) for x in v] for m, v in d.items()}
                        for s, d in results.items()},
            "gaps": {s: (float(a), float(b)) for s, (a, b) in gaps.items()},
            "repeatability": repeat, "n_pairs": len(diffs)}


# --------------------------------------------------------------------------
# Figure 4: when does the accelerator start paying for itself?
# --------------------------------------------------------------------------
def fig_devices(df: pd.DataFrame, groups: np.ndarray) -> dict:
    """Epoch time against model width, on a synthetic set big enough to be fair.

    Measured on Apple MPS, because that is the accelerator this machine has. A
    datacentre CUDA card has a much larger ceiling, but the *shape* is the same:
    a fixed cost per kernel launch that only amortises once there is enough
    arithmetic behind it.
    """
    def epoch_ms(width, depth, rows, d_in, batch, device, reps=7):
        """Minimum epoch time over `reps`, in ms.

        The minimum, not the mean: this is a shared laptop, and interference can
        only ever make a measurement slower. An earlier draft averaged, and the
        reported GPU crossover moved by a factor of three between runs depending
        on what else was executing.
        """
        dev = torch.device(device)
        torch.manual_seed(SEED)
        X = torch.randn(rows, d_in, device=dev)
        Y = torch.randn(rows, 1, device=dev)
        model = mlp(width, depth, d_in).to(dev)
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        loss_fn = nn.MSELoss()

        def one_epoch():
            for i in range(0, rows, batch):
                opt.zero_grad()
                loss_fn(model(X[i:i + batch]), Y[i:i + batch]).backward()
                opt.step()

        one_epoch()                       # warm up allocator and kernels
        if device == "mps":
            torch.mps.synchronize()
        best = float("inf")
        for _ in range(reps):
            start = time.perf_counter()
            one_epoch()
            if device == "mps":
                torch.mps.synchronize()
            best = min(best, time.perf_counter() - start)
        return best * 1e3

    widths = [(64, 8), (256, 8), (1024, 64), (2048, 256), (4096, 512)]
    timings = {d: [] for d in DEVICES}
    for width, d_in in widths:
        for d in DEVICES:
            timings[d].append(epoch_ms(width, 3, 8192, d_in, 1024, d))
        row = "  ".join(f"{d} {timings[d][-1]:9.2f} ms" for d in DEVICES)
        speed = (timings["cpu"][-1] / timings["mps"][-1]) if "mps" in DEVICES else float("nan")
        print(f"  width {width:5d} (d_in {d_in:4d}): {row}   speedup {speed:.2f}x")

    X = df[FEATURES].to_numpy(np.float32)
    y = df["strength_mpa"].to_numpy(np.float32)
    tr, va = next(iter(GroupKFold(5).split(X, y, groups)))
    real = {}
    for d in DEVICES:
        best = float("inf")
        for _ in range(5):
            start = time.perf_counter()
            train(X[tr], y[tr], X[va], y[va], epochs=10, device=d)
            if d == "mps":
                torch.mps.synchronize()
            best = min(best, (time.perf_counter() - start) / 10)
        real[d] = best * 1e3
        print(f"  the actual concrete MLP on {d}: {real[d]:.2f} ms/epoch")

    transfer = {}
    if "mps" in DEVICES:
        for n in (256, 1024, 4096):
            A = torch.randn(n, n)
            torch.mps.synchronize()
            dt = float("inf")
            for _ in range(20):
                start = time.perf_counter()
                _ = A.to("mps")
                torch.mps.synchronize()
                dt = min(dt, time.perf_counter() - start)
            transfer[n] = (dt * 1e3, A.numel() * 4 / 1e6 / dt / 1e3)
            print(f"  copy {n}x{n} ({A.numel()*4/1e6:.1f} MB) to mps: "
                  f"{dt*1e3:.3f} ms -> {A.numel()*4/1e6/dt/1e3:.2f} GB/s")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.0, 5.6))
    xs = [w for w, _ in widths]
    ax1.loglog(xs, timings["cpu"], "o-", color=BLUE, lw=2.2, ms=8, label="CPU")
    if "mps" in DEVICES:
        ax1.loglog(xs, timings["mps"], "s-", color=CMU_RED, lw=2.2, ms=8,
                   label="GPU (Apple MPS)")
    ax1.set_xlabel("Hidden units per layer")
    ax1.set_ylabel("Time per epoch, ms")
    ax1.set_title("8,192 rows, batch 1,024, three hidden layers", pad=10)
    ax1.legend(frameon=False, fontsize=11)
    ax1.grid(True, which="both", color=RULE, lw=0.6)
    ax1.set_axisbelow(True)

    if "mps" in DEVICES:
        ratio = np.array(timings["cpu"]) / np.array(timings["mps"])
        ax2.semilogx(xs, ratio, "o-", color=PURPLE, lw=2.4, ms=9)
        ax2.axhline(1.0, color=INK, lw=1.2)
        ax2.fill_between(xs, 0, 1, color=CMU_RED, alpha=0.10)
        ax2.fill_between(xs, 1, max(ratio) * 1.15, color=GREEN, alpha=0.10)
        ax2.text(0.015, 1.0, " parity", transform=ax2.get_yaxis_transform(),
                 va="bottom", ha="left", fontsize=10.5, color=MUTED)
        for xv, r in zip(xs, ratio):
            ax2.annotate(f"{r:.2f}x", xy=(xv, r), xytext=(0, -20),
                         textcoords="offset points", ha="center", fontsize=10.5,
                         color=PURPLE)
        ax2.set_ylim(0, max(ratio) * 1.65)
        ax2.set_xlabel("Hidden units per layer")
        ax2.set_ylabel("CPU time / GPU time\n(above 1, the accelerator is winning)")
        ax2.set_title("The crossover is the lesson, not the speedup", pad=10)
        ax2.grid(True, color=RULE, lw=0.7)
        ax2.set_axisbelow(True)
        if "mps" in real:
            ax2.text(0.03, 0.97,
                     f"This session's model (64 units, 1,030 rows) runs at\n"
                     f"{real['cpu']:.0f} ms/epoch on CPU and {real['mps']:.0f} ms/epoch "
                     f"on the GPU:\n{real['mps']/real['cpu']:.1f}x slower for moving "
                     "to the accelerator.",
                     transform=ax2.transAxes, va="top", fontsize=11, color=CMU_RED,
                     fontweight="bold")

    fig.suptitle("A GPU is a throughput device with a fixed cost per launch",
                 fontsize=15.5, y=1.0)
    fig.savefig(HERE / "device-crossover.png")
    plt.close(fig)
    print("wrote device-crossover.png")
    return {"widths": xs, "timings": timings, "real": real, "transfer": transfer}


def measure_jax() -> dict:
    """What jit and vmap actually buy, measured rather than assumed.

    An earlier draft reported a 3x jit speedup on a single 512x512 matmul. That
    number was measurement noise: timed properly, jit makes that workload very
    slightly *slower*, because there is nothing to fuse and the eager path was
    already one BLAS call. jit pays when it can collapse many small operations
    into one kernel and delete the per-operation dispatch overhead, which is the
    same argument that decides whether a GPU pays.
    """
    key = jax.random.PRNGKey(SEED)
    matrix = jax.random.normal(key, (512, 512))
    vector = jax.random.normal(key, (2_000_000,))

    def best_ms(fn, arg, reps=40):
        fn(arg).block_until_ready()
        best = float("inf")
        for _ in range(reps):
            start = time.perf_counter()
            fn(arg).block_until_ready()
            best = min(best, time.perf_counter() - start)
        return best * 1e3

    workloads = {
        "one big matmul": (lambda P: jnp.tanh(P @ P.T).sum(), matrix),
        "elementwise chain, 2M floats": (
            lambda x: (jnp.tanh(x) * jnp.exp(-x ** 2) + jnp.sin(x)
                       - jnp.sqrt(jnp.abs(x))).sum(), vector),
        "10-step iterative update": (
            lambda x: jax.lax.fori_loop(0, 10, lambda i, z: z - 0.01 * jnp.tanh(z),
                                        x).sum(), vector),
    }
    timings = {}
    for name, (fn, arg) in workloads.items():
        eager, compiled = best_ms(fn, arg), best_ms(jax.jit(fn), arg)
        timings[name] = (eager, compiled)
        print(f"  {name:30s} eager {eager:7.2f} ms   jit {compiled:7.2f} ms   "
              f"{eager / compiled:5.1f}x")

    # vmap: write the single-example function, get the batched one for free.
    def predict_one(params, x):
        return params["v"] @ jnp.tanh(params["W"] @ x + params["b"]) + params["c"]

    p = {"W": jax.random.normal(key, (16, 8)), "b": jnp.zeros(16),
         "v": jax.random.normal(key, (16,)), "c": jnp.array(0.0)}
    batch = jax.random.normal(key, (256, 8))
    batched = jax.vmap(predict_one, in_axes=(None, 0))(p, batch)
    manual = jnp.stack([predict_one(p, row) for row in batch])
    agreement = float(jnp.max(jnp.abs(batched - manual)))
    print(f"  vmap output shape {tuple(batched.shape)}, "
          f"max |vmap - python loop| = {agreement:.2e}")
    return {"timings": timings, "vmap_agreement": agreement}


if __name__ == "__main__":
    print(f"torch {torch.__version__} | jax {jax.__version__} "
          f"| backend {jax.default_backend()} | devices {DEVICES}")
    df, groups = load()
    n_mix = groups.max() + 1
    sizes = pd.Series(groups).value_counts()
    print(f"\nloaded {len(df)} rows, {n_mix} distinct mixes; "
          f"{(sizes > 1).sum()} mixes appear at more than one age, covering "
          f"{sizes[sizes > 1].sum()} rows ({sizes[sizes > 1].sum()/len(df):.0%})")
    print(f"exact duplicate rows: {df.duplicated().sum()}")

    print("\nfig_autodiff")
    autodiff = fig_autodiff()

    print("\nfig_pathologies")
    pathologies = fig_pathologies(df, groups)

    print("\nfig_dl_vs_trees")
    comparison = fig_dl_vs_trees(df, groups)

    print("\nfig_devices")
    devices = fig_devices(df, groups)

    print("\nmeasure_jax")
    jax_numbers = measure_jax()

    print("\n--- numbers cited in notes.md and slides.md ---")
    print(f"dataset: {len(df)} rows, {n_mix} mixes, "
          f"{sizes[sizes > 1].sum()/len(df):.0%} of rows in a multi-age mix, "
          f"{df.duplicated().sum()} exact duplicate rows")
    print(f"autodiff: torch {autodiff['torch']:.1e}, jax {autodiff['jax']:.1e}, "
          f"agree to {autodiff['agree']:.1e}; two stray Python floats cost "
          f"{autodiff['torch_careless']:.1e}")
    print(f"best finite difference {autodiff['fd_best']:.1e} at h={autodiff['fd_best_h']:.0e}")
    for scheme, (m, e) in comparison["gaps"].items():
        verdict = "significant" if abs(m) > 2 * e else "a tie"
        print(f"  {scheme.replace(chr(10), ' '):34s} MLP - tree = {m:+.3f} +/- {e:.3f} "
              f"({verdict})")
    print(f"repeatability of the crush test: {comparison['repeatability']:.2f} MPa "
          f"from {comparison['n_pairs']} duplicated settings")
    for k, val in pathologies.items():
        print(f"  {k:22s} {val:12.3f} MPa")
    if "mps" in devices["real"]:
        print(f"concrete MLP: {devices['real']['cpu']:.1f} ms/epoch CPU vs "
              f"{devices['real']['mps']:.1f} ms/epoch GPU")
    for name, (eager, compiled) in jax_numbers["timings"].items():
        print(f"jax jit, {name:30s} {eager:7.2f} -> {compiled:7.2f} ms "
              f"({eager / compiled:.1f}x)")
