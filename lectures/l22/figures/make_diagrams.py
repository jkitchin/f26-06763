#!/usr/bin/env python3
"""Copy two of the L22 deck's diagrams into the notes, as standalone SVG files.

The deck draws these diagrams inline, so they can build step by step and link to the
features they show. The notes need the same pictures as plain figures, and a copy kept by
hand would drift from the deck. So this script reads each diagram out of ../slides.md, shows
every step at once, drops the links, and writes it next to the other figures:

    process.svg     how the course was made: the instructors, Claude Code, the automatic
                    checks, the review, and the course you used
    timeline.svg    what was built around the lectures, and when, coloured by kind

    python3 lectures/l22/figures/make_diagrams.py           # rewrite the SVG files
    python3 lectures/l22/figures/make_diagrams.py --check   # fail if they differ from the deck

Change a diagram in the deck, then run this script, so the notes show the same picture.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SLIDES = HERE.parent / "slides.md"

# Each diagram, found by a piece of text that only its opening <svg> tag contains.
DIAGRAMS = {
    "process.svg": 'class="pl-anim"',
    "timeline.svg": 'aria-label="Timeline from July to November 2026',
}

# The deck's own font, which an inline SVG inherits from the slide and a file does not.
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"


def extract(deck: str, marker: str) -> str:
    """The <svg> element whose opening tag contains `marker`, as a standalone file."""
    at = deck.index(marker)
    start = deck.rindex("<svg", 0, at)
    end = deck.index("</svg>", at) + len("</svg>")
    svg = deck[start:end]
    head_end = svg.index(">") + 1
    head, body = svg[:head_end], svg[head_end:]

    # Every step of a build is shown at once, and the links only work on a slide.
    body = body.replace(" data-marpit-fragment", "")
    body = re.sub(r"<a [^>]*>", "", body).replace("</a>", "")

    # A file needs the SVG namespace, a font, and a size of its own instead of the slide's.
    w, h = re.search(r'viewBox="0 0 (\d+) (\d+)"', head).groups()
    label = re.search(r'aria-label="([^"]*)"', head).group(1)
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'font-family="{FONT}" role="img" aria-label="{label}">')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + head + body + "\n"


def main() -> None:
    check = "--check" in sys.argv[1:]
    deck = SLIDES.read_text()
    stale = []
    for name, marker in DIAGRAMS.items():
        svg = extract(deck, marker)
        path = HERE / name
        if check:
            if not path.exists() or path.read_text() != svg:
                stale.append(name)
        else:
            path.write_text(svg)
            print(f"wrote {name}")
    if stale:
        sys.exit(f"out of date with the deck: {', '.join(stale)}; run make_diagrams.py")
    if check:
        print("OK: the notes' diagrams match the deck")


if __name__ == "__main__":
    main()
