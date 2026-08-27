#!/usr/bin/env python3
"""Which lecture should be released next, and what releasing it will do.

The course ships one lecture at a time, and `tools/release_lecture.py` already
knows how to release one. This works out *which* one, from the calendar and from
what is already live, so a reminder can name it rather than leaving someone to
count sessions by hand.

    python3 tools/next_release.py                  # what is due, and what is behind it
    python3 tools/next_release.py --today 2026-10-19
    python3 tools/next_release.py --format number  # "3", for a workflow
    python3 tools/next_release.py --format body    # markdown for an issue
    python3 tools/next_release.py --lecture 3      # this one, calendar or not

Exactly one lecture comes back, the earliest unreleased one whose session falls
inside the horizon. Two properties follow from picking the earliest rather than
the nearest, and both are deliberate:

  * a lecture that gets missed is picked up by the next run instead of being left
    behind forever, because it stays the earliest unreleased one until it ships;
  * releases stay in lecture order, which is what keeps the build green. A
    released lecture may cross-reference an earlier one, so L4 cannot go public
    before L3, and a run that finds L3 still unreleased will not skip ahead to it.

`--lecture` names one directly, for releasing ahead of the calendar or catching up
out of band. It skips the horizon, so it is the one path that can release early; it
still refuses a lecture that is already live or has no notes.

No dependencies beyond the standard library and `release_lecture`, which is
imported rather than copied so the assignment and project maps cannot drift into
a second version of themselves.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_lecture import (  # noqa: E402  (path set above)
    LECTURE_ASSIGNMENTS,
    LECTURE_PROJECTS,
    REPO,
    TOC,
)

SCHEDULE = REPO / "course" / "schedule.md"

# "| Lecture 3: 08-31-2026 (Monday) | Databases for engineering data |"
SESSION = re.compile(r"Lecture\s+(\d+):\s*(\d{2}-\d{2}-\d{4})[^|]*\|\s*(.*?)\s*\|")

# The same expression tools/world.py uses for "released", deliberately. Two
# definitions of released is one too many: the absence of a leading # is the
# whole mechanism, and a second copy of it is a second thing to get wrong.
RELEASED = re.compile(r"^\s*-\s*file:\s*lectures/(l\d\d)/notes\b", re.M)

#: How far ahead to look. The reminder fires twice a week, two lecture days
#: ahead of each session, so a week covers both the Wednesday run reaching the
#: following Monday's lecture and the Monday run reaching Wednesday's.
HORIZON_DAYS = 7


def sessions():
    """Every dated lecture in the schedule, as (number, date, topic), in date order."""
    text = SCHEDULE.read_text(encoding="utf-8")
    out = [(int(n), dt.datetime.strptime(d, "%m-%d-%Y").date(), topic)
           for n, d, topic in SESSION.findall(text)]
    if not out:
        sys.exit(f"no dated lectures found in {SCHEDULE}; has the table format changed?")
    return sorted(out, key=lambda t: t[1])


def released():
    """Lecture ids already live in _toc.yml."""
    return set(RELEASED.findall(TOC.read_text(encoding="utf-8")))


def has_content(n):
    """Some scheduled sessions have no lecture directory at all (L20, L22).

    release_lecture.py is a silent no-op for those, so naming them in a reminder
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


def pending():
    """Every unreleased lecture that has content, earliest session first."""
    live = released()
    return [s for s in sessions()
            if f"l{s[0]:02d}" not in live and has_content(s[0])]


def due(today, horizon_days=HORIZON_DAYS):
    """The one lecture to release now, the queue behind it, and the horizon.

    The earliest unreleased lecture, and only if its session is inside the
    horizon. Taking the earliest rather than the nearest is what keeps releases
    in lecture order when one has been missed.
    """
    horizon = today + dt.timedelta(days=horizon_days)
    queue = pending()
    if not queue or queue[0][1] > horizon:
        return None, queue, horizon
    return queue[0], queue[1:], horizon


def extras(n):
    """The assignment and project slugs that ride along with this lecture."""
    return LECTURE_ASSIGNMENTS.get(n, []) + LECTURE_PROJECTS.get(n, [])


def semester(today):
    """First and last dated session, so the window is not a second hardcoded date."""
    all_dates = [d for _, d, _ in sessions()]
    return min(all_dates), max(all_dates)


def body(item, queue, today, horizon):
    """The issue text: what to run, and the things RELEASING.md does not say."""
    n, date, topic = item
    nn = f"{n:02d}"
    also = ", ".join(extras(n)) or "nothing"
    lines = [
        f"**L{n}: {topic}** meets {date:%A %b %-d}, inside the horizon through "
        f"{horizon:%b %-d}. Releasing it publishes its notes, its deck, its map "
        f"room and (below) its quiz.",
        "",
        "| Lecture | Session | Also releases | Quiz bank |",
        "|---|---|---|---|",
        f"| L{n} | {date:%a %b %-d} | {also} | {bank_note(n)} |",
        "",
        "## Do it",
        "",
        "```bash",
        f"git fetch origin && git checkout -b release-l{nn} origin/main",
        "",
        "# --check first if you want to see what it touches without changing anything",
        f"python tools/release_lecture.py {n}",
        "",
        "# Verify locally the way CI will",
        "python game/validate.py",
        "python tools/world.py --check",
        "python tools/pool_archive.py --check",
        "jupyter-book build . --warningiserror",
        "",
        f"git add -A && git commit -m 'Release Lecture {n}'",
        f"git push -u origin release-l{nn}",
        "```",
        "",
    ]
    if queue:
        nxt = ", ".join(f"L{m} ({d:%b %-d})" for m, d, _ in queue[:3])
        lines += [
            f"Behind it: {nxt}. Each gets its own pull request, and the next "
            "reminder will not name one until this one is merged, because a "
            "lecture that cross-references L"
            f"{n} cannot build before L{n} is public.",
            "",
        ]
    lines += [
        "## Worth knowing",
        "",
        "- **`git add -A` has to pick up `game/src/map/world.json`.** "
        "`release_lecture.py` regenerates it, and CI's `tools/world.py --check` "
        "fails the build if the regenerated map is not committed.",
        "- **A lecture with an empty quiz bank still releases**, notes, deck and all, "
        "and its map room opens with them. Only the practice module stays hidden, "
        "because the room follows `_toc.yml` and the module follows the bank's "
        "`status:`. Expect `stays held, no quiz written yet` for L6, L8, L10, L12, "
        "L14 and L16; re-run `release_lecture.py` for that lecture once its bank "
        "is written.",
        "- **Never** set `only_build_toc_files: false` or add `course/modules` to "
        "`_toc.yml`. That setting is the only thing keeping unreleased lectures off "
        "guessable URLs (CLAUDE.md sections 1 and 10).",
        "- To undo a release: re-comment its `_toc.yml` lines and any assignment line "
        "it uncommented, set the bank back to `status: unwritten`, and run "
        "`python tools/world.py --write`.",
        "",
        "Full procedure: "
        "[`RELEASING.md`](https://github.com/jkitchin/f26-06763/blob/main/RELEASING.md).",
    ]
    return "\n".join(lines)


def report(fmt, item, queue, today, horizon):
    """Print one lecture in the format the caller asked for."""
    n, date, topic = item
    if fmt == "number":
        print(n)
    elif fmt == "title":
        print(f"Release L{n}: {topic}")
    elif fmt == "body":
        print(body(item, queue, today, horizon))
    else:
        print(f"Today {today}, horizon {horizon}.")
        print(f"  L{n:<3} {date:%a %Y-%m-%d}  quiz: {bank_note(n):<26}"
              f" also: {', '.join(extras(n)) or '-'}")
        print(f"       {topic}")
        if queue:
            print("\n  Behind it: " + ", ".join(
                f"L{m} {d:%b %-d}" for m, d, _ in queue[:4]))
        print(f"\n  python tools/release_lecture.py {n}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--today", help="pretend it is this date, YYYY-MM-DD (for testing)")
    ap.add_argument("--lecture", type=int,
                    help="release this lecture instead of whatever the calendar says")
    ap.add_argument("--horizon-days", type=int, default=HORIZON_DAYS,
                    help=f"how far ahead to look, in days (default {HORIZON_DAYS})")
    ap.add_argument("--format", choices=("human", "number", "body", "title"),
                    default="human")
    args = ap.parse_args()

    today = (dt.date.fromisoformat(args.today) if args.today
             else dt.datetime.now().date())
    starts, ends = semester(today)

    if args.lecture:
        # Named explicitly, so neither the semester window nor the horizon
        # applies. The two checks that still do are the ones that would make the
        # release a no-op or a broken build.
        named = [s for s in sessions() if s[0] == args.lecture]
        if not named:
            sys.exit(f"L{args.lecture} is not a dated session in {SCHEDULE}.")
        if f"l{args.lecture:02d}" in released():
            sys.exit(f"L{args.lecture} is already released in _toc.yml.")
        if not has_content(args.lecture):
            sys.exit(f"L{args.lecture} has no lectures/l{args.lecture:02d}/notes.md.")
        item = named[0]
        queue = [s for s in pending() if s[1] > item[1]]
        horizon = item[1]
        held = [s for s in pending() if s[1] < item[1]]
        if held and args.format == "human":
            print("Note: releasing out of order. Still held: "
                  + ", ".join(f"L{m}" for m, _, _ in held))
        return report(args.format, item, queue, today, horizon)

    # Outside the semester there is nothing to release and nobody to remind.
    if today < starts - dt.timedelta(days=7) or today > ends:
        if args.format == "human":
            print(f"Outside the semester ({starts} to {ends}); nothing to release.")
        return 0

    item, queue, horizon = due(today, args.horizon_days)
    if item is None:
        if args.format == "human":
            nxt = (f" The next one is L{queue[0][0]} on {queue[0][1]}."
                   if queue else " Everything with content is released.")
            print(f"Nothing due through {horizon}.{nxt}")
        return 0

    return report(args.format, item, queue, today, horizon)


if __name__ == "__main__":
    raise SystemExit(main())
