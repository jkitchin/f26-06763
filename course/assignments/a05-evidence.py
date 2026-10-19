# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=1.26", "scipy>=1.11"]
# ///
r"""Build the Assignment 5 evidence report.

Run this in the root of your A5 project, the directory holding `data/`,
`results/` and your `REPORT.md`:

    uv run --no-project https://kitchingroup.cheme.cmu.edu/f26-06763/a05-evidence.py \
        --andrew-id yourid --name "Your Name"

or, on a copy you downloaded:

    uv run --no-project a05-evidence.py --andrew-id yourid --name "Your Name"

`--no-project` matters. This script declares its own dependencies in the block
at the top of this file, so uv builds it a small environment of its own, and a
stale lockfile in *your* project cannot leave you with no report at all.

It writes `evidence.pdf`. Upload that to Canvas. Read it before you send it.

WHAT IT DOES. A5 is worth six points, in five groups. This script decides four
of them and prints the total on the first page; the fifth is your answers in
`REPORT.md`, which a person reads. Within a group the checks are equally
weighted.

It does not take your numbers on trust. It solves the bioreactor model itself,
and it fits the discrete-time model the assignment fixes, from the same data
file you used. Then it checks:

  * your true model and your discrete-time model for run 5 against its own,
    which is exact, because both have one answer;
  * your PINN and neural ODE for run 5 against the true model, within a
    tolerance. A trained network is not exact: the same code gives slightly
    different numbers on different computers;
  * your learned growth rate against the true one;
  * the RMSEs in your `REPORT.md` against the ones it computes from your
    `run5.csv`.

It also reads your code for `jax.grad` and `diffeqsolve`.

IT DOES NOT CHANGE YOUR FILES. It reads the data, the results and the code,
and writes `evidence.pdf` (and `evidence.html` with --html). It does not re-run
your code and does not download anything.

NAMES. The assignment names its deliverables (`results/run5.csv`,
`results/mu.csv`, `results/run5.png`, `REPORT.md`) and this script looks for
those first. When it does not find them it goes looking by what the files
contain. What it found is printed at the top, and every guess can be
overridden with --data, --run5, --mu and --report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp

SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ipynb_checkpoints",
             "build", "dist", ".pytest_cache", "site-packages", ".mypy_cache",
             ".ruff_cache", "target"}
OURS = ("a05-evidence.py", "a05-make-data.py", "evidence.html", "evidence.pdf")

DATA_FILE = "a05-bioreactor.csv"
DATA_SHA256 = "b079d36b419c02d9001b3fd794a8245c934b4bf23ceea4140f7b2b0500d4137c"

# The model, as the assignment gives it.
V = math.pi * 3.0**2 * 5.7     # m3
F = 5.02597                    # m3/s
SF = 300.0                     # mol/m3

TRAIN = (1, 2, 3, 4)
IC5 = (3.0, 80.0)                            # run 5, the new start-up
T = np.arange(0, 301, 5).astype(float)       # s, 61 samples
ALPHA = 1.0                                  # Ridge(alpha=1.0)
S_GRID = np.arange(10, 131, 5).astype(float)
MU_RANGE = (20.0, 130.0)                     # where the training data pin mu down

MODELS = ("true", "discrete", "pinn", "node")
COLUMNS = ["t"] + [f"{v}_{m}" for m in MODELS for v in ("x", "s")]

# Tolerances. The true model and the ridge model have one answer each, so their
# tolerances only absorb solver and rounding differences; the true-model one
# also passes V rounded to 161.16 m3 (S off by 0.044) and fails solve_ivp's
# default tolerances (S off by 0.36). The trained networks get limits from the
# reference solution run several ways (float64 and float32, seeds 0 to 3, two
# learning-rate schedules for the PINN), with about three times the worst run
# to spare: a network that trained passes, and one that did not train fails.
TRUE_TOL = (2e-3, 5e-2)                      # max |error| in X (kg/m3), S (mol/m3)
DISCRETE_TOL = (1e-3, 1e-2)
PINN_LIMIT = (0.10, 2.5)                     # RMSE X, S against the true model
NODE_LIMIT = (0.05, 1.5)
MU_REL_TOL = 0.05                            # 5 % of the true mu

# --------------------------------------------------------------------------
# The five groups. Four are scored here; group 5 is the report, and a TA reads
# it. Within a group the checks are equally weighted. Points sum to 6.
# --------------------------------------------------------------------------
GROUPS = [
    ("discrete", "Discrete-time model", 1.0, "script"),
    ("pinn",     "PINN",                1.0, "script"),
    ("node",     "Neural ODE",          1.5, "script"),
    ("compare",  "Comparison",          1.5, "script"),
    ("report",   "REPORT.md",           1.0, "your TA"),
]
TOTAL = sum(g[2] for g in GROUPS)
AUTO_TOTAL = sum(g[2] for g in GROUPS if g[3] == "script")
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Step:
    """One recorded action: what was read, what came back."""

    def __init__(self, label, stdout, ok=True):
        self.label, self.stdout, self.ok = label, stdout, ok


# ------------------------------------------------------------------ discovery

def _usable(path):
    return not any(part in SKIP_DIRS for part in Path(path).parts)


def walk(root, patterns):
    found, seen, out = [], set(), []
    for pattern in patterns:
        found += [p for p in sorted(root.rglob(pattern))
                  if p.is_file() and _usable(p.relative_to(root))]
    for p in found:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def notebook_sources(path):
    try:
        cells = json.loads(Path(path).read_text(errors="replace"))["cells"]
    except (ValueError, KeyError, TypeError, OSError):
        return ""
    return "\n\n".join("".join(c.get("source", []))
                       for c in cells if c.get("cell_type") == "code")


def text_of(path):
    path = Path(path)
    if path.suffix == ".ipynb":
        return notebook_sources(path)
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def given_path(root, flag):
    if not flag:
        return None
    p = Path(flag)
    p = p if p.is_absolute() else root / p
    return p if p.exists() else None


def by_name(candidates, hints):
    scored = []
    for path in candidates:
        hint = min((i for i, h in enumerate(hints) if h in str(path).lower()),
                   default=len(hints))
        scored.append((hint, len(str(path)), path))
    scored.sort()
    return scored[0][2] if scored else None


def csv_header(path):
    try:
        with open(path, errors="replace") as f:
            return [c.strip().strip('"').lower() for c in f.readline().split(",")]
    except OSError:
        return []


def discover(root, args):
    found = {}

    def csv_with(flag, needed, hints):
        p = given_path(root, flag)
        if p is not None:
            return p
        cands = [c for c in walk(root, ["*.csv"]) if needed <= set(csv_header(c))]
        return by_name(cands, hints)

    data = given_path(root, args.data)
    if data is None:
        named = walk(root, [DATA_FILE])
        data = named[0] if named else None
    found["data"] = data
    found["run5"] = csv_with(args.run5, {"t", "x_node", "s_node"}, ["results/run5", "run5"])
    found["mu"] = csv_with(args.mu, {"s", "mu"}, ["results/mu", "mu"])
    found["png"] = by_name(walk(root, ["*.png"]), ["results/run5", "run5", "run_5"])
    if found["png"] is not None and not re.search(r"run.?5", found["png"].name, re.I):
        found["png"] = None

    report = given_path(root, args.report)
    if report is None:
        report = by_name(walk(root, ["REPORT.md", "report.md", "*.md"]),
                         ["report.md", "report", "readme"])
    found["report"] = report

    found["code"] = [p for p in walk(root, ["*.py", "*.ipynb"]) if p.name not in OURS]
    return found


# ------------------------------------------------------------ the reference

def mu_true(S):
    return 1e-3 * S * np.exp(-S / 120.0)


def bioreactor(t, y):
    X, S = y
    mu = mu_true(S)
    return [-F / V * X + mu * X, F / V * (SF - S) - mu / (5.4e-3 + 1.8e-4 * S) * X]


def true_run5():
    sol = solve_ivp(bioreactor, (0, T[-1]), IC5, t_eval=T, rtol=1e-10, atol=1e-12)
    return sol.y.T


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_data(path, steps):
    """The published data file, as {run: (61, 2) array of X, S}, or None."""
    if path is None:
        steps.append(Step("data", f"no data file found; put {DATA_FILE} in data/ or pass --data",
                          ok=False))
        return None
    digest = sha(path)
    match = digest == DATA_SHA256
    lines = [f"{path.name}: sha256 {digest}",
             "matches the published file" if match else
             f"DOES NOT MATCH the published file ({DATA_SHA256})"]
    if not match:
        steps.append(Step("data", "\n".join(lines), ok=False))
        return None
    rows = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(int(r["run"]), []).append((float(r["t"]), float(r["X"]), float(r["S"])))
    data = {run: np.array([v[1:] for v in sorted(vals)]) for run, vals in rows.items()}
    lines.append(f"runs {sorted(data)}, {sum(len(v) for v in data.values())} rows")
    steps.append(Step("data", "\n".join(lines)))
    return data


def ridge_run5(data):
    """make_pipeline(StandardScaler(), Ridge(alpha=1.0)), written out in NumPy,
    then simulated from run 5's initial condition.

    StandardScaler divides by the population standard deviation (ddof=0), and
    Ridge fits an intercept, which is the mean of the targets once the inputs
    are centred. The result is scikit-learn's to rounding.
    """
    A = np.vstack([data[r][:-1] for r in TRAIN])     # x[k], inside each run
    B = np.vstack([data[r][1:] for r in TRAIN])      # x[k+1]
    mean, std = A.mean(axis=0), A.std(axis=0)
    Z = (A - mean) / std
    b = B.mean(axis=0)
    W = np.linalg.solve(Z.T @ Z + ALPHA * np.eye(Z.shape[1]), Z.T @ (B - b))
    path = [np.array(IC5)]
    while len(path) < len(T):
        path.append(((path[-1] - mean) / std) @ W + b)
    return np.array(path)


def rmse(a, b):
    return np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2, axis=0))


# ------------------------------------------------------------- your files

def read_csv(path):
    if path is None:
        return None
    try:
        with open(path, newline="", errors="replace") as f:
            rows = list(csv.DictReader(f))
    except (OSError, csv.Error):
        return None
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in rows]


def inspect_run5(path, steps):
    """{model: (61, 2) array} from run5.csv."""
    info = {"present": path is not None, "curves": {}}
    rows = read_csv(path)
    if rows is None:
        steps.append(Step("run5.csv", "not found or unreadable", ok=False))
        info["present"] = False
        return info
    cols = list(rows[0]) if rows else []
    missing = [c for c in COLUMNS if c not in cols]
    lines = [f"{len(rows)} rows, columns {cols}" + (f"; missing {missing}" if missing else "")]
    try:
        rows = sorted(rows, key=lambda r: float(r["t"]))
        t = np.array([float(r["t"]) for r in rows])
    except (KeyError, TypeError, ValueError):
        t = np.array([])
    info["grid_ok"] = len(t) == len(T) and np.allclose(t, T)
    if not info["grid_ok"]:
        lines.append("t is not 0, 5, ..., 300")
    for m in MODELS:
        try:
            curve = np.array([[float(r[f"x_{m}"]), float(r[f"s_{m}"])] for r in rows])
        except (KeyError, TypeError, ValueError):
            continue
        if info["grid_ok"] and np.all(np.isfinite(curve)):
            info["curves"][m] = curve
    info["ok"] = not missing and info["grid_ok"] and len(info["curves"]) == len(MODELS)
    steps.append(Step("run5.csv", "\n".join(lines), ok=info["ok"]))
    return info


def inspect_mu(path, steps):
    info = {"present": path is not None}
    rows = read_csv(path)
    if rows is None:
        steps.append(Step("mu.csv", "not found or unreadable", ok=False))
        info["present"] = False
        return info
    try:
        pts = sorted((float(r["s"]), float(r["mu"])) for r in rows)
    except (KeyError, TypeError, ValueError):
        steps.append(Step("mu.csv", f"columns {list(rows[0]) if rows else []}; need S and mu", ok=False))
        info["present"] = False
        return info
    S = np.array([p[0] for p in pts])
    mu = np.array([p[1] for p in pts])
    lines = [f"{len(S)} rows", "", f"{'S':>6}  {'yours':>9}  {'true':>9}  {'error':>7}"]
    within = []
    for s, m in zip(S, mu):
        ref = mu_true(s)
        err = abs(m - ref) / ref if ref > 0 else float("inf")
        inside = MU_RANGE[0] <= s <= MU_RANGE[1]
        if inside:
            within.append(err <= MU_REL_TOL)
        lines.append(f"{s:6.1f}  {m:9.5f}  {ref:9.5f}  {err:7.1%}" + ("" if inside else "   (not checked)"))
    covered = all(any(abs(s - g) < 1e-9 for s in S) for g in S_GRID if MU_RANGE[0] <= g <= MU_RANGE[1])
    if not covered:
        lines.append("not every S from 20 to 130 in steps of 5 is in the file")
    info["mu_ok"] = bool(within) and all(within) and covered
    steps.append(Step("mu.csv against the true growth rate", "\n".join(lines), ok=info["mu_ok"]))
    return info


# --------------------------------------------------------------------- code

def strip_comments(body):
    body = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", body)
    return re.sub(r"(?m)#.*$", "", body)


def analyse_code(root, files, steps):
    parts = [(p, strip_comments(text_of(p))) for p in files]
    everything = "\n".join(b for _, b in parts)
    out = {
        "files": [p for p, _ in parts],
        "grad": bool(re.search(r"jax\.(grad|jacfwd|jacrev)\b|\b(grad|jacfwd|jacrev)\s*\(", everything)),
        "diffeqsolve": bool(re.search(r"diffeqsolve\s*\(", everything)),
        "x64": bool(re.search(r"jax_enable_x64", everything)),
    }
    lines = [f"{len(files)} code files: {', '.join(str(p.relative_to(root)) for p in files[:12])}", "",
             f"jax.grad: {'yes' if out['grad'] else 'no'}",
             f"diffrax.diffeqsolve: {'yes' if out['diffeqsolve'] else 'no'}",
             f"jax_enable_x64: {'yes' if out['x64'] else 'no'}"]
    steps.append(Step("read the code", "\n".join(lines)))
    return out


# ------------------------------------------------------------------- report

NUMBER = re.compile(r"-?\d[\d,]*\.\d+")
AI_LINE = re.compile(r"(?i)generative|\bAI\b|LLM|ChatGPT|Claude|Copilot|Gemini")


def decimals_in(text):
    """Every decimal number in the text, with how many places it was written to."""
    out = []
    for token in NUMBER.findall(text or ""):
        token = token.replace(",", "")
        try:
            out.append((float(token), len(token.split(".")[1])))
        except (ValueError, IndexError):
            pass
    return out


def quoted(value, numbers):
    """Is `value` in the report, to the precision the report wrote it?"""
    for number, places in numbers:
        if places >= 2 and abs(number - value) <= 0.5 * 10 ** -places + 1e-12:
            return True
    return False


def analyse_report(path, errors, steps):
    """errors: {(model, state): RMSE recomputed from run5.csv}."""
    if path is None:
        steps.append(Step("REPORT.md", "no report found", ok=False))
        return {"present": False}
    text = text_of(path)
    numbers = decimals_in(text)
    hits = {key: quoted(value, numbers) for key, value in errors.items()}
    heads = re.findall(r"(?m)^#{1,3}\s+(.+)$", text)
    lines = [f"{len(re.findall(r'[A-Za-z]+', text))} words, {len(heads)} headings: {heads[:10]}", "",
             "RMSE recomputed from run5.csv, and whether REPORT.md quotes it:"]
    lines += [f"  {m:<9} {v}  {errors[(m, v)]:.4f}  {'quoted' if hits[(m, v)] else 'NOT FOUND'}"
              for (m, v) in errors]
    lines.append(f"AI-use line: {'yes' if AI_LINE.search(text) else 'not found'}")
    steps.append(Step("REPORT.md", "\n".join(lines)))
    return {"present": True, "hits": hits}


# ------------------------------------------------------------------- checks


def collect(root, args, found, steps):
    notes = []
    truth = true_run5()
    data = load_data(found["data"], steps)
    ridge = ridge_run5(data) if data is not None else None
    lines = [f"true model, run 5: X(300) {truth[-1, 0]:.4f}, S(300) {truth[-1, 1]:.3f}"]
    if ridge is not None:
        e = rmse(ridge, truth)
        lines.append(f"discrete-time model refitted here, run 5: RMSE X {e[0]:.4f}, S {e[1]:.4f}")
    steps.append(Step("the script's own true model and discrete-time model", "\n".join(lines)))

    run5 = inspect_run5(found["run5"], steps)
    mu = inspect_mu(found["mu"], steps)
    code = analyse_code(root, found["code"], steps)
    curves = run5["curves"]
    own_truth = curves.get("true", truth)
    errors = {}
    for m in ("discrete", "pinn", "node"):
        if m in curves:
            e = rmse(curves[m], own_truth)
            errors[(m, "X")], errors[(m, "S")] = e[0], e[1]
    report = analyse_report(found["report"], errors, steps)

    checks = []

    def add(group, label, state, note=""):
        checks.append((group, label, state, note))

    def decided(value):
        return PASS if value else FAIL

    def coded(flag):
        return decided(code[flag]) if code["files"] else SKIP

    def within(model, limit):
        got = curves.get(model)
        if got is None:
            return FAIL, f"no {model} columns in run5.csv"
        e = rmse(got, truth)
        return decided(e[0] <= limit[0] and e[1] <= limit[1]), f"RMSE X {e[0]:.4f}, S {e[1]:.4f}"

    # 1. the discrete-time model, and the true model it is compared with
    add("discrete", "run5.csv with the nine columns and t = 0, 5, ..., 300", decided(run5.get("ok")))
    if "true" in curves:
        d = np.max(np.abs(curves["true"] - truth), axis=0)
        add("discrete", "your true model matches the script's",
            decided(d[0] <= TRUE_TOL[0] and d[1] <= TRUE_TOL[1]),
            f"largest difference X {d[0]:.2e}, S {d[1]:.2e}; allowed {TRUE_TOL[0]:g}, {TRUE_TOL[1]:g}")
    else:
        add("discrete", "your true model matches the script's", FAIL, "no true-model columns")
    if ridge is None:
        add("discrete", "your discrete-time model matches the script's fit", SKIP,
            "the data file is missing or is not the published one, so the fit cannot be redone")
    elif "discrete" in curves:
        d = np.max(np.abs(curves["discrete"] - ridge), axis=0)
        add("discrete", "your discrete-time model matches the script's fit",
            decided(d[0] <= DISCRETE_TOL[0] and d[1] <= DISCRETE_TOL[1]),
            f"largest difference X {d[0]:.2e}, S {d[1]:.2e}; allowed {DISCRETE_TOL[0]:g}, {DISCRETE_TOL[1]:g}")
    else:
        add("discrete", "your discrete-time model matches the script's fit", FAIL, "no discrete columns")

    # 2. the PINN
    state, note = within("pinn", PINN_LIMIT)
    add("pinn", f"run 5 within an RMSE of {PINN_LIMIT[0]} on X and {PINN_LIMIT[1]} on S", state, note)
    add("pinn", "jax.grad in the code", coded("grad"))

    # 3. the neural ODE
    state, note = within("node", NODE_LIMIT)
    add("node", f"run 5 within an RMSE of {NODE_LIMIT[0]} on X and {NODE_LIMIT[1]} on S", state, note)
    add("node", f"learned mu within {MU_REL_TOL:.0%} of the true mu from S = "
                f"{MU_RANGE[0]:.0f} to {MU_RANGE[1]:.0f}",
        decided(mu.get("present") and mu.get("mu_ok")))
    add("node", "diffeqsolve in the code", coded("diffeqsolve"))

    # 4. the comparison
    add("compare", "results/run5.png", decided(found["png"] is not None))
    if not report.get("present"):
        add("compare", "REPORT.md quotes the RMSE of X and S of each model", FAIL, "no report")
    elif not errors:
        add("compare", "REPORT.md quotes the RMSE of X and S of each model", FAIL,
            "run5.csv had no predictions to compute them from")
    else:
        missing = [f"{m} {v}" for (m, v), hit in report["hits"].items() if not hit]
        add("compare", "REPORT.md quotes the RMSE of X and S of each model",
            decided(len(errors) == 6 and not missing),
            "all six quoted" if not missing and len(errors) == 6 else
            "not found: " + ", ".join(missing) if missing else "some models are missing from run5.csv")

    add("report", "answers to 5(c) and 5(d), and the AI-use line", SKIP, "read by your TA")

    if code["files"] and not code["x64"]:
        notes.append("jax_enable_x64 is not in your code. The worked examples turn it on.")
    if mu.get("present"):
        notes.append("mu.csv is checked from S = 20 up. Below that the training runs have only a "
                     "few samples, so the learned mu there is loosely pinned.")
    return {"checks": checks, "notes": notes, "steps": steps}


def score(checks):
    """Group scores. Within a group the checks weigh the same.

    A SKIP is a check that could not be decided here. It is excluded from the
    group's denominator and its share is held for a TA, carved out of the group,
    so a student loses the evidence rather than the marks.
    """
    rows = []
    for key, title, points, who in GROUPS:
        mine = [c for c in checks if c[0] == key]
        passed = sum(1 for c in mine if c[2] == PASS)
        failed = sum(1 for c in mine if c[2] == FAIL)
        skipped = sum(1 for c in mine if c[2] == SKIP)
        decidable = passed + failed
        earned = points * passed / decidable if decidable else 0.0
        held = points * skipped / len(mine) if mine else 0.0
        if who != "script":
            earned, held = 0.0, 0.0
        earned = min(earned, points - held)
        rows.append({"key": key, "title": title, "points": points, "who": who,
                     "passed": passed, "failed": failed, "skipped": skipped,
                     "of": len(mine), "earned": earned, "held": held, "checks": mine})
    return rows


# ------------------------------------------------------- colour and highlight

BLACK = (0, 0, 0)
GREEN = (0.00, 0.45, 0.15)
RED = (0.70, 0.06, 0.06)
AMBER = (0.60, 0.42, 0.00)
BLUE = (0.10, 0.25, 0.60)
GREY = (0.40, 0.40, 0.40)
KEYWORD = (0.45, 0.15, 0.55)
STRING = (0.62, 0.20, 0.12)
NUMBER_C = (0.05, 0.40, 0.50)
COMMENT = (0.35, 0.48, 0.38)

KEYWORDS = {
    "False", "None", "True", "and", "as", "assert", "async", "await", "break",
    "class", "continue", "def", "del", "elif", "else", "except", "finally",
    "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
    "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
}
TOKENS = re.compile(
    r"(?P<comment>#[^\n]*)"
    r"|(?P<string>'''|\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")"
    r"|(?P<number>\b\d+\.?\d*\b)"
    r"|(?P<word>[A-Za-z_]\w*)"
)


def plain(text, bold=False, colour=BLACK):
    return [(text, bold, colour)]


def highlight(source, indent="  "):
    """Python source as coloured runs, one list of runs per line."""
    out, in_triple = [], None
    for raw in source.splitlines():
        runs, position = [(indent, False, BLACK)], 0
        if in_triple:
            end = raw.find(in_triple)
            if end == -1:
                out.append([(indent, False, BLACK), (raw, False, STRING)])
                continue
            runs.append((raw[:end + 3], False, STRING))
            position = end + 3
            in_triple = None
        for match in TOKENS.finditer(raw, position):
            if match.start() < position:
                continue
            if match.start() > position:
                runs.append((raw[position:match.start()], False, BLACK))
            text = match.group()
            kind = match.lastgroup
            if kind == "comment":
                runs.append((text, False, COMMENT))
            elif kind == "string":
                if text in ("'''", '"""'):
                    rest = raw[match.start():]
                    closing = rest.find(text, 3)
                    if closing == -1:
                        runs.append((rest, False, STRING))
                        in_triple = text
                        position = len(raw)
                        break
                    text = rest[:closing + 3]
                    runs.append((text, False, STRING))
                    position = match.start() + len(text)
                    continue
                runs.append((text, False, STRING))
            elif kind == "number":
                runs.append((text, False, NUMBER_C))
            elif text in KEYWORDS:
                runs.append((text, True, KEYWORD))
            else:
                runs.append((text, False, BLACK))
            position = match.end()
        if position < len(raw):
            runs.append((raw[position:], False, BLACK))
        out.append(runs)
    return out


# ----------------------------------------------------------------- PDF output


def escape_pdf(text):
    out = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return out.encode("latin-1", "replace").decode("latin-1")


def wrap(lines, max_chars, indent="      "):
    out = []
    for runs in lines:
        current, used = [], 0
        for text, bold, colour in runs:
            text = text.replace("\t", "    ")
            while True:
                room = max_chars - used
                if len(text) <= room:
                    if text:
                        current.append((text, bold, colour))
                        used += len(text)
                    break
                cut = text.rfind(" ", 0, room)
                cut = cut if cut > room // 2 else room
                current.append((text[:cut], bold, colour))
                out.append(current)
                current, used = [(indent, False, BLACK)], len(indent)
                text = text[cut:].lstrip()
        out.append(current)
    return out


def write_pdf(path, lines, title):
    """A paginated, coloured, monospace PDF with no dependency at all."""
    width, height = 612, 792
    left, top, bottom, size, leading = 42, 748, 60, 8, 10.2
    max_chars = int((width - 2 * left) / (size * 0.6))
    rows = int((top - bottom) / leading)

    wrapped = wrap(lines, max_chars)
    pages = [wrapped[i:i + rows] for i in range(0, len(wrapped), rows)] or [[]]

    streams = []
    for number, page in enumerate(pages, start=1):
        parts = [f"BT /F1 {size} Tf {left} {top} Td {leading} TL"]
        font, colour = "F1", BLACK
        for runs in page:
            for text, bold, run_colour in runs:
                want = "F2" if bold else "F1"
                if want != font:
                    parts.append(f"/{want} {size} Tf")
                    font = want
                if run_colour != colour:
                    parts.append(f"{run_colour[0]:.2f} {run_colour[1]:.2f} "
                                 f"{run_colour[2]:.2f} rg")
                    colour = run_colour
                if text:
                    parts.append(f"({escape_pdf(text)}) Tj")
            parts.append("T*")
        parts.append("ET")
        footer = f"{title}   page {number} of {len(pages)}"
        parts.append(f"BT /F1 7 Tf 0.40 0.40 0.40 rg {left} {bottom - 20} Td "
                     f"({escape_pdf(footer)}) Tj ET")
        streams.append("\n".join(parts).encode("latin-1", "replace"))

    objects = {}
    page_ids = [5 + 2 * i for i in range(len(pages))]
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[2] = f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"
    objects[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>"
    for page_id, stream in zip(page_ids, streams):
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {page_id + 1} 0 R >>").encode()
        objects[page_id + 1] = (f"<< /Length {len(stream)} >>\nstream\n".encode()
                                + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref_at = len(out)
    count = max(objects) + 1
    out += f"xref\n0 {count}\n0000000000 65535 f \n".encode()
    for number in range(1, count):
        out += f"{offsets.get(number, 0):010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n"
            f"{xref_at}\n%%EOF\n").encode()
    Path(path).write_bytes(bytes(out))
    return len(pages)


def write_html(path, lines):
    def span(run):
        text, bold, colour = run
        style = f"color:rgb({int(colour[0]*255)},{int(colour[1]*255)},{int(colour[2]*255)})"
        if bold:
            style += ";font-weight:700"
        return f"<span style='{style}'>{html.escape(text)}</span>"

    body = "\n".join(
        "<div>" + ("".join(span(r) for r in runs) or "&nbsp;") + "</div>"
        for runs in lines
    )
    Path(path).write_text(
        "<!doctype html><meta charset='utf-8'><title>A5 evidence</title>"
        "<style>body{font:10pt/1.35 ui-monospace,Menlo,monospace;max-width:62rem;"
        "margin:2rem auto;padding:0 1rem}div{white-space:pre-wrap}</style>\n" + body)


# ---------------------------------------------------------------- the report


def self_hash():
    """This file's own sha256, printed in the report.

    HONESTLY, WHAT THIS BUYS. Not much on its own; anyone who edits the script can
    edit this function too. What it catches is the cheap case, a check quietly
    changed and the header line forgotten. The expensive-to-forge part of this
    report is that the curves, the recomputed errors and the report's own numbers
    all have to agree with each other and with the true model.
    """
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def trim(text, head=70, tail=16):
    lines = text.splitlines()
    if len(lines) <= head + tail + 3:
        return text
    return "\n".join(lines[:head] + [f"    [... {len(lines) - head - tail} lines elided ...]"]
                     + lines[-tail:])


def read(path, limit=24000):
    if path is None or not Path(path).exists():
        return f"[{path} is not in this project]"
    text = text_of(path)
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def rel(root, path):
    if path is None:
        return "none found"
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


LABELS = ("data", "run5", "mu", "png", "report")


def report_lines(root, args, found, result):
    rows = score(result["checks"])
    auto = sum(r["earned"] for r in rows if r["who"] == "script")
    held = sum(r["held"] for r in rows)
    ta_group = next(r for r in rows if r["who"] == "your TA")
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    lines = [plain("Assignment 5 evidence", bold=True), plain("")]
    lines += [plain(t) for t in [
        f"{args.name or args.andrew_id} ({args.andrew_id})",
        f"generated {stamp} on {platform.platform()}, numpy {np.__version__}, scipy {scipy.__version__}",
        f"project {root.name}",
        f"evidence script sha256 {result['script_sha']}",
    ]]
    lines += [plain(""), [
        ("Score  ", True, BLACK),
        (f"{auto:.2f} / {AUTO_TOTAL:.0f}", True, GREEN if auto >= AUTO_TOTAL - 1e-9 else BLACK),
        ("  automatic, out of 6 for the assignment.", False, BLACK),
    ]]
    lines.append(plain(f"  The last {ta_group['points']:.0f} point is REPORT.md, which your TA "
                       f"reads. This script does not score it.", colour=GREY))
    if held > 1e-9:
        lines.append(plain(f"  {held:.2f} could not be decided here and is held for your TA.",
                           colour=AMBER))

    lines += [plain(""), plain("Summary", bold=True), plain("")]
    lines.append(plain(f"  {'group':<22}{'score':>12}   {'checks':<14}decided by", colour=GREY))
    for r in rows:
        if r["who"] == "script":
            value, colour = f"{r['earned']:.2f} / {r['points']:.2f}", (
                GREEN if abs(r["earned"] - r["points"]) < 1e-9 else
                RED if r["earned"] == 0 else BLACK)
        else:
            value, colour = f"  ?  / {r['points']:.2f}", AMBER
        tally = f"{r['passed']}/{r['of']} passed" + (f", {r['skipped']} held" if r["skipped"] and r["who"] == "script" else "")
        lines.append([("  ", False, BLACK), (f"{r['title']:<22}", False, BLACK),
                      (f"{value:>12}", True, colour),
                      (f"   {tally:<14}{r['who']}", False, GREY)])
    lines.append(plain("  " + "-" * 62, colour=GREY))
    lines.append([("  ", False, BLACK), (f"{'automatic total':<22}", True, BLACK),
                  (f"{auto:.2f} / {AUTO_TOTAL:.2f}", True, BLACK),
                  (f"   of {TOTAL:.0f} for the assignment", False, GREY)])

    lines += [plain(""), plain("What this script found", bold=True), plain("")]
    for label in LABELS:
        lines.append(plain(f"  {label:<12} {rel(root, found[label])}"))
    lines.append(plain(f"  {'code':<12} {len(found['code'])} files", colour=GREY))

    for r in rows:
        lines += [plain(""), [
            (f"{r['title']}", True, BLACK),
            (f"   {r['earned']:.2f} / {r['points']:.2f}" if r["who"] == "script"
             else f"   {r['points']:.2f} point, read by your TA", True,
             GREY if r["who"] != "script" else BLACK),
        ], plain("")]
        for _, label, state, note in r["checks"]:
            colour = {PASS: GREEN, FAIL: RED, SKIP: AMBER}[state]
            lines.append([("  ", False, BLACK), (f"[{state}]", True, colour),
                          (f"  {label}", False, BLACK)])
            if note:
                lines.append(plain(f"          {note}", colour=GREY))
    lines += [plain(""), plain("  Each line is decided from the output below, not asserted.",
                               colour=GREY)]

    if result["notes"]:
        lines += [plain(""), plain("Worth a look", bold=True),
                  plain("  Not scored here. These are for whoever reads the report.",
                        colour=GREY), plain("")]
        lines += [plain(f"  - {n}", colour=GREY) for n in result["notes"]]

    lines += [plain(""), plain("Transcript", bold=True)]
    for step in result["steps"]:
        lines += [plain(""), [(f"  {step.label}", True, BLACK),
                              ("" if step.ok else "   [not ok]", False, RED)], plain("")]
        lines += [plain(f"    {l}", colour=GREY)
                  for l in (trim(step.stdout) or "[no output]").splitlines()]

    shown = 0
    for path in found["code"]:
        if shown >= 8:
            break
        shown += 1
        lines += [plain(""), plain(f"Code: {rel(root, path)}", bold=True), plain("")]
        lines += highlight(read(path))
    lines += [plain(""), plain(f"REPORT: {rel(root, found['report'])}", bold=True), plain("")]
    lines += [plain(f"  {l}") for l in read(found["report"]).splitlines()]

    summary = {
        "andrew_id": args.andrew_id, "generated": stamp,
        "auto_score": round(auto, 2), "auto_of": AUTO_TOTAL,
        "report_points": ta_group["points"], "held_for_ta": round(held, 2),
        "assignment_total": TOTAL,
        "groups": {r["key"]: round(r["earned"], 2) for r in rows if r["who"] == "script"},
        "script_sha256": result["script_sha"],
    }
    lines += [plain(""), plain("Summary line", bold=True), plain(""),
              plain("  The script hash should match the checksum published beside the script.",
                    colour=GREY),
              plain(""), plain(f"  {json.dumps(summary)}")]
    return lines, rows, auto, held


def main():
    parser = argparse.ArgumentParser(description="Build the Assignment 5 evidence PDF.")
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--data", default=None, help=f"data/{DATA_FILE}")
    parser.add_argument("--run5", default=None, help="results/run5.csv")
    parser.add_argument("--mu", default=None, help="results/mu.csv")
    parser.add_argument("--report", default=None, help="REPORT.md")
    parser.add_argument("--out", default="evidence.pdf")
    parser.add_argument("--html", action="store_true", help="also write evidence.html")
    args = parser.parse_args()

    root = Path.cwd()
    found = discover(root, args)
    if not any([found["run5"], found["mu"], found["report"]]):
        raise SystemExit(f"Found no run5.csv, no mu.csv and no report in {root}. "
                         f"Run this from your A5 project root.")

    print(f"Building evidence for {args.andrew_id} in {root}")
    for label in LABELS:
        print(f"  {label:<12} {rel(root, found[label])}")

    result = collect(root, args, found, [])
    result["script_sha"] = self_hash()
    lines, rows, auto, held = report_lines(root, args, found, result)

    pages = write_pdf(root / args.out, lines, f"A5 evidence, {args.andrew_id}")
    if args.html:
        write_html(root / "evidence.html", lines)

    print(f"\nWrote {args.out}, {pages} pages.\n")
    for r in rows:
        if r["who"] == "script":
            print(f"  {r['title']:<22} {r['earned']:.2f} / {r['points']:.2f}"
                  f"   ({r['passed']}/{r['of']} checks"
                  + (f", {r['skipped']} held" if r["skipped"] else "") + ")")
        else:
            print(f"  {r['title']:<22}    ? / {r['points']:.2f}   (read by your TA)")
        for _, label, state, note in r["checks"]:
            if state != PASS and r["who"] == "script":
                print(f"      {state}  {label}" + (f"\n            {note}" if note else ""))
    print(f"\nAutomatic score {auto:.2f} of {AUTO_TOTAL:.2f}"
          + (f", with {held:.2f} held for your TA" if held > 1e-9 else "")
          + f".  The assignment is worth {TOTAL:.0f}.")
    if auto < AUTO_TOTAL - 1e-9:
        print("\nA failing check is a reason to fix it and run this again, "
              "not a reason to skip the submission.")
    print(f"\nUpload {args.out} to Canvas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
