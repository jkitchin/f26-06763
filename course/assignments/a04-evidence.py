# /// script
# requires-python = ">=3.11"
# dependencies = ["polars>=1.20", "pyreadr>=0.5", "pandas", "pyarrow"]
# ///
r"""Build the Assignment 4 evidence report.

Run this in the root of your A4 project, the directory holding `data/`,
`results/` and your `REPORT.md`:

    uv run --no-project https://kitchingroup.cheme.cmu.edu/f26-06763/a04-evidence.py \
        --andrew-id yourid --name "Your Name"

or, on a copy you downloaded:

    uv run --no-project a04-evidence.py --andrew-id yourid --name "Your Name"

`--no-project` matters. This script declares its own dependencies in the block
at the top of this file, so uv builds it a small environment of its own, and a
stale lockfile in *your* project cannot leave you with no report at all.

It writes `evidence.pdf`. Upload that to Canvas. Read it before you send it.

WHAT IT DOES. A4 is worth six points, in six groups. This script decides five
of them and prints the total on the first page; the sixth is your `REPORT.md`,
which a person reads. Within a group the checks are equally weighted, so
passing three of four checks in a one-point group is 0.75.

The part that makes it worth running is that it does not take your numbers on
trust. It reads the same Rieth et al. (2017) file you used and recomputes, on
its own:

  * the target `xmeas_18` at `t + h` for every row of your predictions, which
    catches a shift in the wrong direction, an off-by-one, and a shift that ran
    across two simulation runs;
  * persistence and the training mean at every horizon, on exactly the test
    origins the assignment fixes;
  * the RMSE of your direct and recursive forecasts, from your predictions.

Your `forecast.csv` is then checked against those, and your `REPORT.md`
against your `forecast.csv`. It also reads your code for the few decisions A4
is about: shifts kept inside each run, a scaler inside a pipeline, validation
on runs 301 to 400, `TimeSeriesSplit` with a gap, and a shuffled `KFold`.

Nothing is invented. If something fails, the failure goes in the report, which
is better for you than a report that quietly omits it.

IT DOES NOT CHANGE YOUR FILES. It reads the data, the results and the code,
and writes `evidence.pdf` (and `evidence.html` with --html). It does not re-run
your code and does not download anything.

NAMES. The assignment names its deliverables (`results/predictions.parquet`,
`results/forecast.csv`, `results/validation.csv`, `results/leaky.csv`,
`REPORT.md`) and this script looks for those first. When it does not find them
it goes looking by what the files contain. What it found is printed at the top,
and every guess can be overridden with --data, --predictions, --forecast,
--validation, --leaky and --report.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ipynb_checkpoints",
             "build", "dist", ".pytest_cache", "site-packages", ".mypy_cache",
             ".ruff_cache", "target", "mlruns"}
OURS = ("a04-evidence.py", "evidence.html", "evidence.pdf")

Y = "xmeas_18"
RUN = "simulationRun"
SAMPLE = "sample"
HORIZONS = [1, 5, 10, 20, 40]
TRAIN = (1, 300)
VALIDATION = (301, 400)
TEST = (401, 500)
T_FIRST = 40
SAMPLES_PER_RUN = 500
LEAKY_RUNS = set(range(1, 11))
LEAKY_H = 10
REL_TOL = 0.005          # 0.5 % on an RMSE
PRED_COLUMNS = ["run", "t", "h", "y_true", "persistence", "mean", "direct", "recursive"]
FORECAST_COLUMNS = ["h", "persistence_rmse", "mean_rmse", "direct_rmse", "recursive_rmse", "skill"]
LEAKY_COLUMNS = ["run", "split", "h", "model_rmse", "persistence_rmse"]

# --------------------------------------------------------------------------
# The six groups. Five are scored here; group 6 is the report, and a TA reads
# it. Within a group the checks are equally weighted. Points sum to 6.
# --------------------------------------------------------------------------
GROUPS = [
    ("table",    "The table",          1.0,  "script"),
    ("baseline", "Baselines",          1.0,  "script"),
    ("models",   "Models",             1.25, "script"),
    ("honest",   "Honest evaluation",  1.25, "script"),
    ("numbers",  "Report numbers",     0.5,  "script"),
    ("report",   "REPORT.md",          1.0,  "your TA"),
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


def parquet_columns(path):
    try:
        return list(pl.read_parquet_schema(path).keys())
    except Exception:
        return []


def csv_header(path):
    try:
        with open(path, errors="replace") as f:
            return [c.strip().strip('"').lower() for c in f.readline().split(",")]
    except OSError:
        return []


def discover(root, args):
    found = {}

    data = given_path(root, args.data)
    if data is None:
        parquet = [p for p in walk(root, ["*.parquet"])
                   if {RUN, SAMPLE, Y} <= set(parquet_columns(p))]
        rdata = [p for p in walk(root, ["*.RData", "*.rdata", "*.Rdata"])
                 if "fault" in p.name.lower()]
        free = [p for p in parquet + rdata
                if re.search(r"free", p.name, re.I) or p.suffix == ".parquet"]
        data = by_name(free, ["faultfree", "fault_free", "fault-free", "free"])
    found["data"] = data

    pred = given_path(root, args.predictions)
    if pred is None:
        cands = [p for p in walk(root, ["*.parquet"])
                 if {"run", "t", "h", "y_true"} <= set(parquet_columns(p))]
        pred = by_name(cands, ["results/predictions", "prediction"])
    found["predictions"] = pred

    def csv_with(flag, needed, hints):
        p = given_path(root, flag)
        if p is not None:
            return p
        cands = [c for c in walk(root, ["*.csv"]) if needed <= set(csv_header(c))]
        return by_name(cands, hints)

    found["forecast"] = csv_with(args.forecast, {"h", "direct_rmse"}, ["results/forecast", "forecast"])
    validation = given_path(root, args.validation)
    if validation is None:
        cands = [c for c in walk(root, ["*.csv"])
                 if any("rmse" in h for h in csv_header(c)) and "valid" in c.name.lower()]
        validation = by_name(cands, ["results/validation", "validation"])
    found["validation"] = validation
    found["leaky"] = csv_with(args.leaky, {"split", "model_rmse"}, ["results/leaky", "leaky"])

    report = given_path(root, args.report)
    if report is None:
        report = by_name(walk(root, ["REPORT.md", "report.md", "*.md"]),
                         ["report.md", "report", "readme"])
    found["report"] = report

    code = [p for p in walk(root, ["*.py", "*.ipynb"]) if p.name not in OURS]
    found["code"] = code
    return found


# --------------------------------------------------------------------- data


def load_data(path):
    """The Rieth fault-free training table, as (run, sample, xmeas_18) plus valves."""
    if path is None:
        return None, "no data file found; pass --data"
    try:
        if Path(path).suffix == ".parquet":
            frame = pl.read_parquet(path)
        else:
            import pyreadr
            objects = pyreadr.read_r(str(path))
            name = next((k for k, v in objects.items()
                         if {RUN, SAMPLE, Y} <= set(v.columns)), None)
            if name is None:
                return None, f"{path} holds no table with {RUN}, {SAMPLE} and {Y}"
            frame = pl.from_pandas(objects[name].reset_index(drop=True))
    except Exception as exc:  # noqa: BLE001
        return None, f"could not read {path}: {exc}"
    missing = {RUN, SAMPLE, Y} - set(frame.columns)
    if missing:
        return None, f"{path} is missing {sorted(missing)}"
    frame = frame.select(pl.col(RUN).cast(pl.Int64), pl.col(SAMPLE).cast(pl.Int64),
                         pl.col(Y).cast(pl.Float64)).sort(RUN, SAMPLE)
    return frame, None


def reference(data):
    """Persistence and mean RMSE per horizon, on the fixed test origins."""
    mean = data.filter(pl.col(RUN).is_between(*TRAIN))[Y].mean()
    test = data.filter(pl.col(RUN).is_between(*TEST))
    out = {}
    for h in HORIZONS:
        rows = (test.with_columns(future=pl.col(Y).shift(-h).over(RUN))
                .filter(pl.col(SAMPLE).is_between(T_FIRST, SAMPLES_PER_RUN - h)))
        pers = rows.select(((pl.col("future") - pl.col(Y)) ** 2).mean().sqrt()).item()
        mse = rows.select(((pl.col("future") - mean) ** 2).mean().sqrt()).item()
        out[h] = {"persistence": pers, "mean": mse, "rows": rows.height}
    return mean, out


def close(a, b, rel=REL_TOL):
    if a is None or b is None:
        return False
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    return abs(a - b) <= rel * max(abs(b), 1e-12)


# -------------------------------------------------------------- predictions


def inspect_predictions(path, data, steps):
    info = {"present": path is not None}
    if path is None:
        steps.append(Step("predictions", "no predictions file found", ok=False))
        return info
    try:
        pred = pl.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        steps.append(Step("predictions", f"could not read {path}: {exc}", ok=False))
        info["present"] = False
        return info
    lines = [f"{pred.height:,} rows, columns {pred.columns}"]
    info["columns_ok"] = all(c in pred.columns for c in PRED_COLUMNS)
    missing = [c for c in PRED_COLUMNS if c not in pred.columns]
    if missing:
        lines.append(f"missing columns: {missing}")
        steps.append(Step("predictions", "\n".join(lines), ok=False))
        return info
    try:
        pred = pred.select(pl.col("run").cast(pl.Int64), pl.col("t").cast(pl.Int64),
                           pl.col("h").cast(pl.Int64),
                           *[pl.col(c).cast(pl.Float64) for c in PRED_COLUMNS[3:]])
    except Exception as exc:  # noqa: BLE001
        lines.append(f"columns do not cast to numbers: {exc}")
        info["columns_ok"] = False
        steps.append(Step("predictions", "\n".join(lines), ok=False))
        return info
    info["frame"] = pred

    runs = set(pred["run"].unique().to_list())
    info["runs_ok"] = runs == set(range(TEST[0], TEST[1] + 1))
    lines.append(f"runs: {min(runs)} to {max(runs)}, {len(runs)} distinct"
                 + ("" if info["runs_ok"] else "  (expected exactly 401 to 500)"))
    coverage = {}
    for h in HORIZONS:
        sub = pred.filter(pl.col("h") == h)
        want = (TEST[1] - TEST[0] + 1) * (SAMPLES_PER_RUN - h - T_FIRST + 1)
        dup = sub.height - sub.select("run", "t").unique().height
        out_of_range = sub.filter(~pl.col("t").is_between(T_FIRST, SAMPLES_PER_RUN - h)).height
        coverage[h] = sub.height == want and dup == 0 and out_of_range == 0
        lines.append(f"h={h:>2}: {sub.height:,} rows (expected {want:,}), "
                     f"{dup} duplicated origins, {out_of_range} origins outside {T_FIRST}..{SAMPLES_PER_RUN - h}")
    info["coverage_ok"] = all(coverage.values()) and info["runs_ok"]

    if data is not None:
        truth = data.select(pl.col(RUN).alias("run"), pl.col(SAMPLE).alias("s"), pl.col(Y).alias("ref"))
        joined = (pred.with_columns(s=pl.col("t") + pl.col("h"))
                  .join(truth, on=["run", "s"], how="left"))
        ok = joined.select(((pl.col("y_true") - pl.col("ref")).abs() < 1e-6).mean()).item() or 0.0
        info["y_true_share"] = ok
        lines.append(f"y_true equal to {Y} at t + h: {ok:.2%} of rows")
        if ok < 0.999:
            for label, offset in [("t + h - 1", -1), ("t + h + 1", 1), ("t", None), ("t - h", "neg")]:
                if offset is None:
                    alt = pred.with_columns(s=pl.col("t"))
                elif offset == "neg":
                    alt = pred.with_columns(s=pl.col("t") - pl.col("h"))
                else:
                    alt = pred.with_columns(s=pl.col("t") + pl.col("h") + offset)
                share = (alt.join(truth, on=["run", "s"], how="left")
                         .select(((pl.col("y_true") - pl.col("ref")).abs() < 1e-6).mean()).item() or 0.0)
                if share > 0.5:
                    lines.append(f"  y_true matches {Y} at {label} for {share:.1%} of rows instead")
        joined = joined.filter(pl.col("ref").is_not_null())
        recomputed = {}
        for h in HORIZONS:
            sub = joined.filter(pl.col("h") == h)
            if sub.height == 0:
                continue
            row = sub.select(
                *[((pl.col(c) - pl.col("ref")) ** 2).mean().sqrt().alias(c)
                  for c in ("persistence", "mean", "direct", "recursive")],
                (pl.col("direct") - pl.col("recursive")).abs().mean().alias("gap"),
            ).row(0, named=True)
            recomputed[h] = row
        info["recomputed"] = recomputed
    steps.append(Step("predictions", "\n".join(lines),
                      ok=info.get("coverage_ok", False) and info.get("y_true_share", 0) >= 0.999))
    return info


def read_csv(path):
    if path is None:
        return None
    try:
        frame = pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001
        return None
    return frame.rename({c: c.strip().lower() for c in frame.columns})


def inspect_forecast(path, ref, pred_info, steps):
    info = {"present": path is not None}
    frame = read_csv(path)
    if frame is None:
        steps.append(Step("forecast.csv", "not found or unreadable", ok=False))
        info["present"] = False
        return info
    missing = [c for c in FORECAST_COLUMNS if c not in frame.columns]
    info["columns_ok"] = not missing
    rows = {}
    if "h" in frame.columns:
        for r in frame.iter_rows(named=True):
            try:
                rows[int(float(r["h"]))] = r
            except (TypeError, ValueError):
                pass
    info["rows"] = rows
    info["horizons_ok"] = set(HORIZONS) <= set(rows)
    recomputed = pred_info.get("recomputed", {})
    lines = [f"columns {frame.columns}" + (f"; missing {missing}" if missing else ""), "",
             f"{'h':>3}  {'persistence':>23}  {'mean':>23}  {'direct':>23}  {'recursive':>23}",
             f"{'':>3}  {'yours / script':>23}  {'yours / script':>23}  "
             f"{'yours / from preds':>23}  {'yours / from preds':>23}"]
    checks = {"pers": [], "mean": [], "skill": [], "direct": [], "recursive": []}
    for h in HORIZONS:
        r = rows.get(h, {})
        ref_h = (ref or {}).get(h, {})
        rec = recomputed.get(h, {})

        def pair(mine, theirs):
            m = f"{float(mine):.4f}" if _num(mine) else "-"
            t = f"{theirs:.4f}" if theirs is not None else "-"
            return f"{m} / {t}"

        lines.append(f"{h:>3}  {pair(r.get('persistence_rmse'), ref_h.get('persistence')):>23}  "
                     f"{pair(r.get('mean_rmse'), ref_h.get('mean')):>23}  "
                     f"{pair(r.get('direct_rmse'), rec.get('direct')):>23}  "
                     f"{pair(r.get('recursive_rmse'), rec.get('recursive')):>23}")
        checks["pers"].append(close(r.get("persistence_rmse"), ref_h.get("persistence")))
        checks["mean"].append(close(r.get("mean_rmse"), ref_h.get("mean")))
        checks["direct"].append(close(r.get("direct_rmse"), rec.get("direct")))
        checks["recursive"].append(close(r.get("recursive_rmse"), rec.get("recursive")))
        if all(_num(r.get(c)) for c in FORECAST_COLUMNS[1:]):
            want = 1 - float(r["direct_rmse"]) / min(float(r["persistence_rmse"]), float(r["mean_rmse"]))
            checks["skill"].append(abs(float(r["skill"]) - want) < 1e-3)
        else:
            checks["skill"].append(False)
    info["checks"] = {k: bool(v) and all(v) for k, v in checks.items()}
    steps.append(Step("forecast.csv against the script's recomputation", "\n".join(lines),
                      ok=all(info["checks"].values())))
    return info


def _num(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def inspect_validation(path, steps):
    frame = read_csv(path)
    if frame is None:
        steps.append(Step("validation.csv", "not found or unreadable", ok=False))
        return {"present": False, "rows": 0}
    rmse_cols = [c for c in frame.columns if "rmse" in c]
    steps.append(Step("validation.csv",
                      f"{frame.height} settings, columns {frame.columns}\n\n{frame.head(12)}",
                      ok=frame.height >= 3 and bool(rmse_cols)))
    return {"present": True, "rows": frame.height, "rmse": bool(rmse_cols)}


def inspect_leaky(path, steps):
    frame = read_csv(path)
    if frame is None:
        steps.append(Step("leaky.csv", "not found or unreadable", ok=False))
        return {"present": False}
    info = {"present": True}
    missing = [c for c in LEAKY_COLUMNS if c not in frame.columns]
    info["columns_ok"] = not missing
    lines = [f"{frame.height} rows, columns {frame.columns}" + (f"; missing {missing}" if missing else "")]
    if missing:
        steps.append(Step("leaky.csv", "\n".join(lines), ok=False))
        return info
    frame = frame.with_columns(
        kind=pl.when(pl.col("split").cast(pl.Utf8).str.to_lowercase().str.contains("shuf"))
        .then(pl.lit("shuffled"))
        .when(pl.col("split").cast(pl.Utf8).str.to_lowercase().str.contains("time|series|order"))
        .then(pl.lit("time")).otherwise(pl.lit("other")))
    runs = {k: set(frame.filter(pl.col("kind") == k)["run"].cast(pl.Int64).to_list())
            for k in ("shuffled", "time")}
    info["both_ok"] = all(LEAKY_RUNS <= r for r in runs.values())
    means = (frame.filter(pl.col("kind") != "other").group_by("kind")
             .agg(pl.col("model_rmse").cast(pl.Float64).mean(),
                  pl.col("persistence_rmse").cast(pl.Float64).mean()).sort("kind"))
    info["means"] = {r["kind"]: r["model_rmse"] for r in means.iter_rows(named=True)}
    lines += [f"runs with a shuffled row: {sorted(runs['shuffled'])}",
              f"runs with a time-ordered row: {sorted(runs['time'])}", "", str(means)]
    steps.append(Step("leaky.csv", "\n".join(lines), ok=info["both_ok"]))
    return info


# --------------------------------------------------------------------- code

def strip_comments(body):
    body = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", body)
    return re.sub(r"(?m)#.*$", "", body)


def analyse_code(root, files, steps):
    parts = [(p, strip_comments(text_of(p))) for p in files]
    everything = "\n".join(b for _, b in parts)
    gaps = re.findall(r"TimeSeriesSplit\s*\([^)]*gap\s*=\s*([^,)\s]+)", everything)
    gap_ok = any((g.isdigit() and int(g) >= LEAKY_H) or not g.isdigit() for g in gaps)
    out = {
        "files": [p for p, _ in parts],
        "over_run": bool(re.search(
            r"over\(\s*(?:[\"']simulationRun[\"']|[A-Za-z_]\w*)"
            r"|group_by\([^)]*simulationRun|groupby\([^)]*simulationRun"
            r"|partition_by\([^)]*simulationRun"
            r"|for\s+[^\n:]+\s+in\s+[^\n:]*(?:simulationRun|group_by|groupby|partition_by)",
            everything)),
        "pipeline": bool(re.search(r"make_pipeline|Pipeline\s*\(", everything))
                    and bool(re.search(r"StandardScaler|RobustScaler|MinMaxScaler", everything)),
        "validation_runs": bool(re.search(
            r"301\D{0,40}?40[01]\b|is_between\(\s*301|range\(\s*301", everything)),
        "tss": bool(re.search(r"TimeSeriesSplit\s*\(", everything)),
        "gaps": gaps,
        "gap_ok": gap_ok,
        "kfold_shuffle": bool(re.search(r"KFold\s*\([^)]*shuffle\s*=\s*True", everything)),
    }
    lines = [f"{len(files)} code files: {', '.join(str(p.relative_to(root)) for p in files[:12])}", "",
             f"shifts kept inside a run (.over / group_by / per-run loop): {'yes' if out['over_run'] else 'no'}",
             f"scaler inside a pipeline: {'yes' if out['pipeline'] else 'no'}",
             f"validation runs 301 to 400 referenced: {'yes' if out['validation_runs'] else 'no'}",
             f"TimeSeriesSplit: {'yes' if out['tss'] else 'no'}; gap arguments: {gaps or 'none'}",
             f"KFold with shuffle=True: {'yes' if out['kfold_shuffle'] else 'no'}"]
    steps.append(Step("read the code", "\n".join(lines)))
    return out


# ------------------------------------------------------------------- report

NUMBER = re.compile(r"-?\d[\d,]*\.\d+")
AI_LINE = re.compile(r"(?i)generative|\bAI\b|LLM|ChatGPT|Claude|Copilot")


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


def analyse_report(path, forecast, leaky, steps):
    if path is None:
        steps.append(Step("REPORT.md", "no report found", ok=False))
        return {"present": False}
    text = text_of(path)
    numbers = decimals_in(text)
    values = []
    for r in (forecast.get("rows") or {}).values():
        for c in ("persistence_rmse", "mean_rmse", "direct_rmse", "recursive_rmse"):
            if _num(r.get(c)):
                values.append(float(r[c]))
    hits = sum(1 for v in values if quoted(v, numbers))
    means = leaky.get("means") or {}
    leaky_hits = {k: quoted(v, numbers) for k, v in means.items() if v is not None}
    heads = re.findall(r"(?m)^#{1,3}\s+(.+)$", text)
    words = len(re.findall(r"\w+", text))
    lines = [f"{words} words, {len(heads)} headings: {heads[:10]}",
             f"RMSE values from forecast.csv quoted in the report: {hits} of {len(values)}",
             "leaky.csv means quoted: " + (", ".join(f"{k} {'yes' if v else 'no'}"
                                                     for k, v in leaky_hits.items()) or "none to look for"),
             f"AI-use line: {'yes' if AI_LINE.search(text) else 'not found'}"]
    steps.append(Step("REPORT.md", "\n".join(lines)))
    return {"present": True, "hits": hits, "values": len(values),
            "leaky_hits": leaky_hits, "words": words}


# ------------------------------------------------------------------- checks


def collect(root, args, found, steps):
    data, problem = load_data(found["data"])
    notes = []
    if data is None:
        steps.append(Step("data", problem, ok=False))
        ref_mean, ref = None, None
    else:
        runs = data[RUN].n_unique()
        per_run = data.group_by(RUN).len()["len"].unique().to_list()
        ref_mean, ref = reference(data)
        lines = [f"{data.height:,} rows, {runs} runs, samples per run {per_run}",
                 f"training mean of {Y} over runs {TRAIN[0]} to {TRAIN[1]}: {ref_mean:.5f}"]
        if runs != 500 or per_run != [SAMPLES_PER_RUN]:
            lines.append("this does not look like the fault-free training file (500 runs of 500)")
            notes.append("The data file is not the 500-run fault-free training file.")
        lines += [f"h={h:>2}: persistence {v['persistence']:.4f}, mean {v['mean']:.4f} "
                  f"on {v['rows']:,} test origins" for h, v in ref.items()]
        steps.append(Step("data, and the script's own baselines", "\n".join(lines),
                          ok=runs == 500))

    pred = inspect_predictions(found["predictions"], data, steps)
    forecast = inspect_forecast(found["forecast"], ref, pred, steps)
    validation = inspect_validation(found["validation"], steps)
    leaky = inspect_leaky(found["leaky"], steps)
    code = analyse_code(root, found["code"], steps)
    report = analyse_report(found["report"], forecast, leaky, steps)

    checks = []

    def add(group, label, state, note=""):
        checks.append((group, label, state, note))

    def decided(value):
        return PASS if value else FAIL

    no_data = "the data file could not be read, so this cannot be recomputed"

    # 1. the table
    add("table", "predictions.parquet with the eight columns",
        decided(pred.get("present") and pred.get("columns_ok")))
    add("table", "every test run and origin, for every horizon, and nothing else",
        decided(pred.get("coverage_ok")) if pred.get("columns_ok") else FAIL)
    if data is None:
        add("table", f"y_true is {Y} at t + h", SKIP, no_data)
    else:
        share = pred.get("y_true_share", 0.0)
        add("table", f"y_true is {Y} at t + h", decided(share >= 0.999),
            f"{share:.2%} of rows match" if pred.get("columns_ok") else "")
    add("table", "shifts kept inside each run in the code",
        decided(code["over_run"]) if code["files"] else SKIP,
        "" if code["files"] else "no code found")

    # 2. baselines
    fc = forecast.get("checks", {})
    add("baseline", "forecast.csv with the five horizons and the six columns",
        decided(forecast.get("present") and forecast.get("horizons_ok") and forecast.get("columns_ok")))
    if data is None:
        add("baseline", "persistence RMSE matches the recomputation", SKIP, no_data)
        add("baseline", "mean RMSE matches the recomputation", SKIP, no_data)
    else:
        add("baseline", "persistence RMSE matches the recomputation", decided(fc.get("pers")),
            "within 0.5 % at every horizon")
        add("baseline", "mean RMSE matches the recomputation", decided(fc.get("mean")),
            "mean over all samples of runs 1 to 300")
    add("baseline", "skill = 1 - direct / better baseline", decided(fc.get("skill")))

    # 3. models
    rec = pred.get("recomputed") or {}
    if data is None or not rec:
        for label in ("direct RMSE matches your predictions",
                      "recursive RMSE matches your predictions",
                      "direct beats the better baseline at four or more horizons",
                      "recursive differs from direct beyond h = 1"):
            add("models", label, SKIP, no_data if data is None else "no usable predictions")
    else:
        add("models", "direct RMSE matches your predictions", decided(fc.get("direct")))
        add("models", "recursive RMSE matches your predictions", decided(fc.get("recursive")))
        wins = sum(1 for h in HORIZONS if h in rec and ref and
                   rec[h]["direct"] < min(ref[h]["persistence"], ref[h]["mean"]))
        add("models", "direct beats the better baseline at four or more horizons",
            decided(wins >= 4), f"{wins} of {len(HORIZONS)}")
        beyond = [rec[h]["gap"] for h in HORIZONS if h > 1 and h in rec]
        add("models", "recursive differs from direct beyond h = 1",
            decided(beyond and min(beyond) > 1e-6))
    add("models", "a scaler inside a pipeline in the code",
        decided(code["pipeline"]) if code["files"] else SKIP)

    # 4. honest evaluation
    add("honest", "validation.csv with three or more settings",
        decided(validation["present"] and validation["rows"] >= 3 and validation.get("rmse")))
    add("honest", "validation on runs 301 to 400 in the code",
        decided(code["validation_runs"]) if code["files"] else SKIP)
    add("honest", "leaky.csv with both splits for runs 1 to 10",
        decided(leaky.get("present") and leaky.get("columns_ok") and leaky.get("both_ok")))
    add("honest", "TimeSeriesSplit with a gap of at least 10 in the code",
        decided(code["tss"] and code["gap_ok"]) if code["files"] else SKIP,
        f"gap arguments found: {code['gaps']}" if code["gaps"] else "")
    add("honest", "shuffled KFold in the code",
        decided(code["kfold_shuffle"]) if code["files"] else SKIP)

    # 5. report numbers
    if not report.get("present"):
        add("numbers", "RMSE values in REPORT.md come from forecast.csv", FAIL, "no report")
        add("numbers", "REPORT.md quotes both leaky.csv means", FAIL, "no report")
    else:
        add("numbers", "RMSE values in REPORT.md come from forecast.csv",
            decided(report["hits"] >= 4), f"{report['hits']} of {report['values']} quoted; four needed")
        lh = report["leaky_hits"]
        add("numbers", "REPORT.md quotes both leaky.csv means",
            decided(len(lh) == 2 and all(lh.values())) if lh else FAIL,
            "" if lh else "leaky.csv had no means to look for")
    add("report", "six sections and the AI-use line", SKIP, "read by your TA")

    means = leaky.get("means") or {}
    if {"shuffled", "time"} <= set(means) and means["shuffled"] >= means["time"]:
        notes.append("leaky.csv: the shuffled mean is not lower than the time-ordered one. "
                     "That is unusual on this channel; check the two splits used the same features.")
    for h in HORIZONS:
        r = rec.get(h)
        if r and ref and r["recursive"] > ref[h]["mean"]:
            notes.append(f"h={h}: the recursive forecast is worse than the mean. "
                         "Worth a sentence in section 4 of the report.")
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
        "<!doctype html><meta charset='utf-8'><title>A4 evidence</title>"
        "<style>body{font:10pt/1.35 ui-monospace,Menlo,monospace;max-width:62rem;"
        "margin:2rem auto;padding:0 1rem}div{white-space:pre-wrap}</style>\n" + body)


# ---------------------------------------------------------------- the report


def self_hash():
    """This file's own sha256, printed in the report.

    HONESTLY, WHAT THIS BUYS. Not much on its own; anyone who edits the script can
    edit this function too. What it catches is the cheap case, a check quietly
    changed and the header line forgotten. The expensive-to-forge part of this
    report is that the raw capture, the tables, the recomputed windows and the
    report's own numbers all have to agree with each other.
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



def report_lines(root, args, found, result):
    rows = score(result["checks"])
    auto = sum(r["earned"] for r in rows if r["who"] == "script")
    held = sum(r["held"] for r in rows)
    ta_group = next(r for r in rows if r["who"] == "your TA")
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    lines = [plain("Assignment 4 evidence", bold=True), plain("")]
    lines += [plain(t) for t in [
        f"{args.name or args.andrew_id} ({args.andrew_id})",
        f"generated {stamp} on {platform.platform()}, polars {pl.__version__}",
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
    for label in ("data", "predictions", "forecast", "validation", "leaky", "report"):
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
    parser = argparse.ArgumentParser(description="Build the Assignment 4 evidence PDF.")
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--data", default=None, help="the Rieth fault-free training file (.RData or .parquet)")
    parser.add_argument("--predictions", default=None, help="results/predictions.parquet")
    parser.add_argument("--forecast", default=None, help="results/forecast.csv")
    parser.add_argument("--validation", default=None, help="results/validation.csv")
    parser.add_argument("--leaky", default=None, help="results/leaky.csv")
    parser.add_argument("--report", default=None, help="REPORT.md")
    parser.add_argument("--out", default="evidence.pdf")
    parser.add_argument("--html", action="store_true", help="also write evidence.html")
    args = parser.parse_args()

    root = Path.cwd()
    found = discover(root, args)
    if not any([found["predictions"], found["forecast"], found["report"]]):
        raise SystemExit(f"Found no predictions, no forecast table and no report in {root}. "
                         f"Run this from your A4 project root.")

    print(f"Building evidence for {args.andrew_id} in {root}")
    for label in ("data", "predictions", "forecast", "validation", "leaky", "report"):
        print(f"  {label:<12} {rel(root, found[label])}")

    result = collect(root, args, found, [])
    result["script_sha"] = self_hash()
    lines, rows, auto, held = report_lines(root, args, found, result)

    pages = write_pdf(root / args.out, lines, f"A4 evidence, {args.andrew_id}")
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
