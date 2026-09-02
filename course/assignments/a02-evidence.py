#!/usr/bin/env python3
r"""Build the Assignment 2 evidence report.

Run this in the root of your A2 project, the directory holding your `sql/`,
your loader, your `lab.db` and your `REPORT.md`:

    uv run --no-project https://kitchingroup.cheme.cmu.edu/f26-06763/a02-evidence.py \
        --andrew-id yourid --name "Your Name"

or, on a copy you downloaded:

    uv run --no-project a02-evidence.py --andrew-id yourid --name "Your Name"

`--no-project` matters. This script imports nothing outside the standard
library, so it needs nothing from your project, and that flag keeps it from
touching your environment on the way in. A plain `uv run` would sync your
project first, which means a stale lockfile or an unresolvable dependency would
leave you with no report at all -- one mistake taking down a submission that is
otherwise fine. `python3 a02-evidence.py ...` works identically if you prefer it.

It writes `evidence.pdf`. Upload that to Canvas. Read it before you send it.

WHAT IT DOES. A2 is worth six points, in six groups. This script decides five of
them and prints the total on the first page; the sixth is your `REPORT.md`, which
a person reads. Within a group the checks are equally weighted, so passing three
of four checks in a one-point group is 0.75.

It assembles, in one place, what a grader would otherwise go looking for: which
files you wrote, what your SQL actually says, what your database actually
contains, and what your report claims. Four things are worth the run on their
own:

  * It parses the raw `data.txt` itself, in the one way that is correct, and
    tells you how many rows are really in it and how many carry an empty field.
    The delimiter is a *single space*, and a transmission that dropped a channel
    leaves that field empty. Every parser that collapses runs of whitespace --
    `line.split()`, `sep=r'\s+'`, `awk` -- shifts the following values one column
    left and produces rows that are well-formed, plausible and wrong. If your
    reported counts disagree with the file, you see it here rather than in a
    comment on your grade.

  * It looks at how your loader reads that file, and says so.

  * It opens your `lab.db` and reads the schema the database actually has: the
    types, the foreign keys, the `foreign_keys` pragma, the indexes, the row
    counts. A `REFERENCES` clause with the pragma off is decoration, and this is
    where that shows up.

  * It runs its own `EXPLAIN QUERY PLAN` for one sensor over one day, and runs
    each of your four queries, so "the queries work" is a fact rather than a
    claim about keywords.

Nothing is invented. If something fails, the failure goes in the report, which is
better for you than a report that quietly omits it.

IT DOES NOT WRITE TO YOUR DATABASE. It opens `lab.db` read-only through a
`file:...?mode=ro` URI, so a write would raise rather than land. It does not
delete anything, does not re-run your loader, and does not download anything.

NAMES. The assignment names deliverables (`lab.db`, `sql/schema.sql`, a load
script, `sql/queries.sql`, a Parquet/DuckDB script, `REPORT.md`) and this script
looks for those first. It also goes looking when it does not find them, so a
project laid out sensibly under other names still produces a report rather than a
page of failures. What it found is printed at the top, and the guesses can be
overridden with --db, --schema, --queries, --report and --raw.

Standard library only -- `sqlite3` is in it -- so it runs under any Python 3.11
or newer with nothing installed, whether that is uv's or your system's. It shells
out to `git` if it is there, and to nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import re
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

TIMEOUT = 120
QUERY_BUDGET = 90.0     # seconds any one student query may run before it is cut off
SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ipynb_checkpoints",
             "build", "dist", ".pytest_cache", "site-packages", "pgdata",
             ".mypy_cache", ".ruff_cache", "target", "parquet"}
DATA_SUFFIXES = (".csv", ".tsv", ".txt", ".xlsx", ".xls", ".zip", ".data",
                 ".gz", ".bz2", ".h5", ".nc")
OURS = ("a02-evidence.py", "evidence.html", "evidence.pdf")
OS_JUNK = {".DS_Store", "Thumbs.db", "desktop.ini", ".Spotlight-V100", ".Trashes"}
BIG_FILE = 5_000_000

# --------------------------------------------------------------------------
# Ground truth about Intel Lab `data.txt`, so a report's counts have something
# to be checked against. Recomputed from the student's own copy whenever it is
# on hand rather than trusted from here.
# --------------------------------------------------------------------------
RAW_ROWS = 2_313_682
RAW_NO_MOTE = 526
RAW_OUT_OF_ROSTER = 9_866
RAW_IN_ROSTER = 2_303_290
RAW_EMPTY_FIELD_ROWS = 93_879
RAW_EMPTY_CELLS = 93_948
LONG_READINGS = 9_119_212
ROSTER = 54

# --------------------------------------------------------------------------
# The six groups. Five are scored here; group 6 is the report, and a TA reads
# it. Within a group the checks are equally weighted, so the group is worth the
# fraction of its checks that passed. Points sum to 6, which is what Canvas
# expects, and the fractions are what make partial credit possible without
# inventing a thirteen-row rubric for a six-point assignment.
# --------------------------------------------------------------------------
GROUPS = [
    ("schema",  "Schema and types",   1.0,  "script"),
    ("load",    "Load and cleaning",  1.0,  "script"),
    ("queries", "Queries",            1.5,  "script"),
    ("index",   "Index and plan",     0.75, "script"),
    ("store",   "Parquet and DuckDB", 0.75, "script"),
    ("report",  "REPORT.md",          1.0,  "your TA"),
]
TOTAL = sum(g[2] for g in GROUPS)          # 6.0
AUTO_TOTAL = sum(g[2] for g in GROUPS if g[3] == "script")   # 5.0
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class Step:
    """One recorded action: what was run, what came back, how long it took."""

    def __init__(self, label, command, stdout, code, seconds):
        self.label, self.command = label, command
        self.stdout, self.code, self.seconds = stdout, code, seconds

    @property
    def ok(self):
        return self.code == 0


def run(label, command, cwd, steps, timeout=TIMEOUT):
    print(f"  {label} ...", flush=True)
    start = time.monotonic()
    try:
        proc = subprocess.run(command, cwd=cwd or None, capture_output=True,
                              text=True, timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except FileNotFoundError:
        out, code = f"{command[0]}: not found on PATH", 127
    except subprocess.TimeoutExpired:
        out, code = f"timed out after {timeout}s", 124
    step = Step(label, " ".join(str(c) for c in command), out.strip(), code,
                time.monotonic() - start)
    steps.append(step)
    return step


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


def pick(candidates, *, must_contain=(), name_hints=()):
    scored = []
    for path in candidates:
        body = text_of(path)
        if must_contain and not any(re.search(p, body, re.I) for p in must_contain):
            continue
        hint = min((i for i, h in enumerate(name_hints)
                    if h in path.name.lower()), default=len(name_hints))
        scored.append((hint, -len(body), path))
    scored.sort()
    return scored[0][2] if scored else None


def find_db(root, given=None):
    """The SQLite file. Prefer the prescribed name, else the largest database."""
    if given:
        p = Path(given)
        return p if p.is_absolute() or not (root / given).exists() else root / given
    named = root / "lab.db"
    if named.is_file():
        return named
    candidates = [p for p in walk(root, ["*.db", "*.sqlite", "*.sqlite3", "*.db3"])
                  if p.stat().st_size > 4096]
    candidates.sort(key=lambda p: -p.stat().st_size)
    return candidates[0] if candidates else None


def discover(root, args):
    sql_files = walk(root, ["*.sql"])
    py_files = [p for p in walk(root, ["*.py"]) if p.name not in OURS]
    notebooks = walk(root, ["*.ipynb"])
    md_files = walk(root, ["*.md"])

    def given(flag):
        return root / flag if flag and (root / flag).exists() else None

    schema = given(args.schema) or pick(
        sql_files + py_files + notebooks, must_contain=[r"CREATE\s+TABLE"],
        name_hints=["schema", "ddl", "create", "load", "setup"])
    queries = given(args.queries) or pick(
        sql_files + notebooks + py_files,
        must_contain=[r"strftime|date_trunc|\bOVER\s*\("],
        name_hints=["quer", "analy", "sql", "report"])
    loader = pick(
        py_files + notebooks + sql_files,
        must_contain=[r"executemany|read_csv|\bINSERT\s+INTO|\.split\("],
        name_hints=["load", "ingest", "etl", "import", "main"])
    duck = pick(py_files + notebooks + sql_files,
                must_contain=[r"duckdb|read_parquet"],
                name_hints=["duck", "parquet", "export", "olap", "bench"])
    parquet = pick(py_files + notebooks + sql_files,
                   must_contain=[r"to_parquet|write_to_dataset|PARTITION_BY"
                                 r"|FORMAT\s+parquet|write_table|partition_cols"],
                   name_hints=["export", "parquet", "duck"])
    report = given(args.report)
    if report is None:
        named = [p for p in md_files if p.stem.lower() in ("report", "a02", "results")]
        report = named[0] if named else pick(
            md_files, must_contain=[r"OLAP|OLTP|column store|SCAN|SEARCH"],
            name_hints=["report", "readme"])
    readme = next((p for p in root.glob("*")
                   if p.is_file() and p.stem.lower() == "readme"), None)

    return {"sql_files": sql_files, "py_files": py_files, "notebooks": notebooks,
            "schema": schema, "queries": queries, "loader": loader, "duck": duck,
            "parquet": parquet, "report": report, "readme": readme,
            "db": find_db(root, args.db)}


def corpus(found):
    """Everything that might hold SQL, labelled, because students put it in .sql
    files, in Python string literals and in notebook cells alike."""
    return [(p, text_of(p)) for p in
            found["sql_files"] + found["py_files"] + found["notebooks"]]


def blob(parts):
    return "\n".join(body for _, body in parts)


# --------------------------------------------------------------- the raw file


def find_raw(root, given=None):
    if given:
        p = Path(given)
        return p if p.exists() else None
    for pattern in ("data/data.txt", "**/data.txt", "**/*labdata*.txt"):
        for path in sorted(root.glob(pattern)):
            if path.is_file() and _usable(path.relative_to(root)):
                return path
    return None


def profile_raw(path):
    """Parse data.txt the one way that is correct, and report what is in it.

    A single space is the delimiter. Split on it and every line yields exactly
    eight fields, some of them empty; that emptiness is the whole point, because
    it is an absent measurement and not a zero one.
    """
    rows = empty_rows = empty_cells = no_mote = out_of_roster = in_roster = ragged = 0
    names = ["temperature", "humidity", "light", "voltage"]
    channels = dict.fromkeys(names, 0)
    with Path(path).open(errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            rows += 1
            fields = line.split(" ")
            if len(fields) != 8:
                ragged += 1
                continue
            mote = fields[3]
            valid = mote.isdigit() and 1 <= int(mote) <= ROSTER
            if not mote.strip():
                no_mote += 1
            elif not valid:
                out_of_roster += 1
            else:
                in_roster += 1
            missing = [i for i in range(4, 8) if fields[i] == ""]
            if missing:
                empty_rows += 1
                for i in missing:
                    channels[names[i - 4]] += 1
                    if valid:
                        empty_cells += 1
    return {"path": str(path), "rows": rows, "ragged": ragged, "no_mote": no_mote,
            "out_of_roster": out_of_roster, "in_roster": in_roster,
            "empty_rows": empty_rows, "empty_cells": empty_cells,
            "channels": channels, "long_readings": in_roster * 4 - empty_cells}


def raw_summary(profile):
    if profile is None:
        return ["data.txt was not found under this project, so the raw file could not",
                "be profiled. The published file has 2,313,682 rows, of which 93,879",
                "carry at least one empty field. Pass --raw PATH if you keep it",
                "somewhere unusual."]
    return [
        f"parsed {profile['path']} by splitting on a single space", "",
        f"  {profile['rows']:>10,}  rows in the file",
        f"  {profile['ragged']:>10,}  rows that did NOT yield exactly 8 fields",
        f"  {profile['no_mote']:>10,}  rows with an empty mote id",
        f"  {profile['out_of_roster']:>10,}  rows with a mote id outside 1-54",
        f"  {profile['in_roster']:>10,}  rows from a mote in the roster", "",
        f"  {profile['empty_rows']:>10,}  rows with at least one EMPTY channel field",
        f"  {profile['empty_cells']:>10,}  empty channel fields among in-roster rows", "",
        "  empty fields by channel:",
        *(f"      {name:<12} {n:>8,}" for name, n in profile["channels"].items()), "",
        f"  a long-format load should therefore hold {profile['long_readings']:,} readings",
        f"  ({profile['in_roster']:,} rows x 4 channels, less the "
        f"{profile['empty_cells']:,} that were empty)", "",
        "  Every row splits cleanly into 8 fields on a single space. A parser that",
        "  collapses runs of whitespace sees 7 fields on those rows, shifts the",
        "  values left, and produces rows that are well-formed, plausible and wrong.",
    ]


# ---------------------------------------------------------- the database

def open_readonly(path):
    """The student's database, opened so a write would raise rather than land."""
    uri = "file:" + str(Path(path).resolve()).replace("?", "%3f").replace("#", "%23")
    return sqlite3.connect(uri + "?mode=ro", uri=True, timeout=10)


def budgeted(conn, seconds):
    """Abort a query that runs longer than `seconds`.

    A student's query (c) over nine million rows is legitimately slow, and a
    report that hangs is worse than one that says "this took too long". The
    progress handler is the only interruption sqlite3 offers from Python.
    """
    deadline = time.monotonic() + seconds
    conn.set_progress_handler(lambda: time.monotonic() > deadline, 100_000)


def introspect(db_path, steps, statements):
    """Read the schema the database actually has, then exercise it.

    Everything here is a SELECT, a PRAGMA or an EXPLAIN. Returned as a dict the
    checks read, and as text for the transcript.
    """
    out, lines = {"opened": False}, []
    if db_path is None or not Path(db_path).is_file():
        steps.append(Step("open the database", "", "no SQLite database found; pass --db PATH",
                          2, 0.0))
        return out
    print("  reading the database ...", flush=True)
    t0 = time.monotonic()
    try:
        conn = open_readonly(db_path)
        conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as error:
        steps.append(Step("open the database", str(db_path),
                          f"could not open: {error}", 1, time.monotonic() - t0))
        return out

    out["opened"] = True
    out["path"] = str(db_path)
    out["size_mb"] = Path(db_path).stat().st_size / 1e6
    q = lambda sql, a=(): conn.execute(sql, a).fetchall()

    lines += [f"opened {db_path} read-only  ({out['size_mb']:,.0f} MB, "
              f"sqlite {sqlite3.sqlite_version})", ""]

    # --- the schema as declared -------------------------------------------
    objects = q("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
    tables = [n for t, n, _ in objects if t == "table"]
    views = [n for t, n, _ in objects if t == "view"]
    ddl = "\n".join(s for _, _, s in objects if s)
    out["tables"], out["views"], out["ddl"] = tables, views, ddl
    out["strict"] = bool(re.search(r"\)\s*STRICT", ddl, re.I))

    # `PRAGMA foreign_keys` reports this connection's setting, which says nothing
    # about how the data was loaded. What the file itself can tell us is whether
    # any row actually violates a declared key, which is the question that
    # matters: a REFERENCES clause loaded with the pragma off leaves orphans.
    out["pragma_fk_here"] = q("PRAGMA foreign_keys")[0][0]
    violations = q("PRAGMA foreign_key_check")
    out["fk_violations"] = len(violations)

    lines.append("tables")
    counts = {}
    for name in tables:
        try:
            counts[name] = q(f'SELECT count(*) FROM "{name}"')[0][0]
        except sqlite3.Error:
            counts[name] = -1
        lines.append(f"  {name:<26} {counts[name]:>12,} rows")
    out["counts"] = counts
    if views:
        lines += ["", "views", "  " + ", ".join(views)]

    # --- the fact table, its columns, its keys ----------------------------
    facts = [t for t in tables if "stag" not in t.lower() and "raw" not in t.lower()]
    fact = max(facts or tables, key=lambda t: counts.get(t, 0), default=None)
    out["fact_table"] = fact

    lines += ["", "columns"]
    columns, fk_by_table = {}, {}
    for name in tables:
        info = q(f'PRAGMA table_info("{name}")')
        columns[name] = [(c[1], c[2], bool(c[3]), bool(c[5])) for c in info]
        fk_by_table[name] = q(f'PRAGMA foreign_key_list("{name}")')
        lines.append(f"  {name}")
        for col, kind, notnull, pk in columns[name]:
            flags = "".join([" PK" if pk else "", " NOT NULL" if notnull else ""])
            lines.append(f"      {col:<18} {kind or '(no type)':<10}{flags}")
    out["columns"] = columns
    out["has_fk"] = any(fk_by_table.values())
    out["fk_list"] = {t: [(r[2], r[3], r[4]) for r in v] for t, v in fk_by_table.items() if v}

    lines += ["", "foreign keys"]
    lines += ([f"  {t}.{frm} -> {tbl}.{to}" for t, v in out["fk_list"].items()
               for tbl, frm, to in v] or ["  none declared"])
    lines.append(f"  rows violating a declared foreign key: {out['fk_violations']:,}")
    lines.append(f"  tables declared STRICT: {'yes' if out['strict'] else 'no'}")

    # --- indexes and the natural key --------------------------------------
    lines += ["", "indexes"]
    indexes = []
    for name in tables:
        for row in q(f'PRAGMA index_list("{name}")'):
            idx, unique = row[1], bool(row[2])
            cols = [c[2] for c in q(f'PRAGMA index_info("{idx}")')]
            indexes.append((name, idx, cols, unique))
            lines.append(f"  {name:<20} {idx:<26} ({', '.join(cols)})"
                         + ("  UNIQUE" if unique else ""))
    if not indexes:
        lines.append("  none")
    out["indexes"] = indexes

    sensorish = re.compile(r"sensor|mote|node|device", re.I)
    timeish = re.compile(r"^ts$|time|stamp|date|epoch|unix", re.I)
    fact_cols = [c for c, *_ in columns.get(fact, [])]
    sensor_col = next((c for c in fact_cols if sensorish.search(c)), None)
    ts_col = next((c for c in fact_cols if c.lower() == "ts"), None) or \
        next((c for c in fact_cols if timeish.search(c)), None)
    out["sensor_column"], out["ts_column"] = sensor_col, ts_col
    # A key over (sensor, time, ...) -- declared PRIMARY KEY or a UNIQUE index.
    out["natural_key"] = any(
        t == fact and unique and len(cols) >= 2
        and any(sensorish.search(c) for c in cols) and any(timeish.search(c) for c in cols)
        for t, _, cols, unique in indexes)
    out["index_sensor_first"] = any(
        t == fact and cols and sensorish.search(cols[0]) for t, _, cols, unique in indexes)

    if fact and sensor_col:
        distinct = q(f'SELECT count(DISTINCT "{sensor_col}") FROM "{fact}"')[0][0]
        lo, hi = q(f'SELECT min("{sensor_col}"), max("{sensor_col}") FROM "{fact}"')[0]
        out["distinct_sensors"] = distinct
        lines += ["", f"{fact}: {counts.get(fact, 0):,} rows, {distinct} distinct "
                      f"{sensor_col} ({lo} to {hi})"]
    if fact and ts_col:
        lo, hi = q(f'SELECT min("{ts_col}"), max("{ts_col}") FROM "{fact}"')[0]
        out["ts_min"], out["ts_max"] = str(lo), str(hi)
        lines.append(f"{ts_col} spans {lo} to {hi}")

    # --- the plan, before and after, for one sensor over one day ----------
    if fact and sensor_col and ts_col:
        pick_row = q(f'SELECT "{sensor_col}" FROM "{fact}" LIMIT 1')
        sid = pick_row[0][0] if pick_row else None
        probe = (f'SELECT count(*) FROM "{fact}" WHERE "{sensor_col}" = ? '
                 f'AND "{ts_col}" >= ? AND "{ts_col}" < ?')
        lo_hi = _day_window(out.get("ts_min"), out.get("ts_max"))
        if sid is not None and lo_hi:
            try:
                plan = " ".join(r[3] for r in q("EXPLAIN QUERY PLAN " + probe,
                                                (sid, *lo_hi)))
                budgeted(conn, QUERY_BUDGET)
                t = time.perf_counter()
                n = q(probe, (sid, *lo_hi))[0][0]
                ms = (time.perf_counter() - t) * 1000
                conn.set_progress_handler(None, 0)
                out["probe_plan"], out["probe_rows"], out["probe_ms"] = plan, n, ms
                out["probe_uses_index"] = "USING" in plan and "INDEX" in plan
                lines += ["", f"EXPLAIN QUERY PLAN, {sensor_col} = {sid} over "
                              f"{str(lo_hi[0])[:10]}:", f"  {plan}",
                          f"  returned {n:,} rows in {ms:,.3f} ms"]
            except sqlite3.Error as error:
                lines += ["", f"the probe query failed: {error}"]

    # --- the student's own queries, actually run --------------------------
    if statements:
        lines += ["", "your queries, run against this database"]
        results = {}
        for name, sql in statements.items():
            budgeted(conn, QUERY_BUDGET)
            t = time.perf_counter()
            try:
                cur = conn.execute(sql)
                rows = cur.fetchmany(5000)
                ms = (time.perf_counter() - t) * 1000
                cols = [d[0] for d in (cur.description or [])]
                results[name] = {"ok": True, "rows": len(rows), "ms": ms, "cols": cols,
                                 "sample": [tuple(r) for r in rows[:3]]}
                more = "+" if len(rows) == 5000 else ""
                lines.append(f"  {name:<26} {len(rows):>8,}{more} rows in {ms:>9,.0f} ms")
                if rows:
                    lines.append(f"      {', '.join(map(str, cols))[:96]}")
                    lines.append(f"      {str(tuple(rows[0]))[:96]}")
            except sqlite3.Error as error:
                ms = (time.perf_counter() - t) * 1000
                results[name] = {"ok": False, "error": str(error), "ms": ms}
                lines.append(f"  {name:<26} FAILED: {error}")
            finally:
                conn.set_progress_handler(None, 0)
        out["query_results"] = results

    conn.close()
    steps.append(Step("read the database", f"sqlite3 {db_path} (read-only)",
                      "\n".join(lines), 0, time.monotonic() - t0))
    return out


def _day_window(ts_min, ts_max):
    """A one-day window inside the data, in whatever spelling ts uses.

    Students store the instant as ISO text, as a unix number, or as a julian day,
    and the probe has to compare against the same kind of thing the column holds.
    """
    if ts_min is None:
        return None
    text = str(ts_min)
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        try:
            start = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
        # Ten days in, so the window sits inside the deployment rather than on
        # its first ragged day.
        lo = start + timedelta(days=10)
        return (lo.strftime("%Y-%m-%d 00:00:00"),
                (lo + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"))
    try:
        lo = float(ts_min) + 10 * 86400.0
        return (lo, lo + 86400.0)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------- named statements

def named_statements(path):
    """Pull `-- name: x` blocks out of a .sql file, or fall back to splitting it.

    The reference solution labels its queries; most students will not, so an
    unlabelled file is split on `;` and the statements are numbered. Either way
    the point is to get four runnable SELECTs out of whatever they wrote.
    """
    if path is None:
        return {}
    text = text_of(path)
    if not text.strip():
        return {}
    named, current, body = {}, None, []
    for line in text.splitlines():
        match = re.match(r"\s*--\s*name:\s*(\S+)", line)
        if match:
            if current and "".join(body).strip():
                named[current] = "\n".join(body).strip().rstrip(";")
            current, body = match.group(1), []
        elif current is not None:
            body.append(line)
    if current and "".join(body).strip():
        named[current] = "\n".join(body).strip().rstrip(";")
    if named:
        return named

    statements = [s.strip() for s in re.split(r";\s*(?:\n|$)", text) if s.strip()]
    selects = [s for s in statements
               if re.match(r"(?is)^\s*(--[^\n]*\n|\s)*(with|select)\b", s)]
    return {f"query {i}": s for i, s in enumerate(selects[:8], start=1)}


# ------------------------------------------------------------ static analysis

# Parsers that collapse runs of whitespace, and so silently shift the columns of
# every row that dropped a channel.
COLLAPSING = [
    (r"delim_whitespace\s*=\s*True", "delim_whitespace=True"),
    (r"""sep\s*=\s*r?["']\\s\+["']""", r"sep='\s+'"),
    (r"""(sep|delimiter)\s*=\s*None""", "sep=None"),
    # `.split()` with no argument, but only on a line that is plainly parsing an
    # input line: `dsn.split()` in a helper is not this mistake, and calling it
    # one costs a student a check for a habit they do not have.
    (r"""(?i)^(?=.*\b(line|row|record|raw|txt|text|fields|parts|cols?|columns)\b)"""
     r"""(?!.*(dsn|url|uri|version|args|argv|command|cmd|shlex)).*\.split\(\s*\)""",
     ".split() with no argument"),
    (r"""\bawk\b""", "awk"),
]
SINGLE_SPACE = [
    (r"""(sep|delimiter)\s*=\s*["'] ["']""", "sep=' '"),
    (r"""\.split\(\s*["'] ["']""", ".split(' ')"),
    (r"""DELIMITER\s+["']\s["']""", "DELIMITER ' '"),
]
BULK = [
    (r"executemany", "executemany"),
    (r"\bBEGIN\b|begin\s*\(\s*\)|isolation_level", "an explicit transaction"),
    (r"to_sql\([^)]*chunksize", "to_sql(chunksize=...)"),
    (r"\.import\b|read_csv_auto|\bCOPY\b", "a bulk import"),
]
# A commit inside a loop is the SQLite catastrophe, and an execute-per-row is the
# lesser version of it.
COMMIT_IN_LOOP = r"""for\b[^\n]*\n(?:[^\n]*\n){0,8}?[^\s#][^\n]*\.commit\(\s*\)"""
ROW_AT_A_TIME = r"""for\b[^\n]*\n(?:[^\n]*\n){0,6}?[^\n]*execute\(\s*[frb]*["'][^"']{0,60}INSERT\s+INTO"""
WIDE_COLUMN = re.compile(r"^\s*((?:mote|sensor|node|s|m|dev)_?\d+)\s+\w", re.I | re.M)


def analyse_sql(parts, live):
    """What the student's SQL says. The live schema wins where the two disagree."""
    text = blob(parts)
    ddl = live.get("ddl", "") or "\n".join(
        b for _, b in parts if re.search(r"CREATE\s+TABLE", b, re.I))

    def has(pattern, body=None):
        return bool(re.search(pattern, text if body is None else body, re.I))

    return {
        "pragma_fk": has(r"PRAGMA\s+foreign_keys\s*=\s*(ON|1|True)"),
        "strict": live.get("strict") or has(r"\)\s*STRICT", ddl),
        "foreign_key": live.get("has_fk") or has(r"REFERENCES\s+\w+|FOREIGN\s+KEY", ddl),
        "wide_columns": WIDE_COLUMN.findall(ddl),
        "hour_bucket": has(r"strftime\s*\(\s*['\"]%Y-%m-%d %H|date_trunc|date_bin"),
        "hour_of_day": has(r"strftime\s*\(\s*['\"]%H['\"]|extract\s*\(\s*hour"),
        "window": has(r"\bOVER\s*(\(|\s+\w+\s*$)"),
        "range_frame": has(r"RANGE\s+BETWEEN"),
        "range_numeric": has(r"ORDER\s+BY\s+[\w.]*(unix|epoch|_s\b|julian)[\w.]*\s*"
                             r"(RANGE|\))|RANGE\s+BETWEEN\s+\d+\s+PRECEDING"),
        "rows_frame": has(r"ROWS\s+BETWEEN"),
        "lag": has(r"\blag\s*\(|\blead\s*\("),
        "left_join": has(r"LEFT\s+(OUTER\s+)?JOIN"),
        "having": has(r"\bHAVING\b"),
        "range_check": has(r"NOT\s+BETWEEN|BETWEEN\s+[\w.]+\s+AND\s+[\w.]+")
                       or has(r"value\s*[<>]\s*-?\d"),
        "index": has(r"CREATE\s+(UNIQUE\s+)?INDEX") or bool(live.get("indexes")),
        "explain": has(r"EXPLAIN"),
        "duckdb": has(r"duckdb|read_parquet"),
        "parquet_write": has(r"to_parquet|write_to_dataset|write_table|FORMAT\s+parquet"),
        "partitioned": has(r"partition_cols|PARTITION_BY|partition_by|date\s*=|hive"),
        "attach_sqlite": has(r"ATTACH[^\n]*TYPE\s+sqlite") or has(r"INSTALL\s+sqlite"),
        "three_engines": all(has(p) for p in (r"\bpandas\b|pd\.", r"sqlite", r"duckdb")),
        "timing": has(r"perf_counter|time\.time|timeit|%%time"),
    }


def analyse_loader(parts):
    """How the raw file is read, and whether the load is batched."""
    sources = [(p, b) for p, b in parts
               if p.suffix in (".py", ".ipynb", ".sql")
               and re.search(r"read_csv|read_table|open\(|split\(|executemany|INSERT\s+INTO",
                             b, re.I)]
    # Only a parse of the readings file counts. `mote_locs.txt` really is
    # whitespace-separated, so `line.split()` there is correct, and flagging it
    # would cost a student the check for doing the right thing on the other file.
    other_file = re.compile(r"mote_loc|roster|sensors?\b|locations?\b|coord", re.I)
    collapsing = []
    for pattern, label in COLLAPSING:
        for path, body in sources:
            lines = body.splitlines()
            for i, line in enumerate(lines):
                if not re.search(pattern, line, re.M):
                    continue
                context = " ".join(lines[max(0, i - 3):i + 2])
                if other_file.search(context) and not re.search(r"data\.txt|readings\b", line, re.I):
                    continue
                collapsing.append((label, path.name, line.strip()[:88]))
                break
            else:
                continue
            break
    single = [(label, path.name) for pattern, label in SINGLE_SPACE
              for path, body in sources if re.search(pattern, body)]
    bulk = [(label, path.name) for pattern, label in BULK
            for path, body in sources if re.search(pattern, body, re.I)]
    return {
        "collapsing": collapsing,
        "single_space": single,
        "bulk": bulk,
        "commit_in_loop": [p.name for p, b in sources if re.search(COMMIT_IN_LOOP, b)],
        "per_row": [p.name for p, b in sources if re.search(ROW_AT_A_TIME, b, re.I)],
        "skips_bad_lines": [p.name for p, b in sources
                            if re.search(r"on_bad_lines\s*=\s*[\"']skip|error_bad_lines\s*=\s*False", b)],
        "roster_rule": any(re.search(r"\b1\b\s*[,<=]+\s*\w*(mote|sensor)|between\s+1\s+and\s+54"
                                     r"|<=?\s*54|range\(1,\s*55", b, re.I) for _, b in sources),
        "voltage_rule": any(re.search(r"2\.4", b) for _, b in sources),
    }


NUMBER = re.compile(r"-?\d[\d,]*\.?\d*(?:[eE][-+]?\d+)?")


def numbers_in(text):
    out = []
    for token in NUMBER.findall(text or ""):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:
            pass
    return out


def analyse_report(path, profile):
    """What the report claims, and whether its counts match the raw file."""
    if path is None:
        return {"present": False}
    text = text_of(path)
    low = text.lower()

    def near(word, window=200):
        out = []
        for match in re.finditer(word, low):
            out += numbers_in(text[max(0, match.start() - window): match.end() + window])
        return out

    truth = profile or {"rows": RAW_ROWS, "in_roster": RAW_IN_ROSTER,
                        "long_readings": LONG_READINGS, "empty_rows": RAW_EMPTY_FIELD_ROWS}
    all_numbers = set(numbers_in(text))

    def mentions(value, tol=0.005):
        return any(abs(n - value) <= max(1.0, tol * value) for n in all_numbers)

    dropped_claim = None
    for sentence in re.split(r"(?<=[.\n])", text):
        if re.search(r"malform|bad row|skip|unparse|invalid|discard|drop", sentence, re.I):
            for n in numbers_in(sentence):
                if 90_000 <= n <= 100_000:
                    dropped_claim = sentence.strip()[:160]

    timed = {name: bool([n for n in near(pat) if n > 0]) for name, pat in
             (("pandas", r"pandas"), ("sqlite", r"sqlite"), ("duckdb", r"duckdb"))}
    sections = {
        "schema": bool(re.search(r"schema|primary key|foreign key|table", low)),
        "cleaning": bool(re.search(r"clean|discard|flag|reject|2\.4\s*v|voltage", low)),
        "indexing": bool(re.search(r"index|scan|search", low)),
        "comparison": all(timed.values()),
        "when to choose": bool(re.search(r"oltp|olap|row store|column|choose|when to", low)),
    }
    return {
        "present": True, "path": str(path), "words": len(text.split()), "text": text,
        "scan": bool(re.search(r"\bscan\b", low)),
        "search_index": bool(re.search(r"search[^\n]*using[^\n]*index|index\s+(only\s+)?scan", low)),
        "explain": "explain" in low or "query plan" in low,
        "oltp_olap": ("oltp" in low and "olap" in low)
                     or (bool(re.search(r"row[- ]store|row[- ]oriented", low))
                         and bool(re.search(r"column(ar|[- ]store|[- ]oriented)", low))),
        "sqlite_strength": bool(re.search(
            r"(sqlite|row store)[^.]{0,220}?(point lookup|one sensor|transaction|integrity"
            r"|foreign key|constraint|enforce|write|dashboard|update|index|single row)", low)),
        "timed": timed, "three_way": all(timed.values()), "sections": sections,
        "ai_note": bool(re.search(
            r"\bai\b|generative|llm|claude|chatgpt|gpt-|copilot|gemini|language model", low)),
        "counts_match_raw": mentions(truth["rows"]) or mentions(truth["in_roster"])
                            or mentions(truth.get("long_readings", LONG_READINGS)),
        "dropped_claim": dropped_claim,
    }


def committed_data(root, steps):
    tracked = run("tracked files", ["git", "ls-files"], root, steps)
    if tracked.ok and tracked.stdout:
        names, source = [root / l for l in tracked.stdout.splitlines() if l.strip()], "git"
    else:
        names, source = [p for p in walk(root, ["*"]) if p.is_file()], "filesystem"
    stray = []
    for path in names:
        if not path.exists() or not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name in OS_JUNK or rel.name in OURS:
            continue
        if rel.name in ("uv.lock", "poetry.lock", "requirements.txt"):
            continue
        size = path.stat().st_size
        raw_looking = (path.suffix.lower() in DATA_SUFFIXES
                       and not re.search(r"readme|licen[cs]e|report|notes", path.stem, re.I))
        if raw_looking and size > 200_000:
            stray.append(f"{rel} ({size // 1000} kB)")
        elif size > BIG_FILE and path.suffix.lower() not in (".lock",):
            stray.append(f"{rel} ({size // 1000} kB)")
    return stray, source


# ----------------------------------------------------------------- collection


def collect(root, args, found, steps):
    """Run everything, then decide each check from what came back."""
    parts = corpus(found)

    raw_path = find_raw(root, args.raw)
    print("  profiling the raw file ..." if raw_path
          else "  no data.txt found, skipping the raw profile", flush=True)
    profile = profile_raw(raw_path) if raw_path else None
    steps.append(Step("profile data.txt", f"read {raw_path}" if raw_path else "",
                      "\n".join(raw_summary(profile)), 0 if raw_path else 2, 0.0))

    statements = named_statements(found["queries"])
    live = introspect(found["db"], steps, statements)
    sql = analyse_sql(parts, live)
    loader = analyse_loader(parts)
    report = analyse_report(found["report"], profile)
    stray, stray_source = committed_data(root, steps)

    expected = (profile or {}).get("long_readings", LONG_READINGS)
    fact_rows = live.get("counts", {}).get(live.get("fact_table"), 0)
    typed_expected = (profile or {}).get("in_roster", RAW_IN_ROSTER)
    # Either schema shape is allowed, so a full load is near one count or the other.
    full_load = any(0.9 * e <= fact_rows <= 1.1 * e for e in (expected, typed_expected))

    ran = live.get("query_results", {})
    ok_queries = [n for n, r in ran.items() if r.get("ok") and r.get("rows", 0) > 0]

    checks = []   # (group, label, state, note)

    # ---- 1. schema and types ------------------------------------------------
    checks.append((
        "schema", "readings references a sensors dimension, and no row violates it",
        PASS if (sql["foreign_key"] and live.get("fk_violations", 1) == 0) else FAIL,
        ("no foreign key declared" if not sql["foreign_key"] else
         f"{live.get('fk_violations', 0):,} rows violate a declared foreign key")
        if not (sql["foreign_key"] and live.get("fk_violations", 1) == 0) else ""))
    checks.append((
        "schema", "PRAGMA foreign_keys = ON, so the key is enforced and not decoration",
        PASS if sql["pragma_fk"] else FAIL,
        "" if sql["pragma_fk"] else "no `PRAGMA foreign_keys = ON` anywhere in your code"))
    if live.get("opened"):
        state = PASS if live.get("natural_key") else FAIL
        note = "" if state == PASS else "no PRIMARY KEY or UNIQUE index over (sensor, time, ...)"
    else:
        state, note = SKIP, "the database could not be opened"
    checks.append(("schema", "a key covers the natural key (sensor, time, ...)", state, note))
    checks.append((
        "schema", "no column is named after an individual mote",
        PASS if not sql["wide_columns"] else FAIL,
        ("columns named after individual sensors: "
         + ", ".join(sorted(set(sql["wide_columns"]))[:6])) if sql["wide_columns"] else ""))

    # ---- 2. load and cleaning ----------------------------------------------
    if loader["collapsing"]:
        state = FAIL
        note = ("collapses runs of whitespace: "
                + "; ".join(f"{l} in {n}: {src}" for l, n, src in loader["collapsing"][:2]))
    elif loader["single_space"]:
        state, note = PASS, ""
    else:
        state, note = SKIP, "could not tell how data.txt is split into fields"
    checks.append(("load", "data.txt is split on a single space, so an empty field stays empty",
                   state, note))
    if loader["commit_in_loop"]:
        state, note = FAIL, "a commit inside the insert loop in " + ", ".join(loader["commit_in_loop"])
    elif loader["bulk"]:
        state, note = PASS, ""
    elif loader["per_row"]:
        state, note = FAIL, "a row-at-a-time INSERT loop in " + ", ".join(loader["per_row"])
    else:
        state, note = SKIP, "no batched load and no insert loop could be identified"
    checks.append(("load", "the load is batched inside one transaction", state, note))
    if not live.get("opened"):
        state, note = SKIP, "the database could not be opened"
    elif full_load:
        state, note = PASS, ""
    else:
        state = FAIL
        note = (f"the fact table holds {fact_rows:,} rows; a full load is about "
                f"{expected:,} (long) or {typed_expected:,} (typed)")
    checks.append(("load", "the whole file was loaded, not a sample", state, note))
    checks.append((
        "load", "the roster and battery cleaning rules are in the code",
        PASS if (loader["roster_rule"] and loader["voltage_rule"]) else FAIL,
        ("no 1-54 roster filter found; " if not loader["roster_rule"] else "")
        + ("no 2.4 V rule found" if not loader["voltage_rule"] else "")))

    # ---- 3. queries ---------------------------------------------------------
    for label, present in (
            ("(a) hourly buckets, not hour-of-day", sql["hour_bucket"]),
            ("(b) missing intervals", sql["lag"] or sql["having"] or sql["left_join"]),
            ("(d) a plausible-range check", sql["range_check"])):
        checks.append(("queries", label, PASS if present else FAIL,
                       "" if present else "not found in your SQL"))
    if not sql["window"]:
        state, note = FAIL, "no window function (`OVER (...)`) found"
    elif sql["range_frame"] and not sql["range_numeric"]:
        state = FAIL
        note = ("a RANGE frame that is not ordered by a numeric time column gives every "
                "row a window of one row, silently -- order by ts_unix")
    else:
        state, note = PASS, ("" if sql["range_frame"] else
                             "a ROWS frame counts rows, not time; RANGE over ts_unix is the "
                             "window the question asks for")
    checks.append(("queries", "(c) a window function over a time-based frame", state, note))
    if not live.get("opened") or not statements:
        state, note = SKIP, ("the database could not be opened" if not live.get("opened")
                             else "no queries could be found to run")
    elif len(ok_queries) >= 4:
        state, note = PASS, ""
    else:
        broken = [f"{n}: {r.get('error', 'no rows')}" for n, r in ran.items()
                  if not (r.get("ok") and r.get("rows", 0) > 0)]
        state = FAIL
        note = (f"{len(ok_queries)} of {len(ran)} queries returned rows. "
                + "; ".join(broken[:2]))
    checks.append(("queries", "all four queries run against your database and return rows",
                   state, note))

    # ---- 4. index and plan --------------------------------------------------
    if not live.get("opened"):
        state, note = SKIP, "the database could not be opened"
    elif live.get("index_sensor_first"):
        state, note = PASS, ""
    else:
        state = FAIL
        note = ("no index leads with the sensor column; leading with the timestamp scatters "
                "one sensor's readings across the whole index")
    checks.append(("index", "an index leads with the sensor column", state, note))
    probe = live.get("probe_uses_index")
    if probe is None:
        state, note = SKIP, "the probe query could not be planned"
    elif probe:
        state, note = PASS, (f"{live.get('probe_rows', 0):,} rows in "
                             f"{live.get('probe_ms', 0):,.3f} ms")
    else:
        state, note = FAIL, f"one sensor over one day still plans as: {live.get('probe_plan')}"
    checks.append(("index", "one sensor over one day uses that index (EXPLAIN QUERY PLAN)",
                   state, note))
    if not report.get("present"):
        state, note = FAIL, "no REPORT.md"
    elif report["scan"] and report["search_index"]:
        state, note = PASS, ""
    else:
        state = FAIL
        note = ("the report does not show a plan changing from SCAN to SEARCH ... USING INDEX"
                if report["explain"] else "no query plan in the report")
    checks.append(("index", "the report shows the plan before and after", state, note))

    # ---- 5. parquet and duckdb ---------------------------------------------
    on_disk = bool(list(root.glob("**/date=*"))) or bool(list(root.glob("**/*=*/*.parquet")))
    checks.append((
        "store", "Parquet is written date-partitioned",
        PASS if (sql["parquet_write"] or on_disk) and (sql["partitioned"] or on_disk) else FAIL,
        ("no Parquet write found; " if not (sql["parquet_write"] or on_disk) else "")
        + ("no partitioning found" if not (sql["partitioned"] or on_disk) else "")))
    checks.append((
        "store", "DuckDB queries the Parquet directly",
        PASS if sql["duckdb"] else FAIL,
        "" if sql["duckdb"] else "no DuckDB query found"))
    if not report.get("present"):
        state, note = FAIL, "no REPORT.md"
    elif report["three_way"]:
        state, note = PASS, ""
    else:
        state = FAIL
        note = "no number beside: " + ", ".join(k for k, v in report["timed"].items() if not v)
    checks.append(("store", "a timed three-way comparison: pandas, SQLite, DuckDB", state, note))

    # ---- 6. the report, which a TA scores ----------------------------------
    for name, present in report.get("sections", {}).items():
        checks.append(("report", f"section: {name}",
                       PASS if present else FAIL,
                       "" if present else "not found in REPORT.md"))
    checks.append(("report", "the generative-AI use statement",
                   PASS if report.get("ai_note") else FAIL,
                   "" if report.get("ai_note") else "no AI-use sentence found"))

    # ---- notes: for a person, not for the score -----------------------------
    notes = []
    if report.get("dropped_claim"):
        notes.append("the report says it dropped ~93,000 rows, which is the fingerprint of a "
                     "whitespace-collapsing parser rather than a property of the file: \""
                     + report["dropped_claim"] + "\"")
    if profile and report.get("present") and not report["counts_match_raw"]:
        notes.append(f"no count in the report matches the raw file ({profile['rows']:,} rows, "
                     f"{profile['in_roster']:,} in roster, {profile['long_readings']:,} readings)")
    if sql["window"] and sql["rows_frame"] and not sql["range_frame"]:
        notes.append("the rolling average uses a ROWS frame; on irregular sampling a numeric "
                     "RANGE frame is the window in time the question asks for")
    if sql["hour_of_day"] and not sql["hour_bucket"]:
        notes.append("hour-of-day bucketing gives 24 buckets for the whole month rather than "
                     "one bucket per hour")
    if live.get("opened") and not sql["strict"]:
        notes.append("no table is declared STRICT, so SQLite will accept the text 'hot' in a "
                     "REAL column without complaining")
    if loader["skips_bad_lines"]:
        notes.append("the loader skips bad lines silently (" +
                     ", ".join(loader["skips_bad_lines"]) + "), so anything it rejected is "
                     "invisible in the counts")
    if live.get("distinct_sensors", 0) > ROSTER:
        notes.append(f"{live['distinct_sensors']} distinct sensor ids are stored and the roster "
                     f"has {ROSTER}: the corrupt mote ids were not rejected")
    if report.get("present") and not report.get("sqlite_strength"):
        notes.append("the report never says what SQLite is better at, which is the half of the "
                     "OLTP/OLAP argument most reports miss")
    if sql["attach_sqlite"]:
        notes.append("stretch attempted: DuckDB's sqlite extension (ATTACH)")
    if stray:
        notes.append(f"raw data committed ({stray_source}): " + ", ".join(stray[:4]))
    if not live.get("opened"):
        notes.append("no database could be opened, so the schema, the key, the index and the "
                     "queries were read from your SQL rather than from a running database; "
                     "pass --db PATH if it is not called lab.db")
    if report.get("present") and report["words"] > 1900:
        notes.append(f"the report runs to about {report['words']} words, past the two-page "
                     f"limit once its tables are rendered")

    return {"steps": steps, "checks": checks, "notes": notes, "sql": sql, "loader": loader,
            "report": report, "live": live, "profile": profile, "parts": parts,
            "statements": statements}


def score(checks):
    """Group scores, and the total. Within a group the checks weigh the same.

    A SKIP is a check that could not be decided here, so it is neither passed nor
    failed: it is excluded from the group's denominator and its share is reported
    separately as held for a TA. That way a student whose database would not open
    loses the evidence, not the marks, and a TA knows exactly how much is theirs
    to decide.
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
        # Held share is carved out of the group, so earned + held <= points.
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
    "SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "JOIN", "LEFT", "INNER",
    "OUTER", "ON", "USING", "CREATE", "TABLE", "VIEW", "INDEX", "PRIMARY",
    "KEY", "FOREIGN", "REFERENCES", "NOT", "NULL", "INSERT", "INTO", "VALUES",
    "COPY", "WITH", "AS", "OVER", "PARTITION", "RANGE", "ROWS", "BETWEEN",
    "INTERVAL", "HAVING", "LIMIT", "EXPLAIN", "ANALYZE", "UNIQUE", "CHECK",
    "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END", "ALTER", "DROP",
}
TOKENS = re.compile(
    r"(?P<comment>--[^\n]*|#[^\n]*)"
    r"|(?P<string>'''|\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\")"
    r"|(?P<number>\b\d+\.?\d*\b)"
    r"|(?P<word>[A-Za-z_]\w*)"
)


def plain(text, bold=False, colour=BLACK):
    return [(text, bold, colour)]


def highlight(source, indent="  "):
    """Source as coloured runs, one list of runs per line. Python and SQL."""
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
            elif text in KEYWORDS or text.upper() in KEYWORDS:
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
        "<!doctype html><meta charset='utf-8'><title>A2 evidence</title>"
        "<style>body{font:10pt/1.35 ui-monospace,Menlo,monospace;max-width:62rem;"
        "margin:2rem auto;padding:0 1rem}div{white-space:pre-wrap}</style>\n" + body)


# ---------------------------------------------------------------- the report


def sha256(path):
    path = Path(path) if path else None
    return (hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            if path and path.exists() else "absent")


def self_hash():
    """This file's own sha256, printed in the report.

    HONESTLY, WHAT THIS BUYS. Not much on its own; anyone who edits the script can
    edit this function too. What it catches is the cheap case, a check quietly
    changed and the header line forgotten. The expensive-to-forge part of this
    report is not the hash: it is that the raw-file profile, the schema read out
    of the database, the queries actually run and the report's own numbers all
    have to agree with each other.
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


def report_lines(root, args, found, result):
    rows = score(result["checks"])
    auto = sum(r["earned"] for r in rows if r["who"] == "script")
    held = sum(r["held"] for r in rows)
    ta_group = next(r for r in rows if r["who"] == "your TA")
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    lines = [plain("Assignment 2 evidence", bold=True), plain("")]
    lines += [plain(t) for t in [
        f"{args.name or args.andrew_id} ({args.andrew_id})",
        f"generated {stamp} on {platform.platform()}",
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

    # The block a TA reads first: one line per group, and the number to record.
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
    for label, value in [("database", found["db"]), ("schema", found["schema"]),
                         ("loader", found["loader"]), ("queries", found["queries"]),
                         ("Parquet export", found["parquet"]), ("DuckDB", found["duck"]),
                         ("REPORT", found["report"]),
                         ("raw data.txt", (result["profile"] or {}).get("path"))]:
        shown = "none found"
        if value is not None:
            try:
                shown = str(Path(value).relative_to(root))
            except (ValueError, TypeError):
                shown = str(value)
        lines.append(plain(f"  {label:<15} {shown}"))
    live = result["live"]
    lines.append(plain(f"  {'':<15} " + (
        f"opened read-only, {live.get('size_mb', 0):,.0f} MB, "
        f"{live.get('counts', {}).get(live.get('fact_table'), 0):,} rows in "
        f"{live.get('fact_table')}" if live.get("opened") else "the database was NOT opened"),
        colour=GREY if live.get("opened") else AMBER))

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
                          (f"   [exit {step.code}, {step.seconds:.1f}s]", False,
                           BLACK if step.ok else RED)])
        lines.append(plain(""))
        lines += [plain(f"    {l}", colour=GREY)
                  for l in (trim(step.stdout) or "[no output]").splitlines()]

    sections = [(f"Schema: {found['schema']}", read(found["schema"]), True),
                (f"Loader: {found['loader']}", read(found["loader"]), True),
                (f"Queries: {found['queries']}", read(found["queries"]), True),
                (f"Parquet / DuckDB: {found['duck'] or found['parquet']}",
                 read(found["duck"] or found["parquet"]), True),
                (f"REPORT: {found['report']}", read(found["report"]), False)]
    for path in [p for p in found["sql_files"]
                 if p not in (found["schema"], found["queries"], found["loader"])][:3]:
        sections.append((f"Also: {path.relative_to(root)}", read(path), True))
    for title, body, code in sections:
        lines += [plain(""), plain(str(title), bold=True), plain("")]
        lines += highlight(body) if code else [plain(f"  {l}") for l in body.splitlines()]

    summary = {
        "andrew_id": args.andrew_id, "generated": stamp,
        "auto_score": round(auto, 2), "auto_of": AUTO_TOTAL,
        "report_points": ta_group["points"], "held_for_ta": round(held, 2),
        "assignment_total": TOTAL,
        "groups": {r["key"]: round(r["earned"], 2) for r in rows if r["who"] == "script"},
        "script_sha256": result["script_sha"],
        "raw_rows": (result["profile"] or {}).get("rows"),
        "fact_rows": live.get("counts", {}).get(live.get("fact_table")),
        "probe_uses_index": live.get("probe_uses_index"),
    }
    lines += [plain(""), plain("Summary line", bold=True), plain(""),
              plain("  The script hash should match the checksum published beside the script.",
                    colour=GREY),
              plain(""), plain(f"  {json.dumps(summary)}")]
    return lines, rows, auto, held


def main():
    parser = argparse.ArgumentParser(description="Build the Assignment 2 evidence PDF.")
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--db", default=None, help="your SQLite file; lab.db if omitted")
    parser.add_argument("--schema", default=None, help="path to your schema SQL")
    parser.add_argument("--queries", default=None, help="path to your queries SQL or notebook")
    parser.add_argument("--report", default=None, help="path to your REPORT.md")
    parser.add_argument("--raw", default=None, help="path to data.txt")
    parser.add_argument("--out", default="evidence.pdf")
    parser.add_argument("--html", action="store_true", help="also write evidence.html")
    args = parser.parse_args()

    root = Path.cwd()
    found = discover(root, args)
    if not any([found["schema"], found["queries"], found["report"], found["db"]]):
        raise SystemExit(f"Found no SQL, no database and no report in {root}. "
                         f"Run this from your A2 project root.")

    print(f"Building evidence for {args.andrew_id} in {root}")
    for label in ("db", "schema", "loader", "queries", "duck", "report"):
        print(f"  {label:<9} {found[label]}")

    steps = []
    result = collect(root, args, found, steps)
    result["script_sha"] = self_hash()
    lines, rows, auto, held = report_lines(root, args, found, result)

    pages = write_pdf(root / args.out, lines, f"A2 evidence, {args.andrew_id}")
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
