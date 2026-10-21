"""Write course/assignments/a05.ipynb, the Assignment 5 notebook students work in.

    python3 course/assignments/a05-make-notebook.py

A5 is handed out as a notebook, in the format of the 06-325 homework: the problem text in
markdown cells, the code the assignment gives as runnable cells, and an "ADD YOUR CODE HERE"
cell after each item. Students work in Google Colab, export the notebook with Colab's
File > Print > Save as PDF, and submit the PDF.

The two figures are embedded as data URIs, so they show in Colab, in a local Jupyter and on the
course site without any file next to the notebook. Edit this script, not the .ipynb: the
reference solution is built from the same cells (every student cell has a key), so the two
cannot drift apart.
"""
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "a05.ipynb"

SITE = "https://kitchingroup.cheme.cmu.edu/f26-06763"
COLAB = "https://colab.research.google.com/github/jkitchin/f26-06763/blob/main/course/assignments/a05.ipynb"
L8 = f"[Lecture 8]({SITE}/lectures/l08/notes.html)"
L9 = f"[Lecture 9]({SITE}/lectures/l09/notes.html)"
L13 = f"[Lecture 13]({SITE}/lectures/l13/notes.html)"
PINN_NB = f"[`l13-pinn-jax.ipynb`]({SITE}/lectures/l13/l13-pinn-jax.html)"
NODE_NB = f"[`l13-neural-dae.ipynb`]({SITE}/lectures/l13/l13-neural-dae.html)"

ADD = "# ADD YOUR CODE HERE  -- feel free to add additional code or markdown blocks if needed \n"


def image(name, alt):
    data = base64.b64encode((HERE / "figures" / name).read_bytes()).decode()
    return f"![{alt}](data:image/png;base64,{data})"


def md(text):
    return {"type": "markdown", "source": text.strip("\n")}


def code(text, tags=()):
    return {"type": "code", "source": text.strip("\n"), "tags": list(tags)}


def student(key):
    # a cell the student fills in; the solution builder replaces it by its key
    return {"type": "code", "source": ADD, "key": key}


CELLS = [
    md("""
# Assignment 5: Four models of a bioreactor
**Released:** L15 (2026-10-21) · **Due:** Wednesday 2026-10-28 · **6 points on Canvas.**
"""),
    md(f"""
Exporting and submitting your homework

0. Work in Google Colab. Open this notebook from [this link]({COLAB}) (or "Open in Colab" on the course page), then File > Save a copy in Drive, and work in your copy.

1. Run every cell from top to bottom (Runtime > Run all), so that all outputs and plots are in the notebook.

2. Export the notebook as a PDF: File > Print, then choose "Save as PDF" as the destination.

3. Check the PDF before you submit it. It is your responsibility to make sure the PDF exported correctly: every code cell, output, plot and answer must be in it and readable. Equations from the problem statement need not render perfectly, as long as your answers are clear.

4. Submit the PDF to Canvas.
"""),
    md(f"""
Consider a continuous bioreactor in which the biomass (cells) grows by consuming substrate. Five experiments were run on it, each from a different initial condition. Build four models, use each one to predict experiment 5, and compare the predictions.

The four models are of two kinds, each without and with physics:

| | Data only | Data and physics |
|---|---|---|
| **A model of one trajectory**: time $\\mapsto (X, S)$ | Problem 1: neural network of time ({L13}, {PINN_NB}) | Problem 2: physics-informed neural network, PINN ({L13}, {PINN_NB}) |
| **A model of the reactor**: state $\\mapsto$ its change | Problem 3: neural-network time-series model ({L8}, {L9}) | Problem 4: neural ODE, ordinary differential equation ({L13}, {NODE_NB}) |

- A model of one trajectory takes the time as its input, so it describes one experiment, and it can learn only from that experiment. Problems 1 and 2 train on the first 40 s of experiment 5 and predict the rest.
- A model of the reactor takes the state as its input. Its rule, from the state now to how the state changes, is the same in every experiment, because every experiment runs the same reactor. So Problems 3 and 4 learn from experiments 1 to 4 and predict experiment 5 from its initial condition.
- Problem 5 compares the four.

Points: Problem 1, 1; Problem 2, 1.5; Problem 3, 1; Problem 4, 1.5; Problem 5, 1. Your TA grades the PDF. A model that fails, reported and explained, loses no points.
"""),
    md(f"""
## The bioreactor

{image("a05-reactor.png", "A stirred bioreactor: the feed F with substrate S_F enters at the top, the outflow F with X and S leaves through the side, and the volume V is constant.")}

The feed enters at rate $F$ with substrate concentration $S_F$. The outflow leaves at the same rate, at the reactor concentrations $X$ and $S$, so the volume $V$ is constant.

The model consists of two dynamic mass balances, one for the biomass $X$ and one for the substrate $S$:

$$
\\frac{{dX}}{{dt}} = \\underbrace{{-\\frac{{F}}{{V}}\\,X}}_{{\\text{{outflow}}}} + \\underbrace{{\\mu(S)\\,X}}_{{\\text{{growth}}}}
$$

$$
\\frac{{dS}}{{dt}} = \\underbrace{{\\frac{{F}}{{V}}\\,(S_F - S)}}_{{\\text{{feed}} - \\text{{outflow}}}} - \\underbrace{{\\frac{{\\mu(S)}}{{Y(S)}}\\,X}}_{{\\text{{consumption}}}}
$$

where $\\mu(S)$ is the specific growth rate and $Y(S)$ the yield:

$$
\\mu(S) = 10^{{-3}}\\,S\\,e^{{-S/120}}, \\qquad Y(S) = 5.4 \\cdot 10^{{-3}} + 1.8 \\cdot 10^{{-4}}\\,S
$$

| Symbol | Meaning | Value | Units |
|---|---|---|---|
| $X$ | Biomass concentration | state | kg/m³ |
| $S$ | Substrate concentration | state | mol/m³ |
| $\\mu(S)$ | Specific growth rate | equation above | 1/s |
| $Y(S)$ | Yield: biomass made per substrate consumed | equation above | kg/mol |
| $V$ | Reactor volume | $\\pi \\cdot 3^2 \\cdot 5.7$ | m³ |
| $F$ | Feed and outflow rate | 5.02597 | m³/s |
| $S_F$ | Substrate concentration in the feed | 300 | mol/m³ |
"""),
    md(f"""
## The data

- Columns: `experiment` (1 to 5), `t` (s), `X` (kg/m³), `S` (mol/m³). One sample every 5 s.
- Experiments 1 to 4: 0 to 100 s, 21 samples each.
- Experiment 5: 0 to 300 s, 61 samples. Problems 1 and 2 train on its first 40 s. Its measurements after 40 s are the test.
- The first sample of each experiment ($t = 0$) is the exact initial condition. The others are measurements with Gaussian noise: standard deviation 0.05 kg/m³ on $X$ and 1 mol/m³ on $S$.

| Experiment | $X_0$ (kg/m³) | $S_0$ (mol/m³) | Measured | Use |
|---|---|---|---|---|
| 1 | 5.0 | 10 | 0 to 100 s | Training |
| 2 | 2.0 | 20 | 0 to 100 s | Training |
| 3 | 4.0 | 120 | 0 to 100 s | Training |
| 4 | 2.5 | 60 | 0 to 100 s | Training |
| 5 | 3.0 | 80 | 0 to 300 s | First 40 s: training for Problems 1 and 2. After 40 s: **test** |

{image("a05-data.png", "X and S of the five experiments against time. Experiments 1 to 4 run from 0 to 100 s; experiment 5 runs from 0 to 300 s, with its first 40 s filled. All approach the steady state, X near 3.46 and S near 45.6.")}

The training data: experiments 1 to 4 (0 to 100 s), and the first 40 s of experiment 5 for Problems 1 and 2. The test: experiment 5 after 40 s.
"""),
    md("""
## Set-up

Run the two cells below first. The first installs the two packages Colab does not have. The second loads the libraries, the data and the model's parameters.
"""),
    code("""
!pip install -q equinox diffrax optax
""", tags=["skip-execution"]),
    code(f"""
import diffrax                      # ODE solvers in JAX (Lecture 13)
import equinox as eqx               # neural networks in JAX (Lecture 13)
import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
import numpy as np
import optax                        # optimizers for JAX (Lectures 11 and 13)
import pandas as pd
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# double precision (Lecture 11)
jax.config.update("jax_enable_x64", True)

# the data: columns experiment, t (s), X (kg/m3), S (mol/m3)
df = pd.read_csv("{SITE}/a05-bioreactor.csv")

# the model's parameters
V = np.pi * 3**2 * 5.7      # m3
F = 5.02597                 # m3/s
SF = 300.0                  # mol/m3


def mu(S):
    # specific growth rate (1/s)
    return 1e-3 * S * jnp.exp(-S / 120)


def Y(S):
    # yield (kg/mol)
    return 5.4e-3 + 1.8e-4 * S
"""),
    md("""
## Notes for all problems
- **Problems 1 and 2**, the models of one trajectory, train on experiment 5 from 0 to 40 s, its first 9 samples.
- **Problems 3 and 4**, the models of the reactor, train on experiments 1 to 4. From experiment 5 they use only its initial condition, $(X_0, S_0) = (3.0, 80)$.
- Every model predicts experiment 5 at $t = 0, 5, \\ldots, 300$ s. Its measurements after 40 s are the test, in Problem 5.
- JAX takes NumPy arrays, not pandas columns. Read the times as floats with `df["t"].astype(float).to_numpy()`, because `jax.grad` refuses integers and the column `t` holds integers. Read `X` and `S` with `.to_numpy()` too.
- Build time grids with `np.linspace` (Lecture 13), which gives floats.
- Inside a function that JAX differentiates or integrates, write the math with `jnp` (`jnp.exp`), not `np`.
- The L13 notebooks import packages A5 does not need (`pyomo`, `sindae`). Copy only the cells you need.
- A model is allowed to fail. Report what you get and explain it.
"""),
    # ------------------------------------------------------------------ problem 1
    md("""
## 1. Neural network of time
Consider the plain network of Lecture 13: a neural network that maps time to the states, $t \\mapsto (X, S)$, trained on data only.

a) Run the cell below. It codes the network:
"""),
    code("""
net = eqx.nn.MLP(              # t -> (X, S)
    in_size=1,
    out_size=2,
    width_size=32,
    depth=3,
    activation=jnp.tanh,
    key=jax.random.PRNGKey(0),
)


def model(net, t):
    # X and S of experiment 5 at time t (s)
    return net(jnp.array([t]))
"""),
    md("""
b) Train it on the 9 samples of experiment 5 from 0 to 40 s. In the cell below, build `t_fit`, their 9 times, and `y_fit`, their 9 rows of $(X, S)$, as NumPy arrays.
"""),
    student("1b"),
    md("""
Then run the cell below. It defines the loss, the mean squared error against the 9 samples, and a training function, and trains the network:
- `jax.vmap` (JAX; Lectures 11 and 13) evaluates `model` at all 9 times at once.
- `train` is the training step of `l13-neural-dae.ipynb` (Equinox and Optax; Lecture 13) inside a function, so that Problems 2 and 4 can call it with their own loss. The step of `l13-pinn-jax.ipynb` does not work on an Equinox network.
"""),
    code("""
def loss_nn(net):
    # mean squared error against the 9 samples: times t_fit, values y_fit
    pred = jax.vmap(model, in_axes=(None, 0))(net, t_fit)
    return jnp.mean((pred - y_fit) ** 2)


def train(loss, net, steps, opt):
    # the training step of l13-neural-dae.ipynb, for any loss
    state = opt.init(eqx.filter(net, eqx.is_array))

    @eqx.filter_jit
    def step(net, state):
        value, grads = eqx.filter_value_and_grad(loss)(net)
        updates, state = opt.update(grads, state, net)
        return eqx.apply_updates(net, updates), state, value

    for _ in range(steps):
        net, state, value = step(net, state)
    return net


net_nn = train(loss_nn, net, 20_000, optax.adam(1e-3))
"""),
    md("""
c) Evaluate `net_nn` at $t = 0, 5, \\ldots, 300$ s with `jax.vmap(model, in_axes=(None, 0))`. Plot $X$ and $S$ with the measurements, marking the 40 s it trained on. How good is it before 40 s, and after? Why?
"""),
    student("1c"),
    # ------------------------------------------------------------------ problem 2
    md("""
## 2. PINN
Consider the PINN of Lecture 13: the network of Problem 1, trained on the same data and on the residuals of the model's equations. For this reactor the residuals are

$$
r_X = \\frac{dX}{dt} + \\frac{F}{V}\\,X - \\mu(S)\\,X, \\qquad
r_S = \\frac{dS}{dt} - \\frac{F}{V}\\,(S_F - S) + \\frac{\\mu(S)}{Y(S)}\\,X
$$

with $X$ and $S$ the network's outputs.

a) Run the cell below. It codes the residuals. $dX/dt$ and $dS/dt$ come from `jax.grad` (JAX; Lectures 11 and 13) of each output with respect to $t$.
"""),
    code("""
def residuals(net, t):
    X, S = model(net, t)
    # dX/dt and dS/dt: jax.grad of each output with respect to t
    dXdt = jax.grad(lambda t: model(net, t)[0])(t)
    dSdt = jax.grad(lambda t: model(net, t)[1])(t)
    rX = dXdt + F / V * X - mu(S) * X
    rS = dSdt - F / V * (SF - S) + mu(S) / Y(S) * X
    return jnp.array([rX, rS])
"""),
    md("""
b) Run the cell below. It trains the PINN with `train`, from the same starting network `net`, on data plus physics. The loss is $\\mathcal{L}_\\text{data} + \\mathcal{L}_\\text{physics}$: the loss of Problem 1, plus the mean of $r_X^2 + r_S^2$ at 301 collocation points from 0 to 300 s.
"""),
    code("""
t_phys = np.linspace(0, 300, 301)       # 301 collocation points (s)


def loss_pinn(net):
    # the residuals at every collocation point
    r = jax.vmap(residuals, in_axes=(None, 0))(net, t_phys)
    return loss_nn(net) + jnp.mean(r[:, 0] ** 2 + r[:, 1] ** 2)


net_pinn = train(loss_pinn, net, 20_000, optax.adam(1e-3))
"""),
    md("""
c) Evaluate `net_pinn` at $t = 0, 5, \\ldots, 300$ s and plot it with the measurements and the prediction of Problem 1. How good is it after 40 s, compared with Problem 1? Why does the physics help? Why is the prediction still off?
"""),
    student("2c"),
    # ------------------------------------------------------------------ problem 3
    md(f"""
## 3. Neural-network time-series model
Consider a model that predicts the next sample from the current one:

$$
X_{{k+1}} = f_X(X_k, S_k), \\qquad S_{{k+1}} = f_S(X_k, S_k)
$$

It is the recursive time-series model of {L8}, with a neural network ({L9}) as the regression.

Using experiments 1 to 4, do the following:

a) Build the training table: features $X_k$ and $S_k$, targets $X_{{k+1}}$ and $S_{{k+1}}$. That is 20 rows per experiment, 80 in total.

Hint: one experiment at a time. For an array `arr` of its 21 samples, the features are `arr[:-1]` and the targets are `arr[1:]`.
"""),
    student("3a"),
    md("""
b) Fit $f_X$ and $f_S$, each with `make_pipeline(StandardScaler(), MLPRegressor(solver="lbfgs", random_state=0, max_iter=5000))` (scikit-learn; Lectures 8 and 9).
"""),
    student("3b"),
    md("""
c) Predict experiment 5 recursively (Lecture 8, "Direct and recursive forecasting"). Start from $(3.0, 80)$. At each step, predict $X_{k+1}$ and $S_{k+1}$ from the same $(X_k, S_k)$, then use the pair as the next features. Repeat 60 times.
"""),
    student("3c"),
    md("""
d) Plot $X$ and $S$ of your prediction with the measurements of experiment 5. How good is the prediction? Why?
"""),
    student("3d"),
    # ------------------------------------------------------------------ problem 4
    md(f"""
## 4. Neural ODE
Consider the same balances with two networks: $\\mu_\\text{{NN}}(S)$, the growth rate in the biomass balance, and $f_\\text{{NN}}(X, S)$, the whole right-hand side of the substrate balance:

$$
\\frac{{dX}}{{dt}} = -\\frac{{F}}{{V}}\\,X + \\mu_\\text{{NN}}(S)\\,X, \\qquad
\\frac{{dS}}{{dt}} = f_\\text{{NN}}(X, S)
$$

The biomass balance keeps its physics. Nothing of the substrate balance is given. The code follows {NODE_NB}.

a) Run the cell below. It codes the two networks and the right-hand side:
"""),
    code("""
mu_net = eqx.nn.MLP(           # S -> growth rate mu
    in_size=1,
    out_size=1,
    width_size=16,
    depth=2,
    activation=jnp.tanh,
    key=jax.random.PRNGKey(0),
)
f_net = eqx.nn.MLP(            # (X, S) -> dS/dt
    in_size=2,
    out_size=1,
    width_size=16,
    depth=2,
    activation=jnp.tanh,
    key=jax.random.PRNGKey(1),
)
nets = (mu_net, f_net)


def mu_nn(mu_net, S):
    # growth rate (1/s): positive, and of the size of the true mu (at most 0.044)
    return 0.05 * jax.nn.softplus(mu_net(jnp.array([S / 100]))[0])


def balances(t, x, nets):
    mu_net, f_net = nets
    X, S = x
    # biomass balance, with mu learned
    dXdt = -F / V * X + mu_nn(mu_net, S) * X
    # substrate balance, learned whole
    dSdt = f_net(jnp.array([X / 5, S / 100]))[0]
    return jnp.array([dXdt, dSdt])
"""),
    md("""
b) Run the cell below. It simulates with `diffrax.diffeqsolve` (Diffrax; Lecture 13):
"""),
    code("""
def simulate(nets, x0, ts):
    # X and S at the times ts, from the initial condition x0
    sol = diffrax.diffeqsolve(
        diffrax.ODETerm(balances),
        diffrax.Tsit5(),
        t0=0.0,
        t1=ts[-1],
        dt0=0.5,
        y0=x0,
        args=nets,
        saveat=diffrax.SaveAt(ts=ts),
        stepsize_controller=diffrax.PIDController(
            rtol=1e-6,
            atol=1e-8,
        ),
    )
    return sol.ys
"""),
    md("""
c) Train on experiments 1 to 4. In the cell below, define:
- `x0s`, their four initial conditions, `ts`, their 21 sample times, and `ys`, their measurements, of shape (4, 21, 2);
- `sigma`, the standard deviation of $X$ and of $S$ over all samples of experiments 1 to 4;
- `loss_node(nets)`: simulate the four experiments at once with `jax.vmap(simulate, in_axes=(None, 0, None))(nets, x0s, ts)`, and return the mean of $\\left((\\text{prediction} - \\text{data}) / \\sigma\\right)^2$.
"""),
    student("4c"),
    md("""
Then run the cell below. It trains for 10,000 steps with `train` (Problem 1) and a cosine schedule (Optax; Lecture 13). `train` accepts the pair `nets`, because `eqx.filter` and `eqx.filter_value_and_grad` work on a tuple of networks.
"""),
    code("""
opt = optax.adam(optax.cosine_decay_schedule(1e-2, 10_000, alpha=0.05))
nets = train(loss_node, nets, 10_000, opt)
"""),
    md("""
d) Predict experiment 5 by integrating from its initial condition with `simulate`. It is a new initial-value problem: do not retrain, and use only its initial condition. Plot it with the measurements.
"""),
    student("4d"),
    md("""
e) Evaluate `mu_nn` with the trained growth-rate network, `nets[0]`, at $S = 0, 10, \\ldots, 300$ mol/m³: `jax.vmap(mu_nn, in_axes=(None, 0))(nets[0], S)` (JAX; Lectures 11 and 13). Plot it with the true $\\mu(S)$ on the same grid. Where do they agree? Where not, and why?
"""),
    student("4e"),
    # ------------------------------------------------------------------ problem 5
    md("""
## 5. Compare
a) Plot $X$ and $S$ of experiment 5 in one figure: the measurements and your four predictions, with the 40 s of Problems 1 and 2 marked.
"""),
    student("5a"),
    md("""
b) Compute the root mean square error (RMSE) of each prediction, for $X$ and for $S$, against the $N = 52$ measurements of experiment 5 after 40 s ($t = 45$ to 300 s). No model trained on them. Report the RMSEs in a table:

$$
\\text{RMSE} = \\sqrt{\\frac{1}{N} \\sum_{i=1}^{N} \\left(\\hat{y}_i - y_i\\right)^2}
$$

Note: the measurement noise sets a floor. No model can score much below 0.05 kg/m³ on $X$ or 1 mol/m³ on $S$.
"""),
    student("5b"),
    md("""
c) Which model would you use to predict a sixth experiment from its initial condition only? Why can the models of the reactor (Problems 3 and 4) do it, while the models of one trajectory (Problems 1 and 2) cannot?
"""),
    student("5c"),
    # ------------------------------------------------------------------ end
    md("""
## Generative AI statement (please indicate if you used generative AI, where and how):
"""),
    md("""
## End of homework.
"""),
]


def notebook(cells):
    out = []
    for i, c in enumerate(cells):
        cell = {"cell_type": c["type"], "id": f"a05-{i:02d}", "metadata": {},
                "source": c["source"].splitlines(keepends=True)}
        if c.get("tags"):
            cell["metadata"]["tags"] = c["tags"]
        if c["type"] == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        out.append(cell)
    return {"cells": out, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        # ipython3, so the !pip cell highlights without a lexer error
        "language_info": {"name": "python", "pygments_lexer": "ipython3"}},
        "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    OUT.write_text(json.dumps(notebook(CELLS), indent=1) + "\n")
    print(f"wrote {OUT} ({len(CELLS)} cells)")
