#!/usr/bin/env python3
"""Build the map world from the schedule, the notes and the extracted graph.

    python tools/world.py            # print the world
    python tools/world.py --write    # write game/src/map/world.json
    python tools/world.py --check    # fail if the committed copy is stale

Nothing here is placed by hand. The rooms are the sessions in course/schedule.md,
their titles are the schedule's titles, their regions are the arcs the notes
declare, and the corridors are the edges tools/graph.py already verified. That
is the same standard the lecture figures hold: compute the claim rather than
assert it, so the map cannot quietly disagree with the course it describes.

A NOTE ON THE PARSER, because it already bit. The session cell names the session
and carries the date and weekday, and two rows add a conference annotation inside
the weekday parenthesis:

    | Lecture 18: 11-09-2026 (Monday, AIChE) | Prompting, RAG, or fine-tuning ...

An earlier version of this regex (against the older bracketed date format)
required the annotation to sit in its own token and silently dropped L18 and L19,
reporting a clean parse of 24 rows. L19 is a *written* lecture that anchors five
authored map edges, so the map would have shipped with a room missing and five
corridors leading out of nothing, with no error anywhere. Hence EXPECTED_SESSIONS:
a parser that can under-count silently is worse than one that crashes, and this
one now refuses to emit anything if the count moves without the constant being
updated. The weekday parenthesis is matched as a whole, so an annotation inside
it (Monday, AIChE) no longer breaks the parse.

ARCS. Each written lecture declares its own arc in its notes ("**Arc** Data
Systems"). The twelve sessions with no notes cannot, so they inherit the arc of
the nearest preceding written lecture. That is an interpolation and it is stated
rather than hidden: it is correct for every gap in the current schedule, because
the arcs run as contiguous blocks in course order, and `--check` will not notice
if that ever stops being true. If a future arc starts on an unwritten session,
this rule puts it in the wrong region and the fix is to write that lecture or to
record arcs in the schedule itself.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "game" / "src" / "map" / "world.json"
GRAPH = REPO / "game" / "src" / "map" / "graph.json"
SCHEDULE = REPO / "course" / "schedule.md"
TOC = REPO / "_toc.yml"

#: A room is "open" (has a clickable notes link, drawn as reachable) only once
#: its lecture is RELEASED, meaning listed in _toc.yml. The course ships one week
#: at a time, so a lecture whose notes.md exists on disk but is not yet in _toc.yml
#: is drawn as a shuttered room, exactly like a lecture that has no notes at all.
#: Without this the map would link every future lecture to a notes.html the site
#: never built. Regions and arcs still come from the notes on disk, so the shape
#: of the whole course stays legible; only the open/shut state follows _toc.yml.
def released_ids() -> set[str]:
    """Lecture ids (l01, l19, ...) released in _toc.yml.

    Matches only real, uncommented `- file:` entries, so commenting a lecture
    out of _toc.yml (the weekly-release mechanism) correctly reads as unreleased.
    """
    text = TOC.read_text(encoding="utf-8") if TOC.is_file() else ""
    return set(re.findall(r"^\s*-\s*file:\s*lectures/(l\d\d)/notes\b", text, re.M))

#: L1 through L23 plus the two mini-project sessions. Update deliberately.
#:
#: Was 26, for L1 through L24. L24 was a capstone studio row that never had a
#: lecture directory and was dropped from the schedule; the two final-project
#: presentation rows carry no session label and so have never been counted here.
#: L23 is counted because it is written: it has notes, a notebook, an item bank
#: and a room on the map, and a schedule edit briefly dropped its row while all
#: four remained, which is the state this constant exists to refuse.
EXPECTED_SESSIONS = 25

#: Rooms per row within a region. Two reads as a course sequence going down the
#: page, and keeps the widest region from dominating the layout.
COLS = 2

ROW = re.compile(
    r"^\|\s*"
    r"(?:Lecture\s+(\d+)|Mini-project day\s+(\d+))"   # session (one group set)
    r":\s*(\d{2})-(\d{2})-(\d{4})"                    # date, month-day-year
    r"\s*\([^)]*\)"                                   # (weekday) or (weekday, AIChE)
    r"\s*\|\s*(.*?)\s*\|"                             # title
)
ARC = re.compile(r"\*\*Arc\*\*\s+(.+?)\s*$")


def slug(session: str) -> str:
    """`L7` -> `l07`, `MP-1` -> `mp1`. Matches the lectures/ directory names."""
    if session.startswith("MP"):
        return "mp" + session.split("-")[1]
    return f"l{int(session[1:]):02d}"


def written() -> dict[str, str]:
    """{lecture id: declared arc} for every lecture that has notes."""
    out = {}
    for p in sorted(REPO.glob("lectures/l*/notes.md")):
        for line in p.read_text(encoding="utf-8").split("\n")[:20]:
            m = ARC.search(line)
            if m:
                out[p.parent.name] = m.group(1)
                break
    return out


def sessions() -> list[dict]:
    """Every session in course order, with its title, date and region."""
    rows = []
    for line in SCHEDULE.read_text(encoding="utf-8").split("\n"):
        m = ROW.match(line)
        if m:
            lec, mp, mm, dd, yyyy, title = m.groups()
            session = f"L{lec}" if lec else f"MP-{mp}"
            date = f"{yyyy}-{mm}-{dd}"  # store ISO so the JSON is stable and sorts
            rows.append({"session": session, "id": slug(session), "date": date,
                         "title": title.replace("**", "").strip()})

    if len(rows) != EXPECTED_SESSIONS:
        raise SystemExit(
            f"{SCHEDULE.relative_to(REPO)}: parsed {len(rows)} sessions, expected "
            f"{EXPECTED_SESSIONS}. Either the schedule changed and "
            f"EXPECTED_SESSIONS should be updated deliberately, or a row is "
            f"formatted in a way this parser drops. Parsed: "
            f"{', '.join(r['session'] for r in rows)}"
        )

    arcs = written()
    released = released_ids()
    current = None
    for r in rows:
        has_arc = r["id"] in arcs
        if has_arc:
            current = arcs[r["id"]]
        # A room is open only once its lecture is released in _toc.yml; the arc
        # is still read from the notes on disk so regions do not move.
        r["written"] = r["id"] in released
        r["arc_source"] = "declared" if has_arc else "inherited"
        if current is None:
            raise SystemExit(
                f"{r['session']} precedes every written lecture, so it has no arc "
                f"to inherit. Record arcs in the schedule rather than only in the "
                f"notes."
            )
        r["arc"] = current
    return rows


def build() -> dict:
    rows = sessions()
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))

    # Regions in course order, which is the order students already carry.
    regions: list[dict] = []
    for r in rows:
        if not regions or regions[-1]["name"] != r["arc"]:
            regions.append({"name": r["arc"], "rooms": []})
        regions[-1]["rooms"].append(r["id"])

    # Lay each region out as its own block of COLS-wide rows, then place the
    # blocks left to right with one cell of corridor between them.
    rooms: dict[str, dict] = {}
    x = 1
    for ri, region in enumerate(regions):
        region["x0"] = x
        region["rows"] = (len(region["rooms"]) + COLS - 1) // COLS
        for i, rid in enumerate(region["rooms"]):
            row = next(r for r in rows if r["id"] == rid)
            rooms[rid] = {
                **row,
                "region": ri,
                "x": x + (i % COLS),
                "y": 1 + (i // COLS),
                "notes": f"../lectures/{rid}/notes.html" if row["written"] else None,
            }
        x += COLS + 1

    width = x
    height = max(r["rows"] for r in regions) + 2

    doors = [
        {"from": e["from"], "to": e["to"], "origin": e["origin"],
         "relation": e.get("relation"), "why": e.get("why"), "where": e["where"]}
        for e in graph["edges"]
        if e["from"] in rooms and e["to"] in rooms
    ]

    signs = [
        {"lecture": s["lecture"], "promised_by": s["promised_by"], "where": s["where"]}
        for s in graph.get("shutters", [])
        if s["lecture"] in rooms
    ]

    return {
        "generated_by": "tools/world.py",
        "note": (
            "Rooms are the sessions in course/schedule.md, regions are the arcs "
            "the notes declare, corridors are the edges tools/graph.py verified. "
            "Nothing is placed by hand."
        ),
        "grid": {"width": width, "height": height, "cols_per_region": COLS},
        # Bottom-left of the first region, which is where the course starts.
        "spawn": {"x": 1, "y": max(r["rows"] for r in regions) + 1},
        "regions": [{"name": r["name"], "x0": r["x0"], "rows": r["rows"],
                     "rooms": r["rooms"]} for r in regions],
        "rooms": [rooms[k] for k in sorted(rooms, key=lambda k: (rooms[k]["region"],
                                                                rooms[k]["y"],
                                                                rooms[k]["x"]))],
        "doors": doors,
        "signs": signs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    w = build()
    text = json.dumps(w, indent=2, ensure_ascii=False) + "\n"

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(REPO)}: {len(w['rooms'])} rooms, "
              f"{len(w['regions'])} regions, {len(w['doors'])} corridors, "
              f"{len(w['signs'])} signed shutters")
        return 0

    if args.check:
        if not OUT.is_file():
            print(f"::error::{OUT.relative_to(REPO)} is missing. "
                  f"Run: python tools/world.py --write", file=sys.stderr)
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"::error::{OUT.relative_to(REPO)} is stale. "
                  f"Run: python tools/world.py --write", file=sys.stderr)
            return 1
        print(f"OK: the committed world matches the schedule and the graph "
              f"({len(w['rooms'])} rooms, {len(w['doors'])} corridors)")
        return 0

    print(f"world: {w['grid']['width']}x{w['grid']['height']}, "
          f"spawn at {w['spawn']['x']},{w['spawn']['y']}")
    for i, region in enumerate(w["regions"]):
        print(f"\n  {region['name']}  (x{region['x0']})")
        for rid in region["rooms"]:
            room = next(r for r in w["rooms"] if r["id"] == rid)
            mark = "open " if room["written"] else "shut "
            print(f"    {mark} {room['session']:<5} {room['title'][:56]}")
    print(f"\n  {len(w['doors'])} corridors, {len(w['signs'])} signed shutters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
