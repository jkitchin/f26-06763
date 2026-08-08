#!/usr/bin/env python3
"""Print the quotable material in a lecture, so items are turned rather than invented.

    python game/harvest.py l09
    python game/harvest.py l09 --kind tables
    python game/harvest.py --counts          # what every lecture has to offer

Deterministic and dumb on purpose. There is no model here and no judgement: it
finds the seams a good item is built from and prints each one with the exact
text and line number, so the author's job is to *turn* material into a question
rather than to go looking for it. That division matters, because an author who
is also searching will reach for whatever they remember, and what they remember
is the tidy summary rather than the surprising measurement.

The seams, in rough order of how well they convert:

  surprises   the "N of these measurements changed what the lecture says"
              bullets in a figure script's docstring. The best items in the
              bank come from here: the drafted expectation is a ready-made
              distractor and the measurement is the answer.
  admonitions "What a practitioner should take from this" and "Common pitfall"
              blocks, which are already written as the thing worth keeping.
  pushback    "## Where this pushes back" and its subsections, where the notes
              weigh a technology instead of selling it.
  tables      contrasts, which convert directly into rank and mcq items.
  claims      bolded numeric claims, with the sentence around them.
  figures     figure alt text, which carries the numbers in prose.
  objectives  the "## Learning objectives" bullets, verbatim, for objectives.yml.

Nothing here reads course/modules/. The module files are the spec and are
instructor-only; a public bank must never quote them.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

KINDS = ("objectives", "surprises", "admonitions", "pushback", "tables", "claims",
         "figures", "headings", "notebook")


def read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n") if path.is_file() else []


def show(label: str, line: int, text: str, width: int = 96) -> None:
    flat = " ".join(text.split())
    if len(flat) > width:
        flat = flat[: width - 1] + "…"
    print(f"  {label}:{line:<5} {flat}")


# --- seams -----------------------------------------------------------------

def objectives(lines: list[str]) -> None:
    """The bullets, verbatim. These go into objectives.yml unchanged."""
    inside = False
    for i, line in enumerate(lines, 1):
        if line.startswith("## Learning objectives"):
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.strip().startswith("- "):
            # Objectives wrap; join the continuation lines.
            text = line.strip()[2:]
            j = i
            while j < len(lines) and lines[j].startswith("  ") and lines[j].strip():
                text += " " + lines[j].strip()
                j += 1
            show("obj", i, text, width=200)


def surprises(script: list[str]) -> None:
    """The numbered "changed what the lecture says" bullets in a figure script."""
    inside = False
    buf: list[str] = []
    start = 0
    for i, line in enumerate(script, 1):
        if re.match(r"^\s*(Four|Five|Six|Seven|Eight|Nine|Ten|\d+) of these", line):
            inside = True
            continue
        if inside and line.strip().startswith(("Outputs", '"""')):
            break
        if not inside:
            continue
        if re.match(r"^\s+\d+\.\s", line):
            if buf:
                show("sup", start, " ".join(buf), width=260)
            buf, start = [line.strip()], i
        elif buf and line.strip():
            buf.append(line.strip())
    if buf:
        show("sup", start, " ".join(buf), width=260)


def admonitions(lines: list[str]) -> None:
    for i, line in enumerate(lines, 1):
        m = re.match(r"^:::\{admonition\}\s*(.+?)\s*$", line)
        if not m:
            continue
        title = m.group(1)
        cls = ""
        body: list[str] = []
        for j in range(i, len(lines)):
            if lines[j].startswith(":class:"):
                cls = lines[j].split(":class:")[1].strip()
                continue
            if lines[j].startswith(":::"):
                break
            body.append(lines[j])
        show(f"adm[{cls or '?'}]", i, f"{title} || {' '.join(body)}", width=170)


def pushback(lines: list[str]) -> None:
    """The limitations section and its subsections, where a claim gets weighed."""
    inside = False
    for i, line in enumerate(lines, 1):
        if re.match(r"^## .*(push(es)? back|limitation|trade-?off|where this)", line, re.I):
            inside = True
            show("PUSH", i, line.lstrip("# "))
            continue
        if inside and line.startswith("## "):
            inside = False
        elif inside and line.startswith("### "):
            show("  sub", i, line.lstrip("# "))


def tables(lines: list[str]) -> None:
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|", lines[i + 1]):
            start = i + 1
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(lines[i])
                i += 1
            print(f"  tbl:{start:<5} {len(rows) - 2} rows")
            for r in rows:
                print(f"        {r}")
        i += 1


def claims(lines: list[str]) -> None:
    """Bolded spans containing a digit, with the sentence around them."""
    for i, line in enumerate(lines, 1):
        if line.startswith(("|", ":alt:", "```")):
            continue
        for m in re.finditer(r"\*\*([^*]*\d[^*]*)\*\*", line):
            show("num", i, f"{m.group(1)}  <<  {line}", width=150)


def figures(lines: list[str]) -> None:
    for i, line in enumerate(lines, 1):
        if line.startswith(":alt:"):
            show("alt", i, line[5:], width=240)


def headings(lines: list[str]) -> None:
    """Valid values for an item's source.heading."""
    for i, line in enumerate(lines, 1):
        if re.match(r"^#{2,3} ", line):
            show("hdg", i, line)


def notebook(path: Path) -> None:
    """Cell markers, for notebook_run items."""
    import json
    try:
        nb = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for n, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        first = next((s for s in src.split("\n") if s.strip() and not s.startswith("#")), "")
        if "print" in src or "plt." in src:
            show(f"cell[{n}]", n, first, width=110)


# --- driver ----------------------------------------------------------------

def harvest(lecture: str, kinds: tuple[str, ...]) -> None:
    notes = REPO / "lectures" / lecture / "notes.md"
    if not notes.is_file():
        print(f"no notes for {lecture}")
        return
    lines = read(notes)
    script = read(REPO / "lectures" / lecture / "figures" / "make_figures.py")
    nbs = sorted((REPO / "lectures" / lecture).glob("*.ipynb"))

    print(f"\n{'=' * 78}\n{lecture}  {notes}  ({len(lines)} lines)\n{'=' * 78}")
    for kind in kinds:
        print(f"\n--- {kind} ---")
        if kind == "objectives":
            objectives(lines)
        elif kind == "surprises":
            surprises(script) if script else print("  (no figure script)")
        elif kind == "admonitions":
            admonitions(lines)
        elif kind == "pushback":
            pushback(lines)
        elif kind == "tables":
            tables(lines)
        elif kind == "claims":
            claims(lines)
        elif kind == "figures":
            figures(lines)
        elif kind == "headings":
            headings(lines)
        elif kind == "notebook":
            notebook(nbs[0]) if nbs else print("  (no notebook)")


def counts() -> None:
    """What each lecture has to offer, so authoring effort can be aimed."""
    print(f"{'lec':<6}{'words':>7}{'adm':>5}{'tbl':>5}{'num':>5}{'fig':>5}{'sup':>5}  hint")
    for d in sorted((REPO / "lectures").glob("l*/")):
        notes = d / "notes.md"
        if not notes.is_file():
            continue
        lines = read(notes)
        text = "\n".join(lines)
        script = read(d / "figures" / "make_figures.py")
        n_adm = len(re.findall(r"^:::\{admonition\}", text, re.M))
        n_tbl = len(re.findall(r"^\|[\s:|-]+\|", text, re.M))
        n_num = len(re.findall(r"\*\*[^*]*\d[^*]*\*\*", text))
        n_fig = len(re.findall(r"^:alt:", text, re.M))
        n_sup = len(re.findall(r"^\s+\d+\.\s", "\n".join(script[:60]), re.M)) if script else 0
        hint = "numeric" if n_num > 25 else ("conceptual" if n_num < 8 else "mixed")
        print(f"{d.name:<6}{len(text.split()):>7}{n_adm:>5}{n_tbl:>5}{n_num:>5}"
              f"{n_fig:>5}{n_sup:>5}  {hint}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("lecture", nargs="?", help="e.g. l09")
    ap.add_argument("--kind", action="append", choices=KINDS)
    ap.add_argument("--counts", action="store_true")
    args = ap.parse_args()

    if args.counts or not args.lecture:
        counts()
        return 0
    harvest(args.lecture, tuple(args.kind) if args.kind else KINDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
