# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy"]
# ///
"""Make the Assignment 5 data: five experiments on a continuous bioreactor.

    uv run --no-project course/assignments/a05-make-data.py

writes course/assignments/a05-bioreactor.csv and its .sha256. Both are published
at the site root, where the A5 notebook reads the CSV by URL.

Run this once. The CSV is the data, and the committed copy is the reference:
NumPy does not promise the same random stream across versions, so a rerun on a
newer NumPy may not reproduce it bit for bit, and the reference solution's
numbers would move with it.

The model is the chemostat of the 06-325 homework 3 (fall 2025), at the
nominal feed. Every experiment starts in the basin of the productive steady
state, X = 3.46198 kg/m3 and S = 45.6033 mol/m3, so none washes out.
Experiments 1 to 4 are for training and are kept for their first 100 s only,
the transient: fitting a neural ODE sequentially to the whole 300 s of these
oscillating responses stalls in local minima for some seeds, and the first
100 s do not (see wk07.md). Experiment 5 is the test, kept for all 300 s. The
noise is drawn for all 61 samples of every experiment, in order, so the rows
that are kept are the same as in earlier versions of this file.
"""

import hashlib
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
OUT = HERE / "a05-bioreactor.csv"

V = np.pi * 3.0**2 * 5.7     # m3
F = 5.02597                  # m3/s
SF = 300.0                   # mol/m3

SEED = 6763
T = np.arange(0, 301, 5)                 # s, 61 samples
T_TRAIN = 100                            # s: experiments 1 to 4 are kept up to here
NOISE = {"X": 0.05, "S": 1.0}            # standard deviation of each measurement
EXPERIMENTS = {                          # X0 (kg/m3), S0 (mol/m3)
    1: (5.0, 10.0),
    2: (2.0, 20.0),
    3: (4.0, 120.0),
    4: (2.5, 60.0),
    5: (3.0, 80.0),                      # the test experiment
}


def mu(S):
    return 1e-3 * S * np.exp(-S / 120.0)


def sigma(S):
    return mu(S) / (5.4e-3 + 1.8e-4 * S)


def bioreactor(t, y):
    X, S = y
    dXdt = -F / V * X + mu(S) * X
    dSdt = F / V * (SF - S) - sigma(S) * X
    return [dXdt, dSdt]


def main():
    rng = np.random.default_rng(SEED)
    lines = ["experiment,t,X,S"]
    for exp, ic in EXPERIMENTS.items():
        sol = solve_ivp(
            bioreactor,
            (0, T[-1]),
            ic,
            t_eval=T,
            rtol=1e-10,
            atol=1e-12,
        )
        X = sol.y[0] + NOISE["X"] * rng.standard_normal(T.size)
        S = sol.y[1] + NOISE["S"] * rng.standard_normal(T.size)
        X[0], S[0] = ic          # the reactor is charged with known amounts
        for k, t in enumerate(T):
            if exp != 5 and t > T_TRAIN:
                continue
            lines.append(f"{exp},{t},{X[k]:.4f},{S[k]:.3f}")
    OUT.write_text("\n".join(lines) + "\n")
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    OUT.with_suffix(".csv.sha256").write_text(f"{digest}  {OUT.name}\n")
    print(f"wrote {OUT.name}: {len(lines) - 1} rows, sha256 {digest}")


if __name__ == "__main__":
    main()
