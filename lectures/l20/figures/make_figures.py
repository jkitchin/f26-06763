#!/usr/bin/env python3
"""Figures and numbers for L20, reinforcement learning.

Three worked examples, each small enough to run in seconds with NumPy alone, so every number
in the notes and on the slides can be regenerated and checked:

  bandit   five candidate catalysts as the arms of a bandit; greedy, epsilon-greedy, UCB and
           Thompson sampling over 500 pulls, 500 runs each (Sutton & Barto ch. 2).
  tank     the PyCSE tank (A = 1, k = 0.5, setpoint 5, inflow from {0, 0.5, 1, 1.5, 2}),
           tabular Q-learning with PyCSE's settings over ten seeds, against PID with PyCSE's
           hand-picked gains and with gains tuned on the same test, and two rewards that a
           reasonable engineer might write that the agent satisfies the wrong way.
  cliff    cliff walking (Sutton & Barto Example 6.6), Q-learning against SARSA, 50 runs.

Also writes _static/l20-widget-data.js, the parameters the browser figures simulate with, so
the tank in the notes is the tank in this file.

    uv run --no-project --python 3.12 --with numpy --with matplotlib \
        python lectures/l20/figures/make_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).parent
REPO = HERE.parent.parent.parent
RESULTS = {}

plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 110})
BLUE, ORANGE, GREEN, GREY, RED = "#1f6fb2", "#c2410c", "#2b8a3e", "#888888", "#c41230"


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / name, dpi=150)
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- bandit

ARMS = ["Cat A", "Cat B", "Cat C", "Cat D", "Cat E"]
ARM_MEANS = np.array([62.0, 70.0, 74.0, 66.0, 58.0])  # mean yield, %
ARM_SD = 8.0  # run-to-run noise in one yield measurement, %


def bandit_run(method, rng, T=500, eps=0.1, c=ARM_SD, prior=(65.0, 15.0)):
    k = len(ARM_MEANS)
    n = np.zeros(k)
    q = np.zeros(k)
    regret = np.zeros(T)
    best = ARM_MEANS.max()
    picks = np.zeros(T, int)
    for t in range(T):
        if method == "greedy":
            a = int(np.argmax(q)) if t >= k else t
        elif method == "eps":
            a = int(rng.integers(k)) if rng.random() < eps else int(np.argmax(q))
        elif method == "ucb":
            if t < k:
                a = t
            else:
                a = int(np.argmax(q + c * np.sqrt(np.log(t + 1) / n)))
        elif method == "thompson":
            # Gaussian posterior on each arm's mean, known noise ARM_SD
            m0, s0 = prior
            prec = 1 / s0**2 + n / ARM_SD**2
            mean = (m0 / s0**2 + q * n / ARM_SD**2) / prec
            a = int(np.argmax(rng.normal(mean, 1 / np.sqrt(prec))))
        r = rng.normal(ARM_MEANS[a], ARM_SD)
        n[a] += 1
        q[a] += (r - q[a]) / n[a]
        regret[t] = best - ARM_MEANS[a]
        picks[t] = a
    return np.cumsum(regret), picks


def bandit():
    # UCB's c has the units of the reward. Sutton & Barto's c = 2 is for rewards of unit
    # spread; these yields have a spread of 8, so c = 2 under-explores (kept as "ucb2").
    methods = [("greedy", "greedy"), ("eps", "ε-greedy, ε = 0.1"), ("ucb2", "UCB, c = 2"),
               ("ucb", "UCB, c = σ = 8"), ("thompson", "Thompson sampling")]
    runs, T = 500, 500
    out = {}
    fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.9))
    for (m, label), col in zip(methods, [GREY, ORANGE, "#9ec5e8", BLUE, GREEN]):
        rng = np.random.default_rng(20)
        cum = np.zeros((runs, T))
        best_frac = np.zeros(runs)
        for i in range(runs):
            cr, picks = bandit_run("ucb" if m == "ucb2" else m, rng, T, c=2.0 if m == "ucb2" else ARM_SD)
            cum[i] = cr
            best_frac[i] = np.mean(picks[-100:] == 2)
        out[m] = {"regret_500": round(float(cum[:, -1].mean()), 1),
                  "best_last100": round(float(best_frac.mean()), 3),
                  "stuck_runs": round(float(np.mean(best_frac < 0.5)), 3)}
        ax[0].plot(cum.mean(0), color=col, label=label, lw=2)
        ax[1].bar(label, best_frac.mean(), color=col)
    ax[0].set_xlabel("pull (one yield measurement)")
    ax[0].set_ylabel("cumulative regret (yield points)")
    ax[0].legend(frameon=False, fontsize=9)
    ax[0].set_title("Regret: yield lost to not knowing the best catalyst", fontsize=11)
    ax[1].set_ylabel("share of the last 100 pulls on Cat C")
    ax[1].set_ylim(0, 1)
    ax[1].tick_params(axis="x", labelsize=8, rotation=12)
    ax[1].set_title("Did it find the best arm?", fontsize=11)
    save(fig, "bandit-regret.png")
    RESULTS["bandit"] = out
    print("bandit", json.dumps(out))


# ---------------------------------------------------------------- tank

TANK = dict(A=1.0, k=0.5, setpoint=5.0, dt=0.5, steps=100, n_states=20, level_max=10.0,
            flows=[0.0, 0.5, 1.0, 1.5, 2.0], effort=0.01)


def tank_bin(h, T=TANK):
    h = min(max(h, 0.0), T["level_max"])
    return min(int(h / T["level_max"] * (T["n_states"] - 1)), T["n_states"] - 1)


def tank_step(h, F, T=TANK):
    return max(0.0, h + T["dt"] * (F - T["k"] * np.sqrt(max(h, 0.0))) / T["A"])


def reward_fn(kind, h, h_prev, F, T=TANK):
    if kind == "setpoint":       # PyCSE's reward: squared error plus a little effort
        return -(h - T["setpoint"]) ** 2 - T["effort"] * F**2
    if kind == "steady":         # "keep the level steady": penalize movement
        return -abs(h - h_prev)
    if kind == "band":           # "+1 for every step inside 5 ± 1"
        return 1.0 if abs(h - T["setpoint"]) <= 1.0 else 0.0
    raise ValueError(kind)


def q_learning_tank(seed, episodes=1000, alpha=0.2, gamma=0.95, eps=0.2, reward="setpoint",
                    flows=None, curve=False):
    T = dict(TANK)
    if flows is not None:
        T["flows"] = flows
    rng = np.random.default_rng(seed)
    nA = len(T["flows"])
    Q = np.zeros((T["n_states"], nA))
    totals = []
    for ep in range(episodes):
        h = rng.uniform(1.0, 9.0)
        s = tank_bin(h, T)
        tot = 0.0
        for t in range(T["steps"]):
            a = int(rng.integers(nA)) if rng.random() < eps else int(np.argmax(Q[s]))
            h2 = tank_step(h, T["flows"][a], T)
            r = reward_fn(reward, h2, h, T["flows"][a], T)
            s2 = tank_bin(h2, T)
            Q[s, a] += alpha * (r + gamma * Q[s2].max() - Q[s, a])
            s, h, tot = s2, h2, tot + r
        totals.append(tot)
    return (Q, np.array(totals)) if curve else Q


def run_policy(Q, h0, flows=None):
    flows = flows or TANK["flows"]
    h, hs, fs = h0, [h0], []
    for _ in range(TANK["steps"]):
        F = flows[int(np.argmax(Q[tank_bin(h)]))]
        h = tank_step(h, F)
        hs.append(h)
        fs.append(F)
    return np.array(hs), np.array(fs)


def run_pid(Kp, Ki, Kd, h0, quantize=False):
    T = TANK
    h, integ, prev = h0, 0.0, T["setpoint"] - h0
    hs, fs = [h0], []
    for _ in range(T["steps"]):
        e = T["setpoint"] - h
        integ += e * T["dt"]
        F = float(np.clip(Kp * e + Ki * integ + Kd * (e - prev) / T["dt"], 0.0, 2.0))
        prev = e
        if quantize:
            F = min(T["flows"], key=lambda f: abs(f - F))
        h = tank_step(h, F)
        hs.append(h)
        fs.append(F)
    return np.array(hs), np.array(fs)


def mse(hs):
    return float(np.mean((hs - TANK["setpoint"]) ** 2))


H0S = [1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 9.0]  # test starts, none at the setpoint


def tank():
    seeds = range(10)
    Qs = [q_learning_tank(s) for s in seeds]
    rl_h2 = [mse(run_policy(Q, 2.0)[0]) for Q in Qs]
    rl_all = [np.mean([mse(run_policy(Q, h0)[0]) for h0 in H0S]) for Q in Qs]

    pycse_gains = (0.8, 0.1, 0.2)
    pid_h2 = mse(run_pid(*pycse_gains, 2.0)[0])
    pid_all = np.mean([mse(run_pid(*pycse_gains, h0)[0]) for h0 in H0S])
    # Tune on the same eight starts, a plain grid, the way an engineer would in an afternoon.
    best = None
    for Kp in np.arange(0.2, 4.01, 0.2):
        for Ki in [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]:
            for Kd in [0.0, 0.1, 0.2]:
                v = np.mean([mse(run_pid(Kp, Ki, Kd, h0)[0]) for h0 in H0S])
                if best is None or v < best[0]:
                    best = (v, round(float(Kp), 2), Ki, Kd)
    tuned = best[1:]
    tuned_h2 = mse(run_pid(*tuned, 2.0)[0])
    tuned_q_all = np.mean([mse(run_pid(*tuned, h0, quantize=True)[0]) for h0 in H0S])

    # The action grid: steady state h = (F/k)^2, so no listed inflow holds h = 5.
    steady = [round((f / TANK["k"]) ** 2, 2) for f in TANK["flows"]]
    hs, fs = run_policy(Qs[0], 2.0)
    tail = fs[-40:]
    chatter = {f: int(np.sum(tail == f)) for f in sorted(set(tail.tolist()))}
    switches = int(np.sum(tail[1:] != tail[:-1]))

    # A finer action grid, 9 inflows, the same everything else.
    fine = [round(x, 3) for x in np.linspace(0, 2, 9)]
    Qf = [q_learning_tank(s, flows=fine) for s in seeds]
    fine_all = [np.mean([mse(run_policy(Q, h0, fine)[0]) for h0 in H0S]) for Q in Qf]

    # Learning curve and sample count
    _, curve = q_learning_tank(0, curve=True)
    samples = 1000 * TANK["steps"]

    # Two rewards that look reasonable and are not what was meant.
    hacks = {}
    for kind in ["steady", "band"]:
        finals, mses = [], []
        for s in seeds:
            Q = q_learning_tank(s, reward=kind)
            per = [run_policy(Q, h0) for h0 in H0S]
            finals.append([round(float(p[0][-1]), 2) for p in per])
            mses.append(np.mean([mse(p[0]) for p in per]))
        hacks[kind] = {"final_levels_seed0": finals[0],
                       "mean_final_level": round(float(np.mean(finals)), 2),
                       "mse_mean": round(float(np.mean(mses)), 2)}
        if kind == "steady":
            hack_traj = run_policy(q_learning_tank(0, reward=kind), 8.0)
        else:
            band_traj = run_policy(q_learning_tank(0, reward=kind), 2.0)

    out = {
        "rl_mse_h2": {"mean": round(float(np.mean(rl_h2)), 3), "min": round(float(np.min(rl_h2)), 3),
                      "max": round(float(np.max(rl_h2)), 3)},
        "rl_mse_8starts": {"mean": round(float(np.mean(rl_all)), 3), "sd": round(float(np.std(rl_all)), 3),
                           "min": round(float(np.min(rl_all)), 3), "max": round(float(np.max(rl_all)), 3)},
        "pid_pycse_mse_h2": round(pid_h2, 3), "pid_pycse_mse_8starts": round(float(pid_all), 3),
        "pid_tuned_gains": tuned, "pid_tuned_mse_h2": round(tuned_h2, 3),
        "pid_tuned_mse_8starts": round(float(best[0]), 3),
        "pid_tuned_quantized_mse_8starts": round(float(tuned_q_all), 3),
        "steady_levels": steady, "chatter_last40_seed0": chatter, "switches_last40_seed0": switches,
        "fine_flows": fine, "rl_fine_mse_8starts": {"mean": round(float(np.mean(fine_all)), 3),
                                                     "sd": round(float(np.std(fine_all)), 3)},
        "transitions_trained": samples, "q_table": [TANK["n_states"], len(TANK["flows"])],
        "curve_first50": round(float(curve[:50].mean()), 1), "curve_last50": round(float(curve[-50:].mean()), 1),
        "hacks": hacks,
    }
    RESULTS["tank"] = out
    print("tank", json.dumps(out, indent=1))

    # Figure: the agent's ten seeds against the two PIDs, from h = 2
    t = np.arange(TANK["steps"] + 1) * TANK["dt"]
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.6), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    for i, Q in enumerate(Qs):
        ax[0].plot(t, run_policy(Q, 2.0)[0], color=GREEN, alpha=0.35, lw=1.2,
                   label="Q-learning, 10 seeds" if i == 0 else None)
    ax[0].plot(t, run_pid(*pycse_gains, 2.0)[0], color=GREY, lw=2, ls="--",
               label=f"PID, PyCSE gains {pycse_gains}")
    ax[0].plot(t, run_pid(*tuned, 2.0)[0], color=BLUE, lw=2, label=f"PID, tuned {tuned}")
    ax[0].axhline(5, color=RED, lw=1, ls=":")
    ax[0].set_ylabel("level h")
    ax[0].legend(frameon=False, fontsize=9, loc="lower right")
    ax[0].set_title("Tank level from h = 2: the agent against PID", fontsize=11)
    ax[1].step(t[:-1], fs, where="post", color=GREEN, lw=1.5, label="agent inflow (seed 0)")
    ax[1].plot(t[:-1], run_pid(*tuned, 2.0)[1], color=BLUE, lw=1.5, label="tuned PID inflow")
    ax[1].axhline(np.sqrt(5) * TANK["k"], color=RED, lw=1, ls=":")
    ax[1].text(26, np.sqrt(5) * TANK["k"] - 0.3, "F = 1.118 would hold h = 5; it is not on the menu", color=RED, fontsize=8)
    ax[1].set_ylabel("inflow F")
    ax[1].set_xlabel("time")
    ax[1].legend(frameon=False, fontsize=8, loc="center right", bbox_to_anchor=(1.0, 0.72), ncol=2)
    save(fig, "tank-compare.png")

    # Figure: learning curve
    fig, ax = plt.subplots(figsize=(7, 3))
    w = 50
    ax.plot(curve, color=GREEN, alpha=0.2)
    ax.plot(np.arange(w - 1, len(curve)), np.convolve(curve, np.ones(w) / w, "valid"), color=GREEN, lw=2)
    ax.set_xlabel("episode (100 steps each)")
    ax.set_ylabel("total reward")
    ax.set_title("Q-learning on the tank, seed 0: 100,000 transitions", fontsize=11)
    save(fig, "tank-learning.png")

    # Figure: reward hacking
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.4), sharey=True)
    ax[0].plot(t, hack_traj[0], color=ORANGE, lw=2)
    ax[0].axhline(5, color=RED, lw=1, ls=":")
    ax[0].set_title('reward = −|Δh| ("keep it steady"), from h = 8', fontsize=10)
    ax[0].set_xlabel("time")
    ax[0].set_ylabel("level h")
    ax[1].plot(t, band_traj[0], color=ORANGE, lw=2)
    ax[1].axhspan(4, 6, color=GREEN, alpha=0.12)
    ax[1].axhline(5, color=RED, lw=1, ls=":")
    ax[1].set_title('reward = +1 inside 5 ± 1, from h = 2', fontsize=10)
    ax[1].set_xlabel("time")
    save(fig, "tank-hacks.png")


# ---------------------------------------------------------------- cliff

CLIFF = dict(rows=4, cols=12, start=(3, 0), goal=(3, 11), step=-1, fall=-100)
MOVES = [(-1, 0), (0, 1), (1, 0), (0, -1)]  # up, right, down, left


def cliff_step(pos, a):
    r, c = pos
    dr, dc = MOVES[a]
    r = min(max(r + dr, 0), CLIFF["rows"] - 1)
    c = min(max(c + dc, 0), CLIFF["cols"] - 1)
    if r == 3 and 0 < c < 11:
        return CLIFF["start"], CLIFF["fall"], False
    return (r, c), CLIFF["step"], (r, c) == CLIFF["goal"]


def cliff_learn(method, seed, episodes=500, alpha=0.5, gamma=1.0, eps=0.1):
    rng = np.random.default_rng(seed)
    Q = np.zeros((4, 12, 4))

    def pick(p):
        if rng.random() < eps:
            return int(rng.integers(4))
        q = Q[p]
        return int(rng.choice(np.flatnonzero(q == q.max())))

    rets = []
    for _ in range(episodes):
        p = CLIFF["start"]
        a = pick(p)
        G, done, n = 0, False, 0
        while not done and n < 1000:
            p2, r, done = cliff_step(p, a)
            a2 = pick(p2)
            target = r if done else r + gamma * (Q[p2].max() if method == "q" else Q[p2][a2])
            Q[p][a] += alpha * (target - Q[p][a])
            p, a, G, n = p2, a2, G + r, n + 1
        rets.append(G)
    return Q, np.array(rets)


def greedy_path(Q):
    p, path = CLIFF["start"], [CLIFF["start"]]
    for _ in range(60):
        p, r, done = cliff_step(p, int(np.argmax(Q[p])))
        path.append(p)
        if done or r == CLIFF["fall"]:
            break
    return path


def cliff():
    runs = 50
    out = {}
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6), gridspec_kw={"width_ratios": [1.3, 1]})
    paths = {}
    for m, label, col in [("sarsa", "SARSA (on-policy)", BLUE), ("q", "Q-learning (off-policy)", ORANGE)]:
        R = np.zeros((runs, 500))
        lens = []
        for s in range(runs):
            Q, rets = cliff_learn(m, s)
            R[s] = rets
            lens.append(len(greedy_path(Q)) - 1)
            if s == 0:
                paths[m] = greedy_path(Q)
        sm = np.convolve(R.mean(0), np.ones(10) / 10, "valid")
        ax[0].plot(np.arange(9, 500), sm, color=col, lw=2, label=label)
        out[m] = {"online_return_last100": round(float(R[:, -100:].mean()), 1),
                  "greedy_path_len_mode": int(np.bincount(lens).argmax()),
                  "greedy_path_lens": sorted(set(lens))}
    ax[0].set_ylim(-110, 0)
    ax[0].set_xlabel("episode")
    ax[0].set_ylabel("return during learning (ε = 0.1)")
    ax[0].legend(frameon=False, fontsize=9, loc="lower right")
    ax[0].set_title("What the agent earns while it is still exploring", fontsize=11)
    a = ax[1]
    for c in range(1, 11):
        a.add_patch(plt.Rectangle((c, 0), 1, 1, color=RED, alpha=0.25))
    a.text(6, 0.5, "cliff  −100", ha="center", va="center", fontsize=9, color=RED)
    for m, col, off in [("sarsa", BLUE, 0.12), ("q", ORANGE, -0.12)]:
        xs = [c + 0.5 for r, c in paths[m]]
        ys = [3 - r + 0.5 + off for r, c in paths[m]]
        a.plot(xs, ys, color=col, lw=2.5)
    a.text(0.5, 0.5, "S", ha="center", va="center", fontweight="bold")
    a.text(11.5, 0.5, "G", ha="center", va="center", fontweight="bold")
    a.set_xlim(0, 12)
    a.set_ylim(0, 4)
    a.set_aspect("equal")
    a.set_xticks(range(13))
    a.set_yticks(range(5))
    a.grid(True, alpha=0.3)
    a.tick_params(labelbottom=False, labelleft=False, length=0)
    a.set_title("Greedy path after 500 episodes (seed 0)", fontsize=11)
    save(fig, "cliff.png")
    RESULTS["cliff"] = out
    print("cliff", json.dumps(out))


# ---------------------------------------------------------------- credit assignment

def credit():
    """A corridor of 8 cells, reward +1 only on reaching the right end. With alpha = 1 and the
    agent always walking right, one-step Q-learning moves the news one cell per episode."""
    n, gamma = 8, 0.9
    V = np.zeros(n)
    hist = [V.copy()]
    for ep in range(n):
        for s in range(n - 1):
            r = 1.0 if s + 1 == n - 1 else 0.0
            V[s] = r + (gamma * V[s + 1] if s + 1 < n - 1 else 0.0)
        hist.append(V.copy())
    # (each sweep above runs left to right, so it moves the news one cell per sweep)
    fig, ax = plt.subplots(figsize=(8, 3))
    for i, v in enumerate(hist[:6]):
        ax.plot(range(n - 1), v[:-1], marker="o", color=plt.cm.viridis(i / 6), label=f"after episode {i}")
    ax.plot(range(n - 1), [gamma ** (n - 2 - s) for s in range(n - 1)], color=GREY, ls="--", label="γ^(steps to go)")
    ax.set_xlabel("cell (goal is to the right of cell 6)")
    ax.set_ylabel("value of stepping right")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    ax.set_title("A reward at the end reaches the start one episode at a time", fontsize=11)
    save(fig, "credit.png")


# ---------------------------------------------------------------- choosing an action; a continuous policy

PG = dict(sigma=0.3, iters=300, batch=10, lr=0.01, gamma=0.95, seeds=10, tau=0.1)


def pg_episode(theta, rng, h0, T=TANK):
    """One episode of a Gaussian policy: the mean inflow is theta0 + theta1 (5 - h), the spread is
    fixed at sigma, and the sampled inflow is clipped to [0, 2] before the tank sees it."""
    h, xs, Fs, rs = h0, [], [], []
    for _ in range(T["steps"]):
        x = np.array([1.0, T["setpoint"] - h])
        F = float(theta @ x + PG["sigma"] * rng.standard_normal())
        Fa = float(np.clip(F, 0.0, 2.0))
        h = tank_step(h, Fa)
        xs.append(x)
        Fs.append(F)
        rs.append(reward_fn("setpoint", h, None, Fa))
    return np.array(xs), np.array(Fs), np.array(rs)


def pg_train(seed):
    """REINFORCE with discounted returns-to-go, normalized as the baseline. Two parameters."""
    rng = np.random.default_rng(seed)
    theta, curve = np.zeros(2), []
    for _ in range(PG["iters"]):
        eps = [pg_episode(theta, rng, rng.uniform(1.0, 9.0)) for _ in range(PG["batch"])]
        rets = []
        for _, _, rs in eps:
            G, acc = np.zeros_like(rs), 0.0
            for t in range(len(rs) - 1, -1, -1):
                acc = rs[t] + PG["gamma"] * acc
                G[t] = acc
            rets.append(G)
        allG = np.concatenate(rets)
        b, sd = allG.mean(), allG.std() + 1e-8
        g = np.zeros(2)
        for (xs, Fs, _), G in zip(eps, rets):
            # grad log N(F; mu, sigma) = (F - mu) / sigma^2 * x, weighted by how good the outcome was
            g += ((Fs - xs @ theta) / PG["sigma"] ** 2 * (G - b) / sd) @ xs
        theta = theta + PG["lr"] * g / PG["batch"]
        curve.append(float(np.mean([rs.sum() for _, _, rs in eps])))
    return theta, np.array(curve)


def pg_run(theta, h0, T=TANK):
    """The deployed policy uses the mean inflow, no noise."""
    h, hs = h0, [h0]
    for _ in range(T["steps"]):
        h = tank_step(h, float(np.clip(theta @ [1.0, T["setpoint"] - h], 0.0, 2.0)))
        hs.append(h)
    return np.array(hs)


def actions():
    T = TANK
    runs = [pg_train(s) for s in range(PG["seeds"])]
    thetas = np.array([r[0] for r in runs])
    m8 = [np.mean([mse(pg_run(th, h0)) for h0 in H0S]) for th in thetas]
    m2 = [mse(pg_run(th, 2.0)) for th in thetas]
    best = int(np.argsort(m8)[len(m8) // 2])  # the median seed, for the figures
    th = thetas[best]

    Q = q_learning_tank(0)
    s5 = tank_bin(T["setpoint"])
    row = Q[s5]
    soft = np.exp((row - row.max()) / PG["tau"])
    soft /= soft.sum()
    h_show = 4.8
    mu_show = float(th @ [1.0, T["setpoint"] - h_show])
    out = dict(thetas=thetas.round(3).tolist(), mse_8starts={"mean": round(float(np.mean(m8)), 3),
               "sd": round(float(np.std(m8)), 3), "min": round(float(np.min(m8)), 3), "max": round(float(np.max(m8)), 3)},
               mse_h2_mean=round(float(np.mean(m2)), 3), theta0_mean=round(float(thetas[:, 0].mean()), 3),
               holding_inflow=round(float(T["k"] * np.sqrt(T["setpoint"])), 3),
               transitions=PG["iters"] * PG["batch"] * T["steps"], median_seed=best,
               curve_first10=round(float(np.mean([r[1][:10].mean() for r in runs])), 1),
               curve_last20=round(float(np.mean([r[1][-20:].mean() for r in runs])), 1),
               q_row_setpoint={"bin_level": round(s5 * T["level_max"] / (T["n_states"] - 1), 2),
                               "q": row.round(2).tolist(), "softmax": soft.round(3).tolist(),
                               "argmax_F": T["flows"][int(np.argmax(row))]},
               gaussian_at_h48={"mu": round(mu_show, 3), "sigma": PG["sigma"]})
    RESULTS["actions"] = out
    print("actions", json.dumps(out))

    # Three ways to turn a state into an action
    fig, ax = plt.subplots(1, 3, figsize=(11, 3.1))
    F = np.array(T["flows"])
    a = int(np.argmax(row))
    base = float(np.floor(row.min() - 0.3))
    ax[0].bar(F, row - base, bottom=base, width=0.35, color=[RED if i == a else GREY for i in range(len(F))])
    ax[0].set_title(f"Q-table row at h ≈ {out['q_row_setpoint']['bin_level']}: take the argmax", fontsize=10)
    ax[0].set_xlabel("inflow F")
    ax[0].set_ylabel("Q(s, F), expected return")
    ax[0].set_ylim(base, row.max() + 0.3)
    ax[1].bar(F, soft, width=0.35, color=BLUE)
    ax[1].set_title(f"softmax of the same row (τ = {PG['tau']:g}): sample", fontsize=10)
    ax[1].set_xlabel("inflow F")
    ax[1].set_ylabel("probability")
    x = np.linspace(-0.2, 2.2, 400)
    pdf = np.exp(-0.5 * ((x - mu_show) / PG["sigma"]) ** 2) / (PG["sigma"] * np.sqrt(2 * np.pi))
    ax[2].plot(x, pdf, color=GREEN)
    ax[2].fill_between(x, pdf, alpha=0.2, color=GREEN)
    ax[2].axvline(mu_show, color=GREEN, ls="--")
    ax[2].axvspan(-0.2, 0, color=GREY, alpha=0.2)
    ax[2].axvspan(2, 2.2, color=GREY, alpha=0.2)
    ax[2].set_title(f"Gaussian policy at h = {h_show:g}: sample", fontsize=10)
    ax[2].text(0.05, 0.9, f"μ = {mu_show:.2f}\nσ = {PG['sigma']:g}", transform=ax[2].transAxes, fontsize=9, va="top")
    ax[2].set_xlabel("inflow F (grey: clipped)")
    ax[2].set_ylabel("density")
    for a_ in ax:
        a_.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Three ways a policy outputs an action: discrete by argmax, discrete by sampling, continuous by sampling", fontsize=11)
    save(fig, "action-heads.png")

    # The two policies side by side, and the policy-gradient learning curve
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.4))
    hgrid = np.linspace(0, 10, 400)
    stair = [T["flows"][int(np.argmax(Q[tank_bin(h)]))] for h in hgrid]
    ax[0].step(hgrid, stair, where="post", color=RED, label="Q-learning: argmax over 5 inflows")
    mu = np.clip(th[0] + th[1] * (T["setpoint"] - hgrid), 0, 2)
    ax[0].plot(hgrid, mu, color=GREEN, lw=2, label=f"Gaussian policy mean, θ = ({th[0]:.2f}, {th[1]:.2f})")
    ax[0].fill_between(hgrid, np.clip(mu - PG["sigma"], 0, 2), np.clip(mu + PG["sigma"], 0, 2), color=GREEN, alpha=0.15,
                       label="± σ while training")
    ax[0].axvline(T["setpoint"], color=GREY, ls=":")
    ax[0].axhline(out["holding_inflow"], color=GREY, ls="--", lw=1)
    ax[0].text(0.2, out["holding_inflow"] + 0.06, f"k√5 = {out['holding_inflow']}", fontsize=8, color=GREY)
    ax[0].set_xlabel("level h")
    ax[0].set_ylabel("inflow F chosen")
    ax[0].set_title("The policy, as a function of the state", fontsize=10)
    ax[0].legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0.1, 0.1))
    for r in runs:
        ax[1].plot(np.arange(1, PG["iters"] + 1), r[1], color=GREEN, alpha=0.3, lw=0.8)
    ax[1].set_yscale("symlog", linthresh=50)
    ax[1].set_xlabel(f"iteration ({PG['batch']} episodes each)")
    ax[1].set_ylabel("mean episode reward")
    ax[1].set_title(f"Policy gradient, {PG['seeds']} seeds", fontsize=10)
    for a_ in ax:
        a_.spines[["top", "right"]].set_visible(False)
    save(fig, "policy-gradient.png")


# ---------------------------------------------------------------- Q-learning by hand

QH = dict(states=["low", "ok", "high"], actions=["shut", "open"], alpha=0.5, gamma=0.9, effort=0.1,
          script=[(0, 1), (1, 1), (2, 0), (1, 0), (0, 1), (1, 1)], steps=300, episode=10, epsilon=0.3, seed=3)


def qh_step(s, a, T=QH):
    """A three-level tank. Open raises the level one step and shut lowers it one step (it cannot go
    past low or high). Landing at ok earns +1 and opening costs 0.1, like the tank's effort term.
    As in the real tank, no action holds the level at ok."""
    s2 = min(s + 1, 2) if a == 1 else max(s - 1, 0)
    return s2, (1.0 if s2 == 1 else 0.0) - T["effort"] * a


def qhand():
    """Q-learning on a 3 x 2 table, small enough to do by hand: a scripted first episode, then
    epsilon-greedy steps, against Q* from value iteration."""
    T, al, g = QH, QH["alpha"], QH["gamma"]
    Q = np.zeros((3, 2))
    trace = []

    def update(s, a):
        s2, r = qh_step(s, a)
        old, best = Q[s, a], Q[s2].max()
        target = r + g * best
        Q[s, a] = old + al * (target - old)
        trace.append(dict(s=s, a=a, r=round(float(r), 4), s2=s2, old=round(float(old), 4), best=round(float(best), 4),
                          target=round(float(target), 4), new=round(float(Q[s, a]), 4)))
        return s2

    for s, a in T["script"]:
        update(s, a)
    after_script = Q.copy()
    rng = np.random.default_rng(T["seed"])
    s = 0
    for t in range(T["steps"]):
        if t % T["episode"] == 0:
            s = int(rng.integers(3))
        a = int(rng.integers(2)) if rng.random() < T["epsilon"] else int(np.argmax(Q[s]))
        s = update(s, a)
    # Q* by value iteration on the known model
    Qs = np.zeros((3, 2))
    for _ in range(2000):
        Qn = np.array([[qh_step(s, a)[1] + g * Qs[qh_step(s, a)[0]].max() for a in range(2)] for s in range(3)])
        if np.abs(Qn - Qs).max() < 1e-12:
            break
        Qs = Qn
    err = [None] * len(trace)
    Qr = np.zeros((3, 2))
    for i, u in enumerate(trace):
        Qr[u["s"], u["a"]] = u["new"]
        err[i] = float(np.abs(Qr - Qs).max())
    within = next((i + 1 for i, e in enumerate(err) if e < 0.01), None)
    # the first update after which the greedy policy is pi* and stays so
    pol, Qr, star = [], np.zeros((3, 2)), Qs.argmax(1).tolist()
    for u in trace:
        Qr[u["s"], u["a"]] = u["new"]
        pol.append(all(Qr[i, star[i]] > Qr[i, 1 - star[i]] for i in range(3)))  # strictly, no ties
    settled = next(i + 1 for i in range(len(pol)) if all(pol[i:]))
    visits = np.zeros((3, 2), int)
    for u in trace:
        visits[u["s"], u["a"]] += 1
    out = dict(after_script=after_script.round(3).tolist(), final=Q.round(3).tolist(), qstar=Qs.round(3).tolist(),
               policy=[T["actions"][int(np.argmax(r))] for r in Qs], max_err_final=round(err[-1], 4),
               updates_to_0p01=within, policy_settled_at=settled, visits=visits.tolist(),
               err_by_entry=np.abs(Q - Qs).round(3).tolist())
    RESULTS["qhand"] = out
    QH["trace"], QH["qstar"] = trace, Qs.round(4).tolist()
    print("qhand", json.dumps(out))
    for u in trace[:6]:
        print("  ", u)

    fig, axes = plt.subplots(1, 3, figsize=(8.5, 2.8))
    for ax, M, title in zip(axes, [after_script, Q, Qs],
                            ["after the scripted episode (6 updates)", f"after {len(trace)} updates", "Q* from value iteration"]):
        ax.imshow(M, cmap="Blues", vmin=min(-0.6, M.min()), vmax=max(5, M.max()))
        for i in range(3):
            for j in range(2):
                ax.text(j, i, f"{M[i, j]:.3f}", ha="center", va="center", fontsize=10,
                        color="white" if M[i, j] > 2.5 else "black",
                        fontweight="bold" if j == np.argmax(M[i]) and np.ptp(M[i]) > 0 else "normal")
        ax.set_xticks([0, 1], T["actions"])
        ax.set_yticks([0, 1, 2], T["states"])
        ax.set_title(title, fontsize=10)
    fig.suptitle("Q-learning on a three-level tank: the table is a 3 × 2 matrix (bold = greedy action)", fontsize=11)
    save(fig, "qhand.png")


# ---------------------------------------------------------------- landscape

def landscape():
    rows = [
        ("Supervised (L9, L10)", "x → y*", "the right answer", "none", "one prediction"),
        ("Generative (L16)", "samples of x", "nothing: match the data", "none", "a new sample"),
        ("BO, active learning (L15)", "choose x, see y", "a score for that choice", "none", "one experiment"),
        ("Bandit", "choose an arm, see r", "a noisy score", "none", "one pull"),
        ("Reinforcement learning", "act, see r and s′", "a score, often late", "the action changes it", "a sequence"),
    ]
    fig, ax = plt.subplots(figsize=(11, 3.3))
    ax.axis("off")
    cols = ["method", "data the learner sees", "what it is told", "state", "a decision is"]
    tbl = ax.table(cellText=[list(r) for r in rows], colLabels=cols, loc="center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.6)
    for (i, j), cell in tbl.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if i == 0:
            cell.set_text_props(fontweight="bold")
        if i == 5:
            cell.set_facecolor("#e8f1fa")
    save(fig, "landscape.png")


def widget_data():
    data = {
        "tank": {k: TANK[k] for k in ["A", "k", "setpoint", "dt", "steps", "n_states", "level_max", "flows", "effort"]},
        "tankTrain": {"episodes": 1000, "alpha": 0.2, "gamma": 0.95, "epsilon": 0.2},
        "pid": {"pycse": [0.8, 0.1, 0.2], "tuned": list(RESULTS["tank"]["pid_tuned_gains"])},
        "bandit": {"arms": ARMS, "means": ARM_MEANS.tolist(), "sd": ARM_SD, "pulls": 500,
                   "epsilon": 0.1, "c": ARM_SD, "prior": [65.0, 15.0]},
        "cliff": {"rows": 4, "cols": 12, "step": -1, "fall": -100, "alpha": 0.5, "epsilon": 0.1, "episodes": 500},
        "credit": {"cells": 8, "gamma": 0.9},
        "qhand": {k: QH[k] for k in ["states", "actions", "alpha", "gamma", "effort", "script", "trace", "qstar"]},
        "results": RESULTS,
    }
    path = REPO / "_static" / "l20-widget-data.js"
    path.write_text("/* Generated by lectures/l20/figures/make_figures.py. Do not edit. */\n"
                    "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
                    "window.COURSE_WIDGET_DATA.l20 = " + json.dumps(data) + ";\n")
    print("wrote", path.relative_to(REPO))


if __name__ == "__main__":
    bandit()
    tank()
    cliff()
    credit()
    qhand()
    actions()
    landscape()
    (HERE / "results.json").write_text(json.dumps(RESULTS, indent=1) + "\n")
    widget_data()
