# /// script
# requires-python = ">=3.11"
# dependencies = ["polars>=1.20"]
# ///
r"""Build the Assignment 3 evidence report.

Run this in the root of your A3 project, the directory holding `raw/`,
`processed/`, `results/` and your `REPORT.md`:

    uv run --no-project https://kitchingroup.cheme.cmu.edu/f26-06763/a03-evidence.py \
        --andrew-id yourid --name "Your Name"

or, on a copy you downloaded:

    uv run --no-project a03-evidence.py --andrew-id yourid --name "Your Name"

`--no-project` matters. This script needs Polars to read your Parquet files and
declares that itself, in the block at the top of this file, so uv builds it a
small environment of its own. The flag keeps uv from syncing *your* project on
the way in, which means a stale lockfile or an unresolvable dependency in your
project cannot leave you with no report at all.

It writes `evidence.pdf`. Upload that to Canvas. Read it before you send it.

WHAT IT DOES. A3 is worth six points, in six groups. This script decides five of
them and prints the total on the first page; the sixth is your `REPORT.md`, which
a person reads. Within a group the checks are equally weighted, so passing three
of four checks in a one-point group is 0.75.

Three things it does are worth the run on their own:

  * It parses your raw capture itself, line by line with the standard library,
    and counts what is really in it: messages, readings, statuses, distinct
    (tag, event_time) pairs, and so the duplicates. Your tables and your report
    are checked against those counts, not against numbers typed here.

  * It rebuilds the empty-cell counts from your `tidy.parquet` over your own
    grid's time span, and recomputes your 30-minute windows from your own
    `grid.parquet`, so "the grid and the windows agree" is a fact rather than a
    claim.

  * It reads your code for the three decisions A3 is about: a lazy decode that
    collects once, a pandera schema generated from the birth message, and a
    dedup key that is not `seq`.

Nothing is invented. If something fails, the failure goes in the report, which is
better for you than a report that quietly omits it.

IT DOES NOT CHANGE YOUR FILES. It reads the raw capture, the tables and the code,
and writes `evidence.pdf` (and `evidence.html` with --html). It does not re-run
your pipeline, does not connect to the stream, and does not download anything.

NAMES. The assignment names deliverables (`raw/stream-*.ndjson`,
`processed/tidy.parquet`, `processed/quarantine.parquet`, `processed/grid.parquet`,
`results/watermark.csv`, `results/windows.csv`, `REPORT.md`) and this script
looks for those first. It also goes looking when it does not find them, by what
the files contain, so a project laid out under other names still produces a
report. What it found is printed at the top, and every guess can be overridden
with --raw, --tidy, --quarantine, --grid, --watermark, --windows and --report.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ipynb_checkpoints",
             "build", "dist", ".pytest_cache", "site-packages", ".mypy_cache",
             ".ruff_cache", "target", "mlruns"}
OURS = ("a03-evidence.py", "a03-collect.py", "evidence.html", "evidence.pdf")
TELEMETRY = "plant/tep/telemetry"
BIRTH = "plant/tep/birth"
MIN_PLANT_HOURS = 20.0
SAMPLE_MS = 180_000
WINDOW_MS = 1_800_000
REPORT_WORDS = 1900

# The collector writes every line with this exact prefix, byte for byte. A file
# that was loaded and re-serialised (json.dumps adds spaces after the colons),
# sorted, or edited by hand no longer matches it.
ENVELOPE = re.compile(r'^\{"receivedAt":"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z",'
                      r'"topic":"plant/[\w/-]+","payload":[\{\[]')

TIDY_COLUMNS = ["tag", "value", "status", "event_time", "server_time", "received_at",
                "seq", "is_historical"]
TAG = re.compile(r"^(XMEAS|XMV)_\d+")

# --------------------------------------------------------------------------
# The six groups. Five are scored here; group 6 is the report, and a TA reads
# it. Within a group the checks are equally weighted. Points sum to 6.
# --------------------------------------------------------------------------
GROUPS = [
    ("collect",  "Collection",          0.75, "script"),
    ("decode",   "Decode and reshape",  1.0,  "script"),
    ("validate", "Validate",            1.0,  "script"),
    ("stream",   "Dedup and watermark", 1.25, "script"),
    ("grid",     "Grid and windows",    1.0,  "script"),
    ("report",   "REPORT.md",           1.0,  "your TA"),
]
TOTAL = sum(g[2] for g in GROUPS)
AUTO_TOTAL = sum(g[2] for g in GROUPS if g[3] == "script")
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Step:
    """One recorded action: what was read, what came back, how long it took."""

    def __init__(self, label, command, stdout, code, seconds):
        self.label, self.command = label, command
        self.stdout, self.code, self.seconds = stdout, code, seconds

    @property
    def ok(self):
        return self.code == 0


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


def _looks_raw(path):
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            return handle.readline().startswith('{"receivedAt"')
    except OSError:
        return False


def find_raw(root, flag):
    if flag:
        if any(c in flag for c in "*?["):
            return sorted(p for p in root.glob(flag) if p.is_file())
        p = given_path(root, flag)
        if p is None:
            return []
        return sorted(p.glob("*.ndjson")) if p.is_dir() else [p]
    files = sorted(root.glob("raw/stream-*.ndjson"))
    if files:
        return files
    candidates = [p for p in walk(root, ["*.ndjson", "*.jsonl"]) if _looks_raw(p)]
    if not candidates:
        return []
    home = candidates[0].parent
    return [p for p in candidates if p.parent == home]


def parquet_schema(path):
    try:
        return dict(pl.read_parquet_schema(path))
    except Exception:
        return None


def csv_header(path):
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            return [c.strip().strip('"') for c in handle.readline().split(",")]
    except OSError:
        return []


def discover(root, args):
    parquets = walk(root, ["*.parquet"])
    csvs = walk(root, ["*.csv"])
    schemas = {p: parquet_schema(p) for p in parquets}
    headers = {p: csv_header(p) for p in csvs}

    def named(flag, default):
        return given_path(root, flag) or ((root / default) if (root / default).is_file() else None)

    def parquet_by(pred, hints):
        return by_name([p for p, s in schemas.items() if s is not None and pred(s)], hints)

    def csv_by(pred, hints):
        return by_name([p for p, h in headers.items() if pred(h)], hints)

    def tag_columns(columns):
        return sum(1 for c in columns if TAG.match(c))

    tidy = named(args.tidy, "processed/tidy.parquet") or parquet_by(
        lambda s: {"tag", "event_time"} <= set(s) and "reason" not in s,
        ["tidy", "clean", "readings"])
    quarantine = named(args.quarantine, "processed/quarantine.parquet") or parquet_by(
        lambda s: "reason" in s, ["quarantine", "reject", "bad"])
    grid = named(args.grid, "processed/grid.parquet") or parquet_by(
        lambda s: tag_columns(s) >= 20, ["grid", "wide", "fill"])
    watermark = named(args.watermark, "results/watermark.csv") or csv_by(
        lambda h: any(re.search(r"allow|watermark|lateness", c, re.I) for c in h),
        ["watermark", "sweep"])
    windows = named(args.windows, "results/windows.csv") or csv_by(
        lambda h: tag_columns(h) >= 20, ["window", "agg"])

    md_files = walk(root, ["*.md"])
    report = given_path(root, args.report)
    if report is None:
        top = [p for p in md_files if p.stem.lower() == "report"]
        report = top[0] if top else by_name(
            [p for p in md_files if re.search(r"watermark", text_of(p), re.I)], ["report"])

    code = [p for p in walk(root, ["*.py", "*.ipynb"]) if p.name not in OURS]
    return {"raw": find_raw(root, args.raw), "tidy": tidy, "quarantine": quarantine,
            "grid": grid, "watermark": watermark, "windows": windows, "report": report,
            "code": code, "parquets": parquets, "csvs": csvs}


# --------------------------------------------------------------- the raw file


def parse_instant(text):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def profile_raw(files):
    """Parse the capture with the standard library, and count what is in it.

    Every figure the tables and the report are reconciled against comes from
    here, so it is computed from the student's own file at report time rather
    than trusted from anywhere else.
    """
    p = {"files": [str(f) for f in files], "lines": 0, "blank": 0, "bad_envelope": 0,
         "bad_json": 0, "torn_tail": 0, "first_bad": None, "birth": None, "births": 0,
         "telemetry": 0, "events": 0, "other": 0, "readings": 0, "status": {},
         "historical_messages": 0, "received_decreasing": 0, "max_received_gap_s": 0.0,
         "multi_event_messages": 0, "event_min": None, "event_max": None,
         "received_min": None, "received_max": None}
    keys_all, keys_good, keys_other = set(), set(), set()
    good = 0
    previous = None
    previous_dt = None
    for path in files:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                p["blank"] += 1
                continue
            last = number == len(lines)
            try:
                message = json.loads(line)
            except ValueError:
                if last and not line.endswith("\n"):
                    p["torn_tail"] += 1       # a collector killed mid-write
                else:
                    p["bad_json"] += 1
                    p["first_bad"] = p["first_bad"] or f"{Path(path).name}:{number}"
                continue
            p["lines"] += 1
            if not ENVELOPE.match(line):
                p["bad_envelope"] += 1
                p["first_bad"] = p["first_bad"] or f"{Path(path).name}:{number}"

            received = message.get("receivedAt")
            if isinstance(received, str):
                if previous is not None and received < previous:
                    p["received_decreasing"] += 1
                stamp = parse_instant(received)
                if stamp and previous_dt:
                    p["max_received_gap_s"] = max(p["max_received_gap_s"],
                                                  (stamp - previous_dt).total_seconds())
                previous, previous_dt = received, stamp or previous_dt
                p["received_min"] = p["received_min"] or received
                p["received_max"] = received

            topic = message.get("topic")
            payload = message.get("payload") or {}
            if topic == BIRTH:
                p["births"] += 1
                p["birth"] = p["birth"] or payload
            elif topic == TELEMETRY:
                p["telemetry"] += 1
                if payload.get("isHistorical"):
                    p["historical_messages"] += 1
                stamps = set()
                for metric in payload.get("metrics") or []:
                    p["readings"] += 1
                    tag, ts = metric.get("name"), metric.get("sourceTimestamp")
                    state = metric.get("statusCode")
                    p["status"][state] = p["status"].get(state, 0) + 1
                    key = (tag, ts)
                    keys_all.add(key)
                    if state == "Good":
                        good += 1
                        keys_good.add(key)
                    else:
                        keys_other.add(key)
                    stamps.add(ts)
                    if isinstance(ts, str):
                        if p["event_min"] is None or ts < p["event_min"]:
                            p["event_min"] = ts
                        if p["event_max"] is None or ts > p["event_max"]:
                            p["event_max"] = ts
                if len(stamps) > 1:
                    p["multi_event_messages"] += 1
            elif str(topic).startswith("plant/"):
                p["events"] += 1
            else:
                p["other"] += 1

    lo, hi = parse_instant(p["event_min"]), parse_instant(p["event_max"])
    p["event_span_h"] = (hi - lo).total_seconds() / 3600 if lo and hi else 0.0
    p["good"] = good
    p["uncertain"] = sum(n for s, n in p["status"].items() if str(s).startswith("Uncertain"))
    p["bad"] = sum(n for s, n in p["status"].items() if str(s).startswith("Bad"))
    p["distinct_all"] = len(keys_all)
    p["distinct_good"] = len(keys_good)
    p["distinct_not_good"] = len(keys_other)
    # Two orders are both correct, and they remove slightly different counts:
    # deduplicate first and then quarantine, or quarantine first and then
    # deduplicate what is left.
    p["dup_dedup_first"] = p["readings"] - len(keys_all)
    p["dup_quarantine_first"] = good - len(keys_good)
    p["keys_all"] = keys_all
    return p


def raw_summary(p):
    if p is None:
        return ["no raw capture found. The collector writes raw/stream-<date>.ndjson;",
                "pass --raw PATH if yours is somewhere else."]
    lines = [f"parsed {', '.join(p['files'])} with json.loads, one line at a time", "",
             f"  {p['lines']:>10,}  messages ({p['telemetry']:,} telemetry, {p['births']} birth, "
             f"{p['events']} event)",
             f"  {p['readings']:>10,}  readings",
             f"  {p['historical_messages']:>10,}  messages marked isHistorical",
             ""]
    lines += [f"  {n:>10,}  {s}" for s, n in sorted(p["status"].items(), key=lambda kv: -kv[1])]
    lines += ["",
              f"  {p['distinct_all']:>10,}  distinct (tag, event_time) over all readings",
              f"  {p['distinct_good']:>10,}  distinct (tag, event_time) over Good readings",
              f"  {p['dup_dedup_first']:>10,}  duplicates if you deduplicate first",
              f"  {p['dup_quarantine_first']:>10,}  duplicates if you quarantine first", "",
              f"  event time {p['event_min']} to {p['event_max']}",
              f"             {p['event_span_h']:.2f} plant hours",
              f"  received   {p['received_min']} to {p['received_max']}",
              f"  largest gap between two arrivals {p['max_received_gap_s']:.1f} s", "",
              f"  lines whose receivedAt is earlier than the line before: "
              f"{p['received_decreasing']:,}",
              f"  lines not in the collector's exact format: {p['bad_envelope']:,}"
              + (f" (first at {p['first_bad']})" if p["first_bad"] else ""),
              f"  lines that are not JSON: {p['bad_json']:,};  blank lines: {p['blank']:,}"]
    if p["torn_tail"]:
        lines.append(f"  a torn final line (collector stopped mid-write): {p['torn_tail']}")
    return lines


def birth_classes(birth):
    tags = (birth or {}).get("tags") or []
    names = [t["name"] for t in tags if isinstance(t, dict) and "name" in t]
    has_meta = any(isinstance(t, dict) and "analyserIntervalHours" in t for t in tags)

    def analyser(t):
        if has_meta:
            return t.get("analyserIntervalHours") is not None
        m = re.match(r"XMEAS_(\d+)", t["name"])
        return bool(m) and 23 <= int(m.group(1)) <= 41

    analysers = [t["name"] for t in tags if isinstance(t, dict) and "name" in t and analyser(t)]
    return names, [n for n in names if n not in analysers], analysers


# ---------------------------------------------------------------- the tables


def epoch_ms(series):
    """Any time column as integer milliseconds since the epoch, or None."""
    if isinstance(series.dtype, pl.Datetime):
        return series.dt.epoch("ms")
    if isinstance(series.dtype, pl.Date):
        return series.cast(pl.Datetime("ms")).dt.epoch("ms")
    if series.dtype != pl.String:
        return None
    for kwargs in ({}, {"format": "%Y-%m-%dT%H:%M:%S%.f%z"}, {"format": "%Y-%m-%d %H:%M:%S%z"},
                   {"format": "%Y-%m-%d %H:%M:%S%.f%z"}, {"format": "%Y-%m-%dT%H:%M:%S%.f"},
                   {"format": "%Y-%m-%d %H:%M:%S"}):
        try:
            parsed = series.str.to_datetime(strict=False, **kwargs)
        except Exception:
            continue
        if parsed.null_count() <= 0.1 * len(series):
            return parsed.dt.epoch("ms")
    return None


def time_column(frame, prefer=r"window|start|bucket|time|ts|stamp"):
    names = [c for c in frame.columns if isinstance(frame[c].dtype, (pl.Datetime, pl.Date))]
    names.sort(key=lambda c: 0 if re.search(prefer, c, re.I) else 1)
    if names:
        return names[0]
    for c in frame.columns:
        if frame[c].dtype == pl.String and re.search(prefer, c, re.I) and epoch_ms(frame[c]) is not None:
            return c
    return None


def read_table(path, kind):
    if path is None:
        return None, f"no {kind} found"
    try:
        if Path(path).suffix == ".parquet":
            return pl.read_parquet(path), None
        return pl.read_csv(path, try_parse_dates=True, infer_schema_length=None), None
    except Exception as error:
        return None, f"could not read {path}: {error}"


def dtype_ok(dtype, want):
    if want == "string":
        return dtype == pl.String or isinstance(dtype, (pl.Categorical, pl.Enum))
    if want == "double":
        return dtype == pl.Float64
    if want == "timestamp":
        return isinstance(dtype, pl.Datetime) and dtype.time_zone in ("UTC", "Etc/UTC", "+00:00")
    if want == "int":
        return dtype.is_integer()
    if want == "bool":
        return dtype == pl.Boolean
    return False


WANT = {"tag": "string", "value": "double", "status": "string", "event_time": "timestamp",
        "server_time": "timestamp", "received_at": "timestamp", "seq": "int",
        "is_historical": "bool"}


def iso_ms(column, dtype):
    expr = pl.col(column)
    if isinstance(dtype, pl.Datetime) and dtype.time_zone:
        expr = expr.dt.convert_time_zone("UTC")
    return expr.dt.strftime("%Y-%m-%dT%H:%M:%S%.3fZ")


def inspect_tidy(path, profile, steps):
    out = {"read": False}
    t0 = time.monotonic()
    frame, error = read_table(path, "tidy table")
    if frame is None:
        steps.append(Step("read the tidy table", str(path or ""), error, 2, 0.0))
        return out, None
    out.update(read=True, rows=frame.height, columns=frame.columns)
    lines = [f"{path}: {frame.height:,} rows, {len(frame.columns)} columns", ""]
    types = {}
    for name in TIDY_COLUMNS:
        if name in frame.columns:
            ok = dtype_ok(frame[name].dtype, WANT[name])
            types[name] = ok
            lines.append(f"  {name:<14} {str(frame[name].dtype):<28} "
                         f"{'ok' if ok else 'expected ' + WANT[name]}")
        else:
            types[name] = False
            lines.append(f"  {name:<14} {'MISSING':<28}")
    extra = [c for c in frame.columns if c not in TIDY_COLUMNS]
    if extra:
        lines.append(f"  extra columns: {', '.join(extra)}")
    out["types"], out["extra"] = types, extra

    have = set(frame.columns)
    if {"tag", "event_time"} <= have and isinstance(frame["event_time"].dtype, pl.Datetime):
        keyed = frame.select(pl.col("tag").cast(pl.String),
                             iso_ms("event_time", frame["event_time"].dtype).alias("ev"))
        out["duplicate_keys"] = int(keyed.is_duplicated().sum())
        out["distinct_keys"] = keyed.unique().height
        lines.append(f"\n  rows sharing a (tag, event_time) with another row: {out['duplicate_keys']:,}")
        if profile:
            keys = set(zip(keyed["tag"].to_list(), keyed["ev"].to_list()))
            invented = len(keys - profile["keys_all"])
            out["invented_keys"] = invented
            lines.append(f"  (tag, event_time) pairs that are not in the raw capture: {invented:,}")
    if "status" in have:
        out["not_good"] = int((frame["status"].cast(pl.String) != "Good").sum())
        lines.append(f"  rows whose status is not Good: {out['not_good']:,}")
    clocks = [c for c in ("event_time", "server_time", "received_at") if c in have]
    if len(clocks) == 3 and all(isinstance(frame[c].dtype, pl.Datetime) for c in clocks):
        nulls = sum(frame[c].null_count() for c in clocks)
        e_ms, s_ms, r_ms = (frame[c].dt.epoch("ms") for c in clocks)
        out["clock_nulls"] = nulls
        out["event_ne_server"] = float((e_ms != s_ms).mean() or 0)
        out["received_eq_server"] = float((r_ms == s_ms).mean() or 0)
        per = frame.group_by("server_time").agg(pl.col("event_time").n_unique().alias("n"))
        out["servers_multi"] = int((per["n"] > 1).sum())
        out["servers"] = per.height
        lines += ["",
                  f"  null clock values: {nulls:,}",
                  f"  rows where event_time differs from server_time: {out['event_ne_server']:.1%}",
                  f"  rows where received_at equals server_time: {out['received_eq_server']:.1%}",
                  f"  server_time values carrying more than one event_time: "
                  f"{out['servers_multi']:,} of {out['servers']:,}"]
    steps.append(Step("read the tidy table", f"polars.read_parquet({path})", "\n".join(lines), 0,
                      time.monotonic() - t0))
    return out, frame


def inspect_quarantine(path, steps):
    out = {"read": False}
    frame, error = read_table(path, "quarantine table")
    if frame is None:
        steps.append(Step("read the quarantine table", str(path or ""), error, 2, 0.0))
        return out
    out.update(read=True, rows=frame.height, has_reason="reason" in frame.columns)
    lines = [f"{path}: {frame.height:,} rows; columns {', '.join(frame.columns)}", ""]
    if "status" in frame.columns:
        status = frame["status"].cast(pl.String)
        out["uncertain"] = int(status.str.starts_with("Uncertain").sum())
        out["bad"] = int(status.str.starts_with("Bad").sum())
        lines.append(f"  Uncertain_* rows {out['uncertain']:,};  Bad_* rows {out['bad']:,}")
    if out["has_reason"]:
        counts = frame["reason"].cast(pl.String).value_counts(sort=True).head(10)
        lines.append("  reasons:")
        lines += [f"    {row[1]:>8,}  {str(row[0])[:80]}" for row in counts.iter_rows()]
    steps.append(Step("read the quarantine table", f"polars.read_parquet({path})",
                      "\n".join(lines), 0, 0.0))
    return out


def inspect_grid(path, tidy, profile, steps):
    out = {"read": False}
    frame, error = read_table(path, "grid")
    if frame is None:
        steps.append(Step("read the grid", str(path or ""), error, 2, 0.0))
        return out, None
    names, continuous, analysers = birth_classes((profile or {}).get("birth"))
    names = names or [c for c in frame.columns if TAG.match(c) and c.count("_") >= 1
                      and not re.search(r"fill|mask|imput", c, re.I)]
    tcol = time_column(frame, r"event|time|ts|stamp")
    out.update(read=True, rows=frame.height, time_column=tcol)
    lines = [f"{path}: {frame.height:,} rows, {len(frame.columns)} columns; time column {tcol}"]
    if tcol is None:
        steps.append(Step("read the grid", f"polars.read_parquet({path})",
                          "\n".join(lines + ["  no time column found"]), 1, 0.0))
        return out, frame

    frame = frame.sort(tcol)
    ms = epoch_ms(frame[tcol])
    steps_ms = ms.diff().drop_nulls().unique().to_list()
    out["regular"] = steps_ms == [SAMPLE_MS]
    out["missing_tags"] = [n for n in names if n not in frame.columns]
    present = [n for n in names if n in frame.columns]
    empty = 0
    for n in present:
        col = frame[n]
        empty += col.null_count() + (int(col.is_nan().sum()) if col.dtype.is_float() else 0)
    out["empty_after"] = empty
    masks = {}
    for n in present:
        for c in frame.columns:
            if c != n and c.startswith(n) and re.search(r"fill|mask|imput|invent|synth", c[len(n):], re.I):
                masks[n] = c
                break
    out["mask_columns"] = len(masks)
    other_mask_files = [p for p in walk(Path.cwd(), ["*fill*", "*mask*"])
                        if p.suffix in (".parquet", ".csv") and p != Path(path)]
    out["fill_record"] = (len(masks) >= 0.9 * max(1, len(present))
                          or any(re.search(r"fill|mask|imput", c, re.I) for c in frame.columns)
                          or bool(other_mask_files))
    lines += [f"  spacing between rows: {', '.join(f'{s / 1000:g} s' for s in steps_ms[:5]) or 'n/a'}",
              f"  birth tags missing as columns: {len(out['missing_tags'])}"
              + (f" ({', '.join(out['missing_tags'][:4])})" if out["missing_tags"] else ""),
              f"  empty cells after filling: {empty:,}",
              f"  per-tag fill-mask columns: {len(masks)}"
              + (f"; other fill records: {', '.join(p.name for p in other_mask_files[:3])}"
                 if other_mask_files else "")]

    # --- empty cells before filling, rebuilt from the tidy table -----------
    if tidy is not None and {"tag", "event_time"} <= set(tidy.columns) and names:
        grid_ms = set(ms.to_list())
        long = (tidy.select(pl.col("tag").cast(pl.String),
                            epoch_ms(tidy["event_time"]).alias("ms"))
                .filter(pl.col("ms").is_in(list(grid_ms)))
                .unique())
        rows = frame.height
        holes = {}
        for label, group in (("continuous", continuous), ("analyser", analysers)):
            if not group:
                continue
            filled = long.filter(pl.col("tag").is_in(group)).height
            cells = rows * len(group)
            holes[label] = {"tags": len(group), "cells": cells, "empty": cells - filled,
                            "pct": 100 * (cells - filled) / cells if cells else 0.0}
            if masks and all(n in masks for n in group):
                marked = sum(int(frame[masks[n]].cast(pl.Boolean).sum()) for n in group)
                holes[label]["mask"] = marked
        out["holes"] = holes
        lines += ["", "  empty cells before filling, rebuilt from the tidy table over this grid:"]
        for label, h in holes.items():
            lines.append(f"    {label:<11} {h['tags']:>2} tags  {h['empty']:>8,} of {h['cells']:>8,}"
                         f"  ({h['pct']:.2f}%)"
                         + (f"   your mask marks {h['mask']:,}" if "mask" in h else ""))
    steps.append(Step("read the grid", f"polars.read_parquet({path})", "\n".join(lines), 0, 0.0))
    return out, frame


def inspect_windows(path, grid, grid_info, profile, steps):
    out = {"read": False}
    frame, error = read_table(path, "windows table")
    if frame is None:
        steps.append(Step("recompute the windows", str(path or ""), error, 2, 0.0))
        return out
    names, _, _ = birth_classes((profile or {}).get("birth"))
    wcol = time_column(frame)
    tags = [c for c in frame.columns if c in names] if names else [c for c in frame.columns if TAG.match(c)]
    out.update(read=True, rows=frame.height, tag_columns=len(tags), time_column=wcol,
               count_column=any(re.search(r"^n$|^n_|count|samples|complete|partial|coverage|full",
                                          c, re.I) for c in frame.columns))
    lines = [f"{path}: {frame.height:,} rows, {len(tags)} tag columns, window column {wcol}"]
    if wcol is None or not tags:
        steps.append(Step("recompute the windows", "", "\n".join(lines + ["  cannot read windows"]), 1, 0.0))
        return out
    w_ms = epoch_ms(frame[wcol])
    if w_ms is None:
        steps.append(Step("recompute the windows", "", "\n".join(lines + [f"  {wcol} is not a time"]), 1, 0.0))
        return out
    spacing = w_ms.sort().diff().drop_nulls()
    out["thirty_minutes"] = bool(len(spacing)) and float(spacing.mode()[0]) == WINDOW_MS
    lines.append(f"  most common spacing between windows: "
                 f"{(float(spacing.mode()[0]) / 60000 if len(spacing) else 0):g} min")

    tcol = (grid_info or {}).get("time_column")
    if grid is None or tcol is None:
        lines.append("  no grid to recompute from")
        steps.append(Step("recompute the windows", "", "\n".join(lines), 1, 0.0))
        return out
    common = [t for t in tags if t in grid.columns]
    mine = (grid.select([epoch_ms(grid[tcol]).alias("__ms"), *[pl.col(t).cast(pl.Float64) for t in common]])
            .with_columns(bucket=(pl.col("__ms") // WINDOW_MS) * WINDOW_MS)
            .group_by("bucket").agg(pl.len().alias("__n"), *[pl.col(t).mean() for t in common])
            .sort("bucket"))
    out["windows_expected"] = mine.height
    out["last_incomplete"] = mine.height > 0 and int(mine["__n"][-1]) < WINDOW_MS // SAMPLE_MS
    out["last_bucket"] = int(mine["bucket"][-1]) if mine.height else None
    theirs = frame.select([w_ms.alias("__their_ms"), *[pl.col(t).cast(pl.Float64, strict=False) for t in common]])
    out["student_last"] = int(theirs["__their_ms"].max()) if theirs.height else None

    best = (0, 0.0, 0)
    for offset in (0, WINDOW_MS):
        joined = theirs.with_columns(bucket=pl.col("__their_ms") - offset).join(
            mine, on="bucket", how="inner", suffix="__mine")
        if not joined.height:
            continue
        compared = agreed = 0
        for t in common:
            a, b = joined[t], joined[t + "__mine"]
            ok = ((a - b).abs() <= 1e-5 + 1e-5 * b.abs()).fill_null(False)
            usable = a.is_not_null() & b.is_not_null()
            compared += int(usable.sum())
            agreed += int((ok & usable).sum())
        fraction = agreed / compared if compared else 0.0
        if (joined.height, fraction) > (best[0], best[1]):
            best = (joined.height, fraction, offset)
    out["matched"], out["agreement"], out["offset"] = best
    out["recomputes"] = (best[0] >= 0.5 * mine.height and best[1] >= 0.95)
    lines += [f"  windows recomputed from the grid: {mine.height:,} "
              f"(the last holds {int(mine['__n'][-1]) if mine.height else 0} of "
              f"{WINDOW_MS // SAMPLE_MS} samples)",
              f"  your windows matched to them: {best[0]:,}"
              + ("  (labelled by window end)" if best[2] else ""),
              f"  cells agreeing to 1e-5: {best[1]:.1%}",
              f"  a column recording the count or completeness of each window: "
              f"{'yes' if out['count_column'] else 'no'}"]
    steps.append(Step("recompute the windows", f"group grid.parquet into 30-minute buckets",
                      "\n".join(lines), 0, 0.0))
    return out


def inspect_watermark(path, steps):
    out = {"read": False}
    frame, error = read_table(path, "watermark sweep")
    if frame is None:
        steps.append(Step("read the watermark sweep", str(path or ""), error, 2, 0.0))
        return out
    cols = frame.columns

    def find(pattern):
        # Alternatives are in order of preference, so "completeness_pct" wins
        # over "admitted" when a table carries both.
        for alternative in pattern.split("|"):
            hit = next((c for c in cols if re.search(alternative, c, re.I)), None)
            if hit:
                return hit
        return None

    allow = find(r"allow|lateness|watermark|delay|minutes|bound")
    admitted = find(r"complete|pct|percent|fraction|admit|accept|on_?time|includ|kept|captured")
    waiting = find(r"wait|pending|open|outstanding|held|not_?yet|buffer|unfinal|in_?flight")
    distinct = frame[allow].n_unique() if allow else 0
    out.update(read=True, rows=frame.height, allowance=allow, completeness=admitted,
               waiting=waiting, distinct=distinct)
    try:
        body = Path(path).read_text(errors="replace")
    except OSError:
        body = ""
    lines = [f"{path}: {frame.height} rows", f"  allowance column {allow}; completeness column "
             f"{admitted}; still-waiting column {waiting}", ""]
    lines += [f"  {l}" for l in body.splitlines()[:20]]
    steps.append(Step("read the watermark sweep", f"polars.read_csv({path})", "\n".join(lines), 0, 0.0))
    return out


# ------------------------------------------------------------ static analysis


def strip_comments(body):
    body = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", body)
    return re.sub(r"(?m)#.*$", "", body)


def analyse_code(root, files, steps):
    parts = [(p, text_of(p)) for p in files]
    stripped = [(p, strip_comments(b)) for p, b in parts]
    everything = "\n".join(b for _, b in stripped)

    scans = [(p, b) for p, b in stripped if re.search(r"scan_ndjson|\.lazy\(\s*\)", b)]
    collects = {p: len(re.findall(r"\.collect\(", b)) for p, b in scans}
    eager = [p for p, b in stripped if re.search(r"read_ndjson|json\.loads", b)]
    pandera = [(p, b) for p, b in stripped if re.search(r"import\s+pandera|from\s+pandera", b)]
    literals = sorted(set(re.findall(r"""["']((?:XMEAS|XMV)_\d+[\w]*)["']""", everything)))
    seq_key = [p.name for p, b in stripped if re.search(
        r"""(subset|on|by|keys?)\s*=\s*[\[(][^\])]*["']seq["']|unique\([^)]*["']seq["']"""
        r"""|drop_duplicates\([^)]*["']seq["']""", b)]
    out = {
        "scan_files": [p for p, _ in scans],
        "collect_counts": collects,
        "any_collect": bool(re.search(r"\.collect\(", everything)),
        "eager_files": eager,
        "explain": bool(re.search(r"\.explain\(", everything)),
        "infer_schema": bool(re.search(r"infer_schema_length\s*=\s*None|schema\s*=", everything)),
        "pandera_files": [p for p, _ in pandera],
        "from_birth": any(re.search(r"birth|\btags\b|tag_names|\[\s*['\"]name['\"]\s*\]", b)
                          for _, b in pandera),
        "lazy_true": bool(re.search(r"lazy\s*=\s*True", everything)),
        "tag_literals": literals,
        "seq_key": seq_key,
        "plant_clock": bool(re.search(r"accelerationFactor|plantEpoch|acceleration", everything)),
        "parts": parts,
    }
    lines = [f"{len(files)} code files: {', '.join(str(p.relative_to(root)) for p in files[:12])}", ""]
    lines.append("lazy decode")
    lines += ([f"  {p.relative_to(root)}: scan or .lazy(), {n} .collect() call(s)"
               for p, n in collects.items()] or ["  no scan_ndjson and no .lazy() found"])
    lines.append(f"  .explain() called: {'yes' if out['explain'] else 'no'};  "
                 f"infer_schema_length=None or an explicit schema: {'yes' if out['infer_schema'] else 'no'}")
    lines += ["", "pandera"]
    lines += ([f"  {p.relative_to(root)}" for p in out["pandera_files"]] or ["  no pandera import"])
    lines.append(f"  schema reads the birth tags: {'yes' if out['from_birth'] else 'no'};  "
                 f"lazy=True: {'yes' if out['lazy_true'] else 'no'}")
    lines.append(f"  distinct tag names typed as string literals: {len(literals)}")
    lines += ["", f"dedup keyed on seq: {', '.join(seq_key) if seq_key else 'no'}"]
    steps.append(Step("read the code", "", "\n".join(lines), 0, 0.0))
    return out


NUMBER = re.compile(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")


def numbers_in(text):
    out = []
    for token in NUMBER.findall(text or ""):
        try:
            out.append(float(token.replace(",", "").rstrip(".")))
        except ValueError:
            pass
    return out


def analyse_report(path, birth):
    if path is None:
        return {"present": False}
    text = text_of(path)
    low = text.lower()

    def near(pattern, window=220):
        found = []
        for match in re.finditer(pattern, low):
            found += numbers_in(text[max(0, match.start() - window): match.end() + window])
        return found

    def matches(values, targets, rel=0.01):
        return any(abs(v - t) <= max(1.0, rel * abs(t)) for v in values for t in targets if t is not None)

    sections, current = {}, "_preamble"
    for line in text.splitlines():
        heading = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading:
            current = heading.group(1).strip().lower()
            sections[current] = ""
        else:
            sections[current] = sections.get(current, "") + line + "\n"
    disturbance = "\n".join(body for title, body in sections.items() if "disturb" in title)
    if not disturbance:
        disturbance = "\n".join(par for par in re.split(r"\n\s*\n", text) if "disturb" in par.lower())
    descriptions = [t.get("description", "").lower() for t in (birth or {}).get("tags", [])
                    if isinstance(t, dict) and t.get("description")]
    tag_refs = set(re.findall(r"\b(?:XMEAS|XMV)_?\d+", disturbance, re.I))
    tag_refs |= {d for d in descriptions if d and d in disturbance.lower()}
    when = bool(re.search(r"\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}|plant[- ]hours?|\bhours?\s+\d|\d\s*h\b",
                          disturbance, re.I))

    return {
        "present": True, "path": str(path), "text": text, "words": len(text.split()),
        "near": near, "matches": matches, "numbers": numbers_in(text),
        "clock_comparison": bool(re.search(r"received_?at|receivedat|processing[- ]time", low))
                            and bool(re.search(r"event[_ ]time", low))
                            and bool(re.search(r"differ|disagree|worst|largest|gap|off by|by up to", low)),
        "incomplete_window": bool(re.search(r"(incomplete|partial|last|final)[^.\n]{0,60}window"
                                            r"|window[^.\n]{0,60}(incomplete|partial)", low)),
        "disturbance_tags": sorted(tag_refs), "disturbance_when": when,
        "idempotent": "idempot" in low,
        "sections": {
            "the three clocks": bool(re.search(r"clock", low)) and bool(re.search(r"sourcetimestamp|event[_ ]time", low)),
            "what you collected": bool(re.search(r"collect", low)) and "duplicat" in low,
            "what you filled": bool(re.search(r"\bfill", low)),
            "the watermark": "watermark" in low,
            "event time against processing time": bool(re.search(r"processing[- ]time|received_?at", low)),
            "the disturbance": "disturb" in low,
            "what .explain() showed": "explain" in low,
        },
        "ai_note": bool(re.search(r"\bai\b|generative|llm|claude|chatgpt|gpt-|copilot|gemini|language model", low)),
    }


# ----------------------------------------------------------------- collection


def collect(root, args, found, steps):
    t0 = time.monotonic()
    raw = found["raw"]
    print("  parsing the raw capture ..." if raw else "  no raw capture found", flush=True)
    profile = profile_raw(raw) if raw else None
    steps.append(Step("parse the raw capture", f"read {len(raw)} file(s)" if raw else "",
                      "\n".join(raw_summary(profile)), 0 if raw else 2, time.monotonic() - t0))
    birth = (profile or {}).get("birth")

    print("  reading the tables ...", flush=True)
    tidy_info, tidy = inspect_tidy(found["tidy"], profile, steps)
    quarantine = inspect_quarantine(found["quarantine"], steps)
    grid_info, grid = inspect_grid(found["grid"], tidy, profile, steps)
    windows = inspect_windows(found["windows"], grid, grid_info, profile, steps)
    watermark = inspect_watermark(found["watermark"], steps)
    print("  reading the code and the report ...", flush=True)
    code = analyse_code(root, found["code"], steps)
    report = analyse_report(found["report"], birth)

    checks = []
    no_raw = "no raw capture to check against"

    # ---- 1. collection ------------------------------------------------------
    if profile is None:
        for label in ("the raw NDJSON holds the birth message",
                      f"at least {MIN_PLANT_HOURS:.0f} plant hours of event time",
                      "receivedAt never goes backwards", "the raw file is as the collector wrote it"):
            checks.append(("collect", label, FAIL, "no raw/stream-*.ndjson found"))
    else:
        checks.append(("collect", "the raw NDJSON holds the birth message",
                       PASS if birth else FAIL, "" if birth else "no plant/tep/birth message in the capture"))
        span = profile["event_span_h"]
        checks.append(("collect", f"at least {MIN_PLANT_HOURS:.0f} plant hours of event time",
                       PASS if span >= MIN_PLANT_HOURS else FAIL,
                       f"{span:.1f} plant hours" + ("" if span >= MIN_PLANT_HOURS
                                                    else "; collect for at least ten minutes")))
        dec = profile["received_decreasing"]
        checks.append(("collect", "receivedAt never goes backwards", PASS if dec == 0 else FAIL,
                       "" if dec == 0 else f"{dec:,} lines arrived 'before' the line above them, "
                                           "so the file was reordered"))
        bad = profile["bad_envelope"] + profile["bad_json"] + profile["blank"]
        checks.append(("collect", "the raw file is as the collector wrote it", PASS if bad == 0 else FAIL,
                       "" if bad == 0 else f"{bad:,} lines are not in the collector's exact format "
                                           f"(first at {profile['first_bad']})"))

    # ---- 2. decode and reshape ----------------------------------------------
    if not tidy_info["read"]:
        state, note = FAIL, "no tidy.parquet found; pass --tidy PATH"
    else:
        wrong = [c for c, ok in tidy_info["types"].items() if not ok]
        state = PASS if not wrong and not tidy_info["extra"] else FAIL
        note = "; ".join(filter(None, [
            ("missing or mistyped: " + ", ".join(wrong)) if wrong else "",
            ("extra columns: " + ", ".join(tidy_info["extra"])) if tidy_info["extra"] else ""]))
    checks.append(("decode", "tidy.parquet has exactly the eight columns, with their types", state, note))

    counts = code["collect_counts"]
    if not code["scan_files"]:
        state = FAIL
        note = "no scan_ndjson or .lazy() found" + (
            f"; the raw file is read eagerly in {code['eager_files'][0].name}" if code["eager_files"] else "")
    elif any(n == 1 for n in counts.values()):
        state, note = PASS, ""
    elif all(n == 0 for n in counts.values()) and code["any_collect"]:
        state, note = PASS, "the plan is built in one file and collected in another"
    elif all(n == 0 for n in counts.values()):
        state, note = FAIL, "a LazyFrame is built but never collected"
    else:
        state = SKIP
        note = ("; ".join(f"{p.name} calls .collect() {n} times" for p, n in counts.items())
                + ". A TA reads whether the decode stage itself collects once")
    checks.append(("decode", "the decode is a Polars LazyFrame collected once", state, note))

    if not tidy_info.get("servers"):
        state, note = FAIL, "event_time, server_time and received_at are not all timestamps in tidy.parquet"
    else:
        ok = (tidy_info["clock_nulls"] == 0 and tidy_info["event_ne_server"] > 0
              and tidy_info["received_eq_server"] < 0.01)
        state = PASS if ok else FAIL
        note = "" if ok else (f"{tidy_info['clock_nulls']:,} null clock values; "
                              f"event_time differs from server_time on {tidy_info['event_ne_server']:.1%}; "
                              f"received_at equals server_time on {tidy_info['received_eq_server']:.1%}")
    checks.append(("decode", "the three clocks are distinct and populated", state, note))

    if not tidy_info.get("servers"):
        state, note = FAIL, "no server_time and event_time to compare"
    else:
        state = PASS if tidy_info["servers_multi"] > 0 else FAIL
        note = ("" if state == PASS else
                "every message has one event time, so the analysers' own timestamps were overwritten")
    checks.append(("decode", "more than one event_time per server_time", state, note))

    if profile is None or not tidy_info["read"]:
        state, note = FAIL, no_raw if profile is None else "no tidy table"
    elif "invented_keys" not in tidy_info:
        state, note = FAIL, "tidy.parquet has no usable tag and event_time"
    else:
        expected = profile["distinct_good"]
        rows = tidy_info["rows"]
        close = abs(rows - expected) <= max(10, 0.02 * expected)
        state = PASS if close and tidy_info["invented_keys"] == 0 else FAIL
        note = (f"{rows:,} rows against {expected:,} distinct Good readings in the raw file"
                + (f"; {tidy_info['invented_keys']:,} pairs are not in the raw file"
                   if tidy_info["invented_keys"] else ""))
    checks.append(("decode", "the record count reconciles with the raw file", state, note))

    # ---- 3. validate ----------------------------------------------------------
    if not code["pandera_files"]:
        state, note = FAIL, "no pandera import in your code"
    elif len(code["tag_literals"]) >= 20:
        state, note = FAIL, f"{len(code['tag_literals'])} tag names are typed into the code"
    elif code["from_birth"]:
        state, note = PASS, ""
    else:
        state, note = FAIL, "the schema file never refers to the birth message or its tags"
    checks.append(("validate", "a pandera schema generated from the birth tags", state, note))
    checks.append(("validate", "validation runs with lazy=True",
                   PASS if code["lazy_true"] else FAIL, "" if code["lazy_true"] else "no lazy=True found"))

    if not quarantine["read"]:
        state, note = FAIL, "no quarantine.parquet found; pass --quarantine PATH"
    elif not quarantine["has_reason"]:
        state, note = FAIL, "quarantine.parquet has no reason column"
    elif tidy_info.get("not_good", 1) != 0:
        state, note = FAIL, f"{tidy_info.get('not_good', 0):,} non-Good rows are still in tidy.parquet"
    elif profile is None:
        state, note = FAIL, no_raw
    elif "uncertain" in quarantine:
        held = quarantine["uncertain"] + quarantine["bad"]
        need = profile["distinct_not_good"]
        state = PASS if held >= need - max(2, 0.01 * need) else FAIL
        note = "" if state == PASS else (f"quarantine holds {held:,} Uncertain/Bad rows; the raw file has "
                                         f"{need:,} distinct ones")
    else:
        state, note = SKIP, "quarantine.parquet has no status column to count"
    checks.append(("validate", "Bad and Uncertain are in quarantine.parquet and not in tidy.parquet",
                   state, note))

    if not report.get("present"):
        state, note = FAIL, "no REPORT.md"
    elif profile is None:
        state, note = FAIL, no_raw
    else:
        near, matches = report["near"], report["matches"]
        unc = matches(near(r"uncertain"), [profile["uncertain"], profile.get("distinct_not_good")]) or \
            matches(near(r"uncertain"), [quarantine.get("uncertain")])
        bad = matches(near(r"\bbad"), [profile["bad"], quarantine.get("bad")])
        qrows = quarantine.get("rows")
        quar = qrows is not None and matches(report["numbers"], [qrows])
        state = PASS if unc and bad and quar else FAIL
        note = "" if state == PASS else "no matching number for: " + ", ".join(
            name for name, ok in (("Uncertain count", unc), ("Bad count", bad),
                                  ("rows quarantined", quar)) if not ok)
    checks.append(("validate", "the report's status and quarantine counts reconcile", state, note))

    # ---- 4. dedup and watermark ----------------------------------------------
    if "duplicate_keys" not in tidy_info:
        state, note = FAIL, "no tidy table with tag and event_time"
    else:
        state = PASS if tidy_info["duplicate_keys"] == 0 else FAIL
        note = "" if state == PASS else f"{tidy_info['duplicate_keys']:,} rows share a (tag, event_time)"
    checks.append(("stream", "(tag, event_time) is unique in tidy.parquet", state, note))

    if profile is None or not tidy_info["read"]:
        state, note = FAIL, no_raw if profile is None else "no tidy table"
    else:
        targets = [profile["dup_dedup_first"], profile["dup_quarantine_first"]]
        implied = (profile["readings"] - tidy_info["rows"] - quarantine.get("rows", 0)
                   if quarantine["read"] else None)
        table_ok = implied is not None and any(abs(implied - t) <= max(10, 0.02 * t) for t in targets)
        report_ok = report.get("present") and report["matches"](report["near"](r"duplicat"), targets, rel=0.02)
        state = PASS if table_ok or report_ok else FAIL
        note = (f"the script counts {targets[0]:,} (dedup first) or {targets[1]:,} (quarantine first)"
                + (f"; your tables imply {implied:,}" if implied is not None else ""))
    checks.append(("stream", "the duplicate count matches the script's", state, note))

    if not watermark["read"]:
        state, note = FAIL, "no watermark.csv found; pass --watermark PATH"
    else:
        missing = [n for n, v in (("an allowance column", watermark["allowance"]),
                                  ("a completeness column", watermark["completeness"]),
                                  ("a still-waiting column", watermark["waiting"])) if not v]
        few = watermark["distinct"] < 4
        state = PASS if not missing and not few else FAIL
        note = "; ".join(filter(None, ["no " + ", no ".join(missing) if missing else "",
                                       f"only {watermark['distinct']} allowances" if few else ""]))
    checks.append(("stream", "watermark.csv sweeps several allowances, with completeness and still waiting",
                   state, note))

    if not report.get("present"):
        state, note = FAIL, "no REPORT.md"
    else:
        state = PASS if report["clock_comparison"] else FAIL
        note = "" if state == PASS else "no event_time against received_at comparison found in the report"
    checks.append(("stream", "the report compares event time with processing time", state, note))

    # ---- 5. grid and windows ------------------------------------------------
    if not grid_info["read"]:
        state, note = FAIL, "no grid.parquet found; pass --grid PATH"
    else:
        problems = []
        if not grid_info.get("regular"):
            problems.append("rows are not exactly 180 s apart")
        if grid_info.get("missing_tags"):
            problems.append(f"{len(grid_info['missing_tags'])} birth tags have no column")
        if grid_info.get("empty_after"):
            problems.append(f"{grid_info['empty_after']:,} cells still empty")
        if grid_info.get("time_column") is None:
            problems.append("no time column")
        state = PASS if not problems else FAIL
        note = "; ".join(problems)
    checks.append(("grid", "a regular 180 s grid, one column per tag, no empty cells", state, note))
    checks.append(("grid", "a record of which cells were filled",
                   PASS if grid_info.get("fill_record") else FAIL,
                   "" if grid_info.get("fill_record") else "no fill mask or _filled columns found"))

    holes = grid_info.get("holes")
    if not holes:
        state, note = FAIL, "could not rebuild the empty-cell counts (needs tidy.parquet and grid.parquet)"
    else:
        by_mask = all("mask" in h and abs(h["mask"] - h["empty"]) <= max(5, 0.02 * h["empty"])
                      for h in holes.values())
        by_report = False
        if report.get("present"):
            by_report = all(
                report["matches"](report["near"](pattern), [h["empty"]], rel=0.02)
                or any(abs(v - h["pct"]) <= max(0.1, 0.1 * h["pct"]) for v in report["near"](pattern))
                for pattern, h in ((r"continu", holes.get("continuous")), (r"analy[sz]", holes.get("analyser")))
                if h)
        state = PASS if by_mask or by_report else FAIL
        note = ", ".join(f"{k} {h['empty']:,} ({h['pct']:.2f}%)" for k, h in holes.items())
        note = ("rebuilt: " + note) if state == PASS else (
            "rebuilt: " + note + "; neither your fill mask nor your report matches")
    checks.append(("grid", "the empty-cell counts before filling reconcile", state, note))

    if not windows["read"]:
        state, note = FAIL, "no windows.csv found; pass --windows PATH"
    elif windows["tag_columns"] < 20:
        state, note = FAIL, "windows.csv is not wide (one column per tag)"
    elif not windows.get("thirty_minutes"):
        state, note = FAIL, "windows are not 30 minutes apart"
    elif "recomputes" not in windows:
        state, note = SKIP, "no grid to recompute the windows from"
    else:
        state = PASS if windows["recomputes"] else FAIL
        note = (f"{windows['matched']:,} of {windows['windows_expected']:,} windows matched, "
                f"{windows['agreement']:.1%} of cells agree")
    checks.append(("grid", "wide 30-minute windows.csv that the script recomputes from the grid",
                   state, note))

    if not windows.get("read") or "last_incomplete" not in windows:
        state, note = SKIP, "the windows could not be recomputed"
    elif not windows["last_incomplete"]:
        state, note = PASS, "the last window happens to be complete"
    else:
        dropped = windows["student_last"] is not None and windows["student_last"] < windows["last_bucket"]
        handled = windows["count_column"] or dropped or report.get("incomplete_window")
        state = PASS if handled else FAIL
        note = ("dropped" if dropped else "a count or completeness column" if windows["count_column"]
                else "explained in the report" if handled else
                "kept with no count, flag or explanation")
    checks.append(("grid", "the incomplete last window is handled", state, note))

    if not report.get("present"):
        state, note = FAIL, "no REPORT.md"
    else:
        ok = len(report["disturbance_tags"]) >= 2 and report["disturbance_when"]
        state = PASS if ok else FAIL
        note = "" if ok else ("the disturbance section needs a time interval and at least two tags; found "
                              f"{len(report['disturbance_tags'])} tags"
                              + ("" if report["disturbance_when"] else " and no time"))
    checks.append(("grid", "the disturbance is given an interval and named tags", state, note))

    # ---- 6. the report, which a TA scores ----------------------------------
    for name, present in report.get("sections", {}).items():
        checks.append(("report", f"section: {name}", PASS if present else FAIL,
                       "" if present else "not found in REPORT.md"))
    checks.append(("report", "the generative-AI use statement", PASS if report.get("ai_note") else FAIL,
                   "" if report.get("ai_note") else "no AI-use sentence found"))

    # ---- notes: for a person, not for the score -----------------------------
    notes = []
    if code["seq_key"]:
        notes.append("seq appears in a dedup key (" + ", ".join(code["seq_key"]) + "). It is one byte "
                     "and wraps every 256 messages, so it is not an identity")
    if code["scan_files"] and not code["infer_schema"]:
        notes.append("scan_ndjson without infer_schema_length=None or a schema: a field that first "
                     "appears after line 100 is dropped silently")
    if not code["explain"]:
        notes.append("no .explain() call found, and the report is asked about what it showed")
    if report.get("present") and not report["idempotent"] and not any(
            "idempot" in text_of(p).lower() for p in walk(root, ["*.txt", "*.log", "*.md"])):
        notes.append("nothing shows the idempotence run (the word does not appear in the report or results)")
    if report.get("present") and re.search(r"received_?at", report["text"], re.I) and not code["plant_clock"]:
        notes.append("received_at is wall-clock time; the code never uses accelerationFactor or "
                     "plantEpoch, so a 30-minute bucket on it may hold two plant hours")
    if holes and holes.get("continuous", {}).get("pct", 0) > 3.0:
        notes.append(f"{holes['continuous']['pct']:.2f}% of continuous cells were empty before filling, "
                     "well above the ~1% expected; a grid that starts at a lagged analyser timestamp, "
                     "a collector disconnect, or quarantined rows would each do it")
    if profile and profile["max_received_gap_s"] > 30:
        notes.append(f"the collector received nothing for {profile['max_received_gap_s']:.0f} s at one point; "
                     "anything published then is simply not in the file")
    if profile and len(profile["files"]) > 1:
        notes.append(f"the capture spans {len(profile['files'])} raw files")
    if report.get("present") and report["words"] > REPORT_WORDS:
        notes.append(f"the report runs to about {report['words']} words, past the two-page limit")
    if tidy_info.get("types") and not tidy_info["types"].get("event_time") and "event_time" in tidy_info.get("columns", []):
        notes.append("event_time is not a UTC timestamp; a naive or string time loses the zone the "
                     "stream carried")

    return {"steps": steps, "checks": checks, "notes": notes, "profile": profile, "tidy": tidy_info,
            "quarantine": quarantine, "grid": grid_info, "windows": windows, "watermark": watermark,
            "code": code, "report": report}


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
        "<!doctype html><meta charset='utf-8'><title>A3 evidence</title>"
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
    profile = result["profile"] or {}

    lines = [plain("Assignment 3 evidence", bold=True), plain("")]
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
        tally = f"{r['passed']}/{r['of']} passed" + (f", {r['skipped']} held" if r["skipped"] else "")
        lines.append([("  ", False, BLACK), (f"{r['title']:<22}", False, BLACK),
                      (f"{value:>12}", True, colour),
                      (f"   {tally:<14}{r['who']}", False, GREY)])
    lines.append(plain("  " + "-" * 62, colour=GREY))
    lines.append([("  ", False, BLACK), (f"{'automatic total':<22}", True, BLACK),
                  (f"{auto:.2f} / {AUTO_TOTAL:.2f}", True, BLACK),
                  (f"   of {TOTAL:.0f} for the assignment", False, GREY)])

    lines += [plain(""), plain("What this script found", bold=True), plain("")]
    raw_names = ", ".join(rel(root, p) for p in found["raw"]) or "none found"
    for label, value in [("raw capture", raw_names), ("tidy", rel(root, found["tidy"])),
                         ("quarantine", rel(root, found["quarantine"])),
                         ("grid", rel(root, found["grid"])),
                         ("watermark", rel(root, found["watermark"])),
                         ("windows", rel(root, found["windows"])),
                         ("REPORT", rel(root, found["report"]))]:
        lines.append(plain(f"  {label:<12} {value}"))
    if profile:
        lines.append(plain(f"  {'':<12} {profile['telemetry']:,} telemetry messages, "
                           f"{profile['readings']:,} readings, {profile['event_span_h']:.1f} plant hours",
                           colour=GREY))

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
        lines += [plain(""), plain(f"  {step.label}", bold=True)]
        if step.command:
            lines.append([(f"  $ {step.command}", False, BLUE),
                          (f"   [{'ok' if step.ok else 'not ok'}, {step.seconds:.1f}s]", False,
                           BLACK if step.ok else RED)])
        lines.append(plain(""))
        lines += [plain(f"    {l}", colour=GREY)
                  for l in (trim(step.stdout) or "[no output]").splitlines()]

    code = result["code"]
    shown, sections = set(), []
    for path in code["scan_files"] + code["pandera_files"] + found["code"]:
        if path in shown or len(shown) >= 8:
            continue
        shown.add(path)
        sections.append((f"Code: {rel(root, path)}", read(path), True))
    sections.append((f"REPORT: {rel(root, found['report'])}", read(found["report"]), False))
    for title, body, is_code in sections:
        lines += [plain(""), plain(str(title), bold=True), plain("")]
        lines += highlight(body) if is_code else [plain(f"  {l}") for l in body.splitlines()]

    summary = {
        "andrew_id": args.andrew_id, "generated": stamp,
        "auto_score": round(auto, 2), "auto_of": AUTO_TOTAL,
        "report_points": ta_group["points"], "held_for_ta": round(held, 2),
        "assignment_total": TOTAL,
        "groups": {r["key"]: round(r["earned"], 2) for r in rows if r["who"] == "script"},
        "script_sha256": result["script_sha"],
        "raw_messages": profile.get("telemetry"), "raw_readings": profile.get("readings"),
        "plant_hours": round(profile.get("event_span_h", 0.0), 2),
        "tidy_rows": result["tidy"].get("rows"), "quarantine_rows": result["quarantine"].get("rows"),
    }
    lines += [plain(""), plain("Summary line", bold=True), plain(""),
              plain("  The script hash should match the checksum published beside the script.",
                    colour=GREY),
              plain(""), plain(f"  {json.dumps(summary)}")]
    return lines, rows, auto, held


def main():
    parser = argparse.ArgumentParser(description="Build the Assignment 3 evidence PDF.")
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--raw", default=None, help="raw capture: a file, a directory or a glob")
    parser.add_argument("--tidy", default=None, help="your tidy table (processed/tidy.parquet)")
    parser.add_argument("--quarantine", default=None, help="processed/quarantine.parquet")
    parser.add_argument("--grid", default=None, help="processed/grid.parquet")
    parser.add_argument("--watermark", default=None, help="results/watermark.csv")
    parser.add_argument("--windows", default=None, help="results/windows.csv")
    parser.add_argument("--report", default=None, help="REPORT.md")
    parser.add_argument("--out", default="evidence.pdf")
    parser.add_argument("--html", action="store_true", help="also write evidence.html")
    args = parser.parse_args()

    root = Path.cwd()
    found = discover(root, args)
    if not any([found["raw"], found["tidy"], found["grid"], found["report"]]):
        raise SystemExit(f"Found no raw capture, no tables and no report in {root}. "
                         f"Run this from your A3 project root.")

    print(f"Building evidence for {args.andrew_id} in {root}")
    print(f"  {'raw':<11} {', '.join(rel(root, p) for p in found['raw']) or None}")
    for label in ("tidy", "quarantine", "grid", "watermark", "windows", "report"):
        print(f"  {label:<11} {rel(root, found[label])}")

    steps = []
    result = collect(root, args, found, steps)
    result["script_sha"] = self_hash()
    lines, rows, auto, held = report_lines(root, args, found, result)

    pages = write_pdf(root / args.out, lines, f"A3 evidence, {args.andrew_id}")
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
            if state != PASS:
                print(f"      {state}  {label}" + (f"\n            {note}" if note else ""))
    print(f"\nAutomatic score {auto:.2f} of {AUTO_TOTAL:.0f}"
          + (f", with {held:.2f} held for your TA" if held > 1e-9 else "")
          + f".  The assignment is worth {TOTAL:.0f}.")
    if auto < AUTO_TOTAL - 1e-9:
        print("\nA failing check is a reason to fix it and run this again, "
              "not a reason to skip the submission.")
    print(f"\nUpload {args.out} to Canvas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
