#!/usr/bin/env python3
"""Build the Assignment 1 evidence report.

Run this in the root of your project, the directory holding `pyproject.toml`:

    python3 a01-evidence.py --andrew-id yourid --name "Your Name"

It writes `evidence.html`. Open that in a browser, print it to PDF, and upload
the PDF to Canvas. That PDF is your submission, so read it before you send it.

WHAT IT DOES. It runs the commands in the assignment's Definition of done and
records what they actually printed, then embeds the files a grader needs to read:
your `.gitignore`, everything in `src/`, the code cells of your notebook, and
your README. Nothing is invented. If a command fails, the failure goes in the
report, which is better for you than a report that quietly omits it: a report
showing one broken command and five working ones is worth more marks than no
report at all.

It deletes `.venv` and rebuilds it with `uv sync`, because that rebuild is what
the first 30 points are for. That is the only destructive thing it does, and it
is the same thing the assignment asks you to do by hand at least once.

Standard library only, so it runs on the system Python without being installed
into your project. It shells out to `uv` and `git` for everything else.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT = 900  # seconds, per command; a cold uv cache can take a few minutes


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


def trim(text, head=14, tail=8):
    """Long output, shortened for print.

    `uv sync` lists every package it installed, which is 169 lines for this
    project and five pages of a PDF nobody reads. The count that matters and the
    lines either side of the elision are kept.
    """
    lines = text.splitlines()
    if len(lines) <= head + tail + 3:
        return text
    elided = len(lines) - head - tail
    return "\n".join(lines[:head] + [f"    [... {elided} lines elided ...]"] + lines[-tail:])


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "absent"


def self_hash():
    """This file's own sha256, printed in the report.

    HONESTLY, WHAT THIS BUYS. Not much on its own. Anyone who edits the script
    can also edit this function, and the hash is computed on the machine doing
    the editing. What it catches is the cheap case: a student who changes a
    command or a check and does not think about the header line. The published
    checksum sits next to the script on the course site, so a grader comparing
    one line spots that in a second.

    The expensive-to-forge part of this report is not the hash. It is the
    cross-checks below, which tie the transcript to the MLflow table, the
    notebook, and git, and which all have to agree.
    """
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()


def read(path, limit=20000):
    """File contents, truncated, or a note saying it is missing."""
    if not path.exists():
        return f"[{path} is not in this project]"
    text = path.read_text(errors="replace")
    return text if len(text) <= limit else text[:limit] + "\n[truncated]"


def notebook_code(path):
    """The notebook's code cells, with their execution counts.

    The execution counts are the interesting part. A notebook run top to bottom
    from a fresh kernel numbers its code cells 1, 2, 3 and so on. Any other
    pattern means the cells were run out of order, which is the hidden-state
    problem from Lecture 1.
    """
    if not path.exists():
        return f"[{path} is not in this project]", None

    nb = json.loads(path.read_text())
    counts, blocks = [], []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        count = cell.get("execution_count")
        counts.append(count)
        blocks.append(f"In [{count if count is not None else ' '}]:\n" + "".join(cell["source"]))
    in_order = counts == list(range(1, len(counts) + 1))
    return "\n\n".join(blocks), in_order


def collect(root, module, args):
    """Run every command the report is built from."""
    steps = []
    run("tool versions", ["uv", "--version"], root, steps)
    run("git version", ["git", "--version"], root, steps)

    venv = root / ".venv"
    if venv.exists():
        shutil.rmtree(venv)
    # --locked, not a bare sync. A bare `uv sync` silently WRITES a lockfile if
    # one is missing, so a project with no committed lockfile would rebuild
    # happily and the check it is supposed to fail would pass.
    run("rebuild the environment from the lockfile",
        ["uv", "sync", "--locked"], root, steps)

    run(
        "resolved versions",
        ["uv", "run", "python", "-c",
         "import sys, numpy, pandas, sklearn; "
         "print('python', sys.version.split()[0]); print('numpy', numpy.__version__); "
         "print('pandas', pandas.__version__); print('scikit-learn', sklearn.__version__)"],
        root, steps)

    first = run("run, seed 0", ["uv", "run", "python", "-m", module, "--seed", "0"], root, steps)
    again = run("run, seed 0 again", ["uv", "run", "python", "-m", module, "--seed", "0"], root, steps)
    other = run("run, seed 1", ["uv", "run", "python", "-m", module, "--seed", "1"], root, steps)

    tracked = run("tracked files", ["git", "ls-files"], root, steps)
    run("commits", ["git", "log", "--oneline", "-n", "15"], root, steps)
    status = run("working tree after the runs", ["git", "status", "--porcelain"], root, steps)

    run("MLflow runs",
        ["uv", "run", "python", "-c",
         "import mlflow; mlflow.set_tracking_uri('sqlite:///mlflow.db'); "
         "import pandas as pd; pd.set_option('display.width', 200); "
         "cols = ['run_id', 'params.seed', 'metrics.r2', 'start_time']; "
         "df = mlflow.search_runs(search_all_experiments=True).sort_values('start_time', ascending=False).head(10); "
         "print(df[[c for c in cols if c in df.columns]].to_string(index=False)) "
         "if len(df) else print('no runs found')"],
        root, steps)

    nb_source, nb_in_order = notebook_code(root / args.notebook)

    # This script and its output are not part of the project, so they must not
    # count against the clean-tree check. Otherwise running the tool is what
    # fails the check the tool is reporting on.
    ours = ("a01-evidence.py", "evidence.html", "evidence.pdf")
    dirty = [
        line for line in status.stdout.splitlines()
        if not any(line.strip().endswith(name) for name in ours)
    ]

    data_tracked = [
        line for line in tracked.stdout.splitlines()
        if line.lower().endswith((".csv", ".xlsx", ".zip", ".parquet"))
    ]

    # Does the R2 the CLI printed for seed 0 also appear in the MLflow table?
    # Two independent records of the same run, so a forged number has to be
    # forged in both places, consistently, in a format the student did not
    # choose. This is a better control than any hash of this file.
    printed = ""
    for token in first.stdout.replace(",", " ").split():
        try:
            value = float(token)
        except ValueError:
            continue
        if 0 <= value <= 1:
            printed = f"{value:.4f}"
            break
    logged = [
        line for line in steps[-1].stdout.splitlines()
        if printed and printed[:6] in line
    ]

    checks = [
        ("The environment rebuilds from the committed lockfile",
         steps[2].ok
         and "uv.lock" in tracked.stdout.split()
         and ".python-version" in tracked.stdout.split()),
        ("The same seed prints the same number twice",
         first.ok and first.stdout == again.stdout),
        ("A different seed prints a different number",
         other.ok and other.stdout != first.stdout),
        ("No data file is tracked by git", tracked.ok and not data_tracked),
        ("The working tree is clean after the runs", status.ok and not dirty),
        ("The notebook's cells ran in order from a fresh kernel", bool(nb_in_order)),
        ("The metric printed by the seed 0 run also appears in the MLflow table",
         bool(printed) and bool(logged)),
    ]

    return steps, checks, nb_source


def render(root, args, steps, checks, nb_source):
    """Write evidence.html."""
    def esc(text):
        return html.escape(str(text))

    def block(text):
        return f"<pre>{esc(text) if str(text).strip() else '[no output]'}</pre>"

    passed = sum(1 for _, ok in checks if ok)
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lock_hash = sha256(root / "uv.lock")
    head = next((s.stdout.splitlines()[0] for s in steps if s.label == "commits" and s.stdout), "")
    script_sha = self_hash()
    summary = {
        "andrew_id": args.andrew_id,
        "generated": stamp,
        "script_sha256": script_sha,
        "uv_lock_sha256": lock_hash,
        "head": head.split()[0] if head else None,
        "passed": passed,
        "of": len(checks),
        "failed": [label for label, ok in checks if not ok],
    }

    rows = "\n".join(
        f'<tr><td class="{"pass" if ok else "fail"}">{"PASS" if ok else "FAIL"}</td><td>{esc(label)}</td></tr>'
        for label, ok in checks
    )

    transcript = "\n".join(
        f'<section><h3>{esc(s.label)}</h3>'
        f'<p class="cmd">$ {esc(s.command)} <span class="meta">exit {s.code}, {s.seconds:.1f}s</span></p>'
        f'{block(trim(s.stdout))}</section>'
        for s in steps
    )

    sources = "\n".join(
        f"<section><h3>{esc(p.relative_to(root))}</h3>{block(read(p))}</section>"
        for p in sorted((root / 'src').rglob('*.py'))
    ) or "<p>No Python files found under <code>src/</code>.</p>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>A1 evidence, {esc(args.andrew_id)}</title>
<style>
  body {{ font: 11pt/1.45 -apple-system, Segoe UI, Roboto, sans-serif; max-width: 46rem;
         margin: 2rem auto; padding: 0 1rem; color: #111; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .2rem; }}
  h2 {{ font-size: 1.1rem; margin-top: 2rem; border-bottom: 2px solid #900; padding-bottom: .2rem; }}
  h3 {{ font-size: .95rem; margin: 1.1rem 0 .3rem; }}
  pre {{ background: #f6f6f6; border-left: 3px solid #ccc; padding: .5rem .7rem;
         font-size: 8.5pt; white-space: pre-wrap; word-break: break-word; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: .5rem; }}
  td, th {{ border: 1px solid #ddd; padding: .3rem .5rem; text-align: left; font-size: 10pt; }}
  td.pass {{ color: #060; font-weight: 700; width: 4rem; }}
  td.fail {{ color: #900; font-weight: 700; width: 4rem; }}
  .cmd {{ font-family: ui-monospace, Menlo, monospace; font-size: 9pt; margin: 0 0 .2rem; }}
  .meta {{ color: #666; font-weight: 400; }}
  .id {{ background: #f0f0f0; padding: .6rem .8rem; font-size: 10pt; }}
  section {{ break-inside: avoid; }}
  @media print {{ body {{ margin: 0; max-width: none; }} h2 {{ break-after: avoid; }} }}
</style></head><body>

<h1>Assignment 1 evidence</h1>
<div class="id">
  <strong>{esc(args.name or args.andrew_id)}</strong> ({esc(args.andrew_id)})<br>
  generated {esc(stamp)} on {esc(platform.platform())}<br>
  project <code>{esc(root.name)}</code>, uv.lock sha256 <code>{esc(lock_hash)}</code><br>
  HEAD <code>{esc(head) or 'no commits'}</code><br>
  evidence script sha256 <code>{esc(script_sha)}</code>
</div>

<h2>Definition of done, {passed} of {len(checks)}</h2>
<table><tr><th>Result</th><th>Check</th></tr>
{rows}
</table>
<p style="font-size:9pt;color:#555">Each line is decided from the output below, not asserted.</p>

<h2>Transcript</h2>
{transcript}

<h2>.gitignore</h2>
{block(read(root / '.gitignore'))}

<h2>pyproject.toml</h2>
{block(read(root / 'pyproject.toml'))}

<h2>The package</h2>
{sources}

<h2>Notebook code cells, {esc(args.notebook)}</h2>
{block(nb_source)}

<h2>README.md</h2>
{block(read(root / 'README.md'))}

<h2>Summary line</h2>
<p style="font-size:9pt;color:#555">One line holding what a grader sorts on. The script
hash should match the checksum published beside the script on the course site.</p>
{block(json.dumps(summary, indent=None))}

</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--andrew-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--module", default="sensorlab.train",
                        help="the entry point to run, default sensorlab.train")
    parser.add_argument("--notebook", default="notebooks/explore.ipynb")
    parser.add_argument("--out", default="evidence.html")
    args = parser.parse_args()

    root = Path.cwd()
    if not (root / "pyproject.toml").exists():
        sys.exit(f"No pyproject.toml in {root}. Run this from your project root.")

    print(f"Building evidence for {args.andrew_id} in {root}")
    steps, checks, nb_source = collect(root, args.module, args)
    (root / args.out).write_text(render(root, args, steps, checks, nb_source))

    passed = sum(1 for _, ok in checks if ok)
    print(f"\nWrote {args.out}: {passed} of {len(checks)} checks passed.")
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print("\nOpen it in a browser, print to PDF, and upload the PDF to Canvas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
