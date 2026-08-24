#!/usr/bin/env python3
"""Build the Assignment 1 evidence report.

Run this in the root of your project, the directory holding `pyproject.toml`:

    python3 a01-evidence.py --andrew-id yourid --name "Your Name"

It writes `evidence.pdf`. Upload that to Canvas. That PDF is your submission, so
read it before you send it.

WHAT IT DOES. It runs the commands in the assignment's Definition of done and
records what they actually printed, then embeds the files a grader needs to
read: your `.gitignore`, your `pyproject.toml`, your package, the code cells of
your notebook, and your README. Nothing is invented. If a command fails, the
failure goes in the report, which is better for you than a report that quietly
omits it: a report showing one broken command and five working ones is worth
more marks than no report at all.

It deletes `.venv` and rebuilds it with `uv sync --locked`, because that rebuild
is what the first 30 points are for. That is the only destructive thing it does,
and it is the same thing the assignment asks you to do by hand at least once.

NAMES. The assignment prescribes names (`sensorlab`, `src/sensorlab/train.py`,
`notebooks/explore.ipynb`, `README.md`, `sqlite:///mlflow.db`) and this script
looks for those first. It also goes looking when it does not find them, so a
project laid out sensibly under different names still produces a report rather
than a page of failures. What it found is printed at the top of the report, and
every guess can be overridden with --module, --notebook or --tracking-uri. If
the header says it used something you did not intend, pass the flag and run it
again.

The PDF is written here, with no browser and no LaTeX and nothing to install, so
every submission arrives in the same shape and there is no print dialog to get
wrong.

Standard library only, so it runs on the system Python without being installed
into your project. It shells out to `uv` and `git` for everything else.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT = 900  # seconds, per command; a cold uv cache can take a few minutes
SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ipynb_checkpoints",
             "build", "dist", ".pytest_cache", "mlruns", "site-packages"}
DATA_SUFFIXES = (".csv", ".tsv", ".xlsx", ".xls", ".zip", ".parquet", ".data",
                 ".gz", ".h5", ".nc", ".sqlite")
BIG_FILE = 1_000_000  # a tracked file this large is data by any other name
OURS = ("a01-evidence.py", "evidence.html", "evidence.pdf")
# Finder and Explorer leave these behind in any directory a student opens.
# They say nothing about the submission, and failing the clean-tree check
# over one would be a mark deducted for using a Mac.
OS_JUNK = {".DS_Store", "Thumbs.db", "desktop.ini", ".Spotlight-V100", ".Trashes"}


class Step:
    """One recorded command: what was run, what came back, how long it took."""

    def __init__(self, label, command, stdout, code, seconds):
        self.label = label
        self.command = command
        self.stdout = stdout
        self.code = code
        self.seconds = seconds

    @property
    def ok(self):
        return self.code == 0


def run(label, command, cwd, steps):
    """Run one command, record it, and return the Step."""
    print(f"  {label} ...", flush=True)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        # uv's VIRTUAL_ENV warning fires for anyone who happens to have another
        # environment active. It says nothing about the submission.
        out = "\n".join(
            line for line in out.splitlines()
            if "VIRTUAL_ENV" not in line and "use `--active`" not in line
        )
        code = proc.returncode
    except FileNotFoundError:
        out, code = f"{command[0]}: not found on PATH", 127
    except subprocess.TimeoutExpired:
        out, code = f"timed out after {TIMEOUT}s", 124
    # A python -c one-liner is unreadable as a command line, so show its head.
    shown = " ".join(command)
    if "-c" in command:
        shown = " ".join(command[:command.index("-c") + 1]) + ' "..."'
    step = Step(label, shown, out.strip(), code, time.monotonic() - start)
    steps.append(step)
    return step


# ------------------------------------------------------------------ discovery


def _usable(path):
    return not any(part in SKIP_DIRS for part in Path(path).parts)


def find_module(root, given=None):
    """The module to run with `python -m`, and the package directory it is in.

    src/<pkg>/ first, because that is what the assignment asks for, then a
    package beside pyproject.toml so a flat layout still reports. Within the
    package, train.py wins, then any module that both parses arguments and has a
    main, since that is what an entry point looks like from the outside.
    """
    packages = [p.parent for p in sorted(root.glob("src/*/__init__.py")) if _usable(p)]
    packages += [p.parent for p in sorted(root.glob("*/__init__.py")) if _usable(p)]
    package = packages[0] if packages else None
    if given or package is None:
        return given, package

    modules = [m for m in sorted(package.glob("*.py")) if m.stem != "__init__"]
    entry = next((m for m in modules if m.stem == "train"), None)
    if entry is None:
        for candidate in modules:
            text = candidate.read_text(errors="replace")
            if "argparse" in text and "def main" in text:
                entry = candidate
                break
    if entry is None:
        return package.name, package
    return f"{package.name}.{entry.stem}", package


def find_notebook(root, given=None):
    """The exploratory notebook: the prescribed path first, then anything plausible."""
    if given and (root / given).exists():
        return root / given
    prescribed = root / "notebooks" / "explore.ipynb"
    if prescribed.exists():
        return prescribed
    found = [p for p in sorted(root.rglob("*.ipynb")) if _usable(p)]
    if not found:
        return None
    # Under notebooks/ first, then the largest, which is the exploratory one
    # rather than somebody's scratch file.
    found.sort(key=lambda p: (0 if p.parent.name == "notebooks" else 1, -p.stat().st_size))
    return found[0]


def find_readme(root):
    """README.md, readme.md, README.rst, README.txt, or plain README."""
    for candidate in sorted(root.glob("*")):
        if candidate.is_file() and candidate.stem.lower() == "readme":
            return candidate
    return None


def find_tracking_uri(root, given=None):
    """Where MLflow put the runs.

    The assignment prescribes sqlite:///mlflow.db. A student who used the file
    store instead still has runs worth showing, and reporting "no runs found"
    for a project that logged them correctly would cost ten points over a path
    this script guessed rather than anything they did.
    """
    if given:
        return given

    # Newest wins, not the prescribed name. Called after the runs, the store
    # they just wrote to is the one with the newest mtime, so a leftover
    # mlflow.db from an earlier attempt cannot send the search to an empty
    # database while the real runs sit in the file beside it.
    candidates = [(p.stat().st_mtime, f"sqlite:///{p.name}")
                  for p in root.glob("*.db") if _usable(p) and p.is_file()]
    mlruns = root / "mlruns"
    if mlruns.is_dir():
        candidates.append((mlruns.stat().st_mtime, "file:./mlruns"))
    if candidates:
        return max(candidates)[1]
    return "sqlite:///mlflow.db"


# -------------------------------------------------------------------- reading


def sha256(path):
    path = Path(path) if path else None
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path and path.exists() else "absent"


def self_hash():
    """This file's own sha256, printed in the report.

    HONESTLY, WHAT THIS BUYS. Not much on its own. Anyone who edits the script
    can also edit this function, and the hash is computed on the machine doing
    the editing. What it catches is the cheap case: a student who changes a
    command or a check and does not think about the header line. The published
    checksum sits beside the script on the course site, so a grader comparing
    one line spots that in a second.

    The expensive-to-forge part of this report is not the hash. It is the
    cross-checks, which tie the transcript to the MLflow table, the notebook and
    git, and which all have to agree with each other.
    """
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def read(path, limit=20000):
    """File contents, truncated, or a note saying it is missing."""
    if path is None or not Path(path).exists():
        return f"[{path} is not in this project]"
    text = Path(path).read_text(errors="replace")
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def trim(text, head=14, tail=8):
    """Long output, shortened for print.

    `uv sync` lists every package it installed, which is 169 lines for this
    project and pages of a PDF nobody reads. The count that matters and the
    lines either side of the elision are kept.
    """
    lines = text.splitlines()
    if len(lines) <= head + tail + 3:
        return text
    elided = len(lines) - head - tail
    return "\n".join(lines[:head] + [f"    [... {elided} lines elided ...]"] + lines[-tail:])


def numbers(text):
    """Every decimal number in some output, rounded, as a set.

    Comparing numbers rather than whole strings is what lets the determinism
    check survive a student who prints a run id or a timestamp beside the
    metric. Comparing whole strings called those submissions non-deterministic,
    which they were not.
    """
    return {f"{float(t):.4f}" for t in re.findall(r"-?\d+\.\d{2,}", text)}


def notebook_code(path):
    """The notebook's code cells, with their execution counts.

    The execution counts are the interesting part. A notebook run top to bottom
    from a fresh kernel numbers its code cells 1, 2, 3 and so on. Any other
    pattern means the cells were run out of order, which is the hidden-state
    problem from Lecture 1.
    """
    if path is None or not Path(path).exists():
        return "[no notebook found in this project]", None
    try:
        cells = json.loads(Path(path).read_text(errors="replace"))["cells"]
    except (ValueError, KeyError, TypeError):
        return f"[{path} is not readable as a notebook]", None

    counts, blocks = [], []
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        count = cell.get("execution_count")
        counts.append(count)
        blocks.append(f"In [{count if count is not None else ' '}]:\n"
                      + "".join(cell.get("source", [])))
    if not counts:
        return "[the notebook has no code cells]", None
    return "\n\n".join(blocks), counts == list(range(1, len(counts) + 1))


def package_source(root, package):
    """Every .py in the student's package, plus any scripts/ they wrote."""
    if package is None:
        return "[no package directory found]"
    files = [p for p in sorted((root / package).rglob("*.py")) if _usable(p)]
    files += [p for p in sorted(root.glob("scripts/*.py")) if _usable(p)]
    if not files:
        return f"[no Python files under {package}]"
    return "\n\n".join(f"--- {p.relative_to(root)}\n{read(p, limit=12000)}" for p in files)


# ----------------------------------------------------------------- collection


def collect(root, found):
    """Run every command the report is built from."""
    steps = []
    run("tool versions", ["uv", "--version"], root, steps)
    run("git version", ["git", "--version"], root, steps)

    venv = root / ".venv"
    if venv.exists():
        shutil.rmtree(venv)
    # --locked, not a bare sync. A bare `uv sync` silently WRITES a lockfile if
    # one is missing, so a project with no committed lockfile would rebuild
    # happily and the check that is supposed to fail would pass.
    rebuild = run("rebuild the environment from the lockfile",
                  ["uv", "sync", "--locked"], root, steps)
    if not rebuild.ok:
        # --locked fails when the lockfile is missing OR merely out of date with
        # pyproject.toml, which is one mistake. Without a fallback it also takes
        # the runs, both determinism checks and the cross-check down with it, so
        # one mistake would cost 70 points instead of 30. Sync anyway, and let
        # the lockfile check stay failed on its own.
        run("lockfile rejected, so rebuilding without --locked to continue",
            ["uv", "sync"], root, steps)

    run("resolved versions",
        ["uv", "run", "python", "-c",
         "import sys\n"
         "print('python', sys.version.split()[0])\n"
         "for name in ('numpy', 'pandas', 'sklearn', 'mlflow'):\n"
         "    try:\n"
         "        print(name, __import__(name).__version__)\n"
         "    except Exception as exc:\n"
         "        print(name, 'not importable:', exc)"],
        root, steps)

    module = found["module"]
    blank = Step("run", "", "no entry point found, so the runs were skipped", 1, 0.0)
    first = again = other = blank
    if module:
        first = run("run, seed 0", ["uv", "run", "python", "-m", module, "--seed", "0"], root, steps)
        again = run("run, seed 0 again", ["uv", "run", "python", "-m", module, "--seed", "0"], root, steps)
        other = run("run, seed 1", ["uv", "run", "python", "-m", module, "--seed", "1"], root, steps)
    else:
        steps.append(blank)

    tracked = run("tracked files", ["git", "ls-files"], root, steps)
    run("commits", ["git", "log", "--oneline", "-n", "15"], root, steps)
    status = run("working tree after the runs", ["git", "status", "--porcelain"], root, steps)

    # Detected here rather than before the runs: a file store does not exist
    # until something has been logged to it, so detecting up front sent a
    # perfectly good project to the wrong place and reported "no runs found".
    if not found.get("tracking_given"):
        found["tracking_uri"] = find_tracking_uri(root)

    mlflow_step = run(
        "MLflow runs",
        ["uv", "run", "python", "-c",
         "import mlflow, pandas as pd\n"
         f"mlflow.set_tracking_uri({found['tracking_uri']!r})\n"
         "pd.set_option('display.width', 200)\n"
         "df = mlflow.search_runs(search_all_experiments=True)\n"
         "if len(df):\n"
         "    df = df.sort_values('start_time', ascending=False).head(10)\n"
         "    cols = [c for c in ['run_id', 'params.seed', 'metrics.r2', 'start_time'] if c in df.columns]\n"
         "    cols += [c for c in df.columns if c.startswith('metrics.') and c not in cols][:2]\n"
         "    print(df[cols].to_string(index=False))\n"
         "else:\n"
         "    print('no runs found')"],
        root, steps)

    nb_source, nb_in_order = notebook_code(found["notebook_path"])

    # This script and its own output are not part of the project, so they must
    # not count against the clean-tree check. Otherwise running the tool is what
    # fails the check the tool is reporting on.
    def is_noise(line):
        name = line.strip().split("/")[-1].split()[-1]
        return name in OS_JUNK or any(line.strip().endswith(ours) for ours in OURS)

    dirty = [line for line in status.stdout.splitlines() if not is_noise(line)]
    junk = [line for line in status.stdout.splitlines()
            if line.strip().split("/")[-1].split()[-1] in OS_JUNK]

    tracked_files = tracked.stdout.split()
    data_tracked = [f for f in tracked_files if f.lower().endswith(DATA_SUFFIXES)]
    # A renamed data file has no telling suffix, so size is the other tell.
    for name in tracked_files:
        path = root / name
        if name not in data_tracked and path.is_file() and path.stat().st_size > BIG_FILE:
            data_tracked.append(f"{name} ({path.stat().st_size // 1000} kB)")

    # Do the numbers the seed 0 run printed turn up again in the MLflow table?
    # Two independent records of one run, so a forged number has to be forged in
    # both places, consistently, in a format the student did not choose. That is
    # a better control than any hash of this file.
    printed = numbers(first.stdout)
    logged = numbers(mlflow_step.stdout)

    checks = [
        ("The environment rebuilds from the committed lockfile",
         rebuild.ok and "uv.lock" in tracked_files and ".python-version" in tracked_files),
        ("The same seed prints the same number twice",
         first.ok and again.ok and bool(printed) and printed == numbers(again.stdout)),
        ("A different seed prints a different number",
         other.ok and bool(printed) and numbers(other.stdout) != printed),
        ("No data file is tracked by git", tracked.ok and not data_tracked),
        ("The working tree is clean after the runs", status.ok and not dirty),
        ("The notebook's cells ran in order from a fresh kernel", bool(nb_in_order)),
        ("The metric printed by the seed 0 run also appears in the MLflow table",
         bool(printed & logged)),
    ]

    notes = []
    if data_tracked:
        notes.append("tracked data files: " + ", ".join(data_tracked[:5]))
    if dirty:
        notes.append("uncommitted: " + ", ".join(line.strip() for line in dirty[:5]))
    if junk:
        notes.append("ignored as OS clutter, not counted against you: "
                     + ", ".join(line.strip() for line in junk[:3]))
    return steps, checks, nb_source, notes


# ----------------------------------------------------------------- PDF output


def escape_pdf(text):
    out = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return out.encode("latin-1", "replace").decode("latin-1")


def write_pdf(path, lines, title):
    """Write a paginated monospace PDF. No dependency, no browser, no LaTeX.

    Doing it here rather than telling students to print an HTML page means every
    submission arrives in the same shape: same font, same margins, nothing
    scaled to 60 percent and nothing cut off at the right edge because a print
    dialog defaulted to A4. `lines` is a list of (text, bold) pairs.
    """
    width, height = 612, 792
    left, top, bottom, size, leading = 42, 748, 60, 8, 10.2
    max_chars = int((width - 2 * left) / (size * 0.6))
    rows = int((top - bottom) / leading)

    wrapped = []
    for text, bold in lines:
        text = text.replace("\t", "    ").rstrip()
        if not text:
            wrapped.append(("", bold))
            continue
        while len(text) > max_chars:
            cut = text.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            wrapped.append((text[:cut], bold))
            text = "    " + text[cut:].lstrip()
        wrapped.append((text, bold))

    pages = [wrapped[i:i + rows] for i in range(0, len(wrapped), rows)] or [[]]

    streams = []
    for number, page in enumerate(pages, start=1):
        parts = [f"BT /F1 {size} Tf {left} {top} Td {leading} TL"]
        current = "F1"
        for text, bold in page:
            want = "F2" if bold else "F1"
            if want != current:
                parts.append(f"/{want} {size} Tf")
                current = want
            parts.append(f"({escape_pdf(text)}) Tj T*")
        parts.append("ET")
        footer = f"{title}   page {number} of {len(pages)}"
        parts.append(f"BT /F1 7 Tf {left} {bottom - 20} Td ({escape_pdf(footer)}) Tj ET")
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
    out += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    Path(path).write_bytes(bytes(out))
    return len(pages)


def write_html(path, lines):
    """The same report as a page, for reading on screen while you fix things."""
    body = []
    for text, bold in lines:
        if not text.strip():
            body.append("<br>")
        elif bold:
            body.append(f"<h2>{html.escape(text)}</h2>")
        else:
            body.append(f"<pre>{html.escape(text)}</pre>")
    Path(path).write_text(
        "<!doctype html><meta charset='utf-8'><title>A1 evidence</title>"
        "<style>body{font:11pt/1.4 ui-monospace,Menlo,monospace;max-width:60rem;"
        "margin:2rem auto;padding:0 1rem}pre{margin:0;white-space:pre-wrap}"
        "h2{font-size:1rem;margin:1.2rem 0 .4rem;border-bottom:2px solid #900}"
        "br{line-height:.6}</style>\n" + "\n".join(body))


def report_lines(root, args, found, steps, checks, nb_source, notes):
    """The whole report as (text, bold) pairs, which the PDF and HTML share."""
    passed = sum(1 for _, ok in checks if ok)
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    head = next((s.stdout.splitlines()[0] for s in steps
                 if s.label == "commits" and s.stdout), "")

    lines = [("Assignment 1 evidence", True), ("", False)]
    lines += [(text, False) for text in [
        f"{args.name or args.andrew_id} ({args.andrew_id})",
        f"generated {stamp} on {platform.platform()}",
        f"project {root.name}, uv.lock sha256 {sha256(root / 'uv.lock')}",
        f"HEAD {head or 'no commits'}",
        f"evidence script sha256 {found['script_sha']}",
    ]]

    lines += [("", False), ("What this script found", True), ("", False)]
    for label, value in [
        ("entry point", found["module"] or "none found, so the runs were skipped"),
        ("package", found["package"] or "none found"),
        ("notebook", found["notebook"] or "none found"),
        ("README", found["readme"] or "none found"),
        ("MLflow store", found["tracking_uri"]),
    ]:
        lines.append((f"  {label:<13} {value}", False))

    lines += [("", False), (f"Definition of done, {passed} of {len(checks)}", True), ("", False)]
    lines += [(f"  [{'PASS' if ok else 'FAIL'}]  {label}", False) for label, ok in checks]
    if notes:
        lines.append(("", False))
        lines += [(f"  note: {note}", False) for note in notes]
    lines += [("", False),
              ("  Each line is decided from the output below, not asserted.", False)]

    lines += [("", False), ("Transcript", True)]
    for step in steps:
        lines += [("", False), (f"  {step.label}", True),
                  (f"  $ {step.command}   [exit {step.code}, {step.seconds:.1f}s]", False),
                  ("", False)]
        lines += [(f"    {line}", False)
                  for line in (trim(step.stdout) or "[no output]").splitlines()]

    for title, body in [
        (".gitignore", read(root / ".gitignore")),
        ("pyproject.toml", read(root / "pyproject.toml")),
        ("The package", package_source(root, found["package"])),
        (f"Notebook code cells: {found['notebook'] or 'none'}", nb_source),
        (f"README: {found['readme'] or 'none'}", read(found["readme_path"])),
    ]:
        lines += [("", False), (title, True), ("", False)]
        lines += [(f"  {line}", False) for line in body.splitlines()]

    summary = {
        "andrew_id": args.andrew_id,
        "generated": stamp,
        "script_sha256": found["script_sha"],
        "uv_lock_sha256": sha256(root / "uv.lock"),
        "head": head.split()[0] if head else None,
        "module": found["module"],
        "passed": passed,
        "of": len(checks),
        "failed": [label for label, ok in checks if not ok],
    }
    lines += [("", False), ("Summary line", True), ("", False),
              ("  The script hash should match the checksum published beside the script.", False),
              ("", False), (f"  {json.dumps(summary)}", False)]
    return lines, passed


def main():
    parser = argparse.ArgumentParser(description="Build the Assignment 1 evidence PDF.")
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--module", default=None,
                        help="entry point, e.g. sensorlab.train; found automatically if omitted")
    parser.add_argument("--notebook", default=None,
                        help="path to your notebook; found automatically if omitted")
    parser.add_argument("--tracking-uri", default=None,
                        help="MLflow store, e.g. sqlite:///mlflow.db; found automatically if omitted")
    parser.add_argument("--out", default="evidence.pdf")
    parser.add_argument("--html", action="store_true", help="also write evidence.html")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "pyproject.toml").exists():
        sys.exit(f"No pyproject.toml in {root}. Run this from your project root.")

    module, package = find_module(root, args.module)
    notebook = find_notebook(root, args.notebook)
    readme = find_readme(root)
    found = {
        "module": module,
        "package": str(package.relative_to(root)) if package else None,
        "notebook": str(notebook.relative_to(root)) if notebook else None,
        "notebook_path": notebook,
        "readme": str(readme.relative_to(root)) if readme else None,
        "readme_path": readme,
        "tracking_uri": args.tracking_uri or find_tracking_uri(root),
        "tracking_given": bool(args.tracking_uri),
        "script_sha": self_hash(),
    }

    print(f"Building evidence for {args.andrew_id} in {root}")
    print(f"  entry point: {found['module']}")
    print(f"  notebook:    {found['notebook']}")
    print(f"  MLflow:      {found['tracking_uri']}")

    steps, checks, nb_source, notes = collect(root, found)
    lines, passed = report_lines(root, args, found, steps, checks, nb_source, notes)

    pages = write_pdf(root / args.out, lines, f"A1 evidence, {args.andrew_id}")
    if args.html:
        write_html(root / "evidence.html", lines)

    print(f"\nWrote {args.out}, {pages} pages: {passed} of {len(checks)} checks passed.")
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if passed < len(checks):
        print("\nA failing check is a reason to fix it and run this again, "
              "not a reason to skip the submission.")
    print(f"\nUpload {args.out} to Canvas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
