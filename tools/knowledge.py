#!/usr/bin/env python3
"""Build the knowledge graph and the live system figure from the notes.

    python tools/knowledge.py            # print a summary
    python tools/knowledge.py --write    # write game/src/map/knowledge.json
    python tools/knowledge.py --check    # fail if the committed copy is stale

Two tabs of the course map read this file: the knowledge graph (lectures, or
themes and concepts) and the live version of Lecture 1's system figure.

WHERE EACH PART COMES FROM. Almost everything is extracted, so it cannot drift
from the notes:

  lectures      the session rooms in game/src/map/world.json, so the graph and
                the walkable map show the same sessions, in the same arcs, open
                or shut by the same _toc.yml rule;
  links         the lecture-to-lecture edges in game/src/map/graph.json, each
                with the sentence from the notes that makes it;
  objectives    game/content/objectives.yml, which validate.py keeps verbatim;
  concepts      the {index} entries in each lecture's notes, placed in the H2
                section that defines them, typed by the index's own clusters
                (case study, failure mode, metric);
  case studies  the published pages in case-studies/, with their field and the
                lectures they connect to.

Only game/content/knowledge.yml is hand-written: the themes, a takeaway line or
two per lecture, the data each lecture works on, and the boxes of the system
figure. This script checks every reference in it.

RELEASE. The site is public and the course ships one lecture at a time, so an
unreleased lecture contributes its number, title, date and arc and nothing else:
no takeaways, no objectives, no concepts, and no link whose quoting sentence
comes from its notes. Releasing a lecture changes this file, which is why
tools/release_lecture.py regenerates it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORLD = REPO / "game" / "src" / "map" / "world.json"
GRAPH = REPO / "game" / "src" / "map" / "graph.json"
OBJECTIVES = REPO / "game" / "content" / "objectives.yml"
CONTENT = REPO / "game" / "content" / "knowledge.yml"
CASES = REPO / "case-studies"
TOC = REPO / "_toc.yml"
OUT = REPO / "game" / "src" / "map" / "knowledge.json"

#: Index entry clusters (CLAUDE.md section 4b) and the kind each becomes.
CLUSTERS = {"case study": "case", "failure mode": "failure", "metric": "metric"}

#: Lecture 1's figure is drawn on a 100 x 46 canvas that the boxes tile exactly.
CANVAS = (100, 46)


def fail(msg: str) -> None:
    raise SystemExit(f"{CONTENT.relative_to(REPO)}: {msg}")


def make_id(text: str) -> str:
    """The anchor docutils gives a section, so a concept can link to its section.

    Same steps as docutils.nodes.make_id: lowercase, ASCII-fold, collapse every
    run of other characters to one hyphen, and drop leading digits and hyphens.
    """
    s = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", " ".join(s.split()))
    return re.sub(r"^[-0-9]+|-+$", "", s)


def plain(text: str) -> str:
    """A quoted sentence without its markdown: links to their text, no markers."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\{[a-z]+\}`([^`<]*)(?:<[^>]*>)?`", r"\1", text)
    return re.sub(r"\s+", " ", re.sub(r"[`*_]", "", text)).strip()


def released_pages() -> set[str]:
    text = TOC.read_text(encoding="utf-8")
    return set(re.findall(r"^\s*-\s*file:\s*(\S+)\s*$", text, re.M))


def parse_notes(lec: str) -> dict:
    """Title, H2 sections and index concepts of one lecture's notes."""
    text = (REPO / "lectures" / lec / "notes.md").read_text(encoding="utf-8")
    title, section, sections, concepts = "", None, [], []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            section = line[3:].strip()
            sections.append(section)
        m = re.match(r"^```\{index\}\s*(.*?)\s*$", line)
        if not m:
            continue
        body = m.group(1)
        if body.startswith("see:"):
            continue
        if body.startswith(("pair:", "single:")):
            kind, rest = body.split(":", 1)
            parts = [p.strip() for p in rest.split(";")]
            if kind == "pair" and parts[0] in CLUSTERS:
                concepts.append((parts[1], CLUSTERS[parts[0]], section))
            elif kind == "pair":
                concepts.extend((p, "concept", section) for p in parts)
            else:
                concepts.append((parts[-1], "concept", section))
        else:
            concepts.extend((t.strip(), "concept", section) for t in body.split(",") if t.strip())
    return {"title": title, "sections": sections, "concepts": concepts}


def parse_cases(pages: set[str], rooms: dict) -> list[dict]:
    """The published case-study pages: title, field, and the lectures they connect to."""
    out = []
    for p in sorted(CASES.glob("*.md")):
        if p.stem == "index" or f"case-studies/{p.stem}" not in pages:
            continue
        text = p.read_text(encoding="utf-8")
        title = re.sub(r"^Case study\s*·\s*", "", text.split("\n", 1)[0].lstrip("# ").strip())
        field = re.search(r"^- \*\*Field\*\*:?\s*(.+)$", text, re.M)
        connects = re.search(r"^- \*\*Connects to\*\*:?\s*(.+)$", text, re.M)
        lectures = re.findall(r"lectures/(l\d\d)/notes\.md", connects.group(1) if connects else "")
        out.append({
            "id": p.stem, "title": title,
            "field": field.group(1).strip() if field else "",
            "lectures": [lec for lec in dict.fromkeys(lectures) if lec in rooms],
            "href": f"../case-studies/{p.stem}.html",
        })
    return out


def build() -> dict:
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    content = yaml.safe_load(CONTENT.read_text(encoding="utf-8"))
    objectives = yaml.safe_load(OBJECTIVES.read_text(encoding="utf-8"))
    pages = released_pages()

    rooms = {r["id"]: r for r in world["rooms"] if r["kind"] == "session"}
    released = {lid for lid, r in rooms.items() if r["written"]}
    arcs = [g["name"] for g in world["regions"] if any(rid in rooms for rid in g["rooms"])]
    notes = {lid: parse_notes(lid) for lid in released}

    # --- themes: one primary theme per lecture, single sections claimed by others
    themes = content["themes"]
    primary: dict[str, str] = {}
    claimed: dict[tuple[str, str], str] = {}
    for t in themes:
        for lid in t.get("lectures") or []:
            if lid not in rooms:
                fail(f"theme {t['id']} lists {lid}, which is not a session on the map")
            if lid in primary:
                fail(f"{lid} is the primary lecture of both {primary[lid]} and {t['id']}")
            primary[lid] = t["id"]
        for lid, heads in (t.get("sections") or {}).items():
            if lid not in rooms:
                fail(f"theme {t['id']} claims a section of {lid}, which is not on the map")
            for head in heads:
                if lid in notes and head not in notes[lid]["sections"]:
                    fail(f"theme {t['id']} claims '{head}', which is not an H2 section of {lid}")
                if (lid, head) in claimed:
                    fail(f"'{head}' in {lid} is claimed by both {claimed[(lid, head)]} and {t['id']}")
                claimed[(lid, head)] = t["id"]
    for lid in rooms:
        if lid not in primary:
            fail(f"{lid} has no primary theme; list it under one theme's `lectures`")

    def theme_of(lid: str, section: str | None) -> str:
        return claimed.get((lid, section or ""), primary[lid])

    # --- concepts, deduplicated by term: the first lecture to index it defines it
    concepts: dict[str, dict] = {}
    for lid in sorted(released):
        for term, kind, section in notes[lid]["concepts"]:
            cid = make_id(term) or term
            if cid in concepts:
                if lid not in concepts[cid]["also"] and lid != concepts[cid]["lecture"]:
                    concepts[cid]["also"].append(lid)
                # A term indexed both plainly and in a cluster ("hallucination"
                # and "failure mode; hallucination") is the cluster's kind.
                if concepts[cid]["kind"] == "concept" and kind != "concept":
                    concepts[cid]["kind"] = kind
                continue
            concepts[cid] = {
                "id": cid, "term": term, "kind": kind, "lecture": lid,
                "section": section or "",
                "href": f"../lectures/{lid}/notes.html" + (f"#{make_id(section)}" if section else ""),
                "theme": theme_of(lid, section), "also": [],
            }

    # --- links between lectures, kept only when the citing lecture is released
    edges = []
    for e in graph["edges"]:
        if e["from"] in rooms and e["to"] in rooms and e["from"] in released:
            edges.append({"from": e["from"], "to": e["to"], "weight": e.get("weight", 1),
                          "where": plain(e.get("why") or e["where"])})

    cases = parse_cases(pages, rooms)
    per_lecture = content.get("lectures") or {}
    for lid in per_lecture:
        if lid not in rooms:
            fail(f"lectures.{lid} is not a session on the map")

    lectures = []
    for lid, r in rooms.items():
        node = {"id": lid, "session": r["session"], "title": r["title"], "date": r["date"],
                "arc": r["arc"], "released": lid in released, "theme": primary[lid]}
        if lid in released:
            extra = per_lecture.get(lid) or {}
            if not extra.get("takeaways"):
                fail(f"{lid} is released and has no takeaways")
            node.update({
                "notes": f"../lectures/{lid}/notes.html",
                "slides": f"../slides/{lid}/",
                "takeaways": extra["takeaways"],
                "data": extra.get("data", ""),
                "objectives": [o["text"] for o in objectives if o["lecture"] == lid],
                "themes": sorted({primary[lid]} | {t for (l, _), t in claimed.items() if l == lid}),
                "cases": [c["id"] for c in cases if lid in c["lectures"]],
            })
        lectures.append(node)

    # --- themes as published: only their released lectures and concepts
    out_themes = []
    for t in themes:
        members = sorted({lid for lid, tid in primary.items() if tid == t["id"]}
                         | {lid for (lid, _), tid in claimed.items() if tid == t["id"]})
        members = [lid for lid in members if lid in released]
        if not members:
            continue
        out_themes.append({"id": t["id"], "name": t["name"], "blurb": t["blurb"],
                           "lectures": members,
                           "arc": rooms[members[0]]["arc"]})
    shown = {t["id"] for t in out_themes}

    # Themes connect where their lectures do, and where a lecture spans both.
    weight: dict[tuple[str, str], int] = {}
    def bump(a: str, b: str, w: int = 1) -> None:
        if a != b and a in shown and b in shown:
            k = (min(a, b), max(a, b))
            weight[k] = weight.get(k, 0) + w
    for e in edges:
        bump(primary[e["from"]], primary[e["to"]])
    for (lid, _), tid in claimed.items():
        if lid in released:
            bump(primary[lid], tid)
    theme_edges = [{"a": a, "b": b, "weight": w} for (a, b), w in sorted(weight.items())]

    # --- the system figure
    system = content["system"]
    all_terms = {c["term"]: c for c in concepts.values()}
    area = 0
    boxes = []
    ids = {b["id"] for b in system["boxes"]}
    for b in system["boxes"]:
        x, y, w, h = b["geometry"]
        area += w * h
        for lid in b["lectures"]:
            if lid not in rooms:
                fail(f"system box {b['id']} lists {lid}, which is not a session on the map")
        tools = []
        for term in b["tools"]:
            if term not in all_terms:
                # An unreleased lecture's term is not in the concept list yet, and
                # that is not an error; a term in no lecture's index is.
                if not any(term == t for lid in rooms if (REPO / "lectures" / lid / "notes.md").exists()
                           for t, _, _ in parse_notes(lid)["concepts"]):
                    fail(f"system box {b['id']}: tool '{term}' is not an index term in any lecture")
                continue
            c = all_terms[term]
            tools.append({"term": term, "concept": c["id"], "lecture": c["lecture"]})
        boxes.append({"id": b["id"], "label": b["label"], "x": x, "y": y, "w": w, "h": h,
                      "blurb": b["blurb"],
                      "lectures": [lid for lid in b["lectures"] if lid in released],
                      "tools": tools})
    if area != CANVAS[0] * CANVAS[1]:
        fail(f"the system boxes cover {area} units, not the {CANVAS[0] * CANVAS[1]} of the canvas")
    for fid in system["flow"]:
        if fid not in ids:
            fail(f"system flow names {fid}, which is not a box")

    return {
        "generated_by": "tools/knowledge.py",
        "note": ("Lectures, links, objectives, concepts and case studies are extracted from the "
                 "notes; themes, takeaways and the system boxes come from "
                 "game/content/knowledge.yml. Do not edit by hand."),
        "arcs": arcs,
        "lectures": lectures,
        "edges": edges,
        "themes": out_themes,
        "theme_edges": theme_edges,
        "concepts": sorted(concepts.values(), key=lambda c: (c["lecture"], c["term"].lower())),
        "cases": cases,
        "system": {"canvas": list(CANVAS), "caption": system["caption"],
                   "boxes": boxes, "flow": system["flow"]},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    k = build()
    text = json.dumps(k, indent=1, ensure_ascii=False) + "\n"
    summary = (f"{len(k['lectures'])} lectures, {len(k['edges'])} links, "
               f"{len(k['themes'])} themes, {len(k['concepts'])} concepts, "
               f"{len(k['cases'])} case studies, {len(k['system']['boxes'])} system boxes")

    if args.write:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(REPO)}: {summary}")
        return 0
    if args.check:
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            print(f"::error::{OUT.relative_to(REPO)} is stale. "
                  f"Run: python tools/knowledge.py --write", file=sys.stderr)
            return 1
        print(f"OK: the committed knowledge graph matches the notes ({summary})")
        return 0

    print(summary)
    for t in k["themes"]:
        n = sum(1 for c in k["concepts"] if c["theme"] == t["id"])
        print(f"  {t['name']:<44} {', '.join(t['lectures']):<24} {n} concepts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
