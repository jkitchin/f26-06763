#!/usr/bin/env python3
"""Generate the L11 figures: autodiff, training pathologies, DL vs trees, devices.

Run with:
    uv run --with pandas,numpy,scikit-learn,matplotlib,torch,jax,optax,xlrd \
        python make_figures.py

Every number quoted in notes.md and slides.md is printed by this script. The
`xlrd` dependency is not an oversight: the canonical UCI concrete file is a
1997-vintage .xls that pandas cannot open without it, which is worth knowing
before you spend ten minutes on the traceback.

Four of these figures changed what the lecture says. So did measure_stories,
which found the scaler leak worth nothing measurable on this data (see below).

  1. The autodiff figure was drafted to show "autodiff agrees with the analytic
     gradient to machine precision." PyTorch did not: it disagreed at 7.5e-8
     while JAX agreed at 4.4e-16. The cause was not PyTorch. It was two Python
     floats (`torch.tensor(1.234)` and a bare `rng.normal()` scalar) silently
     becoming float32, at a relative error of 1.25e-7, which is exactly float32
     epsilon. Nothing warned, because float32 promotes to float64 on contact and
     every dtype downstream reads float64. That bug is now the point of the
     figure. Declaring both scalars float64 takes PyTorch to 1.7e-18.

  2. The DL-vs-trees figure was drafted expecting the module's stated result,
     that gradient boosting beats an MLP on small tabular data. On a random
     k-fold it does, by 0.43 +/- 0.09 MPa. Under a mix-grouped split the gap
     falls to 0.23 +/- 0.18 MPa, a tie. The tree's advantage here is substantially its
     greater ability to exploit a leaky split. A single-seed run of the same
     comparison showed the MLP *winning*; five seeds show a tie. Do not report
     single-seed deep-learning results.

  3. The pathology figure was drafted around the module's claim that
     unnormalized inputs cause NaNs. With SGD they do, immediately. With Adam
     they do not: it trains to 8.3 MPa instead of 5.5. Adam's per-parameter
     scaling hides a scaling bug as mediocrity rather than a crash, which is
     worse.

  4. The device figure was drafted expecting "GPU faster." For this model the
     accelerator is 2.5x *slower*, and it only wins past ~256 hidden units. The
     crossover, not the speedup, is the lesson.

Outputs (committed alongside this script):
    autodiff-vs-fd.png        exact gradients, the finite-difference V, and the dtype trap
    training-pathologies.png  zero_grad, learning rate, and input scaling
    dl-vs-trees.png           the honest tabular comparison, and what the leak was worth
    device-crossover.png      where an accelerator starts to pay for itself
    ad-graph.png              the notes' toy network as a computation graph, both passes
    pytorch-tape.png          the autograd graph PyTorch records, read off loss.grad_fn
    adam-paths.png            Adam against SGD, then beta1 and the learning rate
    adam-steps.png            per-parameter steps, beta2's memory, and where eps bites

Regenerate a subset with --only, e.g. `--only ad_graph tape adam jax_loop`. The
device timings are wall-clock on a shared laptop, so a full rerun moves numbers
the notes quote; do not rerun them just to redraw another figure.

The raw archive is cached in .cache/ and is gitignored; do not commit it.
"""

from __future__ import annotations

import io
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
          optimizer="adam", record=False, target_2d=True, info=None):
    """A hand-written training loop, deliberately breakable.

    `zero_grad=False`, `scale=False` and `target_2d=False` exist so the
    pathologies can be measured rather than asserted. Everything else is the
    loop the notes describe. Pass a dict as `info` to get back the spread of the
    validation predictions and the number of warnings the loop raised.
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
    y_t = torch.tensor((y_tr - y_mean) / y_std, device=dev)
    if target_2d:
        # (N, 1) to match the model's output. Leaving it (N,) is the shape bug:
        # MSELoss broadcasts (64, 1) against (64,) into a (64, 64) matrix of
        # every prediction minus every target, warns, and trains anyway.
        y_t = y_t[:, None]
    loader = DataLoader(TensorDataset(torch.tensor(X_tr, device=dev), y_t),
                        batch_size=batch, shuffle=True)
    xv = torch.tensor(X_va, device=dev)
    yv = torch.tensor(y_va, device=dev)[:, None]

    model = mlp(width, depth, X_tr.shape[1]).to(dev)
    opt = (torch.optim.Adam(model.parameters(), lr=lr) if optimizer == "adam"
           else torch.optim.SGD(model.parameters(), lr=lr))
    loss_fn = nn.MSELoss()
    history = []

    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
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
        pred = model(xv) * y_std + y_mean
        rmse = float(torch.sqrt(torch.mean((pred - yv) ** 2)))
    if info is not None:
        info["pred_std"] = float(pred.std())
        info["warnings"] = len(log)
        info["first_warning"] = str(log[0].message) if log else ""
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
    ax1.set_title("5 seeds x 5 folds, 1,030 tests of 428 mixes", pad=10)
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
             "Honest split: the gap is within two standard\n"
             "errors of zero. The two models tie.",
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


# --------------------------------------------------------------------------
# Figure 5: the computation graph, forward and backward
# --------------------------------------------------------------------------
def _box(ax, xy, text, face, edge, w=1.5, h=0.62, fontsize=12.5, color=INK):
    from matplotlib.patches import FancyBboxPatch
    x, y = xy
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=face, ec=edge, lw=1.6, zorder=3))
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=color,
            zorder=4)


def _arrow(ax, a, b, color, lw=1.8, rad=0.0, text=None, text_xy=None, fontsize=11.5,
           shrink=0.0):
    from matplotlib.patches import FancyArrowPatch
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16, lw=lw,
                                 color=color, connectionstyle=f"arc3,rad={rad}",
                                 shrinkA=shrink, shrinkB=shrink, zorder=2))
    if text:
        ax.text(*text_xy, text, ha="center", va="center", fontsize=fontsize,
                color=color, zorder=5,
                bbox=dict(fc="white", ec="none", pad=1.5, alpha=0.9))


def fig_ad_graph() -> None:
    """The one-hidden-layer example from the notes, drawn as a computation graph.

    Forward (blue) runs top to bottom and left to right and stores every
    intermediate. Backward (red) runs right to left along the same nodes. Each
    red edge carries its local derivative, and the label under each node is the
    gradient arriving there: the gradient from its right-hand neighbour times
    that edge's factor, which is the chain rule one step at a time. Every factor
    reuses a quantity the forward pass stored, which is the whole argument for
    reverse mode. Gradients are written dL/d(.) in full, not as adjoint bars.
    """
    fig, ax = plt.subplots(figsize=(14.0, 7.6))
    ax.set_xlim(-0.3, 13.3)
    ax.set_ylim(-4.25, 3.55)
    ax.axis("off")

    def d(s):
        return rf"\partial L/\partial {s}"

    ax.text(0.0, 3.25,
            r"Model: $\hat y = v \cdot \tanh(Wx + b) + c$, one sample $x$ with target $y$."
            r"     Loss: squared error $L = (\hat y - y)^2$, zero for a perfect prediction.",
            fontsize=12, color=INK, ha="left", va="center")

    PARAM_FACE, DATA_FACE, NODE_FACE, GRAD_FACE = "#e6f0e9", "#eeeeee", "#e8eef6", "#f8e4e7"
    chain = {"z": 1.6, "a": 4.1, "yhat": 6.6, "r": 9.1, "L": 11.6}
    labels = {"z": "$z = Wx + b$", "a": r"$a = \tanh z$",
              "yhat": r"$\hat y = v \cdot a + c$", "r": r"$r = \hat y - y$",
              "L": "$L = r^2$"}
    for k, x in chain.items():
        _box(ax, (x, 0), labels[k], NODE_FACE, BLUE, w=1.75)

    leaves = {"x": (0.5, 2.0, DATA_FACE, MUTED, "z"), "W": (1.6, 2.0, PARAM_FACE, GREEN, "z"),
              "b": (2.7, 2.0, PARAM_FACE, GREEN, "z"), "v": (6.0, 2.0, PARAM_FACE, GREEN, "yhat"),
              "c": (7.2, 2.0, PARAM_FACE, GREEN, "yhat"), "y": (9.1, 2.0, DATA_FACE, MUTED, "r")}
    for name, (x, y, face, edge, target) in leaves.items():
        _box(ax, (x, y), f"${name}$", face, edge, w=0.8, h=0.55)
        _arrow(ax, (x, y - 0.3), (chain[target] + 0.25 * (x - chain[target]) / 1.1, 0.33),
               BLUE, lw=1.4)
    ax.text(-0.1, 2.6, "data (no gradient)", fontsize=10.5, color=MUTED, ha="left")
    ax.text(6.6, 2.6, "parameters (green)", fontsize=10.5, color=GREEN, ha="center")

    order = list(chain)
    for a, b in zip(order, order[1:]):
        _arrow(ax, (chain[a] + 0.9, 0.12), (chain[b] - 0.9, 0.12), BLUE, lw=2.0)
    ax.text(4.35, 1.25, "forward: compute and\nstore each value", fontsize=11,
            color=BLUE, ha="center", va="center")

    # Local derivative of each forward step, written on the red edge it scales.
    local = {("L", "r"): "$\\times\\, 2r$", ("r", "yhat"): "$\\times\\, 1$",
             ("yhat", "a"): "$\\times\\, v$", ("a", "z"): "$\\times\\, (1 - a^2)$"}
    rev = order[::-1]
    for a, b in zip(rev, rev[1:]):
        _arrow(ax, (chain[a] - 0.9, -0.18), (chain[b] + 0.9, -0.18), CMU_RED, lw=2.0)
        ax.text((chain[a] + chain[b]) / 2, -0.52, local[(a, b)], ha="center", va="center",
                fontsize=11, color=CMU_RED,
                bbox=dict(fc="white", ec=CMU_RED, lw=0.8, boxstyle="round,pad=0.2"))

    grads = {"L": f"${d('L')} = 1$",
             "r": f"${d('r')} = 2r$",
             "yhat": rf"${d(chr(92) + 'hat y')} = {d('r')}$",
             "a": rf"${d('a')} = {d(chr(92) + 'hat y')} \cdot v$",
             "z": rf"${d('z')} = {d('a')} \odot (1 - a^2)$"}
    for k, x in chain.items():
        ax.text(x, -1.05, grads[k], ha="center", va="center", fontsize=12, color=CMU_RED)
    ax.text(11.6, -1.5, "start: $L$ changes one-for-one\nwith itself", fontsize=10,
            color=CMU_RED, ha="center", va="center")

    params = {"W": (1.0, "z", rf"${d('W')} = {d('z')} \cdot x^\top$"),
              "b": (3.1, "z", rf"${d('b')} = {d('z')}$"),
              "v": (5.9, "yhat", rf"${d('v')} = {d(chr(92) + 'hat y')} \cdot a$"),
              "c": (8.0, "yhat", rf"${d('c')} = {d(chr(92) + 'hat y')}$")}
    for name, (x, target, text) in params.items():
        _box(ax, (x, -2.6), text, GRAD_FACE, CMU_RED, w=2.0, h=0.62, fontsize=12)
        _arrow(ax, (chain[target], -1.35), (x, -2.25), CMU_RED, lw=1.4)
    ax.text(9.5, -2.6, "every parameter's gradient,\nfrom one backward pass",
            fontsize=11, color=CMU_RED, ha="left", va="center")

    ax.text(0.0, -3.55,
            "Backward (red), right to left: the gradient under each node is the one arriving from "
            "its right times the factor on the edge (the chain rule).",
            fontsize=10.5, color=MUTED, ha="left")
    ax.text(0.0, -3.95,
            r"$z$ and $a$ are vectors of hidden units, so $\odot$ is elementwise. Every factor "
            r"reuses a stored forward value ($a$, $v$, $x$, $r$), the memory reverse mode costs.",
            fontsize=10.5, color=MUTED, ha="left")

    fig.savefig(HERE / "ad-graph.png")
    plt.close(fig)
    print("wrote ad-graph.png")


# --------------------------------------------------------------------------
# Figure 6: the tape PyTorch records, read off the real autograd graph
# --------------------------------------------------------------------------
def fig_tape() -> dict:
    """Walk loss.grad_fn for the notes' toy network and draw what is really there.

    Nothing in this figure is hand-drawn from memory. The node names, the edges
    and the saved tensors all come from introspecting the graph PyTorch built,
    so if a future version changes them the figure changes with it. The same
    function prints the JAX program for the same loss, which the notes quote.
    """
    rng = np.random.default_rng(SEED)
    W = torch.tensor(rng.normal(size=(3, 4)), requires_grad=True)
    b = torch.tensor(rng.normal(size=3), requires_grad=True)
    v = torch.tensor(rng.normal(size=3), requires_grad=True)
    c = torch.tensor(rng.normal(), dtype=torch.float64, requires_grad=True)
    x = torch.tensor(rng.normal(size=4))
    y = torch.tensor(1.234, dtype=torch.float64)
    names = {id(W): "W", id(b): "b", id(v): "v", id(c): "c"}
    loss = (v @ torch.tanh(W @ x + b) + c - y) ** 2

    nodes, edges = [], []

    def saved(fn):
        out = []
        for attr in sorted(a for a in dir(fn) if a.startswith("_saved_")):
            val = getattr(fn, attr)
            if torch.is_tensor(val):
                out.append(f"{attr[7:]} {tuple(val.shape)}")
        return out

    def walk(fn, depth):
        label = type(fn).__name__
        if label == "AccumulateGrad":
            label = f"AccumulateGrad\n{names[id(fn.variable)]}.grad +="
        idx = len(nodes)
        nodes.append({"label": label, "depth": depth, "saved": saved(fn), "kids": []})
        for child, _ in fn.next_functions:
            if child is not None:
                k = walk(child, depth + 1)
                nodes[idx]["kids"].append(k)
                edges.append((idx, k))
        return idx

    walk(loss.grad_fn, 0)
    for n in nodes:
        print(f"  {'  ' * n['depth']}{n['label'].splitlines()[0]:<16s} saved: {n['saved']}")

    # A tidy tree layout: leaves take successive columns, parents centre over kids.
    col = [0]

    def place(i):
        kids = nodes[i]["kids"]
        if not kids:
            nodes[i]["x"] = col[0]
            col[0] += 1
        else:
            for k in kids:
                place(k)
            nodes[i]["x"] = np.mean([nodes[k]["x"] for k in kids])

    place(0)

    # Forward order is the order the ops ran in, i.e. the reverse of a
    # post-order walk from the loss. That is the "tape" in the literal sense.
    ops = [n for n in nodes if not n["label"].startswith("AccumulateGrad")]
    tape = sorted(ops, key=lambda n: -n["depth"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.5, 7.4),
                                   gridspec_kw={"width_ratios": [0.9, 1.25]})
    for ax in (ax1, ax2):
        ax.axis("off")

    # Left: the tape, in the order the forward pass wrote it.
    ax1.set_xlim(0, 10)
    ax1.set_ylim(-0.6, len(tape) + 1.2)
    ax1.set_title("1. Forward: each op appends a node\nand keeps what its backward needs",
                  fontsize=13.5, pad=6, loc="left")
    source = {"MvBackward0": "W @ x", "AddBackward0": "+", "TanhBackward0": "torch.tanh",
              "DotBackward0": "v @ a", "SubBackward0": "- y", "PowBackward0": "** 2"}
    add_seen = 0
    for i, n in enumerate(tape):
        yy = len(tape) - i
        op = n["label"]
        code = source.get(op, "")
        if op == "AddBackward0":
            code = "+ b" if add_seen == 0 else "+ c"
            add_seen += 1
        _box(ax1, (2.2, yy), op, "#e8eef6", BLUE, w=3.4, h=0.7, fontsize=11.5)
        ax1.text(0.05, yy, f"{i + 1}", ha="left", va="center", fontsize=11, color=MUTED)
        ax1.text(4.1, yy + 0.14, code, ha="left", va="center", fontsize=11,
                 family="monospace", color=INK)
        ax1.text(4.1, yy - 0.2, ("saves " + ", ".join(n["saved"])) if n["saved"]
                 else "saves no tensor", ha="left", va="center", fontsize=10,
                 color=CMU_RED if n["saved"] else MUTED)
    _arrow(ax1, (9.3, len(tape) + 0.3), (9.3, 0.8), BLUE, lw=2.0)
    ax1.text(9.55, len(tape) / 2 + 0.6, "time", rotation=-90, color=BLUE,
             fontsize=11, va="center")
    ax1.text(0.05, -0.35, "The saved tensors are why reverse mode costs memory\n"
             "in proportion to the depth of the graph.", fontsize=10.5, color=MUTED)

    # Right: the graph backward() walks, from the loss down to the leaves.
    depth = max(n["depth"] for n in nodes)
    xs = [n["x"] for n in nodes]
    span = max(xs) - min(xs)
    ax2.set_xlim(min(xs) - 0.9, max(xs) + 0.9)
    ax2.set_ylim(-depth - 1.5, 1.1)
    ax2.set_title("2. loss.backward(): walk the graph from the loss,\n"
                  "and add into every leaf's .grad", fontsize=13.5, pad=6, loc="left")
    for a, b_ in edges:
        _arrow(ax2, (nodes[a]["x"], -nodes[a]["depth"] - 0.3),
               (nodes[b_]["x"], -nodes[b_]["depth"] + 0.3), CMU_RED, lw=1.6)
    for n in nodes:
        leaf = n["label"].startswith("AccumulateGrad")
        _box(ax2, (n["x"], -n["depth"]), n["label"],
             "#e6f0e9" if leaf else "#f8e4e7", GREEN if leaf else CMU_RED,
             w=0.33 * span / 1.0 if leaf else 0.3 * span, h=0.66 if leaf else 0.5,
             fontsize=10.5)
    ax2.text(nodes[0]["x"] + 0.25 * span, 0.35, "loss.backward() starts here",
             fontsize=11, color=CMU_RED, ha="left")
    ax2.text(min(xs) - 0.8, -depth - 1.25,
             "x and y do not require a gradient, so they have no node: MvBackward0 saves\n"
             "only x, because W's gradient needs x and nothing needs x's gradient.",
             fontsize=10.5, color=MUTED, ha="left")

    fig.savefig(HERE / "pytorch-tape.png")
    plt.close(fig)
    print("wrote pytorch-tape.png")

    # The accumulate-not-assign semantics, measured on the same graph.
    loss.backward()
    first = W.grad.clone()
    ((v @ torch.tanh(W @ x + b) + c - y) ** 2).backward()
    ratio = float((W.grad / first).mean())
    print(f"  second backward() without zero_grad: W.grad is {ratio:.1f}x the first")

    # The same loss in JAX: there is no tape, there is a program.
    def jloss(p, x, y):
        return (p["v"] @ jnp.tanh(p["W"] @ x + p["b"]) + p["c"] - y) ** 2

    params = {"W": jnp.asarray(W.detach().numpy()), "b": jnp.asarray(b.detach().numpy()),
              "v": jnp.asarray(v.detach().numpy()), "c": jnp.asarray(c.detach().numpy())}
    fwd = jax.make_jaxpr(jloss)(params, jnp.asarray(x.numpy()), jnp.asarray(y.numpy()))
    bwd = jax.make_jaxpr(jax.grad(jloss))(params, jnp.asarray(x.numpy()),
                                          jnp.asarray(y.numpy()))
    print(f"  jaxpr of the loss: {len(fwd.jaxpr.eqns)} equations; "
          f"jaxpr of jax.grad(loss): {len(bwd.jaxpr.eqns)} equations")
    print(fwd)
    return {"nodes": len(nodes), "accumulate_ratio": ratio,
            "fwd_eqns": len(fwd.jaxpr.eqns), "grad_eqns": len(bwd.jaxpr.eqns)}


# --------------------------------------------------------------------------
# Figures 7 and 8: what Adam's four numbers do
# --------------------------------------------------------------------------
def adam_path(theta0, grad, lr, b1=0.9, b2=0.999, eps=1e-8, n=100):
    """Adam as Kingma and Ba wrote it, in NumPy, returning the path and each step.

    Checked against torch.optim.Adam and optax.adam in fig_adam(), because a
    figure explaining an optimizer with a subtly different optimizer would be
    worse than no figure.
    """
    theta = np.array(theta0, dtype=float)
    m, v = np.zeros_like(theta), np.zeros_like(theta)
    path, steps = [theta.copy()], []
    for t in range(1, n + 1):
        g = grad(theta)
        m = b1 * m + (1 - b1) * g
        v = b2 * v + (1 - b2) * g * g
        step = lr * (m / (1 - b1 ** t)) / (np.sqrt(v / (1 - b2 ** t)) + eps)
        theta = theta - step
        path.append(theta.copy())
        steps.append(step)
    return np.array(path), np.array(steps)


def sgd_path(theta0, grad, lr, momentum=0.0, n=100):
    """SGD with PyTorch's momentum convention (buf = mu * buf + g)."""
    theta = np.array(theta0, dtype=float)
    buf = np.zeros_like(theta)
    path = [theta.copy()]
    for t in range(n):
        g = grad(theta)
        buf = momentum * buf + g if t else g.copy()
        theta = theta - lr * buf
        path.append(theta.copy())
    return np.array(path)


def fig_adam() -> dict:
    """Adam on a badly scaled bowl, one hyperparameter at a time.

    The bowl is L = (theta1^2 + 40 theta2^2) / 2, so the gradient along theta2
    is 40 times steeper, which is the situation unscaled inputs create. Plain
    SGD must pick a step small enough for the steep direction and then crawls
    along the shallow one; Adam divides each coordinate by its own running RMS
    gradient and takes comparable steps in both.
    """
    curv = np.array([1.0, 40.0])
    grad = lambda th: curv * th                              # noqa: E731
    loss = lambda th: 0.5 * np.sum(curv * th ** 2)           # noqa: E731
    start = [-4.0, 1.5]

    # Check the NumPy Adam against both frameworks before drawing anything.
    ours, _ = adam_path(start, grad, 0.1, n=50)
    t = torch.tensor(start, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.Adam([t], lr=0.1)
    theirs = []
    for _ in range(50):
        opt.zero_grad()
        (0.5 * (torch.tensor(curv) * t ** 2).sum()).backward()
        opt.step()
        theirs.append(t.detach().numpy().copy())
    err_torch = float(np.abs(np.array(theirs) - ours[1:]).max())
    import optax
    tx = optax.adam(0.1)
    th = jnp.array(start)
    state = tx.init(th)
    theirs = []
    for _ in range(50):
        updates, state = tx.update(jnp.array(curv) * th, state)
        th = optax.apply_updates(th, updates)
        theirs.append(np.asarray(th))
    err_optax = float(np.abs(np.array(theirs) - ours[1:]).max())
    print(f"  NumPy Adam vs torch.optim.Adam: {err_torch:.1e}; vs optax.adam: {err_optax:.1e}")

    # A rotated copy of the same bowl: same eigenvalues, no longer axis aligned.
    rot = np.array([[1.0, -1.0], [1.0, 1.0]]) / np.sqrt(2)
    hess = rot @ np.diag(curv) @ rot.T
    aligned = loss(adam_path(start, grad, 0.1, n=100)[0][-1])
    end = adam_path(start, lambda th: hess @ th, 0.1, n=100)[0][-1]
    rotated = float(0.5 * end @ hess @ end)
    print(f"  Adam, 100 steps: loss {aligned:.1e} on the aligned bowl, {rotated:.1e} rotated 45 deg")

    g1 = np.linspace(-4.6, 1.3, 300)
    g2 = np.linspace(-1.3, 1.9, 300)
    G1, G2 = np.meshgrid(g1, g2)
    Z = 0.5 * (curv[0] * G1 ** 2 + curv[1] * G2 ** 2)
    levels = np.geomspace(0.02, 80, 12)

    def bowl(ax, title):
        ax.contour(G1, G2, Z, levels=levels, colors=RULE, linewidths=1.0)
        ax.plot(0, 0, "*", color=INK, ms=14, zorder=5)
        ax.plot(*start, "o", color=INK, ms=7, zorder=5)
        ax.set_xlim(g1[0], g1[-1])
        ax.set_ylim(g2[0], g2[-1])
        ax.set_xlabel(r"$\theta_1$ (shallow)")
        ax.set_ylabel(r"$\theta_2$ (40x steeper)")
        ax.set_title(title, pad=8)
        ax.set_aspect("equal")

    def trace(ax, path, colour, label, n=60):
        ax.plot(path[:n + 1, 0], path[:n + 1, 1], "-o", color=colour, lw=1.6, ms=2.8,
                label=label, alpha=0.95)

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.2))
    out = {"err_torch": err_torch, "err_optax": err_optax, "aligned": aligned,
           "rotated": rotated}

    ax = axes[0]
    bowl(ax, "SGD, momentum, and Adam: 60 steps")
    paths = {"SGD, lr 0.045": sgd_path(start, grad, 0.045),
             "SGD + momentum 0.9, lr 0.01": sgd_path(start, grad, 0.01, 0.9),
             "Adam, lr 0.1": adam_path(start, grad, 0.1)[0]}
    for (label, path), colour in zip(paths.items(), (MUTED, AMBER, BLUE)):
        trace(ax, path, colour, label)
        out[f"loss60 {label}"] = float(loss(path[60]))
    ax.legend(frameon=False, fontsize=10, loc="upper center", bbox_to_anchor=(0.5, -0.2))

    ax = axes[1]
    bowl(ax, r"Adam, $\beta_1$ (momentum)")
    for b1, colour in ((0.0, AMBER), (0.9, BLUE), (0.99, CMU_RED)):
        path = adam_path(start, grad, 0.1, b1=b1)[0]
        trace(ax, path, colour, rf"$\beta_1$ = {b1:g}")
        out[f"loss100 b1={b1}"] = float(loss(path[100]))
    ax.legend(frameon=False, fontsize=10, loc="upper center", bbox_to_anchor=(0.5, -0.2),
              ncol=3)

    ax = axes[2]
    for lr, colour in ((0.01, AMBER), (0.1, BLUE), (0.5, CMU_RED)):
        path = adam_path(start, grad, lr, n=300)[0]
        ax.semilogy(np.linalg.norm(path, axis=1), color=colour, lw=2.0,
                    label=f"lr = {lr:g}")
        out[f"dist300 lr={lr}"] = float(np.linalg.norm(path[-1]))
    ax.set_xlabel("Step")
    ax.set_ylabel(r"Distance to the minimum, $\|\theta\|$")
    ax.set_title("Adam, the learning rate", pad=8)
    ax.grid(True, which="both", color=RULE, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=10.5)
    ax.text(0.97, 0.62, "each step moves each\ncoordinate by about lr",
            transform=ax.transAxes, ha="right", va="top", fontsize=10.5, color=MUTED)

    fig.savefig(HERE / "adam-paths.png")
    plt.close(fig)
    print("wrote adam-paths.png")

    # ---- second figure: the step sizes, which is where beta2 and eps live ----
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 4.9))

    ax = axes[0]
    _, steps = adam_path(start, grad, 0.1, n=60)
    sgd = sgd_path(start, grad, 0.045, n=60)
    sgd_steps = np.abs(np.diff(sgd, axis=0))
    ax.semilogy(np.abs(steps[:, 0]), color=BLUE, lw=2.0, label=r"Adam, $\theta_1$")
    ax.semilogy(np.abs(steps[:, 1]), color=BLUE, lw=2.0, ls="--", label=r"Adam, $\theta_2$")
    ax.semilogy(sgd_steps[:, 0], color=MUTED, lw=2.0, label=r"SGD, $\theta_1$")
    ax.semilogy(sgd_steps[:, 1], color=MUTED, lw=2.0, ls="--", label=r"SGD, $\theta_2$")
    ax.axhline(0.1, color=BLUE, lw=1.0, ls=":")
    ax.text(59, 0.115, "lr", color=BLUE, fontsize=10.5, ha="right")
    ax.set_title("Per-parameter step size", pad=8)
    ax.set_xlabel("Step")
    ax.set_ylabel(r"$|\Delta\theta_i|$")
    ax.legend(frameon=False, fontsize=9.5, loc="lower left")
    first = (float(abs(steps[0, 0])), float(abs(steps[0, 1])))
    out["adam_first_step"] = first
    print(f"  first Adam step per coordinate {first}; first SGD step "
          f"{tuple(float(s) for s in sgd_steps[0])}")

    # beta2: the gradient falls 100-fold at step 200, as it does when training
    # leaves a steep region. v remembers the old, large gradients for about
    # 1/(1 - beta2) steps, so with the default the step collapses and recovers slowly.
    ax = axes[1]
    signal = np.where(np.arange(600) < 200, 1.0, 0.01)
    for b2, colour in ((0.9, AMBER), (0.99, GREEN), (0.999, BLUE)):
        counter = iter(range(10 ** 6))
        _, st = adam_path([0.0], lambda th: np.array([signal[next(counter)]]), 1.0,
                          b2=b2, n=600)
        ax.plot(np.abs(st[:, 0]), color=colour, lw=2.0,
                label=rf"$\beta_2$ = {b2:g} (~{1 / (1 - b2):.0f} steps)")
        out[f"b2={b2} step at 250"] = float(abs(st[250, 0]))
    ax.axvline(200, color=MUTED, lw=1.0, ls=":")
    ax.text(205, 1.02, "gradient drops 100x", fontsize=10, color=MUTED, va="bottom")
    ax.set_ylim(0, 1.18)
    ax.set_title(r"$\beta_2$, how long the scale is remembered", pad=8)
    ax.set_xlabel("Step")
    ax.set_ylabel("Step size / lr")
    ax.legend(frameon=False, fontsize=9.5, loc="center right", bbox_to_anchor=(1.0, 0.6))

    # eps: the first step, as a function of how large the gradient is.
    ax = axes[2]
    scales = np.geomspace(1e-12, 1e2, 200)
    for eps, colour in ((1e-8, BLUE), (1e-4, AMBER), (1e-1, CMU_RED)):
        first_steps = [abs(adam_path([0.0], lambda th, s=s: np.array([s]), 1e-3,
                                     eps=eps, n=1)[1][0, 0]) for s in scales]
        ax.loglog(scales, first_steps, color=colour, lw=2.0, label=rf"Adam, $\epsilon$ = {eps:g}")
    ax.loglog(scales, 1e-3 * scales, color=MUTED, lw=2.0, ls="--", label="SGD")
    ax.set_ylim(1e-9, 1e-1)
    ax.set_xlabel("Gradient magnitude")
    ax.set_ylabel("First step, lr = 1e-3")
    ax.set_title(r"$\epsilon$, where scale invariance stops", pad=8)
    ax.grid(True, which="both", color=RULE, lw=0.5)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9.5, loc="upper left")

    for ax in axes[:2]:
        ax.grid(True, color=RULE, lw=0.6)
        ax.set_axisbelow(True)
    fig.savefig(HERE / "adam-steps.png")
    plt.close(fig)
    print("wrote adam-steps.png")
    for k, val in out.items():
        print(f"  {k}: {val}")
    return out


# --------------------------------------------------------------------------
# The same MLP, trained in JAX with optax, on the same fold
# --------------------------------------------------------------------------
def measure_jax_loop(df: pd.DataFrame, groups: np.ndarray, epochs: int = 120) -> dict:
    """The concrete MLP written the JAX way, against the PyTorch loop above.

    Same fold, same architecture, same initialization distribution
    (PyTorch's nn.Linear default, U(-1/sqrt(fan_in), 1/sqrt(fan_in))), same
    Adam, same batch size, five seeds each. The two libraries draw different
    random numbers, so the runs are not identical; the question is whether they
    land in the same place.
    """
    import optax

    X = df[FEATURES].to_numpy(np.float32)
    y = df["strength_mpa"].to_numpy(np.float32)
    tr, va = next(iter(GroupKFold(5).split(X, y, groups)))
    scaler = StandardScaler().fit(X[tr])
    Xtr = jnp.asarray(scaler.transform(X[tr]), dtype=jnp.float32)
    Xva = jnp.asarray(scaler.transform(X[va]), dtype=jnp.float32)
    y_mean, y_std = float(y[tr].mean()), float(y[tr].std())
    ytr = jnp.asarray((y[tr] - y_mean) / y_std, dtype=jnp.float32)
    yva = jnp.asarray(y[va], dtype=jnp.float32)
    batch = 64

    def init(key, sizes=(8, 64, 64, 1)):
        params = []
        for d_in, d_out in zip(sizes[:-1], sizes[1:]):
            key, kw, kb = jax.random.split(key, 3)
            bound = 1.0 / np.sqrt(d_in)
            params.append({
                "W": jax.random.uniform(kw, (d_in, d_out), jnp.float32, -bound, bound),
                "b": jax.random.uniform(kb, (d_out,), jnp.float32, -bound, bound)})
        return params

    def predict(params, x):
        for layer in params[:-1]:
            x = jax.nn.relu(x @ layer["W"] + layer["b"])
        return (x @ params[-1]["W"] + params[-1]["b"])[..., 0]

    def mse(params, xb, yb):
        return jnp.mean((predict(params, xb) - yb) ** 2)

    tx = optax.adam(1e-3)

    @jax.jit
    def step(params, state, xb, yb):
        loss, grads = jax.value_and_grad(mse)(params, xb, yb)
        updates, state = tx.update(grads, state, params)
        return optax.apply_updates(params, updates), state, loss

    def rmse(params):
        return float(jnp.sqrt(jnp.mean((predict(params, Xva) * y_std + y_mean - yva) ** 2)))

    n = Xtr.shape[0]

    def run(seed):
        key = jax.random.PRNGKey(seed)
        key, sub = jax.random.split(key)
        params = init(sub)
        state = tx.init(params)
        for _ in range(epochs):
            key, sub = jax.random.split(key)
            perm = jax.random.permutation(sub, n)
            for i in range(0, n, batch):
                idx = perm[i:i + batch]
                params, state, _ = step(params, state, Xtr[idx], ytr[idx])
        return rmse(params)

    jax_rmse = [run(s) for s in range(5)]
    torch_rmse = [train(X[tr], y[tr], X[va], y[va], epochs=epochs, seed=s)[0]
                  for s in range(5)]
    print(f"  fold 0, {epochs} epochs, 5 seeds")
    print(f"    PyTorch loop   {np.mean(torch_rmse):.2f} +/- {np.std(torch_rmse):.2f} MPa "
          f"{np.round(torch_rmse, 2)}")
    print(f"    JAX + optax    {np.mean(jax_rmse):.2f} +/- {np.std(jax_rmse):.2f} MPa "
          f"{np.round(jax_rmse, 2)}")
    return {"torch": torch_rmse, "jax": jax_rmse}


# --------------------------------------------------------------------------
# The debugging stories: two bugs that look fine, measured
# --------------------------------------------------------------------------
def measure_stories(df: pd.DataFrame, groups: np.ndarray) -> dict:
    """The target-shape bug and the leaky scaler, on the pathology fold.

    The shape bug is one missing `[:, None]`. The loss still falls and the run
    finishes; the model has learned a constant. The leaky scaler is the bug the
    course warns about most, and it is measured here because on this dataset it
    costs almost nothing, which is itself a finding: the leak that inflates this
    score is the split (see fig_dl_vs_trees), not the scaler.
    """
    X = df[FEATURES].to_numpy(np.float32)
    y = df["strength_mpa"].to_numpy(np.float32)
    folds = list(GroupKFold(5).split(X, y, groups))
    tr, va = folds[0]
    out = {"baseline": float(np.sqrt(np.mean((y[va] - y[tr].mean()) ** 2)))}

    for flag, key in ((True, "shape_ok"), (False, "shape_bug")):
        info = {}
        rmse, _ = train(X[tr], y[tr], X[va], y[va], epochs=120,
                        target_2d=flag, info=info)
        out[key] = rmse
        out[key + "_pred_std"] = info["pred_std"]
        out[key + "_warnings"] = info["warnings"]
        print(f"  target {'(N, 1)' if flag else '(N,)  '} RMSE {rmse:6.2f} MPa, "
              f"prediction std {info['pred_std']:5.2f} MPa, "
              f"{info['warnings']} warnings")
        if info["first_warning"]:
            print(f"    first: {info['first_warning'][:110]}")
    print(f"  predict-the-training-mean baseline {out['baseline']:.2f} MPa, "
          f"validation std {y[va].std():.2f} MPa")

    # Scaler fitted on every row, then the same folds. Three seeds by five folds.
    X_all = StandardScaler().fit_transform(X).astype(np.float32)
    honest, leaky = [], []
    for seed in range(3):
        for tr, va in folds:
            honest.append(train(X[tr], y[tr], X[va], y[va], seed=seed, epochs=200)[0])
            leaky.append(train(X_all[tr], y[tr], X_all[va], y[va], seed=seed,
                               epochs=200, scale=False)[0])
    diff = np.array(leaky) - np.array(honest)
    out.update(scaler_honest=float(np.mean(honest)), scaler_leaky=float(np.mean(leaky)),
               scaler_diff=float(diff.mean()),
               scaler_se=float(diff.std(ddof=1) / np.sqrt(len(diff))))
    print(f"  scaler fitted on train {out['scaler_honest']:.2f}, on all rows "
          f"{out['scaler_leaky']:.2f} MPa, difference {out['scaler_diff']:+.2f} "
          f"+/- {out['scaler_se']:.2f} (n={len(diff)})")
    return out


if __name__ == "__main__":
    import argparse

    ALL = ["autodiff", "pathologies", "dl_vs_trees", "devices", "jax", "ad_graph",
           "tape", "adam", "jax_loop", "stories"]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="+", choices=ALL, default=ALL,
                        help="regenerate only these; the device timings are wall-clock "
                             "and will move, so do not rerun them to fix a typo")
    only = set(parser.parse_args().only)

    print(f"torch {torch.__version__} | jax {jax.__version__} "
          f"| backend {jax.default_backend()} | devices {DEVICES}")
    df, groups = load()
    n_mix = groups.max() + 1
    sizes = pd.Series(groups).value_counts()
    print(f"\nloaded {len(df)} rows, {n_mix} distinct mixes; "
          f"{(sizes > 1).sum()} mixes appear at more than one age, covering "
          f"{sizes[sizes > 1].sum()} rows ({sizes[sizes > 1].sum()/len(df):.0%})")
    print(f"exact duplicate rows: {df.duplicated().sum()}")

    for name, fn in (("ad_graph", fig_ad_graph), ("tape", fig_tape), ("adam", fig_adam)):
        if name in only:
            print(f"\nfig_{name}")
            fn()
    if "jax_loop" in only:
        print("\nmeasure_jax_loop")
        measure_jax_loop(df, groups)
    if "stories" in only:
        print("\nmeasure_stories")
        measure_stories(df, groups)
    if not only & {"autodiff", "pathologies", "dl_vs_trees", "devices", "jax"}:
        raise SystemExit(0)

    # The summary below quotes all five, so these run together or not at all.
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
