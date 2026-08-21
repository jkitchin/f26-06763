#!/usr/bin/env python3
"""Release one lecture for its week.

    python tools/release_week.py 3            # release Lecture 3
    python tools/release_week.py 3 --check    # show what it would do, change nothing

The course ships one week at a time. Every lecture is written and lives on main
from the start, but stays hidden until its week:

  * commented out of _toc.yml, so its notes are not built and (because the slide
    job reads _toc.yml) its deck is not rendered either;
  * its quiz bank marked `status: unwritten`, so the game hides it and its room
    on the map is shuttered;
  * the assignment released that week (if any) commented out of _toc.yml too,
    from the schedule's "Assignment N released" markers.

Releasing flips them all back on and regenerates the map. Nothing here commits or
pushes: run it on a fresh branch, look at the diff, open a PR, merge. That PR is
the weekly review gate.

    git checkout -b release-week-3 main
    python tools/release_week.py 3
    # review, then open a PR and merge into main
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
TOC = REPO / "_toc.yml"

#: Which assignment is released with which lecture, from course/schedule.md's
#: "Assignment N released" markers. The mini-project (A7) launches at L13 and
#: lives in the Projects part, so it is not listed here. A lecture with no entry
#: releases no assignment that week.
LECTURE_ASSIGNMENTS = {
    1: ["a01"], 3: ["a02"], 5: ["a03"], 7: ["a04"], 9: ["a05"],
    11: ["a06"], 15: ["a08"], 17: ["a09"], 20: ["a10"], 22: ["a11"],
}


def toc_release(nn: str, apply: bool) -> str:
    """Uncomment lecture lNN's three lines (notes, sections:, notebook) in _toc.yml."""
    lines = TOC.read_text(encoding="utf-8").split("\n")
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^#\s*-\s*file:\s*lectures/l{nn}/notes\b", line):
            start = i
            break
    if start is None:
        for line in lines:
            if re.match(rf"^\s*-\s*file:\s*lectures/l{nn}/notes\b", line):
                return "already released"
        return "not found in _toc.yml"
    if apply:
        for j in (start, start + 1, start + 2):
            if j < len(lines) and lines[j].lstrip().startswith("#"):
                lines[j] = lines[j].replace("# ", "", 1)
        TOC.write_text("\n".join(lines), encoding="utf-8")
    return "released"


def bank_release(lec: str, apply: bool) -> str:
    """Flip lecture lNN's quiz bank from held (unwritten) to published, if it has items."""
    f = REPO / "game" / "content" / f"{lec}.yml"
    if not f.is_file():
        return "no bank file"
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    status = doc.get("status")
    items = doc.get("items") or []
    if status == "published":
        return "already published"
    if not items:
        return "left held: no quiz written yet (notes release without a quiz)"
    if apply:
        t = f.read_text(encoding="utf-8")
        t = re.sub(r"^status:\s*unwritten", "status: published", t, count=1, flags=re.M)
        f.write_text(t, encoding="utf-8")
    return "published"


def assignment_release(lecture: int, apply: bool) -> str:
    """Uncomment the assignment(s) released with this lecture in _toc.yml."""
    aids = LECTURE_ASSIGNMENTS.get(lecture, [])
    if not aids:
        return "none this lecture"
    lines = TOC.read_text(encoding="utf-8").split("\n")
    out = []
    for aid in aids:
        done = None
        for i, line in enumerate(lines):
            if re.match(rf"^#\s*-\s*file:\s*course/assignments/{aid}\b", line):
                if apply:
                    lines[i] = lines[i].replace("# ", "", 1)
                done = f"{aid} released"
                break
            if re.match(rf"^\s*-\s*file:\s*course/assignments/{aid}\b", line):
                done = f"{aid} already released"
                break
        out.append(done or f"{aid} not found in _toc.yml")
    if apply:
        TOC.write_text("\n".join(lines), encoding="utf-8")
    return ", ".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lecture", type=int, help="lecture number to release, e.g. 3")
    ap.add_argument("--check", action="store_true",
                    help="show what would happen without changing anything")
    args = ap.parse_args()

    nn = f"{args.lecture:02d}"
    lec = f"l{nn}"
    apply = not args.check
    verb = "Would release" if args.check else "Releasing"
    print(f"{verb} {lec}:")

    toc = toc_release(nn, apply)
    print(f"  _toc.yml:  {toc}")
    bank = bank_release(lec, apply)
    print(f"  quiz bank: {bank}")
    asg = assignment_release(args.lecture, apply)
    print(f"  assignment: {asg}")

    if apply and toc == "released":
        print("  regenerating the course map ...")
        subprocess.run([sys.executable, str(REPO / "tools" / "world.py"), "--write"],
                       check=True)

    if args.check:
        print("\n(--check: nothing was changed)")
    else:
        print("\nNext: review the diff, then commit on your release branch and open a PR.")
        print("Verify before pushing:")
        print("  python game/validate.py && python tools/world.py --check && "
              "python tools/pool_archive.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
