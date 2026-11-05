#!/usr/bin/env python3
"""Generate lectures/l20/l20-reinforcement-learning.ipynb, the L20 worked example.

NumPy only, seeded so the printed numbers are the ones in the notes: a three-level tank written as transition matrices, solved by a linear solve and by
value iteration, then Q-learning by hand on it; tabular Q-learning on the PyCSE tank against a PID loop tuned in the
notebook, over ten seeds and eight starts, then two rewards the agent games; and a Gaussian policy trained by
REINFORCE on the same tank. An optional last cell wraps the
tank for Gymnasium and trains PPO with Stable-Baselines3 if both are installed.

The code matches lectures/l20/figures/make_figures.py, which made the figures. Kept in a
generator for deterministic cell ids and no hand-edited JSON. The committed copy carries real
output. After regenerating, execute it:

    python3 lectures/l20/build_notebook.py
    export JUPYTER_DATA_DIR=$(mktemp -d)
    cd lectures/l20 && uv run --no-project --python 3.12 --with numpy --with matplotlib \
        --with nbclient --with nbformat --with ipykernel python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l20-reinforcement-learning.ipynb', as_version=4)
NotebookClient(nb, timeout=1200, kernel_name='python3', resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l20-reinforcement-learning.ipynb')
"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l20-reinforcement-learning.ipynb"
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells, n = [], 0


def md(text):
    global n
    n += 1
    cells.append({"cell_type": "markdown", "id": f"md-{n:02d}", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    global n
    n += 1
    cells.append({"cell_type": "code", "id": f"code-{n:02d}", "execution_count": None,
                  "metadata": {}, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


md("""
# L20 worked example: learning to act from rewards

Every model so far in the course was fitted to recorded data against a known answer. Here the
learner collects its own data by acting and is only told how well things went:

1. **The environment as matrices.** A three-level tank written as one transition matrix per
   action and a reward matrix. A policy is evaluated with one linear solve, and value
   iteration finds the best one.
2. **Q-learning by hand.** The same tank, but the agent never sees the matrices. Its Q-table
   is a 3 × 2 matrix, with every number in the first six updates printed.
3. **Q-learning on a tank.** The level the controller leaves behind is the level it faces next.
   The tank and the settings are from the PyCSE chapter on reinforcement learning. The agent is
   compared with a PID loop **tuned here**, over **ten seeds** and **eight starting levels**.
4. **Two rewards that miss the point.** The same agent, told to "keep it steady" or to stay
   "inside 5 ± 1".
5. **A continuous valve.** A Gaussian policy trained by REINFORCE outputs the inflow directly.

NumPy only. The whole notebook runs in about three minutes on a laptop.
""")

code("""
import numpy as np
import matplotlib.pyplot as plt
""")

md("""
## 1. The environment as matrices

A tank small enough to write down completely: three levels (low, ok, high) and two actions.
**Open** raises the level one step and **shut** lowers it one step. Landing at ok earns +1 and
opening costs 0.1; γ = 0.9.

For a finite problem the environment *is* a set of matrices. Row $s$ of $P_a$ is the
distribution of the next state after action $a$ in state $s$, and $R_{sa}$ is the expected
reward. Build them from the step function by trying every state and action once.
""")

code("""
LEVELS, ACTS = ["low", "ok", "high"], ["shut", "open"]

def small_step(s, a):
    s2 = min(s + 1, 2) if a == 1 else max(s - 1, 0)
    return s2, (1.0 if s2 == 1 else 0.0) - 0.1 * a

P = np.zeros((2, 3, 3))                   # (actions, states, next states)
R = np.zeros((3, 2))
for s in range(3):
    for a in range(2):
        s2, r = small_step(s, a)
        P[a, s, s2] = 1.0
        R[s, a] = r
print("P_shut\\n", P[0], "\\nP_open\\n", P[1], "\\nR\\n", R)

# An action acts on the environment by a matrix product: p_next = p @ P_a
p = np.array([0.5, 0.5, 0.0])             # equally likely low or ok
print("\\np @ P_open =", p @ P[1])
""")

md("""
A policy is a matrix $\\Pi$ (one row per state, rows sum to one). It collapses the per-action
matrices into one Markov chain, $P_\\pi = \\sum_a \\mathrm{diag}(\\Pi_{:,a}) P_a$, with reward
$r_\\pi = (\\Pi \\circ R)\\mathbf{1}$. Its value is the geometric series
$\\sum_k \\gamma^k P_\\pi^k r_\\pi$, which is a linear solve: $(I - \\gamma P_\\pi) V = r_\\pi$.
""")

code("""
g = 0.9

def evaluate(Pi):
    P_pi = sum(np.diag(Pi[:, a]) @ P[a] for a in range(2))
    r_pi = (Pi * R).sum(axis=1)
    return np.linalg.solve(np.eye(3) - g * P_pi, r_pi)

open_low_else_shut = np.array([[0, 1], [1, 0], [1, 0]], float)
print("open from low, shut otherwise:", evaluate(open_low_else_shut).round(3))
print("random (0.5 each):            ", evaluate(np.full((3, 2), 0.5)).round(3))
print("always open:                  ", evaluate(np.array([[0, 1], [0, 1], [0, 1]], float)).round(3))
""")

md("""
Finding the *best* policy adds one nonlinear step, the row-wise max:
$Q_{:,a} = R_{:,a} + \\gamma P_a V$ with $V = \\max_a Q$. Value iteration repeats it. Its row
maxima should equal the linear solve above, because "open from low, shut otherwise" is the
greedy policy of $Q^\\ast$.
""")

code("""
Q = np.zeros((3, 2))
for sweep in range(1, 1000):
    Q_new = R + g * (P @ Q.max(axis=1)).T     # P_a V for every action at once, then the max
    if np.abs(Q_new - Q).max() < 1e-12:
        break
    Q = Q_new
Qstar = Q_new
print(f"value iteration converged in {sweep} sweeps\\nQ* =\\n{Qstar.round(3)}")
print("row maxima of Q*:", Qstar.max(axis=1).round(3))
print("greedy policy:", [ACTS[i] for i in Qstar.argmax(axis=1)])
""")

md("""
## 2. Q-learning by hand

The same tank, but now the agent never sees `P` or `R`. It only sees the transitions it makes.
The Q-table is a 3 × 2 matrix of zeros; α = 0.5, γ = 0.9. The first six updates follow a
scripted episode so you can check every number against the notes. Each update is value
iteration's update with $P_a V$ replaced by the one next state actually observed.
""")

code("""
Qh, al = np.zeros((3, 2)), 0.5

def update(s, a, show=False):
    s2, r = small_step(s, a)
    target = r + g * Qh[s2].max()
    td = target - Qh[s, a]
    if show:
        print(f"{LEVELS[s]:>4} -> {ACTS[a]:4} -> {LEVELS[s2]:4}  r = {r:4.1f}  "
              f"target = {r:4.1f} + {g} x {Qh[s2].max():.3f} = {target:6.3f}  "
              f"TD = {td:6.3f}  Q: {Qh[s, a]:6.3f} -> {Qh[s, a] + al * td:6.3f}")
    Qh[s, a] += al * td
    return s2

for s, a in [(0, 1), (1, 1), (2, 0), (1, 0), (0, 1), (1, 1)]:
    update(s, a, show=True)
print(np.round(Qh, 3))
""")

md("""
Now 300 ε-greedy steps, compared with the $Q^\\ast$ that value iteration computed from the
matrices in section 1. The greedy policy is the argmax of each row.
""")

code("""
rng = np.random.default_rng(3)
s = 0
for t in range(300):
    if t % 10 == 0:
        s = int(rng.integers(3))
    a = int(rng.integers(2)) if rng.random() < 0.3 else int(np.argmax(Qh[s]))
    s = update(s, a)

print("Q after 306 updates\\n", np.round(Qh, 3))
print("Q* from value iteration on P and R\\n", np.round(Qstar, 3))
print("greedy action in each row:", {LEVELS[i]: ACTS[int(np.argmax(Qh[i]))] for i in range(3)})
""")

md("""
## 3. Q-learning on a tank

The PyCSE tank: $dh/dt = (F - k\\sqrt{h})/A$ with $A = 1$, $k = 0.5$, setpoint 5, Euler steps of
0.5, inflow $F$ chosen from five values. The level is cut into 20 bins, which are the states.
The reward is $-(h-5)^2 - 0.01F^2$. Episodes start at a random level in $[1, 9]$ and last 100
steps.
""")

code("""
FLOWS = [0.0, 0.5, 1.0, 1.5, 2.0]
A, K, SETPOINT, DT, STEPS, NBINS = 1.0, 0.5, 5.0, 0.5, 100, 20


def tank_bin(h):
    return min(int(min(max(h, 0.0), 10.0) / 10.0 * (NBINS - 1)), NBINS - 1)


def tank_step(h, F):
    return max(0.0, h + DT * (F - K * np.sqrt(max(h, 0.0))) / A)


def reward_fn(kind, h, h_prev, F):
    if kind == "setpoint":
        return -(h - SETPOINT) ** 2 - 0.01 * F**2
    if kind == "steady":
        return -abs(h - h_prev)
    if kind == "band":
        return 1.0 if abs(h - SETPOINT) <= 1.0 else 0.0


def q_learning(seed, episodes=1000, alpha=0.2, gamma=0.95, eps=0.2, reward="setpoint", flows=FLOWS):
    rng = np.random.default_rng(seed)
    Q = np.zeros((NBINS, len(flows)))
    totals = []
    for _ in range(episodes):
        h = rng.uniform(1.0, 9.0)
        s, total = tank_bin(h), 0.0
        for _ in range(STEPS):
            a = int(rng.integers(len(flows))) if rng.random() < eps else int(np.argmax(Q[s]))
            h2 = tank_step(h, flows[a])
            r = reward_fn(reward, h2, h, flows[a])
            s2 = tank_bin(h2)
            # The Q-learning update: toward r plus the discounted best value of the next state
            Q[s, a] += alpha * (r + gamma * Q[s2].max() - Q[s, a])
            s, h, total = s2, h2, total + r
        totals.append(total)
    return Q, np.array(totals)


Q0, totals = q_learning(0)
print("Q-table shape:", Q0.shape, "  transitions used:", 1000 * STEPS)
print(f"total reward per episode: first 50 {totals[:50].mean():.1f}, last 50 {totals[-50:].mean():.1f}")
print("greedy inflow by level bin:", [FLOWS[int(np.argmax(Q0[b]))] for b in range(NBINS)])
""")

md("""
Now the comparison. PyCSE compares the agent with a PID loop using hand-picked gains
$(K_p, K_i, K_d) = (0.8, 0.1, 0.2)$ from one start, $h = 2$. A fair comparison tunes the PID
loop, tests from several starts, and trains the agent with several seeds.
""")

code("""
def run_policy(Q, h0, flows=FLOWS):
    h, hs, fs = h0, [h0], []
    for _ in range(STEPS):
        F = flows[int(np.argmax(Q[tank_bin(h)]))]
        h = tank_step(h, F)
        hs.append(h)
        fs.append(F)
    return np.array(hs), np.array(fs)


def run_pid(Kp, Ki, Kd, h0, quantize=False):
    h, integ, prev = h0, 0.0, SETPOINT - h0
    hs, fs = [h0], []
    for _ in range(STEPS):
        e = SETPOINT - h
        integ += e * DT
        F = float(np.clip(Kp * e + Ki * integ + Kd * (e - prev) / DT, 0.0, 2.0))
        prev = e
        if quantize:                       # force the PID onto the agent's five inflows
            F = min(FLOWS, key=lambda f: abs(f - F))
        h = tank_step(h, F)
        hs.append(h)
        fs.append(F)
    return np.array(hs), np.array(fs)


def mse(hs):
    return float(np.mean((hs - SETPOINT) ** 2))


STARTS = [1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 9.0]

# Tune the PID on the eight starts with a plain grid search
best = min(((np.mean([mse(run_pid(kp, ki, kd, h0)[0]) for h0 in STARTS]), round(float(kp), 2), ki, kd)
            for kp in np.arange(0.2, 4.01, 0.2) for ki in [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]
            for kd in [0.0, 0.1, 0.2]))
TUNED = best[1:]
print("tuned PID gains (Kp, Ki, Kd):", TUNED)

Qs = [q_learning(s)[0] for s in range(10)]
per_seed = [float(np.mean([mse(run_policy(Q, h0)[0]) for h0 in STARTS])) for Q in Qs]

print(f"\\nfrom h = 2 only:   agent {np.mean([mse(run_policy(Q, 2.0)[0]) for Q in Qs]):.3f} (10 seeds)   "
      f"PyCSE PID {mse(run_pid(0.8, 0.1, 0.2, 2.0)[0]):.3f}   tuned PID {mse(run_pid(*TUNED, 2.0)[0]):.3f}")
print(f"over eight starts: agent {np.mean(per_seed):.3f} +/- {np.std(per_seed):.3f}   "
      f"PyCSE PID {np.mean([mse(run_pid(0.8, 0.1, 0.2, h0)[0]) for h0 in STARTS]):.3f}   "
      f"tuned PID {best[0]:.3f}   tuned PID on five inflows "
      f"{np.mean([mse(run_pid(*TUNED, h0, quantize=True)[0]) for h0 in STARTS]):.3f}")
print("agent, each seed over eight starts:", [round(v, 2) for v in per_seed])
""")

md("""
From $h = 2$ the agent beats the untuned PID, which is PyCSE's result. Over eight starts and ten
seeds the picture splits: about half the seeds learn a policy as good as the tuned PID, and the
rest fail badly from at least one start that training rarely visited.

The action set is the other problem. At steady state $F = k\\sqrt{h}$, so each of the five
inflows holds one level, and none of them is 5.
""")

code("""
print("steady level for each inflow, h = (F/k)^2:", [(F / K) ** 2 for F in FLOWS])
print("inflow that would hold h = 5:", round(K * np.sqrt(5), 3))

hs, fs = run_policy(Qs[0], 2.0)
tail = fs[-40:]
print("agent's inflows in the last 40 steps:", {float(f): int(np.sum(tail == f)) for f in sorted(set(tail))},
      "  switches:", int(np.sum(tail[1:] != tail[:-1])))

t = np.arange(STEPS + 1) * DT
fig, ax = plt.subplots(2, 1, figsize=(9, 5), sharex=True)
ax[0].plot(t, hs, label="agent, seed 0")
ax[0].plot(t, run_pid(*TUNED, 2.0)[0], label=f"tuned PID {TUNED}")
ax[0].plot(t, run_pid(0.8, 0.1, 0.2, 2.0)[0], "--", label="PID, PyCSE gains")
ax[0].axhline(SETPOINT, color="r", lw=0.8, ls=":")
ax[0].set_ylabel("level")
ax[0].legend()
ax[1].step(t[:-1], fs, where="post", label="agent inflow")
ax[1].plot(t[:-1], run_pid(*TUNED, 2.0)[1], label="tuned PID inflow")
ax[1].set_ylabel("inflow")
ax[1].set_xlabel("time")
ax[1].legend()
plt.tight_layout()
plt.show()
""")

md("""
### What the table was estimating

Write the 20-bin tank as matrices the way section 1 did for three levels. For each bin and
inflow, push levels spread evenly across the bin through one step of the physics and count
where they land. The physics is deterministic but the bins are not, because a bin hides where
inside it the level is. Then solve with value iteration and compare with the Q-learning seeds.
Finally, the model-based route on Q-learning's budget: count 100,000 random transitions into
estimated matrices and solve those.
""")

code("""
W = 10.0 / (NBINS - 1)                     # bin width; the last bin holds every level from 10 up


def tank_matrices(n=4000):
    P = np.zeros((len(FLOWS), NBINS, NBINS))
    R = np.zeros((NBINS, len(FLOWS)))
    for s in range(NBINS):
        hs = s * W + (np.arange(n) + 0.5) * W / n
        for a, F in enumerate(FLOWS):
            h2 = [tank_step(h, F) for h in hs]
            P[a, s] = np.bincount([tank_bin(x) for x in h2], minlength=NBINS) / n
            R[s, a] = np.mean([reward_fn("setpoint", x, h, F) for x, h in zip(h2, hs)])
    return P, R


def value_iteration(P, R, gamma=0.95, tol=1e-10):
    Q = np.zeros_like(R)
    while True:
        Q_new = R + gamma * np.einsum("ast,t->sa", P, Q.max(axis=1))
        if np.abs(Q_new - Q).max() < tol:
            return Q_new
        Q = Q_new


Pt, Rt = tank_matrices()
print("F = 1.0, row of bin 9:", {b: round(float(x), 3) for b, x in enumerate(Pt[2, 9]) if x > 0})
Qvi = value_iteration(Pt, Rt)
print("exact greedy inflow by bin:", [FLOWS[i] for i in Qvi.argmax(axis=1)])
print(f"exact policy over eight starts: {np.mean([mse(run_policy(Qvi, h0)[0]) for h0 in STARTS]):.3f}"
      f"   (Q-learning seeds {np.mean(per_seed):.2f} +/- {np.std(per_seed):.2f}, tuned PID {best[0]:.3f})")
print("traps, P[F=0.5] bin1->bin1 and P[F=1.5] bin17->bin17:", Pt[1, 1, 1], Pt[3, 17, 17])
for k, Q in enumerate(Qs):
    print(f"seed {k}: eight-start MSE {per_seed[k]:5.2f}   inflow in bin 1 = {FLOWS[int(Q[1].argmax())]}, "
          f"bin 17 = {FLOWS[int(Q[17].argmax())]}")

# Model-based: the same 100,000-transition budget, counted into P-hat and solved
for seed in range(3):
    rng = np.random.default_rng(100 + seed)
    cnt, rsum = np.zeros_like(Pt), np.zeros_like(Rt)
    for _ in range(1000):
        h = rng.uniform(1.0, 9.0)
        for _ in range(STEPS):
            s, a = tank_bin(h), int(rng.integers(len(FLOWS)))
            h2 = tank_step(h, FLOWS[a])
            cnt[a, s, tank_bin(h2)] += 1
            rsum[s, a] += reward_fn("setpoint", h2, h, FLOWS[a])
            h = h2
    visits = cnt.sum(axis=2).T
    Qmb = value_iteration(cnt / np.maximum(visits.T[:, :, None], 1), rsum / np.maximum(visits, 1))
    print(f"model-based, seed {seed}: eight-start MSE "
          f"{np.mean([mse(run_policy(Qmb, h0)[0]) for h0 in STARTS]):.3f}, unvisited pairs {(visits == 0).sum()}")
""")

md("""
The exact solution over the same five inflows matches the tuned PID, so the table was never
the limit. The failing seeds chose, in a rarely visited bin, one of the two inflows that holds
the level inside that same bin, a diagonal entry of 1 in $P_a$, and the tank parks there. The
same transitions used as data for a model and then solved give the exact policy every time.
""")

md("""
## 4. Two rewards that miss the point

The reward is the only description of the goal the agent sees. "Keep the level steady" becomes
$-|h_{t+1} - h_t|$; "stay near 5" becomes $+1$ inside $5 \\pm 1$. Same agent, same tank.
""")

code("""
for kind in ["steady", "band"]:
    Q = q_learning(0, reward=kind)[0]
    finals = [round(float(run_policy(Q, h0)[0][-1]), 2) for h0 in STARTS]
    print(f"{kind:7s} final level from each start {STARTS}: {finals}")
""")

md("""
Under "steady" the agent parks the tank at the nearest level one inflow can hold, 1, 4 or 9,
and leaves it there: perfectly steady, and the setpoint was never in the reward. Under "band" it
hovers in the lower half of the band, because nothing says 5 is better than 4.3. This is
**specification gaming**.

""")

md("""
## 5. A continuous valve: a policy that outputs the inflow

A Q-table picks an action by argmax over its columns, which needs actions you can list. A
**Gaussian policy** outputs the action instead: a mean $\\mu = \\theta_0 + \\theta_1 (5 - h)$ and a
fixed spread σ = 0.3, from which the inflow is sampled and clipped to $[0, 2]$. **REINFORCE**
(Williams, 1992) makes the inflows that were followed by better-than-average returns more likely.
Three seeds here; the notes report ten. The inflow that holds $h = 5$ is $k\\sqrt{5} = 1.118$.
""")

code("""
def pg_train(seed, iters=300, batch=10, lr=0.01, sigma=0.3, gamma=0.95):
    rng = np.random.default_rng(seed)
    theta = np.zeros(2)
    for _ in range(iters):
        eps = []
        for _ in range(batch):
            h, xs, Fs, rs = rng.uniform(1.0, 9.0), [], [], []
            for _ in range(STEPS):
                x = np.array([1.0, SETPOINT - h])
                F = float(theta @ x + sigma * rng.standard_normal())   # sample an action
                Fa = float(np.clip(F, 0.0, 2.0))
                h = tank_step(h, Fa)
                xs.append(x); Fs.append(F); rs.append(reward_fn("setpoint", h, None, Fa))
            G, acc = np.zeros(STEPS), 0.0
            for t in range(STEPS - 1, -1, -1):
                acc = rs[t] + gamma * acc
                G[t] = acc
            eps.append((np.array(xs), np.array(Fs), G))
        allG = np.concatenate([e[2] for e in eps])
        b, sd = allG.mean(), allG.std() + 1e-8
        grad = sum(((Fs - xs @ theta) / sigma**2 * (G - b) / sd) @ xs for xs, Fs, G in eps)
        theta = theta + lr * grad / batch
    return theta

def pg_run(theta, h0):
    h, hs = h0, [h0]
    for _ in range(STEPS):
        h = tank_step(h, float(np.clip(theta @ [1.0, SETPOINT - h], 0.0, 2.0)))   # the mean action
        hs.append(h)
    return np.array(hs)

for seed in range(3):
    th = pg_train(seed)
    print(f"seed {seed}: theta = {np.round(th, 3)},  MSE over eight starts "
          f"{np.mean([mse(pg_run(th, h0)) for h0 in STARTS]):.3f}   (tuned PID {best[0]:.3f})")
""")

md("""
The learned $\\theta_0$ sits near the holding inflow 1.118, found from reward alone. The policy is
a proportional controller with a feedforward term, so the engineering went into choosing its
form; the reward tuned two numbers, using 300,000 transitions.
""")

md("""
## 6. Optional: the same tank with Gymnasium and PPO

Gymnasium defines the environment interface (`reset`, `step`); Stable-Baselines3 provides PPO,
DQN, SAC and others. This cell runs only if both are installed
(`pip install gymnasium stable-baselines3`); the inflow is continuous in $[0, 2]$, which removes
the five-valve limit. Whether it beats the tuned PID is a question for the same three checks:
tuned baseline, several starts, several seeds.
""")

code("""
try:
    import gymnasium as gym
    from gymnasium import spaces
    from stable_baselines3 import PPO
except ImportError:
    print("gymnasium or stable-baselines3 not installed: skipping this section")
else:
    class TankEnv(gym.Env):
        def __init__(self):
            self.action_space = spaces.Box(0.0, 2.0, shape=(1,), dtype=np.float32)
            self.observation_space = spaces.Box(0.0, 10.0, shape=(1,), dtype=np.float32)

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self.h, self.t = self.np_random.uniform(1.0, 9.0), 0
            return np.array([self.h], dtype=np.float32), {}

        def step(self, action):
            F = float(np.clip(action[0], 0.0, 2.0))
            self.h, self.t = min(tank_step(self.h, F), 10.0), self.t + 1
            reward = -(self.h - SETPOINT) ** 2 - 0.01 * F**2
            # a time limit is a truncation, not a real end: the future still has value
            return np.array([self.h], dtype=np.float32), reward, False, self.t >= STEPS, {}

    model = PPO("MlpPolicy", TankEnv(), seed=0, verbose=0).learn(total_timesteps=50_000)
    def ppo_mse(h0):
        env = TankEnv(); env.reset(seed=0); env.h = h0
        hs, obs = [h0], np.array([h0], dtype=np.float32)
        for _ in range(STEPS):
            obs, *_ = env.step(model.predict(obs, deterministic=True)[0])
            hs.append(float(obs[0]))
        return mse(np.array(hs))
    print(f"PPO, one seed, 50,000 steps: MSE over eight starts {np.mean([ppo_mse(h) for h in STARTS]):.3f}"
          f"   (tuned PID {best[0]:.3f})")
""")

md("""
## Try it

- Train the tank agent for 5,000 episodes instead of 1,000. Do the failing seeds recover? Which
  starting levels were they failing from, and why would training rarely visit them?
- Add 1.125 to `FLOWS` (it holds $h = 5.06$). How do the switching count and the error change?
- Change γ from 0.95 to 0.5. What does the agent do near the setpoint, and why?
- In section 1, give the three-level tank a noisy valve: opening succeeds with probability 0.8
  and does nothing otherwise. Write the new `P[1]`, then re-run the linear solve and value
  iteration. Does the best policy change?
- Write a reward of your own for "reach 5 quickly and then hold it" and check what the agent
  actually does from every start.
""")

cells = with_colab_cell(cells, OUT)
nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT.name} ({len(cells)} cells)")
