#!/usr/bin/env python3
"""What should be released next, and what releasing it will do.

The course ships one week at a time, and `tools/release_week.py` already knows how
to release a lecture. This works out *which* lecture, from the calendar and from
what is already live, so a weekly reminder can name it rather than leaving someone
to count sessions by hand.

    python3 tools/next_release.py                 # what is due before next Sunday
    python3 tools/next_release.py --today 2026-10-19
    python3 tools/next_release.py --format numbers   # "3 4", for a workflow
    python3 tools/next_release.py --format body      # markdown for an issue

Everything due on or before the end of the coming week and not yet released is
included, so a week that gets missed is picked up by the next run instead of
leaving a lecture behind forever.

No dependencies beyond the standard library and `release_week`, which is imported
rather than copied so the assignment and project maps cannot drift into a second
version of themselves.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_week import (  # noqa: E402  (path set above)
    LECTURE_ASSIGNMENTS,
    LECTURE_PROJECTS,
    REPO,
    TOC,
)

SCHEDULE = REPO / "course" / "schedule.md"

# "| Lecture 3: 08-31-2026 (Monday) | Databases for engineering data |"
SESSION = re.compile(r"Lecture\s+(\d+):\s*(\d{2}-\d{2}-\d{4})")

# The same expression tools/world.py uses for "released", deliberately. Two
# definitions of released is one too many: the absence of a leading # is the
# whole mechanism, and a second copy of it is a second thing to get wrong.
RELEASED = re.compile(r"^\s*-\s*file:\s*lectures/(l\d\d)/notes\b", re.M)


def sessions():
    """Every dated lecture in the schedule, as (number, date), in date order."""
    text = SCHEDULE.read_text(encoding="utf-8")
    out = [(int(n), dt.datetime.strptime(d, "%m-%d-%Y").date())
           for n, d in SESSION.findall(text)]
    if not out:
        sys.exit(f"no dated lectures found in {SCHEDULE}; has the table format changed?")
    return sorted(out, key=lambda t: t[1])


def released():
    """Lecture ids already live in _toc.yml."""
    return set(RELEASED.findall(TOC.read_text(encoding="utf-8")))


def has_content(n):
    """Some scheduled sessions have no lecture directory at all (L20, L22).

    release_week.py is a silent no-op for those, so naming them in a reminder
    would send someone looking for a bug that is not there.
    """
    return (REPO / "lectures" / f"l{n:02d}" / "notes.md").is_file()


def bank_note(n):
    """What the quiz bank will do when this lecture is released."""
    bank = REPO / "game" / "content" / f"l{n:02d}.yml"
    if not bank.is_file():
        return "no bank file"
    text = bank.read_text(encoding="utf-8")
    if re.search(r"^status:\s*published", text, re.M):
        return "already published"
    # Counting item ids avoids a yaml dependency for what is a one-line question.
    if not re.search(r"^\s*-\s*id:\s*l\d\d-q", text, re.M):
        return "stays held, no quiz written yet"
    return "will publish"


def due(today, horizon_days=None):
    """Lectures that should be live by the end of the coming week."""
    live = released()
    # Through Sunday of next week: everything a student could reach before the
    # next reminder fires.
    days_to_sunday = (6 - today.weekday()) % 7
    horizon = today + dt.timedelta(days=days_to_sunday + 7)
    return [(n, d) for n, d in sessions()
            if d <= horizon and f"l{n:02d}" not in live and has_content(n)], horizon


def semester(today):
    """First and last dated session, so the window is not a second hardcoded date."""
    all_dates = [d for _, d in sessions()]
    return min(all_dates), max(all_dates)


def body(items, today, horizon):
    """The issue text: what to run, and the things RELEASING.md does not say."""
    nums = [n for n, _ in items]
    first = min(nums)
    lines = [
        f"Releasing **{', '.join('L%d' % n for n in nums)}** covers every session "
        f"through Sunday {horizon:%b %-d}.",
        "",
        "| Lecture | Session | Also releases | Quiz bank |",
        "|---|---|---|---|",
    ]
    for n, d in items:
        extra = [a for a in LECTURE_ASSIGNMENTS.get(n, [])]
        extra += [p for p in LECTURE_PROJECTS.get(n, [])]
        lines.append(f"| L{n} | {d:%a %b %-d} | {', '.join(extra) or 'nothing'} "
                     f"| {bank_note(n)} |")

    cmds = "\n".join(f"python tools/release_week.py {n}" for n in nums)
    lines += [
        "",
        "## Do it",
        "",
        "```bash",
        f"git fetch origin && git checkout -b release-week-{first} origin/main",
        "",
        "# --check first if you want to see what it touches without changing anything",
        cmds,
        "",
        "# Verify locally the way CI will",
        "python game/validate.py",
        "python tools/world.py --check",
        "python tools/pool_archive.py --check",
        "jupyter-book build . --warningiserror",
        "",
        "git add -A && git commit -m 'Release "
        + ", ".join(f"Lecture {n}" for n in nums) + "'",
        f"git push -u origin release-week-{first}",
        "```",
        "",
        "## Worth knowing",
        "",
        "- **`git add -A` has to pick up `game/src/map/world.json`.** "
        "`release_week.py` regenerates it, and CI's `tools/world.py --check` fails "
        "the build if the regenerated map is not committed.",
        "- **A lecture with an empty quiz bank still releases**, notes, deck and all, "
        "and its map room opens with them. Only the practice module stays hidden, "
        "because the room follows `_toc.yml` and the module follows the bank's "
        "`status:`. Expect `left held: no quiz written yet` for L6, L8, L10, L12, "
        "L14 and L16.",
        "- **Never** set `only_build_toc_files: false` or add `course/modules` to "
        "`_toc.yml`. That setting is the only thing keeping unreleased lectures off "
        "guessable URLs (CLAUDE.md §1, §10).",
        "- To undo a release: re-comment its `_toc.yml` lines and any assignment line "
        "it uncommented, set the bank back to `status: unwritten`, and run "
        "`python tools/world.py --write`.",
        "",
        "Full procedure: "
        "[`RELEASING.md`](https://github.com/jkitchin/f26-06763/blob/main/RELEASING.md).",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--today", help="pretend it is this date, YYYY-MM-DD (for testing)")
    ap.add_argument("--format", choices=("human", "numbers", "body", "title"),
                    default="human")
    args = ap.parse_args()

    today = (dt.date.fromisoformat(args.today) if args.today
             else dt.datetime.now().date())
    starts, ends = semester(today)

    # Outside the semester there is nothing to release and nobody to remind.
    if today < starts - dt.timedelta(days=7) or today > ends:
        if args.format == "human":
            print(f"Outside the semester ({starts} to {ends}); nothing to release.")
        return 0

    items, horizon = due(today)
    if not items:
        if args.format == "human":
            print(f"Nothing due through {horizon}. Everything scheduled by then is "
                  f"already released.")
        return 0

    nums = [n for n, _ in items]
    if args.format == "numbers":
        print(" ".join(str(n) for n in nums))
    elif args.format == "title":
        print("Release " + ", ".join(f"L{n}" for n in nums)
              + f" for the week of {horizon - dt.timedelta(days=6):%b %-d}")
    elif args.format == "body":
        print(body(items, today, horizon))
    else:
        print(f"Semester {starts} to {ends}. Today {today}, horizon {horizon}.")
        for n, d in items:
            extra = LECTURE_ASSIGNMENTS.get(n, []) + LECTURE_PROJECTS.get(n, [])
            print(f"  L{n:<3} {d:%a %Y-%m-%d}  quiz: {bank_note(n):<26}"
                  f" also: {', '.join(extra) or '-'}")
        print("\n  python " + "\n  python ".join(
            f"tools/release_week.py {n}" for n in nums))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
