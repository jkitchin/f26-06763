#!/usr/bin/env python3
"""Generate the L13 figures and the data behind its interactive figures, and print every
number the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with sindae --with scipy --with matplotlib \
        --with optax --with diffrax --with python-pptx python make_figures.py

Name groups to regenerate only those; with no names, every group runs. The groups, and
what each writes:
    pinn        spring-data.png, pinn-vs-nn.png, and the "pinn" entry of the widget data: a plain network
                and a physics-informed network (PINN) trained with Adam in JAX on ten
                points of a damped spring-mass, with both predictions recorded at 40
                training steps.
    seqsim      seq-vs-sim.png, and the "seqsim" entry: the same oscillator's damping and
                stiffness estimated from noisy data twice from one poor starting guess,
                once by single shooting (simulate, then BFGS on the two parameters) and
                once by the simultaneous approach (trapezoidal collocation, every state a
                variable, solved by the POUNCE interior-point solver). Every iterate of
                both is recorded.
    fedbatch    fedbatch-data.png, fedbatch-mu.png, fedbatch-models.png, fedbatch-inference.png,
                sindae-stages.png, and the "fedbatch" entry: the fed-batch bioreactor of the
                SiNDAE example (three noisy batches over 40 h, product balance diluted by
                F / V) learned three ways: a purely data-driven neural ODE, the hybrid neural
                ODE trained sequentially with Diffrax and Optax (neural_ode() is the code on
                the slides), and a neural DAE trained with SiNDAE's example settings (its
                smoother and pretraining stages drawn); then a new batch, 60 h, predicted by
                all three. About 3 minutes.
    projection  projection-train.png, and the "proj" entry: a network with and without a
                projection layer onto a splitter's mass balance, trained with Adam on 40
                noisy samples, recorded at 44 epochs.
    pictures    collocation.png, pinn-mini.png, loop-*.png and seq-loop.png (the sequential
                loop), final-seq.png and final-sim.png, disc-1.png to disc-5.png (from one
                simulated curve to a discretized NLP), collocation-poly.png
                (Lagrange polynomials on finite elements). Drawn from the cached pinn and seqsim
                results; run those first.
    examples    ex-pendulum.png, ex-heat.png, ex-cstr.png, ex-tank.png and sciml-examples.png:
                four mechanistic models, each with one closure term.
    vectorfield resnet-vs-ode.png: fixed residual steps against a vector field, after Fig. 1
                of Chen et al. (2018).
    diagrams    projection.png (a projection layer onto a mass balance), splitter.png (the
                splitter the projection-layer example models).
    schematics  tank-manifold.png (Fig. 1 of Lueg et al. 2026, CC BY 4.0, redrawn at a readable
                size), spring-mass.png (the PINN example), card-neural-ode.png (the deck's
                neural ODE card), and, from Victor Alves's decks (shared with his permission):
                fedbatch-reactor.png (his bioreactor drawing, cmu-seminar slide 35, relabeled
                with this lecture's states), sciml-spectrum.png and nn-glyph.png (his
                first-principles, hybrid and data-driven schematic, CAPD 2026 slide 12 and
                cmu-seminar slide 7, redrawn with his network drawing), gen0.png and gen1.png
                (cmu-seminar slides 5 and 8), and logo-*.png (CAPD 2026 slide 20). The decks
                are in attic/, not in the repository.
    mab         mab-multiscale.png: a picture from Victor Alves's CAPD 2026 overview (slide
                15), shared with his permission. Needs
                attic/Victor-Alves-CAPD-Overview-2026.pptx, which is not in the repository.
    cho         cho-pathway.png, cho-trajectories.png, cho-composition.png, from Victor
                Alves's CHO glycosylation slides (attic/cho_glycan_slides.pdf, synthetic data,
                shared with his permission), and cho-network.png, Fig. 5 of Wang, Harcum and
                Xie (arXiv 2412.03883, CC BY 4.0), downloaded to .cache/. Needs poppler's
                pdftoppm and pdfimages.

sindae-logo.png is copied unchanged from the SiNDAE repository (docs/images/SiNDAE_logo.png).

Every group that feeds an interactive figure caches its result in .cache/, and the widget
data file _static/l13-widget-data.js is rewritten from whatever the cache holds at the end
of each run. pinn takes about 15 s, seqsim about 5 s, fedbatch about 3 min, projection about
10 s.

The fed-batch model writes the product balance as dP/dt = Ypx mu X - F P / V, Eq. (30b) of
the paper. SiNDAE 1.0.2's built-in FedBatchBioreactorProblem writes F P / X instead, so this
script defines its own problem rather than importing that one.
"""
import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
CACHE = HERE / ".cache"
WIDGET_JS = REPO / "_static" / "l13-widget-data.js"
SEED = 0

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
ORANGE = "#c2410c"
GOLD = "#b07d12"
GREEN = "#2e7d32"
GRAY = "#8a8a8a"
PURPLE = "#6a3d9a"

STYLE = {
    "font.size": 14, "axes.labelsize": 14, "axes.titlesize": 15,
    "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 13,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "savefig.dpi": 150, "savefig.bbox": "tight",
}


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def cache_put(name, obj):
    CACHE.mkdir(exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps(obj))


def r(a, nd=4):
    """Round an array to a short list for the widget data."""
    return [round(float(v), nd) for v in np.asarray(a).ravel()]


# --------------------------------------------------------------------------------------
# The damped spring-mass, shared by pinn and seqsim
#     m x'' + mu x' + k x = 0,  x(0) = 1, x'(0) = 0
# --------------------------------------------------------------------------------------
def oscillator(t, m, mu, k):
    """Exact solution of the underdamped spring-mass released from x = 1 at rest."""
    d = mu / (2 * m)
    w = np.sqrt(k / m - d**2)
    return np.exp(-d * t) * (np.cos(w * t) + d / w * np.sin(w * t))


# --------------------------------------------------------------------------------------
# pinn
# --------------------------------------------------------------------------------------
def group_pinn():
    import jax
    import jax.numpy as jnp
    import optax

    jax.config.update("jax_enable_x64", True)
    m, mu, k = 1.0, 4.0, 400.0
    t_data = np.linspace(0, 0.36, 10)
    x_data = oscillator(t_data, m, mu, k)
    t_phys = np.linspace(0, 1, 40)            # collocation points for the physics loss
    t_plot = np.linspace(0, 1, 151)
    x_true = oscillator(t_plot, m, mu, k)
    lam = 1e-4                               # weight on the physics loss
    steps = 30000
    snap = sorted(set([0] + [int(s) for s in np.round(np.geomspace(10, steps, 39))]))

    def init(key, sizes):
        params = []
        for a, b in zip(sizes[:-1], sizes[1:]):
            key, sub = jax.random.split(key)
            params.append((jax.random.normal(sub, (a, b)) * np.sqrt(1 / a), jnp.zeros(b)))
        return params

    def net(params, t):
        h = t[:, None]
        for W, b in params[:-1]:
            h = jnp.tanh(h @ W + b)
        W, b = params[-1]
        return (h @ W + b)[:, 0]

    def x_at(params, t):
        return net(params, jnp.array([t]))[0]

    dx = jax.grad(x_at, argnums=1)
    ddx = jax.grad(dx, argnums=1)

    def residual(params, ts):
        x = jax.vmap(lambda t: x_at(params, t))(ts)
        v = jax.vmap(lambda t: dx(params, t))(ts)
        a = jax.vmap(lambda t: ddx(params, t))(ts)
        return m * a + mu * v + k * x

    def data_loss(p):
        return jnp.mean((net(p, jnp.array(t_data)) - x_data) ** 2)

    def phys_loss(p):
        return jnp.mean(residual(p, jnp.array(t_phys)) ** 2)

    def pinn_loss(p):
        return data_loss(p) + lam * phys_loss(p)

    def train(lossf):
        p = init(jax.random.PRNGKey(SEED), [1, 32, 32, 32, 1])
        opt = optax.adam(1e-3)
        state = opt.init(p)

        @jax.jit
        def step(p, state):
            g = jax.grad(lossf)(p)
            u, state = opt.update(g, state, p)
            return optax.apply_updates(p, u), state

        frames = []
        for i in range(steps + 1):
            if i in snap:
                frames.append(dict(
                    step=i, x=np.asarray(net(p, jnp.array(t_plot))),
                    data=float(data_loss(p)), phys=float(phys_loss(p))))
            if i < steps:
                p, state = step(p, state)
        return p, frames

    t0 = time.time()
    p_nn, f_nn = train(data_loss)
    p_pinn, f_pinn = train(pinn_loss)
    print(f"  trained both networks in {time.time() - t0:.1f} s")

    ext = t_plot > t_data[-1]
    rows = []
    for a, b in zip(f_nn, f_pinn):
        rows.append(dict(
            step=a["step"], nn=r(a["x"], 2), pinn=r(b["x"], 2),
            nn_rmse=float(np.sqrt(np.mean((a["x"] - x_true) ** 2))),
            pinn_rmse=float(np.sqrt(np.mean((b["x"] - x_true) ** 2))),
            nn_phys=np.sqrt(a["phys"]), pinn_phys=np.sqrt(b["phys"])))
    final_nn, final_pinn = f_nn[-1]["x"], f_pinn[-1]["x"]
    ext_nn = np.sqrt(np.mean((final_nn[ext] - x_true[ext]) ** 2))
    ext_pinn = np.sqrt(np.mean((final_pinn[ext] - x_true[ext]) ** 2))
    in_nn = np.sqrt(np.mean((final_nn[~ext] - x_true[~ext]) ** 2))
    in_pinn = np.sqrt(np.mean((final_pinn[~ext] - x_true[~ext]) ** 2))
    res_pinn = float(jnp.sqrt(jnp.mean(residual(p_pinn, jnp.array(t_plot)) ** 2)))
    res_nn = float(jnp.sqrt(jnp.mean(residual(p_nn, jnp.array(t_plot)) ** 2)))
    print(f"  after {steps} Adam steps (learning rate 1e-3, 3 x 32 tanh, lambda = {lam}):")
    print(f"    RMSE inside the data window   NN {in_nn:.4f}   PINN {in_pinn:.4f}")
    print(f"    RMSE beyond the data (t > {t_data[-1]})  NN {ext_nn:.3f}   PINN {ext_pinn:.4f}")
    print(f"    physics residual RMS on [0,1]  NN {res_nn:.1f}   PINN {res_pinn:.2f}"
          f"  (scale of k*x: {k:.0f})")
    print(f"    PINN residual RMS at its {t_phys.size} collocation points: "
          f"{rows[-1]['pinn_phys']:.2f}")
    for row in rows:
        if row["step"] in (0, 1000, 3000, 10000, 30000) or row["step"] == snap[-1]:
            print(f"    step {row['step']:>6}: whole-window RMSE NN {row['nn_rmse']:.3f}"
                  f"  PINN {row['pinn_rmse']:.3f}")

    cache_put("pinn", dict(
        system=dict(m=m, mu=mu, k=k), lam=lam, t=r(t_plot), exact=r(x_true, 3),
        t_data=r(t_data), x_data=r(x_data, 3), t_phys=r(t_phys),
        frames=[dict(step=w["step"], nn=w["nn"], pinn=w["pinn"],
                     nn_rmse=round(w["nn_rmse"], 4), pinn_rmse=round(w["pinn_rmse"], 4),
                     pinn_phys=round(float(w["pinn_phys"]), 2)) for w in rows],
        summary=dict(ext_nn=round(ext_nn, 3), ext_pinn=round(ext_pinn, 4),
                     res_pinn=round(res_pinn, 2), res_nn=round(res_nn, 1))))

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(11, 4.4))
        ax.axvspan(0, t_data[-1], color=GRAY, alpha=0.12, lw=0)
        ax.text(t_data[-1] / 2, 1.18, "training data", ha="center", color=MUTED)
        ax.text(0.68, 1.18, "no data: extrapolation", ha="center", color=MUTED)
        ax.plot(t_plot, x_true, color=GRAY, lw=5, alpha=0.5, label="exact solution")
        ax.plot(t_plot, final_nn, color=ORANGE, lw=2.4, label="plain network")
        ax.plot(t_plot, final_pinn, color=BLUE, lw=2.4, ls="--", label="PINN")
        ax.plot(t_data, x_data, "o", color=INK, ms=7, label="data (10 points)")
        ax.set_xlabel("time $t$ (s)")
        ax.set_ylabel("displacement $x$ (m)")
        ax.set_ylim(-1.05, 1.32)
        ax.legend(loc="lower right", ncol=4, bbox_to_anchor=(1.0, -0.42))
        ax.annotate(f"plain network: RMSE {ext_nn:.2f} m", xy=(0.62, final_nn[93]),
                    xytext=(0.62, -0.78), color=ORANGE, ha="center",
                    arrowprops=dict(arrowstyle="->", color=ORANGE))
        ax.annotate(f"PINN: RMSE {ext_pinn:.3f} m", xy=(0.85, final_pinn[128]),
                    xytext=(0.86, 0.62), color=BLUE, ha="center",
                    arrowprops=dict(arrowstyle="->", color=BLUE))
        save(fig, "pinn-vs-nn.png")

        # The example alone, before any model: the question the PINN answers.
        fig, ax = plt.subplots(figsize=(7.4, 4.6))
        ax.axvspan(0, t_data[-1], color=GRAY, alpha=0.12, lw=0)
        ax.text(t_data[-1] / 2, 1.18, "data", ha="center", color=MUTED)
        ax.plot(t_plot, x_true, color=GRAY, lw=4, alpha=0.6, label="exact solution")
        ax.plot(t_data, x_data, "o", color=INK, ms=7, label="10 measurements")
        ax.text(1.0, 0.45, "?", fontsize=40, color=CMU_RED, ha="center", weight="bold")
        ax.annotate("where is the mass\nat t = 1 s?", xy=(0.97, 0.3), xytext=(0.55, -0.85),
                    color=CMU_RED, ha="center", arrowprops=dict(arrowstyle="->", color=CMU_RED))
        ax.set_xlabel("time $t$ (s)")
        ax.set_ylabel("displacement $x$ (m)")
        ax.set_ylim(-1.05, 1.32)
        ax.legend(loc="upper right")
        save(fig, "spring-data.png")


# --------------------------------------------------------------------------------------
# seqsim
# --------------------------------------------------------------------------------------
def group_seqsim():
    import jax
    import jax.numpy as jnp
    import pounce
    import scipy.optimize as so

    jax.config.update("jax_enable_x64", True)
    m, mu_true, k_true = 1.0, 1.0, 400.0
    T, N = 2.0, 200
    h = T / N
    t_grid = np.linspace(0, T, N + 1)
    rng = np.random.default_rng(SEED)
    t_obs = np.linspace(0, T, 51)
    x_obs = oscillator(t_obs, m, mu_true, k_true) + rng.normal(0, 0.03, t_obs.size)
    idx = np.round(t_obs / h).astype(int)
    theta0 = np.array([2.0, 150.0])           # the poor starting guess, for both methods

    def rhs(s, th):
        x, v = s
        return jnp.array([v, -(th[0] * v + th[1] * x) / m])

    def simulate(th):
        def step(s, _):
            k1 = rhs(s, th)
            k2 = rhs(s + h / 2 * k1, th)
            k3 = rhs(s + h / 2 * k2, th)
            k4 = rhs(s + h * k3, th)
            s2 = s + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4)
            return s2, s2[0]
        _, xs = jax.lax.scan(step, jnp.array([1.0, 0.0]), None, length=N)
        return jnp.concatenate([jnp.array([1.0]), xs])

    def sse_seq(th):
        return jnp.sum((simulate(th)[idx] - x_obs) ** 2)

    f, g = jax.jit(sse_seq), jax.jit(jax.grad(sse_seq))
    sim_fn = jax.jit(simulate)
    seq = [theta0.copy()]
    res_seq = so.minimize(lambda th: float(f(th)), theta0, jac=lambda th: np.asarray(g(th)),
                          method="BFGS", callback=lambda xk: seq.append(xk.copy()),
                          options=dict(maxiter=300))

    nx = N + 1

    def unpack(z):
        return z[:nx], z[nx:2 * nx], z[2 * nx:]

    def obj(z):
        x, _, _ = unpack(z)
        return jnp.sum((x[idx] - x_obs) ** 2)

    def cons(z):
        x, v, th = unpack(z)
        a = -(th[0] * v + th[1] * x) / m
        c1 = x[1:] - x[:-1] - h / 2 * (v[1:] + v[:-1])        # trapezoidal collocation
        c2 = v[1:] - v[:-1] - h / 2 * (a[1:] + a[:-1])
        return jnp.concatenate([c1, c2, jnp.array([x[0] - 1.0, v[0]])])

    x_init = np.interp(t_grid, t_obs, x_obs)
    z0 = np.concatenate([x_init, np.gradient(x_init, t_grid), theta0])
    oj, og = jax.jit(obj), jax.jit(jax.grad(obj))
    cj, cJ = jax.jit(cons), jax.jit(jax.jacfwd(cons))
    sim = [z0.copy()]
    res_sim = pounce.minimize(
        lambda z: float(oj(z)), z0, jac=lambda z: np.asarray(og(z)),
        constraints=[dict(type="eq", fun=lambda z: np.asarray(cj(z)),
                          jac=lambda z: np.asarray(cJ(z)))],
        callback=lambda z, *a: sim.append(np.array(z, copy=True)))

    keep = slice(0, nx, 2)                   # every second node is plenty for the picture
    seq_frames = []
    for th in seq:
        xs = np.asarray(sim_fn(jnp.asarray(th)))
        seq_frames.append(dict(mu=round(float(th[0]), 3), k=round(float(th[1]), 2),
                               sse=round(float(f(th)), 4), x=r(xs[keep], 2)))
    sim_frames = []
    for z in sim:
        x, _, th = unpack(z)
        sim_frames.append(dict(mu=round(float(th[0]), 3), k=round(float(th[1]), 2),
                               sse=round(float(oj(z)), 4),
                               defect=float(f"{float(np.max(np.abs(np.asarray(cj(z))))):.3g}"),
                               x=r(x[keep], 2)))
    print(f"  starting guess mu = {theta0[0]}, k = {theta0[1]}  (true mu = {mu_true}, "
          f"k = {k_true}); {t_obs.size} observations, noise SD 0.03, T = {T} s")
    s0, s1 = seq_frames[0], seq_frames[-1]
    print(f"  sequential: {len(seq) - 1} BFGS iterations, ends at mu = {s1['mu']}, "
          f"k = {s1['k']}, SSE = {s1['sse']}  ({res_seq.message})")
    e0, e1 = sim_frames[0], sim_frames[-1]
    print(f"  simultaneous: {len(sim) - 1} interior-point iterations, ends at mu = "
          f"{e1['mu']}, k = {e1['k']}, SSE = {e1['sse']}  ({res_sim.message})")
    print(f"    largest equation error: first iterate {e0['defect']}, last {e1['defect']}")
    print(f"    SSE of the starting guess {s0['sse']}; of the true parameters "
          f"{float(f(np.array([mu_true, k_true]))):.4f}")

    for k_start in (250.0, 350.0, 450.0):
        th = so.minimize(lambda q: float(f(q)), np.array([2.0, k_start]),
                         jac=lambda q: np.asarray(g(q)), method="BFGS",
                         options=dict(maxiter=300)).x
        zs = np.concatenate([x_init, np.gradient(x_init, t_grid), [2.0, k_start]])
        zr = pounce.minimize(
            lambda z: float(oj(z)), zs, jac=lambda z: np.asarray(og(z)),
            constraints=[dict(type="eq", fun=lambda z: np.asarray(cj(z)),
                              jac=lambda z: np.asarray(cJ(z)))]).x
        print(f"    from k = {k_start:.0f}: sequential mu = {th[0]:.2f}, k = {th[1]:.0f};"
              f"  simultaneous mu = {zr[-2]:.2f}, k = {zr[-1]:.0f}")

    cache_put("seqsim", dict(
        T=T, t=r(t_grid[keep]), t_obs=r(t_obs), x_obs=r(x_obs, 3),
        truth=dict(mu=mu_true, k=k_true), start=dict(mu=theta0[0], k=theta0[1]),
        seq=seq_frames, sim=sim_frames))

    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(2, 3, figsize=(15, 7.6), sharex=True, sharey=True)
        picks = {
            "Sequential (single shooting)": (seq_frames, [0, len(seq_frames) // 3,
                                                          len(seq_frames) - 1], ORANGE),
            "Simultaneous (collocation)": (sim_frames, [0, 3, len(sim_frames) - 1], BLUE),
        }
        for row, (name, (frames, which, col)) in enumerate(picks.items()):
            for j, i in enumerate(which):
                ax = axes[row, j]
                fr = frames[i]
                ax.plot(t_obs, x_obs, "o", color=INK, ms=4)
                ax.plot(t_grid[keep], fr["x"], color=col, lw=2,
                        marker="." if row else None, ms=4)
                label = f"iteration {i}" + (" (final)" if i == len(frames) - 1 else "")
                txt = f"$\\mu$ = {fr['mu']:.2f}, $k$ = {fr['k']:.0f}, data error = {fr['sse']:.2f}"
                if row:
                    txt += f"\nequation error = {fr['defect']:.1g}"
                ax.set_title(label + "\n" + txt, fontsize=13, color=col)
            axes[row, 0].set_ylabel(name.split(" (")[0] + "\n$x$ (m)")
        for ax in axes[1]:
            ax.set_xlabel("time $t$ (s)")
        save(fig, "seq-vs-sim.png")


# --------------------------------------------------------------------------------------
# fedbatch
# --------------------------------------------------------------------------------------
FB = dict(Feed=0.05, Ypx=0.2, Yxs=0.5, Ks=1.0, mu_max=0.2)


def fb_rhs(t, x, mu_fn, Sf):
    X, P, S, V = x
    mu = mu_fn(x)
    F = FB["Feed"]
    return [mu * X - F * X / V, FB["Ypx"] * mu * X - F * P / V,
            F * (Sf - S) / V - mu * X / FB["Yxs"], F]


def monod(S):
    return FB["mu_max"] * S / (FB["Ks"] + S)


# The training batches follow the SiNDAE fed-batch example
# (docs/examples_gallery/generate_fedbatch_data.py): three initial charges, 40 h, and the same
# noise per state. The samples are evenly spaced, and a reading below zero is recorded as zero,
# since a concentration cannot be negative.
BATCH_ICS = np.array([[0.05, 0.0, 10.0, 1.00],
                      [0.025, 0.0, 5.0, 0.80],
                      [0.5, 0.0, 7.5, 0.95]])
NOISE = np.array([0.05, 0.05, 0.5, 0.1])
NEW_IC = np.array([0.20, 0.0, 7.0, 0.90])        # batch A of the same example
T_NEW = 60.0                                     # 20 h past the training batches


def fedbatch_data():
    """Three training batches, 31 noisy samples of each state over 40 h, from the Monod model."""
    from scipy.integrate import solve_ivp

    t_obs = np.linspace(0, 40, 31)
    rng = np.random.default_rng(SEED)
    y_obs, truth = [], []
    for ic in BATCH_ICS:
        s = solve_ivp(fb_rhs, (0, 40), ic, t_eval=t_obs, args=(lambda x: monod(x[2]), ic[2]),
                      rtol=1e-10, atol=1e-12)
        y_obs.append(np.clip(s.y.T + rng.normal(0, 1, s.y.T.shape) * NOISE, 0, None))
        dense = solve_ivp(fb_rhs, (0, 40), ic, t_eval=np.linspace(0, 40, 161),
                          args=(lambda x: monod(x[2]), ic[2]), rtol=1e-10, atol=1e-12)
        truth.append(dense.y)
    return BATCH_ICS, t_obs, np.array(y_obs), truth


def neural_ode(train_ics, t_obs, y_obs, steps=10_000):
    """The bioreactor as a neural ODE, trained the sequential way: Diffrax integrates the
    balances with mu from an Equinox network, Optax's Adam updates the weights. The code
    in the deck and in l13-neural-dae.ipynb is this function, line for line."""
    import diffrax
    import equinox as eqx
    import jax
    import jax.numpy as jnp
    import optax

    jax.config.update("jax_enable_x64", True)
    F, Ypx, Yxs = FB["Feed"], FB["Ypx"], FB["Yxs"]
    mu_scale = 0.3                                 # 1/h: sets the size of mu
    x_typical = jnp.array([5.0, 1.0, 10.0, 3.0])   # typical X, P, S, V

    class GrowthRate(eqx.Module):
        mlp: eqx.nn.MLP

        def __call__(self, x):
            out = self.mlp(x / x_typical)[0]       # any real number
            return mu_scale * jax.nn.softplus(out) # mu >= 0, of order mu_scale

    def balances(t, x, args):
        mu_net, Sf = args
        X, P, S, V = x
        mu = mu_net(x)                               # the learned term
        dX = mu * X - F / V * X
        dP = Ypx * mu * X - F / V * P
        dS = F / V * (Sf - S) - mu * X / Yxs
        dV = F
        return jnp.array([dX, dP, dS, dV])

    def simulate(mu_net, x0, ts):
        sol = diffrax.diffeqsolve(
            diffrax.ODETerm(balances),
            diffrax.Tsit5(),
            t0=0.0,
            t1=ts[-1],
            dt0=0.1,
            y0=x0,
            args=(mu_net, x0[2]),
            saveat=diffrax.SaveAt(ts=ts),
            stepsize_controller=diffrax.PIDController(
                rtol=1e-6,
                atol=1e-8,
            ),
        )
        return sol.ys

    x0s, ts, ys = jnp.array(train_ics), jnp.array(t_obs), jnp.array(y_obs)
    y_scale = ys.reshape(-1, 4).std(axis=0)

    def loss(mu_net):
        pred = jax.vmap(simulate, in_axes=(None, 0, None))(mu_net, x0s, ts)
        return jnp.mean(((pred - ys) / y_scale) ** 2)

    mu_net = GrowthRate(eqx.nn.MLP(
        in_size=4,
        out_size=1,
        width_size=16,
        depth=2,
        activation=jnp.tanh,
        key=jax.random.PRNGKey(SEED),
    ))
    opt = optax.adam(optax.cosine_decay_schedule(1e-2, steps, alpha=0.05))
    state = opt.init(eqx.filter(mu_net, eqx.is_array))

    @eqx.filter_jit
    def step(mu_net, state):
        value, grads = eqx.filter_value_and_grad(loss)(mu_net)
        updates, state = opt.update(grads, state, mu_net)
        return eqx.apply_updates(mu_net, updates), state, value

    history = []
    for _ in range(steps):
        mu_net, state, value = step(mu_net, state)
        history.append(float(value))
    run = eqx.filter_jit(simulate)
    return mu_net, (lambda x0, tt: np.asarray(run(mu_net, jnp.asarray(x0), jnp.asarray(tt)))), history


def black_box_ode(train_ics, t_obs, y_obs, steps=10_000):
    """A purely data-driven model: a network for the whole right-hand side, dx/dt = NN(x),
    with no balances. Trained the same way as the neural ODE above."""
    import diffrax
    import equinox as eqx
    import jax
    import jax.numpy as jnp
    import optax

    jax.config.update("jax_enable_x64", True)
    x_typical = jnp.array([5.0, 1.0, 10.0, 3.0])
    rate_typical = jnp.array([0.5, 0.1, 1.0, 0.1])   # typical dX/dt, dP/dt, dS/dt, dV/dt

    class RightHandSide(eqx.Module):
        mlp: eqx.nn.MLP

        def __call__(self, x):
            return rate_typical * self.mlp(x / x_typical)

    def field(t, x, args):
        return args(x)

    def simulate(net, x0, ts):
        sol = diffrax.diffeqsolve(
            diffrax.ODETerm(field),
            diffrax.Tsit5(),
            t0=0.0,
            t1=ts[-1],
            dt0=0.1,
            y0=x0,
            args=net,
            saveat=diffrax.SaveAt(ts=ts),
            stepsize_controller=diffrax.PIDController(
                rtol=1e-6,
                atol=1e-8,
            ),
            max_steps=100_000,
        )
        return sol.ys

    x0s, ts, ys = jnp.array(train_ics), jnp.array(t_obs), jnp.array(y_obs)
    y_scale = ys.reshape(-1, 4).std(axis=0)

    def loss(net):
        pred = jax.vmap(simulate, in_axes=(None, 0, None))(net, x0s, ts)
        return jnp.mean(((pred - ys) / y_scale) ** 2)

    net = RightHandSide(eqx.nn.MLP(
        in_size=4,
        out_size=4,
        width_size=32,
        depth=2,
        activation=jnp.tanh,
        key=jax.random.PRNGKey(SEED),
    ))
    opt = optax.adam(optax.cosine_decay_schedule(1e-2, steps, alpha=0.05))
    state = opt.init(eqx.filter(net, eqx.is_array))

    @eqx.filter_jit
    def step(net, state):
        value, grads = eqx.filter_value_and_grad(loss)(net)
        updates, state = opt.update(grads, state, net)
        return eqx.apply_updates(net, updates), state, value

    for _ in range(steps):
        net, state, value = step(net, state)
    run = eqx.filter_jit(simulate)
    return lambda x0, tt: np.asarray(run(net, jnp.asarray(x0), jnp.asarray(tt))), float(value)


def sindae_problem_class():
    """The fed-batch problem for SiNDAE, written as in the SiNDAE fed-batch example, with the
    product balance diluted by F / V (Eq. 30b of Lueg et al. 2026)."""
    import pyomo.dae as dae
    import pyomo.environ as pyo
    from sindae.problem import ProblemDefinition

    class FedBatchBioreactorProblem(ProblemDefinition):
        def __init__(
            self,
            params,
            ics,
            input_dim,
            z_dim,
            t_span,
            nfe,
            ncp,
            obs_times=None,
            obs_values=None,
            obs_dim=None,
        ):
            super().__init__(ics, input_dim, z_dim, t_span, nfe, ncp,
                             obs_times, obs_values, obs_dim)
            self.params = params

        def build_trajectory(self, block, traj_idx):
            p = self.params
            t0 = self.t_span[0]
            x0 = self.ics[traj_idx]
            Sf = float(x0[2])                # feed concentration = initial substrate
            Feed, Ypx, Yxs = p["Feed"], p["Ypx"], p["Yxs"]

            block.t = dae.ContinuousSet(bounds=self.t_span)
            block.x = pyo.Var(
                block.t,
                range(self.input_dim),
                domain=pyo.NonNegativeReals,
                initialize=1.0,
            )
            block.z = pyo.Var(block.t, range(self.z_dim), initialize=0.1)
            block.dxdt = dae.DerivativeVar(block.x, wrt=block.t)

            @block.Constraint(block.t, range(self.input_dim))
            def diffeq(b, t, s):
                mu = b.z[t, 0]               # growth rate, learned by the network
                X, P, S, V = b.x[t, 0], b.x[t, 1], b.x[t, 2], b.x[t, 3]
                if s == 0:
                    return b.dxdt[t, 0] == mu * X - Feed * (X / V)
                elif s == 1:
                    return b.dxdt[t, 1] == Ypx * mu * X - Feed * (P / V)
                elif s == 2:
                    return b.dxdt[t, 2] == Feed * (Sf - S) / V - mu * (X / Yxs)
                else:
                    return b.dxdt[t, 3] == Feed

            for j in range(self.input_dim):
                block.x[t0, j].fix(float(x0[j]))

        def get_input_vars(self, block, t):
            return [block.x[t, j] for j in range(self.input_dim)]

        def get_output_vars(self, block, t):
            return [block.z[t, 0]]

    return FedBatchBioreactorProblem


def group_fedbatch():
    import logging

    import jax
    import jax.numpy as jnp
    from scipy.integrate import solve_ivp
    from sindae import HybridDAE
    from sindae.algorithms.pretrain import PretrainConfig, pretrain_mlp
    from sindae.algorithms.simultaneous.train import SimultaneousConfig
    from sindae.algorithms.smoother import SmootherConfig
    from sindae.nn_utils import SimpleMLP
    from sindae.solvers import SolverConfig

    jax.config.update("jax_enable_x64", True)
    logging.getLogger("pyomo").setLevel(logging.ERROR)
    train_ics, t_obs, y_obs, truth_train = fedbatch_data()
    t_dense = np.linspace(0, 40, 161)

    # ---- 1. the hybrid neural ODE, trained sequentially (Diffrax + Optax)
    t0 = time.time()
    mu_node, run_node, hist = neural_ode(train_ics, t_obs, y_obs)
    print(f"  neural ODE: 10,000 Adam steps in {time.time() - t0:.0f} s, "
          f"loss {hist[0]:.0f} -> {hist[-1]:.4f}")
    fit_node = [run_node(ic, t_dense) for ic in train_ics]
    rmse_node = np.sqrt(np.mean([(run_node(ic, t_dense) - tr.T) ** 2
                                 for ic, tr in zip(train_ics, truth_train)], axis=(0, 1)))
    print(f"    RMSE against the true model on the training batches, X P S V: "
          f"{np.round(rmse_node, 3).tolist()} (noise SD {NOISE.tolist()})")

    def mu_node_fn(x):
        return float(mu_node(jnp.asarray(x, dtype=float)))

    # ---- 2. the purely data-driven model
    t0 = time.time()
    run_bb, bb_loss = black_box_ode(train_ics, t_obs, y_obs)
    rmse_bb = np.sqrt(np.mean([(run_bb(ic, t_dense) - tr.T) ** 2
                               for ic, tr in zip(train_ics, truth_train)], axis=(0, 1)))
    print(f"  data-driven ODE: {time.time() - t0:.0f} s, final loss {bb_loss:.4f}; RMSE on the "
          f"training batches, X P S V: {np.round(rmse_bb, 3).tolist()}")

    # ---- 3. the neural DAE, trained simultaneously (SiNDAE, the settings of its example)
    Problem = sindae_problem_class()
    problem = Problem(params=FB, ics=train_ics, input_dim=4, z_dim=1, t_span=(0.0, 40.0),
                      nfe=40, ncp=3, obs_dim=4, obs_times=[t_obs] * 3, obs_values=list(y_obs))

    def new_mlp():
        return SimpleMLP(in_size=4, out_size=1, widths=[20, 20],
                         activations=[jax.nn.softplus] * 2, key=jax.random.PRNGKey(SEED))

    pre_cfg = PretrainConfig(epochs=200, batch_size=32, reg_coef=1e-3)
    model = HybridDAE(
        method="simultaneous", nlp_solver="pounce", net=new_mlp(),
        smoother=SmootherConfig(smooth_coef=10.0), pretrain=pre_cfg,
        train=SimultaneousConfig(use_gbm=True, reg_coef=1e-3),
        solver_options=SolverConfig(tol=1e-6, max_iter=1000),
        unfix_io=True)
    t0 = time.time()
    model.fit(problem)
    print(f"  SiNDAE fit: {time.time() - t0:.1f} s, termination {model.termination}")
    smd = model.smoother_data
    im, isd, om, osd = (np.asarray(getattr(smd, a)) for a in
                        ("input_mean", "input_std", "output_mean", "output_std"))
    pre = pretrain_mlp(new_mlp(), smd, pre_cfg)          # the pretraining stage, redone to draw it
    net_pre = jax.jit(lambda x: om + osd * pre((x - im) / isd))

    # ---- 4. a new batch, never seen in training, run 20 h past the training batches
    tt = np.linspace(0.0, T_NEW, 121)
    gt = solve_ivp(fb_rhs, (0, T_NEW), NEW_IC, args=(lambda x: monod(x[2]), NEW_IC[2]),
                   t_eval=tt, rtol=1e-10, atol=1e-12)
    node = run_node(NEW_IC, tt).T
    bb = run_bb(NEW_IC, tt).T
    pred = model.predict(Problem(params=FB, ics=np.array([NEW_IC]), input_dim=4, z_dim=1,
                                 t_span=(0.0, T_NEW), nfe=45, ncp=3, obs_dim=4),
                         slack_coef=1e-5)[0]
    tp, Xp = np.asarray(pred.sampling_times), pred.nn_input
    S_node = node[2]
    mu_path = np.array([mu_node_fn(node[:, i]) for i in range(tt.size)])
    i0 = int(np.argmax(S_node < 0))                # first sample below zero
    w = S_node[i0 - 1] / (S_node[i0 - 1] - S_node[i0])
    t_cross = float(tt[i0 - 1] + w * (tt[i0] - tt[i0 - 1]))
    mu0 = float(mu_path[i0 - 1] + w * (mu_path[i0] - mu_path[i0 - 1]))
    hours_below = float(np.mean(S_node < 0) * T_NEW)

    def rmse(a, b):
        return float(np.sqrt(np.mean((a - b) ** 2)))

    X_dae = np.interp(tt, tp, Xp[:, 0])
    S_dae = np.interp(tt, tp, Xp[:, 2])
    print(f"  new batch, initial charge {NEW_IC.tolist()}, {T_NEW:.0f} h:")
    print(f"    true model:           min S {gt.y[2].min():.3f} g/L, X at the end {gt.y[0, -1]:.2f} g/L")
    print(f"    data-driven ODE:      min S {bb[2].min():.2f} g/L, below zero for "
          f"{np.mean(bb[2] < 0) * T_NEW:.0f} h; RMSE X {rmse(bb[0], gt.y[0]):.2f}, "
          f"S {rmse(bb[2], gt.y[2]):.2f} g/L; X at the end {bb[0, -1]:.2f}")
    print(f"    hybrid neural ODE:    min S {S_node.min():.2f} g/L; S reaches 0 at t = {t_cross:.1f} h,"
          f" where the network gives mu = {mu0:.3f} 1/h (Monod: 0); below zero for "
          f"{hours_below:.0f} h; RMSE X {rmse(node[0], gt.y[0]):.2f}, S {rmse(node[2], gt.y[2]):.2f}; "
          f"X at the end {node[0, -1]:.2f}")
    print(f"    neural DAE (SiNDAE):  min S {Xp[:, 2].min():.3f} g/L; RMSE X "
          f"{rmse(X_dae, gt.y[0]):.2f}, S {rmse(S_dae, gt.y[2]):.2f}; X at the end {Xp[-1, 0]:.2f}")

    cache_put("fedbatch", dict(
        ic=r(NEW_IC), t=r(tt, 2),
        truth=dict(X=r(gt.y[0], 3), S=r(gt.y[2], 3)),
        node=dict(X=r(node[0], 3), S=r(node[2], 3)),
        dae=dict(t=r(tp, 2), X=r(Xp[:, 0], 3), S=r(Xp[:, 2], 3)),
        summary=dict(mu0=round(mu0, 3), minS_node=round(float(S_node.min()), 2),
                     minS_dae=round(float(Xp[:, 2].min()), 3),
                     minS_true=round(float(gt.y[2].min()), 3), t_cross=round(t_cross, 1),
                     hours_below=round(hours_below))))

    names = ["biomass $X$ (g/L)", "product $P$ (g/L)", "substrate $S$ (g/L)", "volume $V$ (L)"]
    cols = (BLUE, ORANGE, GREEN)
    with plt.rc_context(STYLE):
        # ---- the training data, and the neural ODE's fit to it
        fig, axes = plt.subplots(1, 4, figsize=(16, 3.7))
        for j, ax in enumerate(axes):
            for b, col in enumerate(cols):
                ax.plot(t_obs, y_obs[b][:, j], "o", color=col, ms=4, alpha=0.8,
                        label=f"batch {b + 1}, data")
                ax.plot(t_dense, fit_node[b][:, j], color=col, lw=2.2,
                        label=f"batch {b + 1}, neural ODE")
            ax.set_title(names[j])
            ax.set_xlabel("time (h)")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=6, fontsize=12,
                   bbox_to_anchor=(0.5, -0.12))
        save(fig, "fedbatch-data.png")

        # ---- the learned growth rate on the new batch, against the hidden law
        fig, ax = plt.subplots(figsize=(9, 4.4))
        ax.axvspan(-1.6, 0, color=CMU_RED, alpha=0.08, lw=0)
        ax.text(-0.8, 0.105, "$S < 0$:\nimpossible", ha="center", va="center", color=CMU_RED,
                fontsize=13)
        Sg = np.linspace(0, 7.5, 200)
        ax.plot(Sg, monod(Sg), color=GRAY, lw=5, alpha=0.6, label="true law (hidden): $\\mu = 0$ at $S = 0$")
        ax.plot(S_node, mu_path, color=ORANGE, lw=2.6, label="learned $\\mu$, along the new batch")
        for i in (10, 25, 40):
            ax.annotate("", xy=(S_node[i + 1], mu_path[i + 1]), xytext=(S_node[i], mu_path[i]),
                        arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=0, mutation_scale=18))
        ax.plot([0], [mu0], "o", color=CMU_RED, ms=11)
        ax.annotate(f"at $S = 0$ the network still says\n$\\mu$ = {mu0:.3f} 1/h: the cells keep growing",
                    xy=(0.05, mu0), xytext=(1.2, 0.012), color=CMU_RED, va="bottom",
                    arrowprops=dict(arrowstyle="->", color=CMU_RED))
        ax.set_xlim(-1.6, 7.6)
        ax.set_ylim(0, 0.21)
        ax.set_xlabel("substrate $S$ (g/L)")
        ax.set_ylabel("growth rate $\\mu$ (1/h)")
        ax.legend(loc="upper left", bbox_to_anchor=(0.12, 1.0))
        save(fig, "fedbatch-mu.png")

        # ---- the new batch: purely data-driven, physics-informed and physics-enforced
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 4.8))
        for ax, j, lab in ((a1, 0, "biomass $X$ (g/L)"), (a2, 2, "substrate $S$ (g/L)")):
            ax.axvspan(40, T_NEW, color=GRAY, alpha=0.10, lw=0)
            ax.plot(tt, gt.y[j], color=GRAY, lw=6, alpha=0.5, label="true mechanistic model")
            ax.plot(tt, bb[j], color=PURPLE, lw=2.4, ls=":", label="purely data-driven: $\\dot x = \\mathrm{NN}(x)$")
            ax.plot(tt, node[j], color=ORANGE, lw=2.4, label="physics-informed: balances + learned $\\mu$")
            ax.plot(tp, Xp[:, j], color=BLUE, lw=2.4, ls="--", label="physics-enforced: neural DAE, $S \\geq 0$")
            ax.set_xlabel("time (h)")
            ax.set_ylabel(lab)
        a2.axhspan(-1.2, 0, color=CMU_RED, alpha=0.08, lw=0)
        a2.axhline(0, color=MUTED, lw=1)
        a2.text(1, -1.05, "negative concentration: impossible", color=CMU_RED, fontsize=12)
        a2.set_ylim(-1.2, 7.5)
        a1.text(50, 0.3, "beyond the\ntraining time", ha="center", color=MUTED, fontsize=12)
        handles, labels = a1.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=2, fontsize=13,
                   bbox_to_anchor=(0.5, -0.13))
        save(fig, "fedbatch-models.png")

        # ---- the new batch, substrate only: the neural ODE against the neural DAE
        fig, ax = plt.subplots(figsize=(11, 4.6))
        ax.axhspan(-1.2, 0, color=CMU_RED, alpha=0.08, lw=0)
        ax.text(1, -1.0, "negative concentration: physically impossible", ha="left",
                color=CMU_RED)
        ax.axhline(0, color=MUTED, lw=1)
        ax.plot(tt, gt.y[2], color=GRAY, lw=5, alpha=0.5, label="true mechanistic model")
        ax.plot(tt, S_node, color=ORANGE, lw=2.4, label="sequential approach / neural ODE")
        ax.plot(tp, Xp[:, 2], color=BLUE, lw=2.4, ls="--", label="neural DAE")
        ax.annotate(f"{S_node.min():.2f} g/L".replace("-", "−"),
                    xy=(tt[np.argmin(S_node)], S_node.min()),
                    xytext=(tt[np.argmin(S_node)] - 9, -0.75), color=ORANGE,
                    arrowprops=dict(arrowstyle="->", color=ORANGE))
        ax.set_xlabel("time (h)")
        ax.set_ylabel("substrate $S$ (g/L)")
        ax.set_ylim(-1.2, 7.5)
        ax.legend(loc="upper right")
        save(fig, "fedbatch-inference.png")

        # ---- SiNDAE's three stages, on the training batches
        fig = plt.figure(figsize=(15, 5.6))
        gs = fig.add_gridspec(2, 3, height_ratios=[1.3, 1], hspace=0.12, wspace=0.28)
        a1, b1 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0])
        a3, b3 = fig.add_subplot(gs[0, 2]), fig.add_subplot(gs[1, 2])
        a2 = fig.add_subplot(gs[:, 1])
        for stage, (ax_s, ax_m) in ((smd, (a1, b1)), (model.trained_data, (a3, b3))):
            for i, col in enumerate(cols):
                tr = stage[i]
                ax_s.plot(t_obs, y_obs[i][:, 2], "o", color=col, ms=3.5, alpha=0.7)
                ax_s.plot(tr.sampling_times, tr.nn_input[:, 2], color=col, lw=2)
                ax_m.plot(tr.sampling_times, tr.nn_output[:, 0], color=col, lw=2)
            ax_s.set_ylabel("$S$ (g/L)")
            ax_m.set_ylabel("$\\mu$ (1/h)")
            ax_m.set_xlabel("time (h)")
            ax_s.tick_params(labelbottom=False)
            ax_m.set_ylim(-0.01, 0.24)
        a1.set_title("1. Smoother: states and $\\mu(t)$ free,\nno network, kept smooth", fontsize=14)
        a3.set_title("3. Full NLP: network, states and\nbalances solved together", fontsize=14)
        b1.text(0.97, 0.9, "$\\mu$ as a free function of time", transform=b1.transAxes,
                ha="right", va="top", fontsize=12, color=MUTED)
        b3.text(0.97, 0.9, "$\\mu$ = network(states)", transform=b3.transAxes,
                ha="right", va="top", fontsize=12, color=MUTED)
        X_sm = np.vstack([smd[i].nn_input for i in range(3)])
        mu_sm = np.concatenate([smd[i].nn_output[:, 0] for i in range(3)])
        mu_pre = np.array([float(net_pre(jnp.asarray(x))[0]) for x in X_sm])
        a2.plot(X_sm[:, 2], mu_sm, "o", color=GRAY, ms=6, alpha=0.7,
                label="smoother's ($S$, $\\mu$) pairs: the targets")
        a2.plot(X_sm[:, 2], mu_pre, "o", color=GREEN, ms=3.5,
                label="pretrained network, same inputs")
        a2.set_title("2. Pretrain: fit the network to the\nsmoother's pairs with Adam", fontsize=14)
        a2.set_xlabel("substrate $S$ (g/L)")
        a2.set_ylabel("growth rate $\\mu$ (1/h)")
        a2.legend(loc="lower right", fontsize=11)
        save(fig, "sindae-stages.png")


# --------------------------------------------------------------------------------------
# diagrams
# --------------------------------------------------------------------------------------
def nn_glyph(ax, x0, y0, w, h, color):
    layers = [3, 4, 4, 2]
    pts = []
    for i, n in enumerate(layers):
        xs = x0 + w * i / (len(layers) - 1)
        ys = [y0 + h * (j + 0.5) / n for j in range(n)]
        pts.append([(xs, y) for y in ys])
    for a, b in zip(pts[:-1], pts[1:]):
        for p in a:
            for q in b:
                ax.plot([p[0], q[0]], [p[1], q[1]], color=color, lw=0.6, alpha=0.6)
    for layer in pts:
        for p in layer:
            ax.plot(*p, "o", ms=7, mfc="white", mec=color, mew=1.4)


def group_diagrams():
    with plt.rc_context(STYLE):
        # ---- a projection layer
        fig, ax = plt.subplots(figsize=(7.2, 6.2))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.set_aspect("equal")
        xs = np.linspace(0, 10, 2)
        ax.plot(xs, 10 - xs, color=GREEN, lw=3)
        ax.text(2.6, 1.6, "$y_1 + y_2 = F_\\mathrm{in}$\n(mass balance)", color=GREEN,
                ha="center")
        raw = np.array([6.6, 6.0])
        proj = raw - (raw.sum() - 10) / 2 * np.ones(2)
        ax.plot(*raw, "o", color=ORANGE, ms=13)
        ax.text(raw[0] + 0.3, raw[1] + 0.3, "raw network output $\\tilde y$", color=ORANGE)
        ax.plot(*proj, "o", color=BLUE, ms=13)
        ax.text(proj[0] - 0.4, proj[1] - 0.9, "projected output $y$", color=BLUE, ha="right")
        ax.add_patch(FancyArrowPatch(raw, proj, arrowstyle="-|>", mutation_scale=22,
                                     color=INK, lw=2, shrinkA=8, shrinkB=8))
        ax.text(6.3, 4.4, "closest point\non the line", fontsize=13, color=MUTED)
        ax.set_xlabel("outlet flow $y_1$")
        ax.set_ylabel("outlet flow $y_2$")
        save(fig, "projection.png")

        # ---- the splitter the projection-layer example models
        fig, ax = plt.subplots(figsize=(5.4, 2.9))
        ax.set_xlim(0, 10)
        ax.set_ylim(0.7, 5.7)
        ax.axis("off")
        pipe = dict(color=INK, lw=9, solid_capstyle="butt")
        ax.plot([0.4, 4.2], [2.8, 2.8], **pipe)
        ax.plot([4.2, 4.2], [1.2, 4.4], **pipe)
        ax.plot([4.2, 8.4], [4.4, 4.4], **pipe)
        ax.plot([4.2, 8.4], [1.2, 1.2], **pipe)
        for y0_, lab in ((4.4, "$y_1$"), (1.2, "$y_2$")):
            ax.annotate("", xy=(9.5, y0_), xytext=(8.3, y0_),
                        arrowprops=dict(arrowstyle="-|>", color=INK, lw=2.4, mutation_scale=22))
            ax.text(9.6, y0_, lab, fontsize=22, va="center")
        ax.annotate("", xy=(1.6, 2.8), xytext=(0.0, 2.8),
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2.4, mutation_scale=22))
        ax.text(0.1, 3.3, "feed $F = 10$", color=BLUE, fontsize=17)
        vx, vy = 6.3, 4.4
        ax.fill([vx - 0.45, vx, vx - 0.45], [vy - 0.32, vy, vy + 0.32], fc="white", ec=INK, lw=2.2, zorder=3)
        ax.fill([vx + 0.45, vx, vx + 0.45], [vy - 0.32, vy, vy + 0.32], fc="white", ec=INK, lw=2.2, zorder=3)
        ax.plot([vx, vx], [vy, vy + 0.75], color=INK, lw=2.2)
        ax.text(vx, vy + 0.85, "valve, opening $u$", ha="center", fontsize=17, color=ORANGE)
        ax.text(4.8, 2.8, "mass balance:\n$y_1 + y_2 = F$", fontsize=17, color=GREEN, va="center",
                bbox=dict(boxstyle="round", fc="#e8f3e9", ec=GREEN))
        save(fig, "splitter.png")


# --------------------------------------------------------------------------------------
# mab
# --------------------------------------------------------------------------------------
def group_mab():
    import io

    from PIL import Image
    from pptx import Presentation

    src = REPO / "attic" / "Victor-Alves-CAPD-Overview-2026.pptx"
    if not src.exists():
        print(f"  skipped: {src} is not present")
        return
    deck = Presentation(str(src))
    wanted = {(15, "Picture 7"): "mab-multiscale.png"}
    for (n, shape_name), out in wanted.items():
        shape = next(s for s in deck.slides[n - 1].shapes if s.name == shape_name)
        img = Image.open(io.BytesIO(shape.image.blob)).convert("RGBA")
        if out == "mab-multiscale.png":
            # The picture's lower third is empty transparent canvas; keep the panels.
            img = img.crop((0, 0, img.width, int(img.height * 0.63)))
        bg = Image.new("RGBA", img.size, "white")
        Image.alpha_composite(bg, img).convert("RGB").save(HERE / out, optimize=True)
        print(f"  wrote {out} ({img.width} x {img.height})")


# --------------------------------------------------------------------------------------
# schematics
# --------------------------------------------------------------------------------------
def deck_picture(deck_name, slide, shape_name):
    """One picture from one of Victor Alves's decks, as a PIL image on white."""
    import io

    from PIL import Image
    from pptx import Presentation

    deck = Presentation(str(REPO / "attic" / deck_name))
    shape = next(s for s in deck.slides[slide - 1].shapes if s.name == shape_name)
    img = Image.open(io.BytesIO(shape.image.blob)).convert("RGBA")
    bg = Image.new("RGBA", img.size, "white")
    return Image.alpha_composite(bg, img).convert("RGB")


def deck_svg(deck_name, slide, shape_name):
    """An SVG graphic from one of the decks, rendered to PNG with rsvg-convert."""
    import io
    import subprocess

    from PIL import Image
    from pptx import Presentation

    deck = Presentation(str(REPO / "attic" / deck_name))
    sl = deck.slides[slide - 1]
    shape = next(s for s in sl.shapes if s.name == shape_name)
    ns = "{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip"
    rid = next(e for e in shape._element.iter(ns)).get(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
    png = subprocess.run(["rsvg-convert", "-w", "900"], input=sl.part.related_part(rid).blob,
                         capture_output=True, check=True).stdout
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    bg = Image.new("RGBA", img.size, "white")
    return Image.alpha_composite(bg, img).convert("RGB")


def tank_manifold():
    """Fig. 1 of Lueg et al. (2026), redrawn at a size where its labels can be read.

    Coordinates follow the published figure (pixels of a 300 dpi render of page 16),
    with y pointing down. Dashed lines carry the levels x0 and x3 to the pump, whose
    flow depends on them; dotted blue lines are the liquid levels.
    """
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.6, 7.6))
        ax.set_xlim(1030, 1640)
        ax.set_ylim(660, 40)
        ax.set_aspect("equal")
        ax.axis("off")
        lw = 2.6

        def tank(x0, x1, top, bot, level, name, lx, ly):
            ax.plot([x0, x0, x1, x1], [top, bot, bot, top], color=INK, lw=lw)
            ax.plot([x0 + 4, x1 - 4], [level, level], color="#1f3cff", lw=2.2, ls=(0, (1, 2.2)))
            ax.text(lx, ly, name, fontsize=21, ha="center", va="bottom", style="italic")

        def arrow(p, q, both=False):
            ax.annotate("", xy=q, xytext=p, arrowprops=dict(
                arrowstyle="<|-|>" if both else "-|>", color=INK, lw=lw, mutation_scale=20))

        tank(1157, 1271, 133, 260, 196, "$x_1$", 1214, 190)
        tank(1524, 1612, 133, 260, 196, "$x_0$", 1568, 190)
        tank(1474, 1612, 323, 450, 399, "$x_2$", 1543, 393)
        tank(1347, 1612, 513, 640, 587, "$x_3$", 1480, 581)
        # valve: two triangles meeting at the centre, and its actuator on top
        cx, cy = 1397, 173
        ax.fill([cx - 38, cx, cx - 38], [cy - 23, cy, cy + 23], fc="white", ec=INK, lw=lw)
        ax.fill([cx + 38, cx, cx + 38], [cy - 23, cy, cy + 23], fc="white", ec=INK, lw=lw)
        ax.fill([cx - 22, cx + 22, cx], [cy - 40, cy - 40, cy], fc="white", ec=INK, lw=lw)
        # pump: a circle with a triangle
        px, py, pr = 1082, 513, 38
        ax.add_patch(plt.Circle((px, py), pr, fc="white", ec=INK, lw=lw))
        ax.plot([px - pr * 0.92, px, px + pr * 0.92], [py - 10, py - pr, py - 10], color=INK, lw=lw)
        # y0: from x3 to the pump, up and over to the valve
        ax.plot([1347, 1082], [627, 627], color=INK, lw=lw)
        arrow((1082, 627), (1082, py + pr + 2))
        ax.plot([1082, 1082, 1397], [py - pr, 70, 70], color=INK, lw=lw)
        arrow((1397, 70), (1397, cy - 41))
        ax.text(1095, 300, "$y_0$", fontsize=21, style="italic")
        arrow((1273, cy), (cx - 40, cy), both=True)
        ax.text(1314, 156, "$y_2$", fontsize=21, ha="center", style="italic")
        arrow((cx + 40, cy), (1522, cy))
        ax.text(1480, 156, "$y_1$", fontsize=21, ha="center", style="italic")
        arrow((1568, 260), (1568, 322))
        ax.text(1580, 292, "$y_3$", fontsize=21, style="italic")
        arrow((1555, 450), (1555, 512))
        ax.text(1567, 482, "$y_4$", fontsize=21, style="italic")
        # the pump reads the levels x0 and x3
        ax.plot([1522, 1335, 1335, 1125], [237, 237, 485, 485], color=INK, lw=2, ls=(0, (5, 4)))
        arrow((1150, 485), (px + 30, 485))
        ax.plot([1347, 1125], [542, 542], color=INK, lw=2, ls=(0, (5, 4)))
        arrow((1150, 542), (px + 30, 542))
        save(fig, "tank-manifold.png")


def spring_mass():
    """The spring-mass of the PINN section: a labeled schematic at its release from x = 1 m,
    beside the exact solution over one second."""
    m, mu, k = 1.0, 4.0, 400.0
    t = np.linspace(0, 1, 61)
    x = oscillator(t, m, mu, k)
    green = "#2b9a2b"

    with plt.rc_context(STYLE):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.6), gridspec_kw={"width_ratios": [1, 2.3]})
        fig.subplots_adjust(left=0.01, right=0.98, bottom=0.17, top=0.97, wspace=0.05)
        draw_spring_mass(a1, x[0])
        a2.plot(t, x, color="0.85", lw=2)
        a2.plot(t[0], x[0], "o", color=green, ms=10)
        a2.set_xlim(0, 1)
        a2.set_ylim(-1.1, 1.15)
        a2.set_xlabel("time $t$ (s)")
        a2.set_ylabel("$x$ (m)")
        a2.spines[["top", "right"]].set_visible(False)
        save(fig, "spring-mass.png")


def fedbatch_reactor():
    """Victor Alves's bioreactor drawing (cmu-seminar slide 35), with the four states of
    this lecture's model in place of the drawing's own labels."""
    from PIL import ImageDraw

    img = deck_picture("cmu-seminar.pptx", 35, "Picture 17")
    d = ImageDraw.Draw(img)
    d.rectangle((205, 46, 248, 73), fill="white")        # the drawing's [M_i]
    d.rectangle((70, 167, 99, 191), fill="white")        # and its X_v, below the liquid line
    arr = np.asarray(img)
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(7.6, 6.2))
        ax.imshow(arr, extent=(0, arr.shape[1], arr.shape[0], 0))
        ax.set_xlim(-305, arr.shape[1] + 235)
        ax.set_ylim(arr.shape[0] + 10, -60)
        ax.axis("off")
        ax.annotate("feed $F$ (L/h)\nsubstrate at $S_f$", xy=(70, 92), xytext=(-240, -10),
                    fontsize=16, color=BLUE, arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2.4))
        ax.annotate("cells: biomass $X$", xy=(205, 200), xytext=(330, 120), fontsize=16,
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
        ax.annotate("product $P$ and\nsubstrate $S$ (g/L)", xy=(130, 280), xytext=(330, 250),
                    fontsize=16, arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
        ax.annotate("volume $V$ (L)\nrises with the feed", xy=(34, 178), xytext=(-300, 300),
                    fontsize=16, arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
        save(fig, "fedbatch-reactor.png")


def sciml_spectrum():
    """Victor Alves's first-principles / hybrid / data-driven schematic (CAPD 2026 slide 12
    and cmu-seminar slide 7), redrawn with his network drawing. The slide version is built in
    HTML so it can animate in his order; this is the still for the notes."""
    from matplotlib.patches import FancyArrow

    nn = np.asarray(deck_picture("Victor-Alves-CAPD-Overview-2026.pptx", 12, "Picture 13"))
    from PIL import Image
    Image.fromarray(nn).save(HERE / "nn-glyph.png")
    print("  wrote nn-glyph.png")
    red = "#b5121b"
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(14, 7.9))
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        ax.set_xlim(0, 14)
        ax.set_ylim(0, 7.9)
        ax.axis("off")
        xs = [0.15, 4.75, 9.35]
        for i, x0 in enumerate(xs):
            if i == 1:
                for g in (0.24, 0.15, 0.07):
                    ax.add_patch(FancyBboxPatch((x0 - g, 0.95 - g), 4.5 + 2 * g, 6.1 + 2 * g,
                                                boxstyle="round,pad=0,rounding_size=0.35",
                                                fc="#9ec5ea", ec="none", alpha=0.35, zorder=1))
            ax.add_patch(FancyBboxPatch((x0, 0.95), 4.5, 6.1, boxstyle="round,pad=0,rounding_size=0.3",
                                        fc="white", ec=INK, lw=2.4, zorder=2))
        ax.add_patch(FancyArrow(0.0, 6.45, 13.4, 0, width=0.66, head_width=1.05, head_length=0.55,
                                fc=red, ec="none", length_includes_head=True, zorder=3))
        ax.add_patch(FancyArrow(14.0, 1.55, -13.4, 0, width=0.66, head_width=1.05, head_length=0.55,
                                fc=red, ec="none", length_includes_head=True, zorder=3))
        for x0, top, bot in zip(xs, ("Minimal data", "Moderate data", "Extensive data"),
                                ("No ML", "Physics + ML", "No physics")):
            ax.text(x0 + 2.25, 6.45, top, color="white", fontsize=22, ha="center", va="center", zorder=4)
            ax.text(x0 + 2.25, 1.55, bot, color="white", fontsize=22, ha="center", va="center", zorder=4)
        kw = dict(ha="center", va="center", zorder=4)
        ax.text(2.4, 4.45, "$mC_p\\,\\dfrac{dT}{dt} = f(T, C, k_1, k_2, \\ldots)$\n$\\vdots$\n"
                "$\\dfrac{dC}{dt} = g(T, C, k_1, k_2, \\ldots)$", fontsize=20, **kw)
        ax.text(2.4, 2.55, "Challenges:\nunknown physics, time to impact", fontsize=16, color=MUTED, **kw)
        ax.imshow(nn, extent=(5.85, 8.15, 4.55, 5.9), zorder=4)
        ax.text(7.0, 3.55, "$mC_p\\,\\dfrac{dT}{dt} = f_1(T, C, k_1, \\ldots)$\n"
                "$\\dfrac{dC}{dt} = \\mathrm{ML}(T, C, k_1, \\ldots)$\n"
                "$h = 0,\\;\\; g \\leq 0$", fontsize=19, **kw)
        ax.text(7.0, 2.3, "Opportunities:\nmissing tools (train, optimize, UQ)", fontsize=16, color=BLUE, **kw)
        ax.imshow(nn, extent=(10.3, 12.9, 4.15, 5.7), zorder=4)
        ax.text(11.6, 3.45, "$\\hat C = \\mathrm{ML}(T, C, k_1, k_2, \\ldots)$", fontsize=20, **kw)
        ax.text(11.6, 2.55, "Challenges:\nno gained insight, cost to impact", fontsize=16, color=MUTED, **kw)
        for x0, name in zip(xs, ("First-principles", "Hybrid", "Data-driven (ML)")):
            ax.text(x0 + 2.25, 0.45, name, fontsize=23, ha="center", va="center")
        ax.text(7.0, 7.5, "Gen 2", fontsize=24, ha="center", va="center", weight="bold")
        ax.text(11.6, 7.5, "Gen 0, Gen 1", fontsize=21, ha="center", va="center")
        save(fig, "sciml-spectrum.png")


def card_neural_ode():
    """A small picture for the deck's neural ODE card: dh/dt = a network, and a trajectory."""
    nn = plt.imread(HERE / "nn-glyph.png")
    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(6, 3.4))
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        ax.set_xlim(0, 6)
        ax.set_ylim(0, 3.4)
        ax.axis("off")
        ax.text(0.15, 2.55, "$\\dfrac{dh}{dt} =$", fontsize=30, va="center")
        ax.imshow(nn, extent=(2.1, 4.6, 1.9, 3.25), zorder=2)
        ax.text(4.75, 2.55, "$(h;\\,\\theta)$", fontsize=26, va="center")
        t = np.linspace(0, 1, 200)
        ax.plot(0.3 + 5.4 * t, 0.85 + 0.55 * np.exp(-2 * t) * np.cos(9 * t), color=BLUE, lw=3)
        tk = np.linspace(0, 1, 9)
        ax.plot(0.3 + 5.4 * tk, 0.85 + 0.55 * np.exp(-2 * tk) * np.cos(9 * tk), "o", color=ORANGE, ms=7)
        save(fig, "card-neural-ode.png")


def generations_and_logos():
    """Victor Alves's Gen 0 and Gen 1 plots (cmu-seminar slides 5 and 8), and the logos of
    the tools SiNDAE builds on (CAPD 2026 slide 20), each project's own mark."""
    deck_picture("cmu-seminar.pptx", 5, "Picture 9").save(HERE / "gen0.png", optimize=True)
    deck_picture("cmu-seminar.pptx", 8, "Picture 9").save(HERE / "gen1.png", optimize=True)
    print("  wrote gen0.png, gen1.png")
    logos = {"Picture 8": "logo-pyomo.png", "Picture 16": "logo-pyomo-dae.png",
             "Picture 21": "logo-jax.png", "Picture 24": "logo-onnx.png",
             "Picture 20": "logo-ipopt.png", "Picture 6": "logo-omlt.png",
             "Graphic 19": "logo-pounce.png"}
    for shape, out in logos.items():
        if shape == "Graphic 19":
            img = deck_svg("Victor-Alves-CAPD-Overview-2026.pptx", 20, shape)
        else:
            img = deck_picture("Victor-Alves-CAPD-Overview-2026.pptx", 20, shape)
        img.thumbnail((900, 900))
        img.save(HERE / out, optimize=True)
    print(f"  wrote {', '.join(logos.values())}")


def group_schematics():
    tank_manifold()
    spring_mass()
    if not (REPO / "attic" / "cmu-seminar.pptx").exists():
        print("  skipped the reactor and the spectrum: attic/ decks are not present")
        return
    fedbatch_reactor()
    sciml_spectrum()
    card_neural_ode()
    generations_and_logos()


def compose(names, out, cols):
    """Paste several of this lecture's figures into one grid, for the notes."""
    from PIL import Image

    ims = [Image.open(HERE / n).convert("RGB") for n in names]
    w, h = max(i.width for i in ims), max(i.height for i in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), "white")
    for j, im in enumerate(ims):
        sheet.paste(im, ((j % cols) * w + (w - im.width) // 2, (j // cols) * h + (h - im.height) // 2))
    sheet.save(HERE / out, optimize=True)
    print(f"  wrote {out}")


# --------------------------------------------------------------------------------------
# examples: four mechanistic models, each with one term a network could learn
# --------------------------------------------------------------------------------------
def group_examples():
    from scipy.integrate import solve_ivp

    with plt.rc_context(STYLE):
        # ---- a pendulum with unknown friction
        g, L, c = 9.81, 1.0, 0.35
        sol = solve_ivp(lambda t, s: [s[1], -g / L * np.sin(s[0]) - c * s[1]], (0, 12), [1.2, 0],
                        t_eval=np.linspace(0, 12, 600), rtol=1e-9)
        fig, ax = plt.subplots(figsize=(5.2, 3.1))
        ax.plot(sol.t, sol.y[0], color=BLUE, lw=2.4)
        ax.plot(sol.t, 1.2 * np.exp(-c / 2 * sol.t), color=CMU_RED, lw=1.4, ls="--")
        ax.annotate("decay set by the\nfriction term", xy=(6.5, 1.2 * np.exp(-c / 2 * 6.5)),
                    xytext=(7.4, 0.95), color=CMU_RED, fontsize=13,
                    arrowprops=dict(arrowstyle="->", color=CMU_RED))
        ax.set_xlabel("time (s)")
        ax.set_ylabel("angle $\\theta$ (rad)")
        ax.set_ylim(-1.3, 1.45)
        save(fig, "ex-pendulum.png")

        # ---- heat conduction in a rod with an unknown heat source
        nz = 41
        z = np.linspace(0, 1, nz)
        dz = z[1] - z[0]

        def rod(t, T):
            d = np.zeros_like(T)
            d[1:-1] = (T[2:] - 2 * T[1:-1] + T[:-2]) / dz**2 + 4.0 * (1 + 0.8 * T[1:-1])
            return d

        times = [0.01, 0.03, 0.08, 0.5]
        sol = solve_ivp(rod, (0, 0.5), np.zeros(nz), t_eval=times, method="BDF", rtol=1e-8)
        fig, ax = plt.subplots(figsize=(5.2, 3.1))
        shades = [GOLD, ORANGE, CMU_RED, "#7a0b1c"]
        for j, tj in enumerate(times):
            ax.plot(z, sol.y[:, j], color=shades[j], lw=2.4, label=f"t = {tj}")
        ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=11)
        ax.text(0.02, 0.9, "heat released inside the rod,\n$q(T)$, warms the middle",
                color=CMU_RED, fontsize=12, va="top")
        ax.set_xlabel("position along the rod $z$")
        ax.set_ylabel("temperature $T$")
        ax.set_ylim(0, 0.95)
        save(fig, "ex-heat.png")

        # ---- an exothermic CSTR (Bequette's example) with unknown kinetics
        q, V, Cf, Tf, rho, cp, dH, ER, k0, UA, Tc = (100, 100, 1.0, 350, 1000, 0.239, -5e4,
                                                    8750, 7.2e10, 5e4, 310)

        def cstr(t, s):
            C, T = s
            r = k0 * np.exp(-ER / T) * C
            return [q / V * (Cf - C) - r,
                    q / V * (Tf - T) + (-dH) / (rho * cp) * r - UA / (V * rho * cp) * (T - Tc)]

        sol = solve_ivp(cstr, (0, 10), [1.0, 300], t_eval=np.linspace(0, 10, 400), rtol=1e-9)
        fig, ax = plt.subplots(figsize=(5.2, 3.1))
        ax.plot(sol.t, sol.y[1], color=CMU_RED, lw=2.4)
        ax.set_ylabel("temperature $T$ (K)", color=CMU_RED)
        ax2 = ax.twinx()
        ax2.plot(sol.t, sol.y[0], color=BLUE, lw=2.4)
        ax2.set_ylabel("concentration $C$ (mol/L)", color=BLUE)
        ax2.spines["right"].set_visible(True)
        ax2.spines["top"].set_visible(False)
        i = int(np.argmax(sol.y[1]))
        ax.annotate("ignition: the reaction releases\nheat faster than it is removed", xy=(sol.t[i], sol.y[1][i]),
                    xytext=(2.6, 455), color=CMU_RED, fontsize=12,
                    arrowprops=dict(arrowstyle="->", color=CMU_RED))
        ax.set_xlabel("time (min)")
        save(fig, "ex-cstr.png")

        # ---- a tank draining through a valve whose flow law is unknown
        A, qin, cv = 1.0, 0.5, 0.35
        sol = solve_ivp(lambda t, h: [(qin - cv * np.sqrt(max(h[0], 0))) / A], (0, 25), [0.2],
                        t_eval=np.linspace(0, 25, 300), rtol=1e-9)
        hs = (qin / cv) ** 2
        fig, ax = plt.subplots(figsize=(5.2, 3.1))
        ax.plot(sol.t, sol.y[0], color=BLUE, lw=2.4)
        ax.axhline(hs, color=MUTED, lw=1, ls="--")
        ax.annotate("level where outflow = inflow:\nset by the valve law", xy=(18, hs),
                    xytext=(5.5, 0.9), color=CMU_RED, fontsize=13,
                    arrowprops=dict(arrowstyle="->", color=CMU_RED))
        ax.set_xlabel("time (min)")
        ax.set_ylabel("level $h$ (m)")
        ax.set_ylim(0, hs * 1.15)
        save(fig, "ex-tank.png")
    compose(["ex-pendulum.png", "ex-heat.png", "ex-cstr.png", "ex-tank.png"], "sciml-examples.png", 2)


# --------------------------------------------------------------------------------------
# vectorfield: a residual network is a sequence of steps; a neural ODE is a vector field
# --------------------------------------------------------------------------------------
def group_vectorfield():
    from scipy.integrate import solve_ivp

    def f(t, h):
        return 0.9 * np.sin(1.6 * t) - 0.55 * h

    starts = np.linspace(-2, 2, 6)
    with plt.rc_context(STYLE):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 4.9), sharey=True)
        for h0 in starts:
            ts, hs = [0.0], [h0]
            for _ in range(6):
                hs.append(hs[-1] + 1.0 * f(ts[-1], hs[-1]))
                ts.append(ts[-1] + 1.0)
            a1.plot(ts, hs, "-o", color=ORANGE, lw=1.8, ms=7)
        a1.set_title("Residual or recurrent network:\n$h_{k+1} = h_k + f(h_k;\\,\\theta)$, "
                     "six fixed steps", fontsize=15)
        a1.set_xlabel("step $k$ (layer, or time step)")
        a1.set_ylabel("hidden state $h$")
        a1.annotate("the network learns this\njump, for this step size", xy=(2.5, 0.92),
                    xytext=(2.6, 2.35), color=ORANGE, fontsize=13,
                    arrowprops=dict(arrowstyle="->", color=ORANGE))
        T, H = np.meshgrid(np.linspace(0, 6, 25), np.linspace(-2.6, 2.6, 15))
        U, Vv = np.ones_like(T), f(T, H)
        nrm = np.hypot(U, Vv)
        a2.quiver(T, H, U / nrm, Vv / nrm, color=MUTED, alpha=0.55, angles="xy",
                  scale=34, width=0.0028)
        for h0 in starts:
            s = solve_ivp(f, (0, 6), [h0], rtol=1e-6, atol=1e-8)
            dense = solve_ivp(f, (0, 6), [h0], t_eval=np.linspace(0, 6, 300), rtol=1e-9)
            a2.plot(dense.t, dense.y[0], color=BLUE, lw=2.2)
            a2.plot(s.t, s.y[0], "o", color=BLUE, ms=5, mfc="white")
        a2.set_title("Neural ODE: $dh/dt = f(h, t;\\,\\theta)$, a vector field;\n"
                     "the solver chooses where to evaluate it", fontsize=15)
        a2.set_xlabel("time $t$ (or depth)")
        a2.annotate("the network learns\nthese arrows", xy=(4.4, -1.55), xytext=(3.6, -2.55),
                    color=BLUE, fontsize=13, arrowprops=dict(arrowstyle="->", color=BLUE))
        a1.set_ylim(-2.9, 2.9)
        save(fig, "resnet-vs-ode.png")


# --------------------------------------------------------------------------------------
# projection: a network with a projection layer, trained on a splitter's mass balance
# --------------------------------------------------------------------------------------
def group_projection():
    import jax
    import jax.numpy as jnp
    import optax

    jax.config.update("jax_enable_x64", True)
    F = 10.0
    A = jnp.array([[1.0, 1.0]])
    rng = np.random.default_rng(SEED)

    def split(u):                                  # true fraction of the feed to outlet 1
        return 0.2 + 0.6 / (1 + np.exp(-8 * (u - 0.5)))

    u_tr = np.sort(rng.uniform(0, 1, 40))
    y_true = np.stack([F * split(u_tr), F * (1 - split(u_tr))], 1)
    y_meas = y_true + rng.normal(0, 0.4, y_true.shape)
    u_te = np.linspace(0, 1, 200)
    y_te = np.stack([F * split(u_te), F * (1 - split(u_te))], 1)

    def init(key, sizes):
        params = []
        for a, b in zip(sizes[:-1], sizes[1:]):
            key, sub = jax.random.split(key)
            params.append((jax.random.normal(sub, (a, b)) * np.sqrt(1 / a), jnp.zeros(b)))
        return params

    def net(params, u):
        h = u[:, None]
        for W, b in params[:-1]:
            h = jnp.tanh(h @ W + b)
        W, b = params[-1]
        return 5.0 + h @ W + b

    def project(y_raw):                            # y = y~ - A^T (A A^T)^-1 (A y~ - b)
        viol = y_raw @ A.T - F
        return y_raw - viol @ jnp.linalg.inv(A @ A.T) @ A

    def loss_plain(p):
        return jnp.mean((net(p, jnp.array(u_tr)) - y_meas) ** 2)

    def loss_proj(p):
        return jnp.mean((project(net(p, jnp.array(u_tr))) - y_meas) ** 2)

    epochs = 2000
    snap = sorted(set([0] + [int(s) for s in np.round(np.geomspace(1, epochs, 44))]))

    def train(lossf, with_proj):
        p = init(jax.random.PRNGKey(SEED), [1, 16, 16, 2])
        opt = optax.adam(1e-2)
        state = opt.init(p)

        @jax.jit
        def step(p, state):
            g = jax.grad(lossf)(p)
            upd, state = opt.update(g, state, p)
            return optax.apply_updates(p, upd), state

        frames = []
        for i in range(epochs + 1):
            if i in snap:
                raw_tr = np.asarray(net(p, jnp.array(u_tr)))
                out_tr = np.asarray(project(raw_tr)) if with_proj else raw_tr
                raw_te = np.asarray(net(p, jnp.array(u_te)))
                out_te = np.asarray(project(raw_te)) if with_proj else raw_te
                frames.append(dict(
                    epoch=i, raw=raw_tr, out=out_tr, loss=float(lossf(p)),
                    rmse=float(np.sqrt(np.mean((out_te - y_te) ** 2))),
                    viol=float(np.max(np.abs(out_te.sum(1) - F)))))
            if i < epochs:
                p, state = step(p, state)
        return frames

    plain, proj = train(loss_plain, False), train(loss_proj, True)
    a, b = plain[-1], proj[-1]
    print(f"  {epochs} Adam epochs, 40 noisy samples, noise SD 0.4 on each outlet flow:")
    print(f"    test RMSE against the true flows: plain {a['rmse']:.3f}, projected {b['rmse']:.3f}")
    print(f"    largest balance violation |y1 + y2 - F| on the test inputs: plain "
          f"{a['viol']:.3f}, projected {b['viol']:.1e}")
    print(f"    measurements' own violation: mean |y1 + y2 - F| = "
          f"{np.mean(np.abs(y_meas.sum(1) - F)):.2f}")

    cache_put("proj", dict(
        F=F, u=r(u_tr, 3), meas=[r(v, 3) for v in y_meas.T],
        frames=[dict(epoch=fp["epoch"], raw=[r(v, 3) for v in fp["raw"].T],
                     out=[r(v, 3) for v in fp["out"].T], loss=round(fp["loss"], 4),
                     rmse=round(fp["rmse"], 4), viol=float(f"{max(fp['viol'], 1e-16):.3g}"),
                     plain_out=[r(v, 3) for v in fq["out"].T], plain_rmse=round(fq["rmse"], 4),
                     plain_viol=float(f"{fq['viol']:.3g}"))
                for fp, fq in zip(proj, plain)]))

    with plt.rc_context(STYLE):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5))
        xs = np.linspace(0, F, 2)
        a1.plot(xs, F - xs, color=GREEN, lw=3, label="balance $y_1 + y_2 = F$")
        a1.plot(*y_meas.T, "o", color=GRAY, ms=5, label="measurements (noisy)")
        a1.plot(*b["raw"].T, "o", color=ORANGE, ms=5, label="raw network output $\\tilde y$")
        a1.plot(*b["out"].T, "o", color=BLUE, ms=5, label="after the projection layer $y$")
        for p0, p1 in zip(b["raw"], b["out"]):
            a1.plot([p0[0], p1[0]], [p0[1], p1[1]], color=MUTED, lw=0.8)
        a1.set_xlabel("outlet flow $y_1$")
        a1.set_ylabel("outlet flow $y_2$")
        a1.set_aspect("equal")
        a1.set_xlim(1.5, 8.8)
        a1.set_ylim(1.2, 8.5)
        a1.legend(loc="upper center", fontsize=11)
        ep = [f["epoch"] for f in proj][1:]
        a2.semilogy(ep, [f["viol"] for f in plain][1:], color=ORANGE, lw=2.4,
                    label="plain network")
        a2.semilogy(ep, [max(f["viol"], 1e-16) for f in proj][1:], color=BLUE, lw=2.4,
                    label="with projection layer")
        a2.set_xscale("log")
        a2.set_xlabel("training epoch")
        a2.set_ylabel("largest $|y_1 + y_2 - F|$")
        a2.legend(loc="upper right", bbox_to_anchor=(1.0, 0.8))
        a2.annotate("machine precision, every epoch", xy=(300, 1e-15), xytext=(2, 1e-7),
                    color=BLUE, arrowprops=dict(arrowstyle="->", color=BLUE))
        save(fig, "projection-train.png")


# --------------------------------------------------------------------------------------
# pictures: drawn from the cached results of pinn and seqsim, no training
# --------------------------------------------------------------------------------------
def draw_spring_mass(ax, xi, labels=True):
    """A hanging spring-mass with a damper beside the spring; x > 0 lifts the mass."""
    grayc, green = "#9a9a9a", "#2b9a2b"
    ax.set_xlim(-0.75, 0.75)
    ax.set_ylim(-1.75, 1.55)
    ax.axis("off")
    ax.add_patch(Rectangle((-0.5, 1.22), 1.0, 0.18, fc=grayc, ec="none"))
    y_mass = 0.0 - 0.6 * xi
    s = np.linspace(0, 1, 400)
    ax.plot(-0.18 + 0.16 * np.sin(2 * np.pi * 7 * s), 1.22 + (y_mass + 0.2 - 1.22) * s,
            color=grayc, lw=3.2, solid_capstyle="round")
    ax.plot([0.26, 0.26], [1.22, 0.62], color=INK, lw=2.4)
    ax.add_patch(Rectangle((0.16, y_mass + 0.2), 0.2, 0.62 - (y_mass + 0.2) + 0.25,
                           fc="none", ec=INK, lw=2.4))
    ax.plot([0.19, 0.33], [0.62, 0.62], color=INK, lw=3)
    ax.add_patch(Rectangle((-0.42, y_mass - 0.2), 0.84, 0.4, fc=green, ec="none"))
    if labels:
        ax.text(0, y_mass, "$m$", color="white", fontsize=22, ha="center", va="center")
        ax.text(-0.52, 0.75, "$k$", fontsize=22, ha="center")
        ax.text(0.5, 0.75, "$\\mu$", fontsize=22, ha="center")
        ax.annotate("", xy=(-0.66, y_mass - 0.2), xytext=(-0.66, -0.2),
                    arrowprops=dict(arrowstyle="-|>", color=CMU_RED, lw=2.2))
        ax.text(-0.71, -0.55, "$x$", fontsize=22, color=CMU_RED, ha="right")
        ax.plot([-0.75, -0.55], [-0.2, -0.2], color=CMU_RED, lw=1.2, ls=":")


def group_pictures():
    pinn = json.loads((CACHE / "pinn.json").read_text())
    seq = json.loads((CACHE / "seqsim.json").read_text())
    t, exact = np.array(pinn["t"]), np.array(pinn["exact"])
    td, xd, tp = np.array(pinn["t_data"]), np.array(pinn["x_data"]), np.array(pinn["t_phys"])
    with plt.rc_context(STYLE):
        # ---- data points and collocation points on the spring-mass
        fig, (a0, ax) = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [1, 3.6]})
        draw_spring_mass(a0, 1.0)
        ax.axvspan(0, td[-1], color=GRAY, alpha=0.12, lw=0)
        ax.plot(t, exact, color=GRAY, lw=3, alpha=0.45, ls="--", label="the motion we want")
        ax.plot(td, xd, "o", color=INK, ms=8, label="data points: $x$ measured")
        ax.plot(tp, np.full_like(tp, -1.32), "^", color=GREEN, ms=8,
                label="collocation points: no measurement")
        for v in tp:
            ax.plot([v, v], [-1.32, 1.1], color=GREEN, lw=0.6, alpha=0.25)
        ax.annotate("data loss: match the measured $x_i$", xy=(td[3], xd[3]), xytext=(0.42, 0.95),
                    fontsize=15, arrowprops=dict(arrowstyle="->", color=INK))
        ax.annotate("physics loss: here we only ask\n$m\\,x'' + \\mu\\,x' + k\\,x = 0$",
                    xy=(tp[30], -1.3), xytext=(0.6, -0.95), fontsize=15, color=GREEN,
                    arrowprops=dict(arrowstyle="->", color=GREEN))
        ax.set_xlabel("time $t$ (s)")
        ax.set_ylabel("displacement $x$ (m)")
        ax.set_ylim(-1.45, 1.3)
        ax.legend(loc="upper right", ncol=3, fontsize=12, bbox_to_anchor=(1.0, 1.16))
        save(fig, "collocation.png")

        # ---- the PINN after training, small, for the PINN introduction
        last = pinn["frames"][-1]
        fig, ax = plt.subplots(figsize=(6.2, 3.0))
        ax.axvspan(0, td[-1], color=GRAY, alpha=0.12, lw=0)
        ax.plot(t, exact, color=GRAY, lw=5, alpha=0.45, label="exact")
        ax.plot(t, last["pinn"], color=BLUE, lw=2.2, ls="--", label="PINN")
        ax.plot(td, xd, "o", color=INK, ms=5, label="data")
        ax.plot(tp, np.full_like(tp, -1.15), "^", color=GREEN, ms=5, label="collocation")
        ax.set_xlabel("time $t$ (s)")
        ax.set_ylabel("$x$ (m)")
        ax.set_ylim(-1.25, 1.2)
        ax.legend(loc="upper right", ncol=2, fontsize=10)
        save(fig, "pinn-mini.png")

        # ---- the sequential loop, one picture per station
        m = 1.0
        t_obs, x_obs = np.array(seq["t_obs"]), np.array(seq["x_obs"])
        tg = np.array(seq["t"])
        f0, fN = seq["seq"][0], seq["seq"][-1]
        mus, ks = np.linspace(0.05, 3.0, 120), np.linspace(100, 520, 160)
        SSE = np.array([[np.sum((oscillator(t_obs, m, a, b) - x_obs) ** 2) for a in mus] for b in ks])

        def contour(ax):
            cs = ax.contourf(mus, ks, np.log10(SSE), levels=18, cmap="Greys_r", alpha=0.85)
            ax.plot(1.0, 400, "*", color=GOLD, ms=16, mec=INK, label="true")
            ax.plot(f0["mu"], f0["k"], "o", color=ORANGE, ms=10, mec=INK)
            ax.set_xlabel("damping $\\mu$")
            ax.set_ylabel("stiffness $k$")
            return cs

        fig, ax = plt.subplots(figsize=(4.4, 3.0))
        contour(ax)
        ax.annotate("start: $\\theta_0$", xy=(f0["mu"], f0["k"]), xytext=(2.0, 260), color="white",
                    fontsize=13, fontweight="bold", arrowprops=dict(arrowstyle="->", color="white"))
        save(fig, "loop-guess.png")
        fig, ax = plt.subplots(figsize=(4.4, 3.0))
        sse = [fr["sse"] for fr in seq["seq"]]
        ax.plot(range(len(sse)), sse, "-o", color=ORANGE, ms=3.5, lw=1.6)
        ax.text(len(sse) * 0.5, sse[0] * 0.92, "each update lowers the loss", ha="center",
                color=ORANGE, fontsize=12)
        ax.annotate(f"stops at {sse[-1]:.1f}", xy=(len(sse) - 1, sse[-1]),
                    xytext=(len(sse) * 0.45, sse[-1] + 3.5), color=ORANGE, fontsize=12,
                    arrowprops=dict(arrowstyle="->", color=ORANGE))
        ax.set_ylim(0, sse[0] * 1.1)
        ax.set_xlabel("update")
        ax.set_ylabel("loss $L$")
        save(fig, "loop-update.png")
        for name, show_data in (("loop-simulate.png", False), ("loop-loss.png", True)):
            fig, ax = plt.subplots(figsize=(4.4, 3.0))
            xs = np.array(f0["x"])
            ax.plot(tg, xs, color=ORANGE, lw=2)
            if show_data:
                xi = np.interp(t_obs, tg, xs)
                for a_, b_, c_ in zip(t_obs, x_obs, xi):
                    ax.plot([a_, a_], [b_, c_], color=CMU_RED, lw=1)
                ax.plot(t_obs, x_obs, "o", color=INK, ms=3)
                ax.text(1.95, 1.0, f"SSE = {f0['sse']:.1f}", ha="right", color=CMU_RED, fontsize=13)
            else:
                ax.text(1.95, 1.0, "$\\mu = 2,\\ k = 150$", ha="right", color=ORANGE, fontsize=13)
            ax.set_xlabel("time (s)")
            ax.set_ylabel("$x$ (m)")
            ax.set_ylim(-1.2, 1.25)
            save(fig, name)
        compose(["loop-guess.png", "loop-simulate.png", "loop-loss.png", "loop-update.png"],
                "seq-loop.png", 4)

        # ---- the two final fits, for the result cards
        for name, frames, col in (("final-seq.png", seq["seq"], ORANGE), ("final-sim.png", seq["sim"], BLUE)):
            fig, ax = plt.subplots(figsize=(6.0, 2.6))
            ax.plot(t_obs, x_obs, "o", color=INK, ms=3.5, label="data")
            ax.plot(tg, frames[-1]["x"], color=col, lw=2.2, label="fitted model")
            ax.set_xlabel("time (s)")
            ax.set_ylabel("$x$ (m)")
            ax.set_ylim(-1.2, 1.3)
            ax.legend(loc="upper right", ncol=2, fontsize=11)
            save(fig, name)

        # ---- from one simulated curve to a discretized NLP, five frames on one set of axes
        h, T0w, T1w = 0.02, 0.0, 0.6
        x_fin = np.array(seq["sim"][-1]["x"])
        x_init = np.interp(tg, t_obs, x_obs)
        keep = tg <= T1w + 1e-9
        tw, xi_w, xf_w = tg[keep], x_init[keep], x_fin[keep]
        ow = t_obs <= T1w + 1e-9
        v_i = np.gradient(xi_w, tw)
        a_i = -(f0["mu"] * v_i + f0["k"] * xi_w) / m
        defect = np.abs(np.diff(v_i) - h / 2 * (a_i[1:] + a_i[:-1]))
        elems = np.arange(0, T1w + 1e-9, 0.1)
        titles = ["Sequential: the solver returns one curve $x(t;\\theta)$ for the current $\\theta$",
                  "Simultaneous: cut time into finite elements",
                  "Every state at every point becomes an unknown; start them on the data",
                  "The model equations do not hold yet: one residual per point (red)",
                  "One NLP moves all the points and $\\theta$ together, until every equation holds"]
        for n in range(5):
            fig, ax = plt.subplots(figsize=(11, 4.0))
            ax.plot(t_obs[ow], x_obs[ow], "o", color=INK, ms=6, zorder=5)
            if n == 0:
                ax.plot(tg[keep], np.array(f0["x"])[keep], color=ORANGE, lw=2.6)
            if n >= 1:
                for e in elems:
                    ax.axvline(e, color=MUTED, lw=1.2, ls=":")
            if n in (2, 3):
                ax.plot(tw, xi_w, "o", color=BLUE, ms=7, mfc="white", mew=1.8, zorder=6)
            if n == 3:
                sc = 0.12 / defect.max()
                for tt_, xx_, d_ in zip(tw[1:], xi_w[1:], defect):
                    ax.plot([tt_, tt_], [xx_, xx_ + sc * d_ + 0.02], color=CMU_RED, lw=2.2)
            if n == 4:
                ax.plot(tw, xf_w, "-o", color=BLUE, ms=7, lw=1.4, zorder=6)
            ax.set_title(titles[n], fontsize=16, loc="left")
            ax.set_xlim(-0.01, T1w + 0.01)
            ax.set_ylim(-1.25, 1.35)
            ax.set_xlabel("time (s)")
            ax.set_ylabel("$x$ (m)")
            fig.subplots_adjust(left=0.07, right=0.985, bottom=0.14, top=0.89)
            fig.savefig(HERE / f"disc-{n + 1}.png", bbox_inches=fig.bbox_inches)   # one size for all five
            plt.close(fig)
            print(f"  wrote disc-{n + 1}.png")

        # ---- collocation: on each element a polynomial through the points; at each
        # collocation point its slope must equal the slope the model gives
        mu_c, k_c = 1.0, 400.0
        d_c = mu_c / 2
        w_c = np.sqrt(k_c - d_c**2)

        def xa(tq):
            return np.exp(-d_c * tq) * (np.cos(w_c * tq) + d_c / w_c * np.sin(w_c * tq))

        def va(tq):
            return -np.exp(-d_c * tq) * (w_c + d_c**2 / w_c) * np.sin(w_c * tq)

        taus = np.array([0.0, 0.155051, 0.644949, 1.0])
        hlen = 0.1
        elem_cols = (BLUE, ORANGE, GREEN)

        def lagrange(tp, tq, xq):
            out = np.zeros_like(tq)
            for j in range(len(tp)):
                lj = np.ones_like(tq)
                for m_ in range(len(tp)):
                    if m_ != j:
                        lj *= (tq - tp[m_]) / (tp[j] - tp[m_])
                out += xq[j] * lj
            return out

        fig, a1 = plt.subplots(figsize=(11.5, 4.4))
        tg_ = np.linspace(0, 0.3, 400)
        a1.plot(tg_, xa(tg_), color=GRAY, lw=7, alpha=0.4, label="solution of the ODE")
        for e in range(3):
            tp_ = e * hlen + hlen * taus
            tq = np.linspace(tp_[0], tp_[-1], 100)
            a1.plot(tq, lagrange(tp_, tq, xa(tp_)), color=elem_cols[e], lw=2.2,
                    label=f"polynomial on element {e + 1}")
            a1.plot(tp_[0], xa(tp_[0]), "s", color=elem_cols[e], ms=8)
            a1.plot(tp_[1:], xa(tp_[1:]), "o", color=elem_cols[e], ms=8)
            for tj in tp_[1:]:
                dt_ = 0.005
                a1.plot([tj - dt_, tj + dt_], [xa(tj) - va(tj) * dt_, xa(tj) + va(tj) * dt_],
                        color=CMU_RED, lw=2.6, zorder=5)
            a1.axvline(e * hlen, color=MUTED, lw=1, ls=":")
            a1.text(e * hlen + hlen / 2, 1.13, f"element {e + 1}", ha="center", color=MUTED, fontsize=13)
        a1.axvline(0.3, color=MUTED, lw=1, ls=":")
        tj = hlen + hlen * taus[1]
        a1.annotate("at each collocation point (dots), the red slope:\nslope of the polynomial = $f(x)$ from the model",
                    xy=(tj, xa(tj) + 0.05), xytext=(0.105, 0.72), color=CMU_RED,
                    fontsize=13, arrowprops=dict(arrowstyle="->", color=CMU_RED))
        a1.set_xlabel("$t$")
        a1.set_ylabel("$x$")
        a1.set_ylim(-1.15, 1.25)
        handles, labels = a1.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=4, fontsize=12,
                   bbox_to_anchor=(0.5, -0.1))
        save(fig, "collocation-poly.png")


def group_cho():
    """Pictures from Victor Alves's CHO glycosylation slides (attic/cho_glycan_slides.pdf,
    synthetic data from a mechanistic model, shared with his permission), and Fig. 5 of
    Wang, Harcum and Xie (arXiv 2412.03883, CC BY 4.0), a CHO metabolic network."""
    import subprocess
    import urllib.request

    from PIL import Image

    src = REPO / "attic" / "cho_glycan_slides.pdf"
    CACHE.mkdir(exist_ok=True)
    if src.exists():
        subprocess.run(["pdftoppm", "-f", "7", "-l", "7", "-r", "300", "-png", str(src),
                        str(CACHE / "cho")], check=True)
        page = Image.open(next(CACHE.glob("cho-*7.png"))).convert("RGB")
        page.crop((300, 120, 1590, 950)).save(HERE / "cho-pathway.png", optimize=True)
        subprocess.run(["pdfimages", "-f", "10", "-l", "12", "-png", str(src),
                        str(CACHE / "choimg")], check=True)
        traj = Image.open(CACHE / "choimg-000.png").convert("RGB")
        traj = traj.crop((0, int(traj.height * 0.075), traj.width, traj.height))
        traj.resize((traj.width // 2, traj.height // 2)).save(HERE / "cho-trajectories.png",
                                                               optimize=True)
        arr = np.asarray(Image.open(HERE / "cho-trajectories.png"))
        h_, w_ = arr.shape[:2]
        with plt.rc_context(STYLE):
            fig, ax = plt.subplots(figsize=(10, 10 * h_ / w_ + 0.6))
            ax.imshow(arr, extent=(0, w_, h_, 0))
            ax.set_xlim(-10, w_ + 10)
            ax.set_ylim(h_ + 40, -110)
            ax.axis("off")
            for (y0_, y1_, col, lab) in ((0.0, 0.655, BLUE, "process scale: cells, nutrients, metabolites, antibody"),
                                         (0.665, 1.0, ORANGE, "product quality: glycan fractions G0F, G1F, G2F")):
                ax.add_patch(Rectangle((4, y0_ * h_ + 4), w_ - 8, (y1_ - y0_) * h_ - 8, fill=False,
                                       ec=col, lw=3.5))
            ax.text(10, -20, "process scale: cells, nutrients, metabolites, antibody",
                    color=BLUE, fontsize=15, va="bottom")
            ax.text(10, 0.665 * h_ + 2, "product quality (Golgi scale): glycan fractions",
                    color=ORANGE, fontsize=15, va="top", ha="left",
                    bbox=dict(fc="white", ec="none", pad=1))
            save(fig, "cho-trajectories-scales.png")
        comp = Image.open(CACHE / "choimg-004.png").convert("RGB")
        comp.resize((comp.width // 2, comp.height // 2)).save(HERE / "cho-composition.png",
                                                               optimize=True)
        print("  wrote cho-pathway.png, cho-trajectories.png, cho-composition.png")
    else:
        print(f"  skipped the CHO pictures: {src} is not present")
    pdf = CACHE / "wang-2412.03883.pdf"
    if not pdf.exists():
        urllib.request.urlretrieve("https://arxiv.org/pdf/2412.03883v2", pdf)
    subprocess.run(["pdftoppm", "-f", "10", "-l", "10", "-r", "300", "-png", str(pdf),
                    str(CACHE / "wang")], check=True)
    page = Image.open(next(CACHE.glob("wang-*10.png"))).convert("RGB")
    page.crop((821, 1750, 1726, 2657)).save(HERE / "cho-network.png", optimize=True)
    print("  wrote cho-network.png")


# --------------------------------------------------------------------------------------
def write_widget_data():
    data = {}
    for name in ("pinn", "seqsim", "fedbatch", "proj"):
        p = CACHE / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())
    data["source"] = "generated by lectures/l13/figures/make_figures.py"
    text = ("/* Generated by lectures/l13/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l13 = " + json.dumps(data, separators=(",", ":")) +
            ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB; "
          f"entries: {', '.join(k for k in data if k != 'source')})")


GROUPS = {"pinn": group_pinn, "seqsim": group_seqsim, "fedbatch": group_fedbatch,
          "projection": group_projection, "pictures": group_pictures,
          "examples": group_examples, "vectorfield": group_vectorfield,
          "diagrams": group_diagrams, "schematics": group_schematics, "mab": group_mab,
          "cho": group_cho}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(f"[{name}]")
        GROUPS[name]()
    write_widget_data()
