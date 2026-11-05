#!/usr/bin/env python3
"""Figures and numbers for L20, reinforcement learning.

Worked examples, each small enough to run in seconds with NumPy alone, so every number in the
notes and on the slides can be regenerated and checked:

  tank     the PyCSE tank (A = 1, k = 0.5, setpoint 5, inflow from {0, 0.5, 1, 1.5, 2}),
           tabular Q-learning with PyCSE's settings over ten seeds, against PID with PyCSE's
           hand-picked gains and with gains tuned on the same test, and two rewards that a
           reasonable engineer might write that the agent satisfies the wrong way.

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


# ---------------------------------------------------------------- bandit (widget data only)

ARMS = ["Cat A", "Cat B", "Cat C", "Cat D", "Cat E"]
ARM_MEANS = np.array([62.0, 70.0, 74.0, 66.0, 58.0])  # mean yield, %
ARM_SD = 8.0  # run-to-run noise in one yield measurement, %


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


# ---------------------------------------------------------------- the MDP as matrices

def policy_matrices(P, R, Pi):
    """Collapse per-action transition matrices into the Markov chain a policy induces.
    P is (nA, nS, nS), R is (nS, nA), Pi is (nS, nA) with rows summing to one."""
    P_pi = sum(np.diag(Pi[:, a]) @ P[a] for a in range(P.shape[0]))
    r_pi = (Pi * R).sum(1)
    return P_pi, r_pi


def evaluate(P, R, Pi, gamma):
    """Policy evaluation is a linear solve: (I - gamma P_pi) V = r_pi."""
    P_pi, r_pi = policy_matrices(P, R, Pi)
    return np.linalg.solve(np.eye(len(r_pi)) - gamma * P_pi, r_pi)


def value_iteration(P, R, gamma, tol=1e-12, max_iter=10000):
    """Q <- R + gamma * [P_a V]_a with V = max_a Q. Matrix products, then one max."""
    Q = np.zeros_like(R)
    for it in range(1, max_iter + 1):
        Qn = R + gamma * np.einsum("ast,t->sa", P, Q.max(1))
        if np.abs(Qn - Q).max() < tol:
            return Qn, it
        Q = Qn
    raise RuntimeError("value iteration did not converge")


def mdp_matrices():
    """The three-level tank of the by-hand example, written as the matrices that define it.
    Checks that value iteration on them gives the Q* that qhand() printed, and that the greedy
    policy's value from one linear solve is the same vector."""
    T, g = QH, QH["gamma"]
    nS, nA = 3, 2
    P, R = np.zeros((nA, nS, nS)), np.zeros((nS, nA))
    for s in range(nS):
        for a in range(nA):
            s2, r = qh_step(s, a)
            P[a, s, s2] = 1.0
            R[s, a] = r
    Qs, iters = value_iteration(P, R, g)
    assert np.allclose(Qs.round(3), RESULTS["qhand"]["qstar"]), "value iteration disagrees with qhand()"
    greedy = np.eye(nA)[Qs.argmax(1)]
    V_greedy = evaluate(P, R, greedy, g)
    assert np.allclose(V_greedy, Qs.max(1), atol=1e-9), "linear solve disagrees with value iteration"
    uniform = np.full((nS, nA), 0.5)
    V_uniform = evaluate(P, R, uniform, g)
    P_pi, r_pi = policy_matrices(P, R, greedy)
    # the first sweeps of value iteration, and the gap to Q* after each
    Q, sweeps = np.zeros((nS, nA)), []
    for k in range(6):
        Q = R + g * np.einsum("ast,t->sa", P, Q.max(1))
        sweeps.append(dict(Q=Q.round(3).tolist(), gap=round(float(np.abs(Q - Qs).max()), 3)))
    out = dict(P_shut=P[0].astype(int).tolist(), P_open=P[1].astype(int).tolist(), R=R.round(3).tolist(),
               qstar=Qs.round(3).tolist(), vi_iterations=iters,
               greedy_policy=[T["actions"][i] for i in Qs.argmax(1)],
               P_greedy=P_pi.astype(int).tolist(), r_greedy=r_pi.round(3).tolist(),
               V_greedy=V_greedy.round(3).tolist(), V_uniform=V_uniform.round(3).tolist(), sweeps=sweeps)
    RESULTS["mdp_matrices"] = out
    print("mdp_matrices", json.dumps(out))
    # For the mdp-step widget: the matrices, and every value-iteration sweep until it settles to
    # three decimals, so the reader can step through planning one sweep at a time.
    Q, vi = np.zeros((nS, nA)), [np.zeros((nS, nA)).tolist()]
    for k in range(400):
        Q = R + g * np.einsum("ast,t->sa", P, Q.max(1))
        vi.append(Q.round(3).tolist())
        if np.abs(Q - Qs).max() < 5e-4:
            break
    MDP.update(states=T["states"], actions=T["actions"], gamma=g, P=P.astype(int).tolist(),
               R=R.round(3).tolist(), sweeps=vi, qstar=Qs.round(3).tolist())

    fig, axes = plt.subplots(1, 3, figsize=(9, 3.0), gridspec_kw={"width_ratios": [3, 3, 2]})
    panels = [(P[0], "$P_{shut}$", T["states"], "%d"), (P[1], "$P_{open}$", T["states"], "%d"),
              (R, "$R$", T["actions"], "%.1f")]
    for ax, (M, title, cols, fmt) in zip(axes, panels):
        ax.imshow(M, cmap="Blues", vmin=min(0.0, M.min()) - 0.2, vmax=M.max() * 1.4 + 0.01, aspect="auto")
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                ax.text(j, i, fmt % M[i, j], ha="center", va="center", fontsize=11)
        ax.set_xticks(range(len(cols)), cols)
        ax.set_yticks(range(3), T["states"])
        ax.set_title(title, fontsize=11)
        ax.spines[:].set_visible(False)
        ax.tick_params(length=0)
    axes[0].set_xlabel("next state $s'$")
    axes[1].set_xlabel("next state $s'$")
    axes[0].set_ylabel("state $s$")
    fig.suptitle("The three-level tank as matrices: one transition matrix per action, and the rewards",
                 fontsize=10.5)
    save(fig, "mdp-toy.png")


MDP: dict = {}


def mdp_diagram():
    """The three-level tank's rules as a state diagram: one circle per level, one arrow per
    (level, action), labelled with the reward. The same six facts as the table in the notes."""
    from matplotlib.patches import Circle, FancyArrowPatch
    xs = {0: 0.0, 1: 3.0, 2: 6.0}
    names = QH["states"]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for s, x in xs.items():
        ax.add_patch(Circle((x, 0), 0.55, fc="#eef3f9", ec=BLUE, lw=2))
        ax.text(x, 0, names[s], ha="center", va="center", fontsize=14, weight="bold")

    def arrow(s, s2, a, label, rad):
        col = BLUE if a == 1 else ORANGE
        if s == s2:
            x = xs[s]
            y0 = 0.55 if a == 1 else -0.55
            sign = 1 if a == 1 else -1
            ax.add_patch(FancyArrowPatch((x - 0.3, y0), (x + 0.3, y0), connectionstyle="arc3,rad=%s" % (-1.8 * sign),
                                         arrowstyle="-|>", mutation_scale=16, color=col, lw=2))
            ax.text(x, y0 + sign * 0.95, label, ha="center", va="center", color=col, fontsize=11)
            return
        ax.add_patch(FancyArrowPatch((xs[s], 0), (xs[s2], 0), connectionstyle="arc3,rad=%s" % rad,
                                     arrowstyle="-|>", mutation_scale=16, color=col, lw=2,
                                     shrinkA=24, shrinkB=24))
        mid = (xs[s] + xs[s2]) / 2
        # arc3 with a negative rad bends left of the direction of travel: rightward arrows arc
        # above the circles, leftward ones below.
        ax.text(mid, 1.0 if xs[s2] > xs[s] else -1.0, label, ha="center", va="center", color=col, fontsize=11)

    for s in range(3):
        for a in range(2):
            s2, r = qh_step(s, a)
            lab = f"{QH['actions'][a]}, r = " + ("0" if r == 0 else f"{r:+.1f}".replace("-", "\u2212"))
            if s == s2:
                arrow(s, s2, a, lab, 0)
            else:
                arrow(s, s2, a, lab, -0.45 if s2 > s else -0.45)
    ax.set_xlim(-1.4, 7.4)
    ax.set_ylim(-2.1, 2.1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(-1.3, 1.95, "open (blue) raises the level one step; shut (orange) lowers it one step", fontsize=10,
            color=GREY)
    save(fig, "mdp-diagram.png")


def tank_model(sampler, n_per_bin=4000, T=TANK):
    """Transition matrices P_a (nA, nS, nS) and mean rewards R (nS, nA) for the 20-bin tank.
    `sampler(s)` returns the levels inside bin s to push through the physics."""
    nS, flows = T["n_states"], T["flows"]
    P, R = np.zeros((len(flows), nS, nS)), np.zeros((nS, len(flows)))
    for s in range(nS):
        hs = sampler(s)
        for a, F in enumerate(flows):
            h2 = np.array([tank_step(h, F) for h in hs])
            P[a, s] = np.bincount([tank_bin(x) for x in h2], minlength=nS) / len(hs)
            R[s, a] = np.mean([reward_fn("setpoint", x, h, F) for x, h in zip(h2, hs)])
    return P, R


def tank_matrices():
    """The 20-bin tank as five 20 x 20 transition matrices, built by pushing levels spread across
    each bin through tank_step. The physics is deterministic; the bins are not, because a bin
    hides where in it the level is, so each row splits between at most two next bins. Value
    iteration on these matrices is what tabular Q-learning was estimating from samples.

    Bin s covers [s w, (s + 1) w) with w = 10 / 19, and bin 19 holds every level from 10 up (see
    tank_bin), so its levels are drawn from [10, 10 + w). Spreading levels uniformly inside a bin
    is an assumption; the agent's own visits are not uniform."""
    T, g = TANK, 0.95
    nS, flows = T["n_states"], T["flows"]
    w = T["level_max"] / (nS - 1)
    n = 4000

    def uniform_in_bin(s):
        return s * w + (np.arange(n) + 0.5) * w / n

    P, R = tank_model(uniform_in_bin)
    assert np.allclose(P.sum(2), 1.0)
    Qvi, iters = value_iteration(P, R, g, tol=1e-10)
    pi = Qvi.argmax(1)
    vi_8 = float(np.mean([mse(run_policy(Qvi, h0)[0]) for h0 in H0S]))
    vi_h2 = mse(run_policy(Qvi, 2.0)[0])

    # Tabular Q-learning, the same ten seeds as tank(), against the exact solution
    Qls = [q_learning_tank(s) for s in range(10)]
    agree = [int((Q.argmax(1) == pi).sum()) for Q in Qls]
    disagree_bins = sorted({int(b) for Q in Qls for b in np.where(Q.argmax(1) != pi)[0]})
    ql_8 = [float(np.mean([mse(run_policy(Q, h0)[0]) for h0 in H0S])) for Q in Qls]
    # Inflows that hold the level inside its own bin: a self-loop of probability 1 in P_a. A seed
    # that picks one of these in a rarely visited bin parks the tank there.
    traps = {f"bin{s}_F{flows[a]:g}": float(P[a, s, s]) for s, a in [(1, 1), (17, 3)]}
    choices = {f"bin{s}": [flows[int(Q[s].argmax())] for Q in Qls] for s in (0, 1, 17, 18)}

    # Model-based on the same budget: 100,000 random transitions, counted into P-hat and R-hat,
    # then solved. Ten seeds.
    mb_8, unvisited = [], []
    for seed in range(10):
        rng = np.random.default_rng(100 + seed)
        cnt, rsum = np.zeros_like(P), np.zeros_like(R)
        for _ in range(1000):
            h = rng.uniform(1.0, 9.0)
            for _ in range(T["steps"]):
                s, a = tank_bin(h), int(rng.integers(len(flows)))
                h2 = tank_step(h, flows[a])
                cnt[a, s, tank_bin(h2)] += 1
                rsum[s, a] += reward_fn("setpoint", h2, h, flows[a])
                h = h2
        visits = cnt.sum(2).T                       # (nS, nA)
        Ph = cnt / np.maximum(visits.T[:, :, None], 1)  # an unvisited pair keeps a zero row
        Rh = rsum / np.maximum(visits, 1)
        Qmb, _ = value_iteration(Ph, Rh, g, tol=1e-10)
        mb_8.append(float(np.mean([mse(run_policy(Qmb, h0)[0]) for h0 in H0S])))
        unvisited.append(int((visits == 0).sum()))

    out = dict(gamma=g, n_per_bin=n, max_nonzeros_per_row=int((P > 0).sum(2).max()),
               example_row=dict(F=flows[2], bin=9, P=P[2, 9].round(3).tolist()),
               vi_iterations=iters, vi_policy=[flows[i] for i in pi],
               vi_mse_8starts=round(vi_8, 3), vi_mse_h2=round(vi_h2, 3),
               ql_policy_agreement=agree, ql_disagree_bins=disagree_bins,
               ql_mse_8starts=[round(x, 3) for x in ql_8], ql_choices_by_seed=choices, trap_self_loops=traps,
               model_based_mse_8starts=dict(mean=round(float(np.mean(mb_8)), 3), sd=round(float(np.std(mb_8)), 3),
                                            min=round(float(np.min(mb_8)), 3), max=round(float(np.max(mb_8)), 3)),
               model_based_unvisited_pairs=unvisited, transitions=1000 * T["steps"])
    RESULTS["tank_matrices"] = out
    print("tank_matrices", json.dumps(out))

    edges = np.arange(nS + 1) * w
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.9), gridspec_kw={"width_ratios": [1, 1, 1.35]})
    for k, a in enumerate([0, 2]):
        ax[k].imshow(P[a], cmap="Blues", vmin=0, vmax=1, origin="lower",
                     extent=[0, edges[-1], 0, edges[-1]])
        ax[k].plot([0, edges[-1]], [0, edges[-1]], color=GREY, lw=0.6, ls=":")
        ax[k].set_title(f"$P_a$ for inflow F = {flows[a]:g}", fontsize=10.5)
        ax[k].set_xlabel("next level bin (h)")
        ax[k].set_ylabel("level bin now (h)")
    ax[0].text(0.4, 9.5, "valve shut: every\nlevel falls, so the\nmass sits left of\nthe diagonal", fontsize=8, va="top")
    ax[1].text(0.4, 9.5, "F = 1 holds h = 4:\nabove it, left of the\ndiagonal; below it,\nright of it", fontsize=8, va="top")
    centres = (np.arange(nS) + 0.5) * w
    for i, Q in enumerate(Qls):
        ax[2].plot(centres, [flows[j] for j in Q.argmax(1)], "o", ms=4, color=GREEN, alpha=0.25,
                   label="Q-learning, 10 seeds" if i == 0 else None)
    ax[2].step(edges, [flows[j] for j in pi] + [flows[pi[-1]]], where="post", color=BLUE, lw=2,
               label=f"value iteration on $P_a$ (MSE {vi_8:.3f})")
    ax[2].axvline(T["setpoint"], color=RED, lw=1, ls=":")
    ax[2].set_xlabel("level h")
    ax[2].set_ylabel("inflow chosen")
    ax[2].set_title("Greedy policy, solved and learned", fontsize=10.5)
    ax[2].legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(0.5, 0.66))
    save(fig, "tank-matrices.png")


# ---------------------------------------------------------------- landscape

def landscape():
    rows = [
        ("Supervised (L9, L10)", "x → y*", "the right answer", "none", "one prediction"),
        ("Generative (L16)", "samples of x", "nothing: match the data", "none", "a new sample"),
        ("BO, active learning (L15)", "choose x, see y", "a score for that choice", "none", "one experiment"),
        ("Reinforcement learning", "act, see r and s′", "a score, often late", "the action changes it", "a sequence"),
    ]
    fig, ax = plt.subplots(figsize=(11, 2.4))
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
        if i == 4:
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
        "mdp": MDP,
        "results": RESULTS,
    }
    path = REPO / "_static" / "l20-widget-data.js"
    path.write_text("/* Generated by lectures/l20/figures/make_figures.py. Do not edit. */\n"
                    "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
                    "window.COURSE_WIDGET_DATA.l20 = " + json.dumps(data) + ";\n")
    print("wrote", path.relative_to(REPO))


if __name__ == "__main__":
    tank()
    credit()
    qhand()
    mdp_matrices()
    mdp_diagram()
    tank_matrices()
    actions()
    landscape()
    (HERE / "results.json").write_text(json.dumps(RESULTS, indent=1) + "\n")
    widget_data()
