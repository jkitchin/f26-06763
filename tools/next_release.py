#!/usr/bin/env python3
"""What each release cycle has to do this week, and which lecture it is about.

The course ships one lecture at a time, and `tools/release_lecture.py` already
knows how to release one. This works out *which* one, from the calendar and from
what is already live, and assembles the checklist that goes with it, so a reminder
can name the work rather than leaving someone to count sessions by hand.

    python3 tools/next_release.py --weekday monday    # John's cycle
    python3 tools/next_release.py --weekday wednesday # Victor's cycle
    python3 tools/next_release.py --today 2026-10-19
    python3 tools/next_release.py --format number     # "3", for a workflow
    python3 tools/next_release.py --format body       # markdown for an issue
    python3 tools/next_release.py --lecture 3         # this one, calendar or not

Sessions meet Monday and Wednesday, and each weekday is somebody's lane. A lane
looks a week ahead: the Monday cycle releases the following Monday's lecture, the
Wednesday cycle the following Wednesday's. Every lecture therefore belongs to
exactly one lane, and the two owners never contend for the same release.

Within a lane it is the *earliest* unreleased lecture inside the horizon, not the
nearest, so a cycle that gets skipped picks its lecture back up next week instead
of leaving it behind forever.

Each cycle also names the lecture most recently delivered, which is the one whose
recording has to reach Canvas. Because the runs are at midnight and the sessions
are during the day, the Wednesday cycle always looks back at Monday's session and
the Monday cycle at the previous Wednesday's. So every lecture gets exactly one
"embed it" reminder, and it comes from the other person's lane.

`--lecture` names one directly, for releasing ahead of the calendar or catching up
out of band. It skips the horizon and the lane, so it is the one path that can
release early; it still refuses a lecture that is already live or has no notes.

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

#: Where the released notes and decks answer, for the Canvas links in the
#: checklist. Section 8 of CLAUDE.md: https, because http answers a 301.
SITE = "https://kitchingroup.cheme.cmu.edu/f26-06763"

# "| Lecture 3: 08-31-2026 (Monday) | Databases for engineering data |"
SESSION = re.compile(r"Lecture\s+(\d+):\s*(\d{2}-\d{2}-\d{4})[^|]*\|\s*(.*?)\s*\|")

# The same expression tools/world.py uses for "released", deliberately. Two
# definitions of released is one too many: the absence of a leading # is the
# whole mechanism, and a second copy of it is a second thing to get wrong.
RELEASED = re.compile(r"^\s*-\s*file:\s*lectures/(l\d\d)/notes\b", re.M)

#: The two lanes, as Python weekday numbers, and who owns each.
LANES = {
    "monday": (0, "jkitchin", "John Kitchin"),
    "wednesday": (2, "victoraalves", "Victor Alves"),
}

#: How far ahead a lane looks. A cycle runs at midnight on its own weekday and
#: targets the same weekday next week, so seven days is the whole window. It is
#: also the slack that lets a skipped cycle catch up: the lecture stays inside
#: the horizon of the following week's run.
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


def pending(weekday=None):
    """Unreleased lectures that have content, earliest session first.

    `weekday` restricts to one lane, as a Python weekday number.
    """
    live = released()
    return [s for s in sessions()
            if f"l{s[0]:02d}" not in live and has_content(s[0])
            and (weekday is None or s[1].weekday() == weekday)]


def due(today, horizon_days=HORIZON_DAYS, weekday=None):
    """The lecture this cycle releases, and the horizon it was judged against."""
    horizon = today + dt.timedelta(days=horizon_days)
    queue = pending(weekday)
    if not queue or queue[0][1] > horizon:
        return None, horizon
    return queue[0], horizon


def previous(today):
    """The lecture most recently delivered, which is the one to put on Canvas.

    Strictly before today, because a cycle runs at midnight and that day's own
    session has not happened yet.
    """
    done = [s for s in sessions() if s[1] < today and has_content(s[0])]
    return done[-1] if done else None


def blockers(item):
    """Unreleased lectures that come before this one, in either lane.

    Releasing out of order breaks the build: a released lecture may
    cross-reference an earlier one, so L4 cannot go public before L3. The two
    lanes release independently, so this is the check that catches one owner
    getting ahead of the other.
    """
    return [s for s in pending() if s[1] < item[1]]


def extras(n):
    """The assignment and project slugs that ride along with this lecture."""
    return LECTURE_ASSIGNMENTS.get(n, []) + LECTURE_PROJECTS.get(n, [])


def semester(today):
    """First and last dated session, so the window is not a second hardcoded date."""
    all_dates = [d for _, d, _ in sessions()]
    return min(all_dates), max(all_dates)


def title(item, prev):
    """A deterministic issue title, because the duplicate check matches it exactly."""
    if item and prev:
        return f"Release L{item[0]} and embed L{prev[0]} on Canvas"
    if item:
        return f"Release L{item[0]}"
    if prev:
        return f"Embed L{prev[0]} on Canvas"
    return ""


def body(item, prev, lane, today, horizon):
    """The issue text: the three-step cycle, with this week's lectures named."""
    who = LANES[lane][2] if lane in LANES else "whoever runs this"
    lines = [
        f"The {lane} cycle, {who}'s. Three steps: last session onto Canvas, next "
        "lecture released, next module published.",
        "",
    ]

    # 1. The session just delivered.
    if prev:
        pn, pd, ptopic = prev
        pnn = f"{pn:02d}"
        lines += [
            f"- [ ] **Embed L{pn} on Canvas**, delivered {pd:%A %b %-d}, "
            f"\"{ptopic}\". Notes: {SITE}/lectures/l{pnn}/notes.html . "
            f"Deck: {SITE}/slides/l{pnn}/ .",
        ]
    else:
        lines += ["- *Embed the previous lecture: nothing delivered yet.*"]

    # 2. The release itself.
    if item:
        n, date, topic = item
        nn = f"{n:02d}"
        also = ", ".join(extras(n)) or "nothing else"
        lines += [
            f"- [ ] **Release L{n}**, \"{topic}\", which meets {date:%A %b %-d}. "
            f"Notes, deck and quiz go public together, and it also releases "
            f"{also}. Quiz bank: {bank_note(n)}.",
        ]
    else:
        lines += [
            "- *Release next week's lecture: nothing scheduled in this lane "
            f"through {horizon:%b %-d}.*",
        ]

    # 3. The module for what was just released.
    if item:
        n = item[0]
        nn = f"{n:02d}"
        lines += [
            f"- [ ] **Update the Canvas module for L{n}** with links to its notes "
            f"({SITE}/lectures/l{nn}/notes.html) and deck ({SITE}/slides/l{nn}/), "
            "then publish the module. Do this after the release PR has merged and "
            "CI has deployed, or the links will 404.",
        ]
    else:
        lines += ["- *Publish the next Canvas module: nothing released this cycle.*"]

    lines.append("")

    if not item:
        lines += [
            "Nothing to release in this lane this week, so only the Canvas step "
            "above applies. The next lecture in this lane is "
            + (f"L{pending(LANES[lane][0])[0][0]}."
               if lane in LANES and pending(LANES[lane][0]) else "past the end of the schedule."),
            "",
            "Full procedure: "
            "[`RELEASING.md`](https://github.com/jkitchin/f26-06763/blob/main/RELEASING.md).",
        ]
        return "\n".join(lines)

    n = item[0]
    nn = f"{n:02d}"
    held = blockers(item)
    if held:
        lines += [
            f"> **L{n} cannot be released yet.** Still held ahead of it: "
            + ", ".join(f"L{m}" for m, _, _ in held)
            + ". A released lecture may cross-reference an earlier one, so "
            f"publishing L{n} first would fail the build. That is the other "
            "lane's release, so this cycle waits on it.",
            "",
        ]

    lines += [
        "## Step 2, in commands",
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
        "- **Step 3 waits on the deploy.** CI publishes on merge to `main` and the "
        f"`verify` job reads `{SITE}/build-info.json` back off the live site. A "
        "green build is not the same as a live page, so check that before pasting "
        "links into Canvas.",
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


def report(fmt, item, prev, lane, today, horizon):
    """Print this cycle in the format the caller asked for."""
    if fmt == "number":
        print(item[0] if item else "")
    elif fmt == "previous":
        print(prev[0] if prev else "")
    elif fmt == "blockers":
        print(" ".join(str(m) for m, _, _ in blockers(item)) if item else "")
    elif fmt == "title":
        print(title(item, prev))
    elif fmt == "body":
        print(body(item, prev, lane, today, horizon))
    else:
        print(f"Today {today}, horizon {horizon}, lane {lane or 'both'}.")
        if prev:
            print(f"  embed    L{prev[0]:<3} {prev[1]:%a %Y-%m-%d}  {prev[2]}")
        else:
            print("  embed    nothing delivered yet")
        if item:
            n, date, topic = item
            print(f"  release  L{n:<3} {date:%a %Y-%m-%d}  quiz: {bank_note(n)}"
                  f"  also: {', '.join(extras(n)) or '-'}")
            print(f"           {topic}")
            held = blockers(item)
            if held:
                print("  BLOCKED by " + ", ".join(f"L{m}" for m, _, _ in held)
                      + " (released lectures cross-reference earlier ones)")
            else:
                print(f"  python tools/release_lecture.py {n}")
        else:
            print("  release  nothing in this lane inside the horizon")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--today", help="pretend it is this date, YYYY-MM-DD (for testing)")
    ap.add_argument("--weekday", choices=sorted(LANES),
                    help="which lane to report; omit to consider both")
    ap.add_argument("--lecture", type=int,
                    help="release this lecture instead of whatever the calendar says")
    ap.add_argument("--horizon-days", type=int, default=HORIZON_DAYS,
                    help=f"how far ahead to look, in days (default {HORIZON_DAYS})")
    ap.add_argument("--format",
                    choices=("human", "number", "previous", "blockers", "body", "title"),
                    default="human")
    args = ap.parse_args()

    today = (dt.date.fromisoformat(args.today) if args.today
             else dt.datetime.now().date())
    starts, ends = semester(today)
    weekday = LANES[args.weekday][0] if args.weekday else None
    prev = previous(today)

    if args.lecture:
        # Named explicitly, so neither the semester window, the horizon nor the
        # lane applies. The two checks that still do are the ones that would make
        # the release a no-op or a broken build.
        named = [s for s in sessions() if s[0] == args.lecture]
        if not named:
            sys.exit(f"L{args.lecture} is not a dated session in {SCHEDULE}.")
        if f"l{args.lecture:02d}" in released():
            sys.exit(f"L{args.lecture} is already released in _toc.yml.")
        if not has_content(args.lecture):
            sys.exit(f"L{args.lecture} has no lectures/l{args.lecture:02d}/notes.md.")
        item = named[0]
        return report(args.format, item, prev, args.weekday, today, item[1])

    # Outside the semester there is nothing to release and nobody to remind.
    if today < starts - dt.timedelta(days=7) or today > ends:
        if args.format == "human":
            print(f"Outside the semester ({starts} to {ends}); nothing to do.")
        elif args.format in ("number", "previous", "blockers", "title"):
            print("")
        return 0

    item, horizon = due(today, args.horizon_days, weekday)
    if item is None and prev is None:
        if args.format == "human":
            print(f"Nothing due through {horizon}, and nothing delivered yet.")
        elif args.format in ("number", "previous", "blockers", "title"):
            print("")
        return 0

    return report(args.format, item, prev, args.weekday, today, horizon)


if __name__ == "__main__":
    raise SystemExit(main())
