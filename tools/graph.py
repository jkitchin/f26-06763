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

WHAT COUNTS AS AN EDGE. Two things, from two sources, and the split is the
point: everything machine-checkable is extracted, and everything else is
written down with its evidence.

Two kinds of reference exist in the notes. Markdown links of the form
`](../lNN/notes.md)`, which are unambiguous and machine-checkable, and prose
mentions like "as in L5", which are neither. This reads only the first kind.

Extraction alone is a deliberate under-count, and it costs real coverage: L17,
L19, L21 and L23 cite earlier sessions only in prose, so the extracted graph
stops at L15. Extracting prose mentions instead is worse. "from L3" and "unlike
L3" both match a mention regex, and a corridor built on the second would be a
prerequisite the notes explicitly deny. Checked at the time of writing: the
reversing forms do not currently occur, so a regex would work today. It is still
the wrong source of truth, because nothing stops one being written next week and
nothing would catch it.

So the back half is hand-authored in game/content/map-edges.yml, and those edges
are content, held to the standard the rest of this repository holds: each quotes
the sentence that justifies it, and this file checks that the sentence is still
there, that it appears exactly once, and that it actually names the lecture the
edge points at. That last check is the one that does the work. An edge whose
evidence never mentions its target is an invented prerequisite, which is exactly
the plausible-sounding claim the course teaches students to refuse.

Fifteen authored edges and two signed shutters, against nineteen extracted, so
roughly half this graph is a claim somebody made rather than a link somebody
wrote. That ratio is why the checks exist.

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

import yaml

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "game" / "src" / "map" / "graph.json"
AUTHORED = REPO / "game" / "content" / "map-edges.yml"

RELATIONS = {"builds-on", "contrasts", "reuses", "shares-data", "prevents"}

LINK = re.compile(r"\[L(\d+)\]\(\.\./(l\d\d)/notes\.md\)")
ANY_LINK = re.compile(r"\]\(\.\./(l\d\d)/notes\.md\)")


def norm(text: str) -> str:
    """Whitespace-insensitive, because the notes are hard-wrapped.

    A quote worth citing usually spans a line break, and requiring the newline
    to match would push authors toward quoting half a sentence. Same rule
    game/validate.py uses for item quotes.
    """
    return " ".join(text.split())


def names(lecture: str, text: str) -> bool:
    """Does this text refer to `lecture` by its L-number?

    The anti-invention check, and the one that does the real work here. An
    authored edge is a claim that one session depends on another; a quote that
    never mentions the target is not evidence of anything, it is a sentence
    somebody liked. Both spellings occur in the notes, L7 and L07.
    """
    n = int(lecture[1:])
    return re.search(rf"\bL0?{n}\b", text) is not None


def authored() -> tuple[list[dict], list[dict], list[str]]:
    """(edges, shutters, problems) from game/content/map-edges.yml.

    See that file for why these are hand-written rather than extracted.
    """
    if not AUTHORED.is_file():
        return [], [], []
    doc = yaml.safe_load(AUTHORED.read_text(encoding="utf-8")) or {}
    rel = AUTHORED.relative_to(REPO)
    known = set(lectures())
    problems: list[str] = []
    edges: list[dict] = []
    shutters: list[dict] = []

    def cited(where: str, src: dict, must_name: str) -> str | None:
        """The quote, if it holds up. None and a complaint if it does not."""
        path = REPO / src.get("file", "")
        quote = src.get("quote", "")
        if not quote:
            problems.append(f"{rel}: {where} has no source.quote")
            return None
        if not path.is_file():
            problems.append(f"{rel}: {where} cites {src.get('file')}, which does not exist")
            return None
        hay = norm(path.read_text(encoding="utf-8"))
        needle = norm(quote)
        if needle not in hay:
            problems.append(
                f"{rel}: {where} quotes a sentence that is no longer in "
                f"{src.get('file')}. Re-read the section and re-author the edge "
                f"rather than editing the quote to match.\n"
                f'    quote: "{needle[:100]}"'
            )
            return None
        if hay.count(needle) > 1:
            problems.append(
                f"{rel}: {where} quotes something that appears "
                f"{hay.count(needle)} times in {src.get('file')}; widen it so it "
                f"anchors to one place"
            )
            return None
        if not names(must_name, needle):
            problems.append(
                f"{rel}: {where} points at {must_name} but its quote never "
                f"mentions {must_name.upper()}. An edge whose evidence does not "
                f"name its target is an invented prerequisite."
            )
            return None
        return needle

    for e in doc.get("edges", []):
        src_l, dst_l = e.get("from", ""), e.get("to", "")
        where = f"edge {src_l} -> {dst_l}"
        if src_l == dst_l:
            problems.append(f"{rel}: {where} points at itself")
            continue
        for side, l in (("from", src_l), ("to", dst_l)):
            if l not in known:
                problems.append(f"{rel}: {where} has {side}: {l}, which has no notes.md")
        if src_l not in known or dst_l not in known:
            continue
        if e.get("relation") not in RELATIONS:
            problems.append(
                f"{rel}: {where} has relation {e.get('relation')!r}; "
                f"expected one of {', '.join(sorted(RELATIONS))}"
            )
            continue
        if not e.get("why"):
            problems.append(f"{rel}: {where} has no why; say what a student learns walking it")
            continue
        quote = cited(where, e.get("source", {}), dst_l)
        if quote is None:
            continue
        edges.append({
            "from": src_l, "to": dst_l, "weight": 1, "where": quote[:160],
            "origin": "authored", "relation": e["relation"], "why": norm(e["why"]),
        })

    for sh in doc.get("shutters", []):
        lec, by = sh.get("lecture", ""), sh.get("promised_by", "")
        where = f"shutter {lec} promised by {by}"
        if lec in known:
            problems.append(
                f"{rel}: {where}, but {lec} now has notes.md. It is a room, not a "
                f"shutter; move it to edges."
            )
            continue
        if by not in known:
            problems.append(f"{rel}: {where}, but {by} has no notes.md")
            continue
        quote = cited(where, sh.get("source", {}), lec)
        if quote is None:
            continue
        shutters.append({"lecture": lec, "promised_by": by, "where": quote[:160]})

    return edges, shutters, problems


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
    hand, shutters, hand_problems = authored()
    problems += hand_problems

    # An authored edge that duplicates an extracted one is not an error waiting
    # to happen, it is redundancy that will drift: the link says one thing, the
    # quote another, and nothing reconciles them. The link wins, because it is
    # checked by the build.
    linked = {(e["from"], e["to"]) for e in edges}
    for h in hand:
        if (h["from"], h["to"]) in linked:
            problems.append(
                f"game/content/map-edges.yml: {h['from']} -> {h['to']} is already a "
                f"markdown cross-link, which tools/graph.py extracts on its own. "
                f"Delete the authored edge."
            )
    for e in edges:
        e.setdefault("origin", "link")
    edges = sorted(edges + hand, key=lambda e: (e["from"], e["to"]))

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
        "shutters": shutters,
        "note": (
            "Markdown cross-links, plus the hand-authored edges in "
            "game/content/map-edges.yml for the back half of the course, where "
            "lectures cite each other only in prose. See the module docstring."
        ),
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
        tag = "" if e["origin"] == "link" else f"  [{e['relation']}]"
        print(f"  {e['from']:<{w}} -> {e['to']}  ({e['weight']}){tag}")
    n_auth = sum(1 for e in g["edges"] if e["origin"] == "authored")
    print(f"\n  {len(g['edges']) - n_auth} from links, {n_auth} authored, "
          f"{len(g['shutters'])} shutter(s) signed")
    print("\n  cited by (lectures / total links):")
    for l, n in sorted(g["in_degree"].items(), key=lambda kv: (-kv[1], kv[0])):
        if n:
            print(f"    {l}  {n} lecture(s), {g['in_weight'][l]} link(s)")
    print(f"  no inbound: {', '.join(g['unreferenced']) or 'none'}")
    print(f"  cites none: {', '.join(g['terminal']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
