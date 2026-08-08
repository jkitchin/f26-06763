#!/usr/bin/env python3
"""Extract the lecture dependency graph from the notes themselves.

    python tools/graph.py                 # print the graph
    python tools/graph.py --write         # write game/src/map/graph.json
    python tools/graph.py --check         # fail if the committed copy is stale

The course map is drawn from this. A corridor between two rooms is a citation
one lecture actually makes of another, so walking the map shows you structure
that exists rather than structure somebody invented. That is the same standard
the rest of this repository holds itself to: `make_figures.py` computes its
claims rather than asserting them, and this computes the map's.

WHAT COUNTS AS AN EDGE, and why it is only the hard links.

Two kinds of reference exist in the notes. Markdown links of the form
`](../lNN/notes.md)`, which are unambiguous and machine-checkable, and prose
mentions like "as in L5", which are neither. This reads only the first kind.

That is a deliberate under-count, and it costs real coverage: L17, L19, L21 and
L23 cite earlier sessions only in prose, so the extracted graph effectively
stops at L15. The alternative is worse. "from L3" and "unlike L3" both match a
mention regex, and a corridor built on the second one would be a prerequisite
that the notes explicitly deny. Checked at the time of writing: the reversing
forms do not currently occur, so extraction would work today. It is still the
wrong source of truth, because nothing stops one being written next week and
nothing would catch it.

The back half of the course therefore needs hand-authored edges, and those are
content: each cites the sentence that justifies it and is checked like any other
claim. See game/content/map-edges.yml.

A NOTE ON WHAT THIS FOUND. On its first run this reported five links whose text
named one lecture and whose href pointed at another, all of them pointing at a
lecture that does not exist yet. Fixed in a separate commit. The check stays
because the pressure that produced them has not gone away: a link to an
unwritten lecture fails the build under --warningiserror, and redirecting the
href is the quickest way to make that stop.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "game" / "src" / "map" / "graph.json"

LINK = re.compile(r"\[L(\d+)\]\(\.\./(l\d\d)/notes\.md\)")
ANY_LINK = re.compile(r"\]\(\.\./(l\d\d)/notes\.md\)")


def lectures() -> list[str]:
    """Every lecture with notes, in course order."""
    return sorted(p.parent.name for p in REPO.glob("lectures/l*/notes.md"))


def scan() -> tuple[list[dict], list[str]]:
    """Edges and complaints.

    An edge is (from, to, weight, where): weight is how many times the source
    lecture links the target, and `where` is one citing line, so a corridor can
    show the sentence that created it.
    """
    edges: dict[tuple[str, str], dict] = {}
    problems: list[str] = []
    known = set(lectures())

    for path in sorted(REPO.glob("lectures/l*/notes.md")):
        src = path.parent.name
        for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for m in LINK.finditer(line):
                label, target = int(m.group(1)), m.group(2)
                if label != int(target[1:]):
                    problems.append(
                        f"{path.relative_to(REPO)}:{n}: link text says L{label} "
                        f"but the href points at {target}"
                    )
            for m in ANY_LINK.finditer(line):
                target = m.group(1)
                if target == src:
                    continue
                if target not in known:
                    problems.append(
                        f"{path.relative_to(REPO)}:{n}: links to {target}, "
                        "which has no notes.md"
                    )
                    continue
                e = edges.setdefault((src, target), {"from": src, "to": target,
                                                     "weight": 0, "where": ""})
                e["weight"] += 1
                if not e["where"]:
                    e["where"] = " ".join(line.split())[:160]

    return sorted(edges.values(), key=lambda e: (e["from"], e["to"])), problems


def build() -> dict:
    edges, problems = scan()
    if problems:
        for p in problems:
            print(f"::error::{p}", file=sys.stderr)
        raise SystemExit(f"{len(problems)} bad cross-reference(s); fix them before the map uses them")

    # Two different questions, and the map wants both: how many lectures cite
    # this one (how central it is), and how many times in total (how wide the
    # corridor should be drawn).
    indeg = Counter(e["to"] for e in edges)
    outdeg = Counter(e["from"] for e in edges)
    inweight: Counter = Counter()
    for e in edges:
        inweight[e["to"]] += e["weight"]
    known = lectures()
    return {
        "generated_by": "tools/graph.py",
        "note": "Hard markdown cross-links only. See the module docstring for why.",
        "lectures": known,
        "edges": edges,
        "in_degree": {l: indeg.get(l, 0) for l in known},
        "in_weight": {l: inweight.get(l, 0) for l in known},
        "out_degree": {l: outdeg.get(l, 0) for l in known},
        # Lectures nothing points at from a link. Useful for the map: these are
        # rooms with no inbound corridor, which is a fact worth seeing.
        "unreferenced": [l for l in known if indeg.get(l, 0) == 0],
        # Lectures that cite nothing. Includes the early ones, which have
        # nothing to cite, and the late ones, which cite only in prose.
        "terminal": [l for l in known if outdeg.get(l, 0) == 0],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    g = build()
    text = json.dumps(g, indent=2) + "\n"

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(REPO)}: "
              f"{len(g['lectures'])} lectures, {len(g['edges'])} edges")
        return 0

    if args.check:
        if not OUT.is_file():
            print(f"::error::{OUT.relative_to(REPO)} is missing. Run: python tools/graph.py --write")
            return 1
        if OUT.read_text(encoding="utf-8") != text:
            print(f"::error::{OUT.relative_to(REPO)} is stale. Run: python tools/graph.py --write")
            return 1
        print(f"OK: the committed graph matches the notes "
              f"({len(g['edges'])} edges over {len(g['lectures'])} lectures)")
        return 0

    w = max(len(e["from"]) for e in g["edges"])
    for e in g["edges"]:
        print(f"  {e['from']:<{w}} -> {e['to']}  ({e['weight']})")
    print("\n  cited by (lectures / total links):")
    for l, n in sorted(g["in_degree"].items(), key=lambda kv: (-kv[1], kv[0])):
        if n:
            print(f"    {l}  {n} lecture(s), {g['in_weight'][l]} link(s)")
    print(f"  no inbound: {', '.join(g['unreferenced']) or 'none'}")
    print(f"  cites none: {', '.join(g['terminal']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
