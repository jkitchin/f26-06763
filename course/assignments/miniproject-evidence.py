# /// script
# requires-python = ">=3.11"
# dependencies = ["polars>=1.20", "numpy>=1.26", "pyarrow"]
# ///
r"""Build the miniproject (A7) evidence report for one team member.

Run this in the root of your team's repository, once per person:

    uv run --no-project https://kitchingroup.cheme.cmu.edu/f26-06763/miniproject-evidence.py \
        --andrew-id yourid --name "Your Name"

It writes `evidence-<andrew-id>.pdf`. Each member uploads their own. It checks the
team's files, not one person's part, so every member of a team should get the
same automatic score. Who did what is reported by the team in REPORT.pdf, which
is submitted separately and which this script does not read.

WHAT IT DOES. The miniproject fixes both detectors exactly, so this script can
build them itself from the two data files and compare. It recomputes:

  * the PCA model (standardization, the number of components, T-squared and SPE)
    and the one-step ridge forecast residual score, on every run the spec names;
  * the two 99th-percentile thresholds from your own validation scores;
  * three-in-a-row alarms, detection rate, detection delay and false-alarm rate
    for every fault, from your own scores and thresholds;
  * the per-channel contributions for the diagnosis.

Your files are then checked against those. The script scores the detectors and
the evaluation; the report is read by a person.

IT DOES NOT CHANGE YOUR FILES and does not download anything. The data files are
checked against the published sha256 before they are used.
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

import numpy as np
import polars as pl

SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ipynb_checkpoints",
             "build", "dist", ".pytest_cache", "site-packages", ".mypy_cache",
             ".ruff_cache", "target", "mlruns"}
OURS = ("miniproject-evidence.py",)

FREE_FILE = "tep_fault_free_training.parquet"
FAULTY_FILE = "tep_faulty_training_runs01-20.parquet"
SHA256 = {
    FREE_FILE: "bd98fb16e4c129ce9bdec6455016128af6392cb17e84b72a5bdd3aea0ce680c2",
    FAULTY_FILE: "e3966fccd6598ff0471c7c939d9203b0d88b4b33536834ac52f7b0d0dabe1ed6",
}
FAULT, RUN, SAMPLE = "faultNumber", "simulationRun", "sample"
KEYS = [FAULT, RUN, SAMPLE]
CHANNELS = [f"xmeas_{i}" for i in range(1, 42)] + [f"xmv_{i}" for i in range(1, 12)]
TRAIN, VALID, TEST = (1, 300), (301, 400), (401, 500)
FAULTS = list(range(1, 21))
FAULT_RUNS = (1, 20)
ONSET = 20            # the faults enter one hour in; samples after 20 are faulty
VARIANCE = 0.90
LAGS = 2
ALPHA = 1.0
QUANTILE = 0.99
IN_A_ROW = 3
MINUTES = 3
SCORE_RTOL = 1e-3     # 0.1 % on a score
THRESHOLD_RTOL = 1e-6  # a threshold is one exact numpy.quantile call
METRIC_TOL = 1e-3
DETECTORS = ["T2", "SPE", "ridge"]

# Points out of 15 for one person: 10 from this script, 5 for the report.
GROUPS = [
    ("detectors", "Detectors",                5, "script"),
    ("evaluation", "Evaluation and diagnosis", 5, "script"),
    ("report",    "REPORT.pdf",               5, "your TA"),
]
TOTAL = sum(g[2] for g in GROUPS)
AUTO_TOTAL = sum(g[2] for g in GROUPS if g[3] == "script")
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Step:
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


def find_data(root, flag, name):
    p = given_path(root, flag)
    if p is not None:
        return p
    return by_name([c for c in walk(root, [name])], ["data/"])




def discover(root, args):
    return {
        "free": find_data(root, args.free, FREE_FILE),
        "faulty": find_data(root, args.faulty, FAULTY_FILE),
        "pca": given_path(root, args.pca) if args.pca else _match(root, "scores_pca.parquet"),
        "ridge": _match(root, "scores_ridge.parquet") if not args.ridge else given_path(root, args.ridge),
        "thresholds": _match(root, "thresholds.csv") if not args.thresholds else given_path(root, args.thresholds),
        "detection": _match(root, "detection.csv") if not args.detection else given_path(root, args.detection),
        "contributions": _match(root, "contributions.csv") if not args.contributions else given_path(root, args.contributions),
        "code": [p for p in walk(root, ["*.py", "*.ipynb"]) if p.name not in OURS],
    }


def _match(root, name):
    return by_name(walk(root, [name]), ["results/", ""])


# ---------------------------------------------------------- the reference


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(found, steps):
    frames, lines, ok = {}, [], True
    for key, name in (("free", FREE_FILE), ("faulty", FAULTY_FILE)):
        path = found[key]
        if path is None:
            lines.append(f"{name}: not found (put it in data/ or pass --{key})")
            ok = False
            continue
        digest = sha(path)
        match = digest == SHA256[name]
        lines.append(f"{name}: {path.name}, sha256 {'matches' if match else 'DOES NOT MATCH'} the published file")
        if not match:
            ok = False
            continue
        frames[key] = pl.read_parquet(path).sort(KEYS)
    steps.append(Step("data", "\n".join(lines), ok=ok))
    return frames if ok else None


class Reference:
    """Both detectors, exactly as the spec fixes them."""

    def __init__(self, free):
        train = free.filter(pl.col(RUN).is_between(*TRAIN))
        X = train.select(CHANNELS).to_numpy()
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0, ddof=1)
        Z = (X - self.mu) / self.sd
        lam, vec = np.linalg.eigh(np.cov(Z, rowvar=False))
        order = np.argsort(lam)[::-1]
        lam, vec = lam[order], vec[:, order]
        self.k = int(np.searchsorted(np.cumsum(lam) / lam.sum(), VARIANCE) + 1)
        self.lam = lam[: self.k]
        self.P = vec[:, : self.k]

        A, B = self._lagged_arrays(train)
        A1 = np.column_stack([np.ones(len(A)), A])
        reg = ALPHA * np.eye(A1.shape[1])
        reg[0, 0] = 0.0
        self.W = np.linalg.solve(A1.T @ A1 + reg, A1.T @ B)
        self.res_sd = (B - A1 @ self.W).std(axis=0, ddof=1)

    def z(self, frame):
        return (frame.select(CHANNELS).to_numpy() - self.mu) / self.sd

    def _lagged_arrays(self, frame):
        As, Bs = [], []
        for _, g in frame.group_by([FAULT, RUN], maintain_order=True):
            z = self.z(g)
            As.append(np.hstack([z[LAGS - 1 - l: len(z) - 1 - l] for l in range(LAGS)]))
            Bs.append(z[LAGS:])
        return np.vstack(As), np.vstack(Bs)

    def pca(self, frame):
        z = self.z(frame)
        t = z @ self.P
        resid = z - t @ self.P.T
        return frame.select(KEYS).with_columns(
            t2=np.sum(t ** 2 / self.lam, axis=1),
            spe=np.sum(resid ** 2, axis=1),
        ), resid ** 2

    def ridge(self, frame):
        parts, contrib = [], []
        for _, g in frame.group_by([FAULT, RUN], maintain_order=True):
            z = self.z(g)
            A = np.hstack([z[LAGS - 1 - l: len(z) - 1 - l] for l in range(LAGS)])
            r = (z[LAGS:] - np.column_stack([np.ones(len(A)), A]) @ self.W) / self.res_sd
            parts.append(g.select(KEYS).slice(LAGS).with_columns(score=np.sum(r ** 2, axis=1)))
            contrib.append(r ** 2)
        return pl.concat(parts), np.vstack(contrib)


def scored_rows(free, faulty):
    """Every row the spec asks to be scored: validation, test and faulty runs."""
    return pl.concat([
        free.filter(pl.col(RUN).is_between(*VALID) | pl.col(RUN).is_between(*TEST)),
        faulty.filter(pl.col(FAULT).is_in(FAULTS) & pl.col(RUN).is_between(*FAULT_RUNS)),
    ]).sort(KEYS)


def split_of(frame):
    return frame.with_columns(
        split=pl.when(pl.col(FAULT) > 0).then(pl.lit("faulty"))
        .when(pl.col(RUN).is_between(*VALID)).then(pl.lit("validation"))
        .otherwise(pl.lit("test")))


def alarms(scores, threshold):
    flags = (scores > threshold).astype(int)
    run = np.convolve(flags, np.ones(IN_A_ROW, int), "valid") >= IN_A_ROW
    return np.r_[np.zeros(IN_A_ROW - 1, bool), run]


def metrics(scores, thresholds):
    """scores: KEYS + one column per detector. Returns the detection table."""
    rows = []
    for det, thr in thresholds.items():
        if det not in scores.columns:
            continue
        per_run = []
        for (f, r), g in scores.select(KEYS + [det]).drop_nulls().group_by(
                [FAULT, RUN], maintain_order=True):
            a = alarms(g[det].to_numpy(), thr)
            s = g[SAMPLE].to_numpy()
            if f == 0:
                if r >= TEST[0]:
                    per_run.append((0, a.mean(), None))
                continue
            post = s > ONSET
            hit = np.nonzero(a & post)[0]
            per_run.append((f, a[post].mean(), (s[hit[0]] - ONSET) * MINUTES if len(hit) else None))
        for f in [0] + FAULTS:
            mine = [p for p in per_run if p[0] == f]
            if not mine:
                continue
            delays = [p[2] for p in mine if p[2] is not None]
            rows.append({"fault": f, "detector": det,
                         "detection_rate": float(np.mean([p[1] for p in mine])),
                         "median_delay_min": float(np.median(delays)) if delays and f else None,
                         "runs_missed": sum(1 for p in mine if p[2] is None) if f else None})
    return pl.DataFrame(rows, schema={"fault": pl.Int64, "detector": pl.Utf8,
                                      "detection_rate": pl.Float64,
                                      "median_delay_min": pl.Float64,
                                      "runs_missed": pl.Int64})


def contributions(ref, faulty, thresholds):
    """Mean squared contribution per channel over post-onset alarm samples, per fault."""
    rows = []
    sub = faulty.filter(pl.col(FAULT).is_in(FAULTS) & pl.col(RUN).is_between(*FAULT_RUNS))
    pca_scores, spe_c = ref.pca(sub)
    ridge_scores, ridge_c = ref.ridge(sub)
    for det, scores, col, contrib in (("SPE", pca_scores, "spe", spe_c),
                                      ("ridge", ridge_scores, "score", ridge_c)):
        keep = np.zeros(scores.height, bool)
        offset = 0
        for _, g in scores.group_by([FAULT, RUN], maintain_order=True):
            a = alarms(g[col].to_numpy(), thresholds[det])
            keep[offset: offset + g.height] = a & (g[SAMPLE].to_numpy() > ONSET)
            offset += g.height
        faults = scores[FAULT].to_numpy()
        for f in FAULTS:
            m = keep & (faults == f)
            if not m.any():
                continue
            mean = contrib[m].mean(axis=0)
            for rank, j in enumerate(np.argsort(mean)[::-1][:5], start=1):
                rows.append({"fault": f, "detector": det, "rank": rank,
                             "channel": CHANNELS[j], "contribution": float(mean[j])})
    return pl.DataFrame(rows)


# ------------------------------------------------------------ comparisons


def read_table(path):
    if path is None:
        return None
    try:
        frame = pl.read_parquet(path) if str(path).endswith(".parquet") else \
            pl.read_csv(path, infer_schema_length=None)
    except Exception:  # noqa: BLE001
        return None
    return frame


def compare_scores(mine, ref, columns):
    """Join on the keys and report agreement for each score column."""
    out = {"rows_mine": mine.height, "rows_ref": ref.height}
    missing = [c for c in KEYS + columns if c not in mine.columns]
    if missing:
        out["missing"] = missing
        return out
    mine = mine.select([pl.col(k).cast(pl.Int64) for k in KEYS]
                       + [pl.col(c).cast(pl.Float64).alias(f"{c}_mine") for c in columns])
    joined = ref.join(mine, on=KEYS, how="left")
    out["covered"] = joined.select(pl.col(f"{columns[0]}_mine").is_not_null().mean()).item()
    out["extra"] = mine.height - mine.join(ref.select(KEYS), on=KEYS, how="semi").height
    for c in columns:
        both = joined.drop_nulls([c, f"{c}_mine"])
        if both.height == 0:
            out[c] = 0.0
            continue
        rel = ((both[f"{c}_mine"] - both[c]).abs() / both[c].abs().clip(lower_bound=1e-9)).to_numpy()
        out[c] = float(np.mean(rel <= SCORE_RTOL))
    return out


def fmt(value, places=4):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    return f"{value:.{places}f}" if isinstance(value, float) else str(value)


def thresholds_from(scores, column):
    val = scores.filter((pl.col(FAULT) == 0) & pl.col(RUN).is_between(*VALID))
    vals = val[column].drop_nulls().to_numpy()
    return float(np.quantile(vals, QUANTILE)) if len(vals) else None


def collect(root, args, found, steps):
    checks, notes = [], []

    def add(group, label, state, note=""):
        checks.append((group, label, state, note))

    def decided(v):
        return PASS if v else FAIL

    frames = load(found, steps)
    ref = None
    if frames:
        ref = Reference(frames["free"])
        rows = scored_rows(frames["free"], frames["faulty"])
        ref_pca, _ = ref.pca(rows)
        ref_ridge, _ = ref.ridge(rows)
        ref_thr = {"T2": thresholds_from(ref_pca, "t2"), "SPE": thresholds_from(ref_pca, "spe"),
                   "ridge": thresholds_from(ref_ridge, "score")}
        steps.append(Step("the script's own detectors", "\n".join([
            f"PCA: {ref.k} components reach {VARIANCE:.0%} of the variance",
            f"ridge: {LAGS} lags of {len(CHANNELS)} channels, alpha {ALPHA}",
            "thresholds (99th percentile of validation runs): "
            + ", ".join(f"{k} {v:.4f}" for k, v in ref_thr.items()),
            f"rows to score: {rows.height:,} (validation, test, faults 1-20 runs 1-20)"])))

    pca = read_table(found["pca"])
    ridge = read_table(found["ridge"])
    thr_tab = read_table(found["thresholds"])
    det_tab = read_table(found["detection"])
    con_tab = read_table(found["contributions"])
    no_data = "the data files are missing or do not match the published sha256"

    # ---- the detectors
    if pca is None:
        for label in ("scores_pca.parquet present", "every required PCA row scored",
                      "T2 matches the reference", "SPE matches the reference"):
            add("detectors", label, FAIL, "no scores_pca.parquet")
    else:
        add("detectors", "scores_pca.parquet present", PASS)
        if ref is None:
            for label in ("every required PCA row scored", "T2 matches the reference",
                          "SPE matches the reference"):
                add("detectors", label, SKIP, no_data)
        else:
            cmp = compare_scores(_lower(pca), ref_pca, ["t2", "spe"])
            steps.append(Step("scores_pca.parquet against the reference", json.dumps(cmp, indent=1)))
            add("detectors", "every required PCA row scored",
                decided(cmp.get("covered", 0) >= 0.999 and cmp.get("extra", 1) == 0),
                f"{cmp.get('covered', 0):.2%} covered, {cmp.get('extra', '?')} extra rows")
            add("detectors", "T2 matches the reference", decided(cmp.get("t2", 0) >= 0.999),
                f"{cmp.get('t2', 0):.2%} of rows within 0.1 %")
            add("detectors", "SPE matches the reference", decided(cmp.get("spe", 0) >= 0.999),
                f"{cmp.get('spe', 0):.2%} of rows within 0.1 %")
    if ridge is None:
        for label in ("scores_ridge.parquet present", "every required ridge row scored",
                      "ridge score matches the reference"):
            add("detectors", label, FAIL, "no scores_ridge.parquet")
    else:
        add("detectors", "scores_ridge.parquet present", PASS)
        if ref is None:
            add("detectors", "every required ridge row scored", SKIP, no_data)
            add("detectors", "ridge score matches the reference", SKIP, no_data)
        else:
            cmp = compare_scores(ridge, ref_ridge, ["score"])
            steps.append(Step("scores_ridge.parquet against the reference", json.dumps(cmp, indent=1)))
            add("detectors", "every required ridge row scored",
                decided(cmp.get("covered", 0) >= 0.999 and cmp.get("extra", 1) == 0),
                f"{cmp.get('covered', 0):.2%} covered, {cmp.get('extra', '?')} extra rows")
            add("detectors", "ridge score matches the reference", decided(cmp.get("score", 0) >= 0.999),
                f"{cmp.get('score', 0):.2%} of rows within 0.1 %")
    add("detectors", "a ridge regression fit in the code",
        decided(code_has(found["code"], r"Ridge\s*\(|np\.linalg\.solve|lstsq")))

    # ---- the evaluation and diagnosis, from the team's own scores
    add("evaluation", "thresholds.csv with T2, SPE and ridge",
        decided(thr_tab is not None and {"T2", "SPE", "ridge"} <= set(_col(thr_tab, "detector"))))
    mine_thr = threshold_dict(thr_tab)
    own = {}
    if pca is not None:
        own["T2"] = thresholds_from(_lower(pca), "t2")
        own["SPE"] = thresholds_from(_lower(pca), "spe")
    if ridge is not None:
        own["ridge"] = thresholds_from(ridge, "score")
    agree = [k for k in own if own[k] is not None and k in mine_thr and _close(mine_thr[k], own[k], THRESHOLD_RTOL)]
    add("evaluation", "thresholds are the 99th percentile of the team's validation scores",
        decided(len(agree) == 3), f"agree for {agree or 'none'}")
    if det_tab is None or not own or not mine_thr:
        add("evaluation", "detection.csv matches a recomputation from the team's scores", FAIL,
            "needs scores, thresholds and detection.csv")
    else:
        merged = _scores_wide(pca, ridge)
        mine_metrics = metrics(merged, {k: v for k, v in mine_thr.items() if k in DETECTORS})
        ok, note = compare_detection(det_tab, mine_metrics)
        steps.append(Step("detection.csv against a recomputation", note))
        add("evaluation", "detection.csv matches a recomputation from the team's scores",
            decided(ok), note.splitlines()[0])
    add("evaluation", "false-alarm rows (fault 0) reported for each detector",
        decided(det_tab is not None and _has_fault0(det_tab)))
    add("evaluation", "detection.csv covers faults 1 to 20 for all three detectors",
        decided(det_tab is not None and _covers(det_tab)))
    if ref is None or det_tab is None:
        add("evaluation", "faults 3, 9 and 15 reported as not detected", SKIP if ref is None else FAIL)
    else:
        low = _rates(det_tab, [3, 9, 15])
        add("evaluation", "faults 3, 9 and 15 reported as not detected",
            decided(low and max(low) < 0.05), f"largest rate {max(low):.3f}" if low else "")
    if con_tab is None:
        add("evaluation", "contributions.csv present", FAIL)
        add("evaluation", "top channels match the reference", FAIL, "no contributions.csv")
    else:
        add("evaluation", "contributions.csv present",
            decided({"fault", "detector", "rank", "channel"} <= set(c.lower() for c in con_tab.columns)))
        if ref is None:
            add("evaluation", "top channels match the reference", SKIP, no_data)
        else:
            ref_con = contributions(ref, frames["faulty"], {"SPE": ref_thr["SPE"], "ridge": ref_thr["ridge"]})
            share, note = compare_contributions(_lower(con_tab), ref_con)
            steps.append(Step("contributions.csv against the reference", note))
            add("evaluation", "top channels match the reference", decided(share >= 0.9),
                f"{share:.0%} of fault/detector top channels agree")
    add("report", "REPORT.pdf, submitted separately and read by your TA", SKIP, "")

    if ref is not None:
        ref_det = metrics(_scores_wide(ref_pca, ref_ridge), ref_thr)
        steps.append(Step("the script's detection table, for comparison",
                          str(ref_det.pivot(on="detector", index="fault", values="detection_rate"))))
    return {"checks": checks, "notes": notes, "steps": steps}


def _lower(frame):
    return frame.rename({c: c.lower() for c in frame.columns if c.lower() in ("t2", "spe")})


def _col(frame, name):
    for c in frame.columns:
        if c.lower() == name:
            return [str(v) for v in frame[c].to_list()]
    return []


def threshold_dict(frame):
    if frame is None:
        return {}
    cols = {c.lower(): c for c in frame.columns}
    if "detector" not in cols or "threshold" not in cols:
        return {}
    out = {}
    for r in frame.iter_rows(named=True):
        try:
            out[str(r[cols["detector"]])] = float(r[cols["threshold"]])
        except (TypeError, ValueError):
            pass
    return out


def _close(a, b, rtol=SCORE_RTOL):
    return abs(a - b) <= rtol * max(abs(b), 1e-12)


def _scores_wide(pca, ridge):
    parts = []
    if pca is not None:
        p = _lower(pca)
        parts.append(p.select([pl.col(k).cast(pl.Int64) for k in KEYS]
                              + [pl.col("t2").cast(pl.Float64).alias("T2"),
                                 pl.col("spe").cast(pl.Float64).alias("SPE")]))
    if ridge is not None:
        parts.append(ridge.select([pl.col(k).cast(pl.Int64) for k in KEYS]
                                  + [pl.col("score").cast(pl.Float64).alias("ridge")]))
    if not parts:
        return pl.DataFrame()
    out = parts[0]
    for p in parts[1:]:
        out = out.join(p, on=KEYS, how="full", coalesce=True)
    return out.sort(KEYS)


def compare_detection(mine, ref):
    cols = {c.lower(): c for c in mine.columns}
    need = ["fault", "detector", "detection_rate"]
    if not all(n in cols for n in need):
        return False, f"detection.csv needs columns {need}"
    mine = mine.select(pl.col(cols["fault"]).cast(pl.Int64).alias("fault"),
                       pl.col(cols["detector"]).cast(pl.Utf8).alias("detector"),
                       pl.col(cols["detection_rate"]).cast(pl.Float64).alias("rate_mine"),
                       *([pl.col(cols["median_delay_min"]).cast(pl.Float64).alias("delay_mine")]
                         if "median_delay_min" in cols else []))
    j = ref.join(mine, on=["fault", "detector"], how="left")
    ok_rate = (j["rate_mine"] - j["detection_rate"]).abs().fill_null(1.0) <= METRIC_TOL
    share = float(ok_rate.mean())
    lines = [f"{share:.0%} of fault/detector detection rates agree within {METRIC_TOL}"]
    if "delay_mine" in j.columns:
        d = j.filter(pl.col("median_delay_min").is_not_null())
        dshare = float(((d["delay_mine"] - d["median_delay_min"]).abs().fill_null(99) <= 0.5).mean()) if d.height else 1.0
        lines.append(f"{dshare:.0%} of median delays agree")
        share = min(share, dshare)
    lines.append(str(j.head(12)))
    return share >= 0.95, "\n".join(lines)


def _has_fault0(frame):
    cols = {c.lower(): c for c in frame.columns}
    if "fault" not in cols or "detector" not in cols:
        return False
    zero = frame.filter(pl.col(cols["fault"]).cast(pl.Int64) == 0)
    return set(DETECTORS) <= set(zero[cols["detector"]].cast(pl.Utf8).to_list())


def _covers(frame):
    cols = {c.lower(): c for c in frame.columns}
    if "fault" not in cols or "detector" not in cols:
        return False
    have = set(zip(frame[cols["fault"]].cast(pl.Int64).to_list(),
                   frame[cols["detector"]].cast(pl.Utf8).to_list()))
    return all((f, d) in have for f in FAULTS for d in DETECTORS)


def _rates(frame, faults):
    cols = {c.lower(): c for c in frame.columns}
    if not {"fault", "detection_rate"} <= set(cols):
        return []
    sub = frame.filter(pl.col(cols["fault"]).cast(pl.Int64).is_in(faults))
    return sub[cols["detection_rate"]].cast(pl.Float64).to_list()


def compare_contributions(mine, ref):
    cols = {c.lower(): c for c in mine.columns}
    top_mine = {}
    for r in mine.iter_rows(named=True):
        try:
            if int(r[cols["rank"]]) == 1:
                top_mine[(int(r[cols["fault"]]), str(r[cols["detector"]]))] = str(r[cols["channel"]])
        except (TypeError, ValueError, KeyError):
            pass
    top_ref = {(r["fault"], r["detector"]): r["channel"]
               for r in ref.filter(pl.col("rank") == 1).iter_rows(named=True)}
    agree = sum(1 for k, v in top_ref.items() if top_mine.get(k) == v)
    share = agree / len(top_ref) if top_ref else 0.0
    lines = [f"{agree} of {len(top_ref)} top channels agree"]
    for k in sorted(top_ref)[:12]:
        lines.append(f"  fault {k[0]:>2} {k[1]:<6} reference {top_ref[k]:<9} yours {top_mine.get(k, '-')}")
    return share, "\n".join(lines)


def strip_comments(body):
    body = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", body)
    return re.sub(r"(?m)#.*$", "", body)


def code_has(files, pattern):
    return any(re.search(pattern, strip_comments(text_of(p))) for p in files)


def score(checks):
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
        "<!doctype html><meta charset='utf-8'><title>A7 evidence</title>"
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
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [plain("Miniproject (A7) evidence", bold=True), plain("")]
    lines += [plain(t) for t in [
        f"{args.name or args.andrew_id} ({args.andrew_id})",
        f"generated {stamp} on {platform.platform()}, polars {pl.__version__}, numpy {np.__version__}",
        f"project {root.name}",
        f"evidence script sha256 {result['script_sha']}",
    ]]
    lines += [plain(""), [("Score  ", True, BLACK),
                          (f"{auto:.1f} / {AUTO_TOTAL}", True, GREEN if auto >= AUTO_TOTAL - 1e-9 else BLACK),
                          (f"  automatic, of {TOTAL} for the miniproject.", False, BLACK)]]
    lines.append(plain(f"  REPORT.pdf is worth {TOTAL - AUTO_TOTAL}, is submitted separately, and is read by your TA.", colour=GREY))
    if held > 1e-9:
        lines.append(plain(f"  {held:.1f} could not be decided here and is held for your TA.", colour=AMBER))
    lines += [plain(""), plain("What this script found", bold=True), plain("")]
    for label in ("free", "faulty", "pca", "ridge", "thresholds", "detection", "contributions"):
        lines.append(plain(f"  {label:<14} {rel(root, found[label])}"))
    for r in rows:
        lines += [plain(""), [(r["title"], True, BLACK),
                              (f"   {r['earned']:.1f} / {r['points']}" if r["who"] == "script"
                               else f"   {r['points']} points, read by your TA", True, BLACK)], plain("")]
        for _, label, state, note in r["checks"]:
            colour = {PASS: GREEN, FAIL: RED, SKIP: AMBER}[state]
            lines.append([("  ", False, BLACK), (f"[{state}]", True, colour), (f"  {label}", False, BLACK)])
            if note:
                lines.append(plain(f"          {note}", colour=GREY))
    lines += [plain(""), plain("Transcript", bold=True)]
    for step in result["steps"]:
        lines += [plain(""), [(f"  {step.label}", True, BLACK),
                              ("" if step.ok else "   [not ok]", False, RED)], plain("")]
        lines += [plain(f"    {l}", colour=GREY) for l in (trim(step.stdout) or "[no output]").splitlines()]
    for path in found["code"][:8]:
        lines += [plain(""), plain(f"Code: {rel(root, path)}", bold=True), plain("")]
        lines += highlight(read(path))
    summary = {"andrew_id": args.andrew_id, "generated": stamp,
               "auto_score": round(auto, 1), "auto_of": AUTO_TOTAL, "held_for_ta": round(held, 1),
               "total": TOTAL, "script_sha256": result["script_sha"]}
    lines += [plain(""), plain("Summary line", bold=True), plain(""), plain(f"  {json.dumps(summary)}")]
    return lines, rows, auto, held


def main():
    parser = argparse.ArgumentParser(description="Build the miniproject (A7) evidence PDF.")
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    for flag in ("free", "faulty", "pca", "ridge", "thresholds", "detection", "contributions"):
        parser.add_argument(f"--{flag}", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()

    root = Path.cwd()
    found = discover(root, args)
    print(f"Building evidence for {args.andrew_id} in {root}")
    for label in ("free", "faulty", "pca", "ridge", "thresholds", "detection", "contributions"):
        print(f"  {label:<14} {rel(root, found[label])}")

    result = collect(root, args, found, [])
    result["script_sha"] = self_hash()
    lines, rows, auto, held = report_lines(root, args, found, result)
    out = args.out or f"evidence-{args.andrew_id}.pdf"
    pages = write_pdf(root / out, lines, f"A7 evidence, {args.andrew_id}")
    if args.html:
        write_html(root / f"evidence-{args.andrew_id}.html", lines)

    print(f"\nWrote {out}, {pages} pages.\n")
    for r in rows:
        if r["who"] != "script":
            print(f"  {r['title']:<26}    ? / {r['points']}   (read by your TA)")
            continue
        print(f"  {r['title']:<26} {r['earned']:5.1f} / {r['points']}   ({r['passed']}/{r['of']} checks"
              + (f", {r['skipped']} held" if r["skipped"] else "") + ")")
        for _, label, state, note in r["checks"]:
            if state != PASS:
                print(f"      {state}  {label}" + (f"\n            {note}" if note else ""))
    print(f"\nAutomatic score {auto:.1f} of {AUTO_TOTAL}"
          + (f", with {held:.1f} held for your TA" if held > 1e-9 else "")
          + f". The miniproject is scored out of {TOTAL}.")
    print(f"\nUpload {out} to Canvas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
