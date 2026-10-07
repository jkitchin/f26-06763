#!/usr/bin/env python3
"""Generate the two L13 worked examples.

    l13-pinn-jax.ipynb      a plain network and a physics-informed network (PINN), built from
                            scratch in JAX and trained with Optax's Adam on ten points of a
                            damped spring-mass.
    l13-neural-dae.ipynb    the fed-batch bioreactor as a neural ODE trained sequentially with
                            Diffrax, then as a neural DAE in SiNDAE, and a new batch predicted
                            by both.

Every code block on the L13 slides is a cell here, verbatim, in the order of the lecture. The
other cells make the data, print and plot. The data and seeds are those of
figures/make_figures.py, so the numbers printed are the numbers in the notes and slides.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed copies
carry real output. After regenerating, execute both and refresh the Colab cell:

    python3 lectures/l13/build_notebooks.py
    cd lectures/l13 && uv run --no-project --python 3.12 --with sindae --with optax \
        --with diffrax --with scipy --with pandas --with matplotlib --with nbclient \
        --with nbformat --with ipykernel \
        python -c "
import nbformat
from nbclient import NotebookClient
for name in ('l13-pinn-jax.ipynb', 'l13-neural-dae.ipynb'):
    nb = nbformat.read(name, as_version=4)
    NotebookClient(nb, timeout=900, resources={'metadata': {'path': '.'}}).execute()
    nbformat.write(nb, name)
"
    python3 tools/colab_setup.py --write lectures/l13/l13-pinn-jax.ipynb
    python3 tools/colab_setup.py --write lectures/l13/l13-neural-dae.ipynb
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from colab_setup import with_colab_cell  # noqa: E402


class Book:
    def __init__(self):
        self.cells, self.n = [], 0

    def _id(self, kind):
        self.n += 1
        return f"{kind}-{self.n:02d}"

    def md(self, text):
        self.cells.append({"cell_type": "markdown", "id": self._id("md"), "metadata": {},
                           "source": text.strip("\n").splitlines(keepends=True)})

    def code(self, text):
        self.cells.append({"cell_type": "code", "id": self._id("code"), "execution_count": None,
                           "metadata": {}, "outputs": [],
                           "source": text.strip("\n").splitlines(keepends=True)})

    def write(self, name):
        out = HERE / name
        cells = with_colab_cell(self.cells, out)
        nb = {"cells": cells, "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
        out.write_text(json.dumps(nb, indent=1) + "\n")
        print(f"wrote {out.name} ({len(cells)} cells)")


# ======================================================================================
# l13-pinn-jax.ipynb
# ======================================================================================
b = Book()
b.md("""
# L13 worked example: a physics-informed network in JAX

A damped spring-mass, measured during its first 0.36 s. A plain network and a
physics-informed neural network (PINN) learn from the same ten points. Where is the mass after
the data run out?

$$
m\\,\\frac{d^2x}{dt^2} + \\mu\\,\\frac{dx}{dt} + k\\,x = 0, \\qquad x(0) = 1\\ \\text{m}, \\quad \\frac{dx}{dt}(0) = 0
$$

$m = 1$ kg, $\\mu = 4$ N·s/m, $k = 400$ N/m.

## 1. The data

`exact(t)` is the closed-form solution: it makes the data and scores the models.
""")
b.code("""
import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
import numpy as np
import optax

jax.config.update("jax_enable_x64", True)

m, mu, k = 1.0, 4.0, 400.0


def exact(t):
    d = mu / (2 * m)
    w = np.sqrt(k / m - d**2)
    return np.exp(-d * t) * (np.cos(w * t) + d / w * np.sin(w * t))


t_data = np.linspace(0, 0.36, 10)       # 10 measurements, first 0.36 s
x_data = exact(t_data)
t_phys = np.linspace(0, 1, 40)          # 40 collocation points, the whole second
t_plot = np.linspace(0, 1, 151)
x_true = exact(t_plot)

fig, ax = plt.subplots(figsize=(8, 3.5))
ax.plot(
    t_plot,
    x_true,
    color="0.7",
    lw=4,
    label="exact solution",
)
ax.plot(t_data, x_data, "ko", label="10 measurements")
ax.axvspan(0, 0.36, color="0.9")
ax.set_xlabel("time t (s)")
ax.set_ylabel("displacement x (m)")
ax.legend()
plt.show()
""")
b.md("""
## 2. The network

Three hidden layers of 32 tanh units. `x_nn` takes one time, the form `jax.grad` needs.
""")
b.code("""
def init(key, sizes):
    params = []
    for n_in, n_out in zip(sizes[:-1], sizes[1:]):
        key, sub = jax.random.split(key)
        W = jax.random.normal(sub, (n_in, n_out)) * np.sqrt(1 / n_in)
        params.append((W, jnp.zeros(n_out)))
    return params

def net(params, t):
    h = t[:, None]
    for W, b in params[:-1]:
        h = jnp.tanh(h @ W + b)
    W, b = params[-1]
    return (h @ W + b)[:, 0]

def x_nn(params, t):
    return net(params, jnp.array([t]))[0]

params0 = init(jax.random.PRNGKey(0), [1, 32, 32, 32, 1])
""")
b.code("""
print("weights and biases:", sum(W.size + b.size for W, b in params0))
""")
b.md("""
## 3. The two losses

The data loss uses the ten measurements. The physics loss uses the residual at the 40
collocation points:

$$
r(t_j) = m\\,x_\\text{NN}''(t_j) + \\mu\\,x_\\text{NN}'(t_j) + k\\,x_\\text{NN}(t_j)
$$
""")
b.code("""
dx = jax.grad(x_nn, argnums=1)      # dx/dt
ddx = jax.grad(dx, argnums=1)       # d2x/dt2

def residual(params, ts):
    x = jax.vmap(lambda t: x_nn(params, t))(ts)
    v = jax.vmap(lambda t: dx(params, t))(ts)
    a = jax.vmap(lambda t: ddx(params, t))(ts)
    return m * a + mu * v + k * x

def data_loss(params):
    return jnp.mean((net(params, jnp.array(t_data)) - x_data) ** 2)

def physics_loss(params):
    return jnp.mean(residual(params, jnp.array(t_phys)) ** 2)

lam = 1e-4

def pinn_loss(params):
    return data_loss(params) + lam * physics_loss(params)
""")
b.code("""
residual0 = residual(params0, jnp.array([0.5]))[0]
print("residual of the untrained network at t = 0.5 s:", float(residual0))
""")
b.md("""
## 4. Training

Adam, 30,000 steps, the same start for both networks: only the loss differs. About 10 s.
""")
b.code("""
def train(loss, steps=30_000):
    opt = optax.adam(1e-3)
    params = params0
    state = opt.init(params)

    @jax.jit
    def step(params, state):
        grads = jax.grad(loss)(params)
        updates, state = opt.update(grads, state, params)
        return optax.apply_updates(params, updates), state

    for _ in range(steps):
        params, state = step(params, state)
    return params

p_nn = train(data_loss)
p_pinn = train(pinn_loss)
""")
b.md("""
## 5. After the data run out
""")
b.code("""
x_nn_plot = np.asarray(net(p_nn, jnp.array(t_plot)))
x_pinn_plot = np.asarray(net(p_pinn, jnp.array(t_plot)))
after = t_plot > t_data[-1]


def rmse(a, mask):
    return np.sqrt(np.mean((a[mask] - x_true[mask]) ** 2))


print(f"{'':30s}{'network':>10s}{'PINN':>10s}")
print(f"{'RMSE inside the data (m)':30s}{rmse(x_nn_plot, ~after):10.4f}{rmse(x_pinn_plot, ~after):10.4f}")
print(f"{'RMSE after the data (m)':30s}{rmse(x_nn_plot, after):10.4f}{rmse(x_pinn_plot, after):10.4f}")
for name, p in [("network", p_nn), ("PINN", p_pinn)]:
    grid = float(jnp.sqrt(jnp.mean(residual(p, jnp.array(t_plot)) ** 2)))
    colloc = float(jnp.sqrt(physics_loss(p)))
    print(f"{name}: residual RMS {grid:.1f} N over the second, {colloc:.2f} N at the collocation points")

fig, ax = plt.subplots(figsize=(9, 3.8))
ax.axvspan(0, 0.36, color="0.9")
ax.plot(
    t_plot,
    x_true,
    color="0.7",
    lw=5,
    label="exact",
)
ax.plot(
    t_plot,
    x_nn_plot,
    color="C1",
    lw=2,
    label="plain network",
)
ax.plot(
    t_plot,
    x_pinn_plot,
    "C0--",
    lw=2,
    label="PINN",
)
ax.plot(t_data, x_data, "ko", label="data")
ax.set_xlabel("time t (s)")
ax.set_ylabel("displacement x (m)")
ax.legend(ncol=4)
plt.show()
""")
b.md("""
The plain network drifts to a flat line once the data stop; the PINN follows the oscillation.
Its residual is small, but not zero: the physics is a penalty.
""")
b.write("l13-pinn-jax.ipynb")


# ======================================================================================
# l13-neural-dae.ipynb
# ======================================================================================
b = Book()
b.md("""
# L13 worked example: a fed-batch bioreactor as a neural ODE and a neural DAE

Four states: biomass $X$, product $P$, substrate $S$ and volume $V$. The balances are known; the
growth rate $\\mu$ is learned by a network of the four states.

$$
\\begin{align}
\\frac{dX}{dt} &= \\mu X - \\frac{F}{V}X &
\\frac{dP}{dt} &= Y_{px}\\,\\mu X - \\frac{F}{V}P \\\\
\\frac{dS}{dt} &= \\frac{F}{V}(S_f - S) - \\frac{\\mu X}{Y_{xs}} &
\\frac{dV}{dt} &= F
\\end{align}
$$

`pip install sindae diffrax` installs everything.
""")
b.code("""
%matplotlib inline

import logging

import diffrax
import equinox as eqx
import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
import numpy as np
import optax
import pandas as pd
import pyomo.dae as dae
import pyomo.environ as pyo
from scipy.integrate import solve_ivp

from sindae import HybridDAE
from sindae.algorithms.pretrain import PretrainConfig
from sindae.algorithms.simultaneous.train import SimultaneousConfig
from sindae.algorithms.smoother import SmootherConfig
from sindae.nn_utils import SimpleMLP
from sindae.plot_utils import plot_instance_data
from sindae.problem import ProblemDefinition
from sindae.solvers import SolverConfig

jax.config.update("jax_enable_x64", True)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logging.getLogger("pyomo").setLevel(logging.ERROR)
logging.getLogger("cyipopt").setLevel(logging.WARNING)
""")
b.md("""
## 1. The data

Three batches, 31 samples each over 40 h. The true kinetics, the Monod law
$\\mu = \\mu_{max} S / (K_s + S)$, only make the measurements and check the result.
""")
b.code("""
FB_PARAMS = {
    "Feed": 0.05,     # F: volumetric feed rate (L/h)
    "Ypx": 0.2,       # product yield
    "Yxs": 0.5,       # biomass yield on substrate
    "Ks": 1.0,        # Monod constant (makes the data only)
    "mu_max": 0.2,    # Monod constant (makes the data only)
}
F, Ypx, Yxs = FB_PARAMS["Feed"], FB_PARAMS["Ypx"], FB_PARAMS["Yxs"]
STATE_NAMES = ["$X$ (biomass)", "$P$ (product)", "$S$ (substrate)", "$V$ (volume)"]
OUTPUT_NAME = [r"$\\mu$ (growth rate)"]
SEED = 0
""")
b.md("""
Each measurement gets random noise. A concentration cannot be negative, so a reading below zero
is recorded as zero.
""")
b.code("""
BATCH_ICS = np.array([
    [0.05, 0.0, 10.0, 1.00],    # batch 0: X, P, S, V at t = 0
    [0.025, 0.0, 5.0, 0.80],    # batch 1
    [0.5, 0.0, 7.5, 0.95],      # batch 2
])
NOISE = np.array([0.05, 0.05, 0.5, 0.1])    # standard deviation of each measurement
t_obs = np.linspace(0, 40, 31)              # 31 samples over 40 h


def true_rhs(t, x, Sf):
    X, P, S, V = x
    mu = FB_PARAMS["mu_max"] * S / (FB_PARAMS["Ks"] + S)
    return [mu * X - F / V * X,
            Ypx * mu * X - F / V * P,
            F / V * (Sf - S) - mu * X / Yxs,
            F]


rng = np.random.default_rng(SEED)
obs_times = []
obs_values = []
for ic in BATCH_ICS:
    sol = solve_ivp(
        true_rhs,
        (0, 40),
        ic,
        t_eval=t_obs,
        args=(ic[2],),
        rtol=1e-10,
        atol=1e-12,
    )
    noisy = sol.y.T + rng.normal(0, 1, sol.y.T.shape) * NOISE
    obs_times.append(t_obs)
    obs_values.append(np.clip(noisy, 0, None))

pd.DataFrame(
    obs_values[0],
    index=pd.Index(t_obs.round(2), name="time (h)"),
    columns=["X", "P", "S", "V"],
).round(3).head()
""")
b.code("""
fig, axes = plt.subplots(1, 4, figsize=(16, 3))
for j, name in enumerate(STATE_NAMES):
    for b_ in range(len(obs_times)):
        axes[j].scatter(
            obs_times[b_],
            obs_values[b_][:, j],
            s=12,
            label=f"batch {b_}",
        )
    axes[j].set_title(name)
    axes[j].set_xlabel("$t$ (h)")
axes[0].legend()
plt.tight_layout()
plt.show()
""")
b.md("""
## 2. A neural ODE, trained sequentially

The network for $\\mu$, in [Equinox](https://docs.kidger.site/equinox/):
""")
b.code("""
mu_scale = 0.3                                 # 1/h: sets the size of mu
x_typical = jnp.array([5.0, 1.0, 10.0, 3.0])   # typical X, P, S, V

class GrowthRate(eqx.Module):
    mlp: eqx.nn.MLP

    def __call__(self, x):
        out = self.mlp(x / x_typical)[0]       # any real number
        return mu_scale * jax.nn.softplus(out) # mu >= 0, of order mu_scale
""")
b.md("""
The balances, as [Diffrax](https://docs.kidger.site/diffrax/) wants them:
""")
b.code("""
def balances(t, x, args):
    mu_net, Sf = args
    X, P, S, V = x
    mu = mu_net(x)                               # the learned term
    dX = mu * X - F / V * X
    dP = Ypx * mu * X - F / V * P
    dS = F / V * (Sf - S) - mu * X / Yxs
    dV = F
    return jnp.array([dX, dP, dS, dV])
""")
b.md("""
The solve: every operation is JAX, so `jax.grad` goes back through the solver.
""")
b.code("""
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
""")
b.md("""
The measurements as JAX arrays:
""")
b.code("""
x0s = jnp.array(BATCH_ICS)
ts = jnp.array(t_obs)
ys = jnp.array(obs_values)
y_scale = ys.reshape(-1, 4).std(axis=0)
steps = 10_000
""")
b.md("""
Training: every step simulates the three batches, then updates the weights. About 35 s.
""")
b.code("""
def loss(mu_net):
    pred = jax.vmap(simulate, in_axes=(None, 0, None))(mu_net, x0s, ts)
    return jnp.mean(((pred - ys) / y_scale) ** 2)

mu_net = GrowthRate(eqx.nn.MLP(
    in_size=4,
    out_size=1,
    width_size=16,
    depth=2,
    activation=jnp.tanh,
    key=jax.random.PRNGKey(0),
))
opt = optax.adam(optax.cosine_decay_schedule(1e-2, steps, alpha=0.05))
state = opt.init(eqx.filter(mu_net, eqx.is_array))

@eqx.filter_jit
def step(mu_net, state):
    value, grads = eqx.filter_value_and_grad(loss)(mu_net)
    updates, state = opt.update(grads, state, mu_net)
    return eqx.apply_updates(mu_net, updates), state, value

for _ in range(10_000):
    mu_net, state, value = step(mu_net, state)
""")
b.code("""
print(f"final loss {float(value):.4f}")
""")
b.md("""
## 3. A neural DAE, trained simultaneously

The problem, as in the SiNDAE example
[Importing Measured Data, Fed-Batch Bioreactor](https://alves-research-group.github.io/SiNDAE/fedbatch-example/),
with $F P / V$ in the product balance. The states are non-negative: here is $S \\ge 0$.
""")
b.code("""
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
""")
b.md("""
The sizes, and the training grid: 40 finite elements of 3 collocation points.
""")
b.code("""
INPUT_DIM = 4      # network inputs: X, P, S, V
Z_DIM = 1          # network output: mu
T_SPAN = (0.0, 40.0)
NFE_TRAIN = 40     # finite elements
NCP_TRAIN = 3      # collocation points per element
OBS_DIM = 4        # measured states
""")
b.md("""
The network and the three training stages: smoother, pretraining, full NLP.
""")
b.code("""
mlp = SimpleMLP(
    in_size=INPUT_DIM,
    out_size=Z_DIM,
    widths=[20, 20],
    activations=[jax.nn.softplus] * 2,
    key=jax.random.PRNGKey(SEED),
)
smoother_config = SmootherConfig(smooth_coef=10.0)
pretrain_config = PretrainConfig(
    epochs=200,
    batch_size=32,
    reg_coef=1e-3,
)
simul_config = SimultaneousConfig(
    use_gbm=True,
    reg_coef=1e-3,
)
solver_options = SolverConfig(
    tol=1e-6,
    max_iter=1000,
)
""")
b.md("""
Attach the measurements and train. About 30 s.
""")
b.code("""
problem = FedBatchBioreactorProblem(
    params=FB_PARAMS,
    ics=BATCH_ICS,
    input_dim=INPUT_DIM,
    z_dim=Z_DIM,
    t_span=T_SPAN,
    nfe=NFE_TRAIN,
    ncp=NCP_TRAIN,
    obs_dim=OBS_DIM,
    obs_times=obs_times,
    obs_values=obs_values,
)
""")
b.code("""
model = HybridDAE(
    method="simultaneous",
    nlp_solver="pounce",
    net=mlp,
    smoother=smoother_config,
    pretrain=pretrain_config,
    train=simul_config,
    solver_options=solver_options,
    unfix_io=True,
)
model.fit(problem)
""")
b.code("""
print(f"solver status: {model.termination}")
smoother_data = model.smoother_data
trained_data = model.trained_data

datasets = [
    (smoother_data, "smoother", {"color": "C2", "ls": "--"}),
    (trained_data, "trained", {"color": "C0", "ls": "-"}),
]
fig_x, _ = plot_instance_data(
    datasets=datasets,
    nn_input_names=STATE_NAMES,
    nn_output_names=OUTPUT_NAME,
    obs_times=problem.obs_times,
    obs_values=problem.obs_values,
    obs_names=STATE_NAMES,
    groups=["inputs"],
    legend_placement="last",
)
plt.show()

fig_mu, ax = plt.subplots(figsize=(5, 4))
for b_ in range(problem.num_trajectories):
    ax.scatter(
        trained_data[b_].nn_input[:, 2],
        trained_data[b_].nn_output[:, 0],
        s=12,
        color="C0",
        label="learned" if b_ == 0 else None,
    )
S_grid = np.linspace(0, 11, 100)
ax.plot(
    S_grid,
    FB_PARAMS["mu_max"] * S_grid / (FB_PARAMS["Ks"] + S_grid),
    "k-",
    label="true Monod",
)
ax.set_xlabel("$S$ (substrate)")
ax.set_ylabel(r"$\\mu$ (growth rate)")
ax.legend()
plt.tight_layout()
plt.show()
""")
b.md("""
## 4. A new batch, predicted by both

0.2 g/L of cells, 7 g/L of substrate and 0.9 L, run for 60 h: 20 h past the training batches.
""")
b.code("""
new_problem = FedBatchBioreactorProblem(
    params=FB_PARAMS,
    ics=np.array([[0.20, 0.0, 7.0, 0.90]]),
    input_dim=INPUT_DIM,
    z_dim=Z_DIM,
    t_span=(0.0, 60.0),
    nfe=45,
    ncp=3,
    obs_dim=OBS_DIM,
)
prediction = model.predict(
    new_problem,
    slack_coef=1e-5,
)
""")
b.code("""
ic_A = np.array([0.20, 0.0, 7.0, 0.90])
tt = np.linspace(0, 60, 121)
truth = solve_ivp(
    true_rhs,
    (0, 60),
    ic_A,
    t_eval=tt,
    args=(ic_A[2],),
    rtol=1e-10,
    atol=1e-12,
)
node = np.asarray(simulate(mu_net, jnp.array(ic_A), jnp.array(tt)))
pred_A = prediction[0]
t_dae = np.asarray(pred_A.sampling_times)
S_dae = pred_A.nn_input[:, 2]

fig, ax = plt.subplots(figsize=(9, 3.8))
ax.axhspan(
    -1.2,
    0,
    color="red",
    alpha=0.08,
)
ax.axhline(
    0,
    color="0.4",
    lw=1,
)
ax.plot(
    tt,
    truth.y[2],
    color="0.7",
    lw=5,
    label="true mechanistic model",
)
ax.plot(
    tt,
    node[:, 2],
    "C1",
    lw=2,
    label="sequential approach / neural ODE",
)
ax.plot(
    t_dae,
    S_dae,
    "C0--",
    lw=2,
    label="neural DAE",
)
ax.set_xlabel("time (h)")
ax.set_ylabel("substrate S (g/L)")
ax.legend()
plt.show()


def rmse(a, b):
    return np.sqrt(np.mean((a - b) ** 2))


S_node = node[:, 2]
S_dae_tt = np.interp(tt, t_dae, S_dae)
print(f"{'':26s}{'true model':>12s}{'neural ODE':>12s}{'neural DAE':>12s}")
print(f"{'lowest S (g/L)':26s}{truth.y[2].min():12.2f}{S_node.min():12.2f}{S_dae.min():12.2f}")
print(f"{'hours with S < 0':26s}{0:12d}{np.mean(S_node < 0) * 60:12.0f}{0:12d}")
print(f"{'error in S, RMSE (g/L)':26s}{'':12s}{rmse(S_node, truth.y[2]):12.2f}"
      f"{rmse(S_dae_tt, truth.y[2]):12.2f}")
""")
b.md("""
The neural ODE drives the substrate below zero; the neural DAE keeps it at or above zero. A
feasible prediction is not automatically an accurate one: compare the errors too.
""")
b.write("l13-neural-dae.ipynb")
