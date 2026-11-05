"""Generate the comic strip in the L22 deck: two instructors and the lecture schedule catching up.

Four panels, drawn as inline SVG so the deck stays text and the joke stays editable. The dates
and the release times in the captions come from figures/make_figures.py (releases.png), which
reads them from git; the characters are cartoons, not likenesses.

    python3 lectures/l22/figures/make_comic.py           # rewrite ../slides.md
    python3 lectures/l22/figures/make_comic.py --check   # fail if slides.md is stale
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SLIDES = Path(__file__).resolve().parent.parent / "slides.md"
INK, RED, BLUE, GOLD, PAPER, GRAY, SKIN = "#2b2b2b", "#c41230", "#1f5c99", "#b07d12", "#fbf7ec", "#8a8a8a", "#f1c9a5"


def person(x, y, shirt, name, pose, hair, glasses=False, mood="smile"):
    """A cartoon figure standing on the ground line y, centred at x."""
    o = []
    a = o.append
    lean = {"stand": 0, "walk": 4, "run": 12, "sprint": 20}[pose]
    hx, hy = x + lean, y - 92
    legs = {"stand": [(-8, 0), (8, 0)], "walk": [(-14, 0), (12, 0)],
            "run": [(-24, -6), (20, 0)], "sprint": [(-32, -14), (26, 0)]}[pose]
    arms = {"stand": [(-20, 18), (20, 18)], "walk": [(-18, 12), (20, 20)],
            "run": [(-26, 0), (24, 8)], "sprint": [(-30, -10), (30, -4)]}[pose]
    hip = (x + lean / 3, y - 38)
    for dx, dy in legs:
        a(f'<line x1="{hip[0]}" y1="{hip[1]}" x2="{x + dx}" y2="{y + dy}" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>')
    sh = (x + lean * 0.75, y - 64)
    a(f'<path d="M{hip[0]-13},{hip[1]+2} L{sh[0]-14},{sh[1]-6} Q{sh[0]},{sh[1]-14} {sh[0]+14},{sh[1]-6} '
      f'L{hip[0]+13},{hip[1]+2} Z" fill="{shirt}" stroke="{INK}" stroke-width="2"/>')
    for dx, dy in arms:
        a(f'<line x1="{sh[0]}" y1="{sh[1]}" x2="{sh[0] + dx}" y2="{sh[1] + dy}" stroke="{INK}" stroke-width="5" stroke-linecap="round"/>')
    a(f'<circle cx="{hx}" cy="{hy}" r="17" fill="{SKIN}" stroke="{INK}" stroke-width="2"/>')
    a(f'<path d="{hair.format(x=hx, y=hy)}" fill="{INK}"/>')
    if glasses:
        a(f'<circle cx="{hx-6}" cy="{hy-1}" r="5" fill="none" stroke="{INK}" stroke-width="1.6"/>'
          f'<circle cx="{hx+7}" cy="{hy-1}" r="5" fill="none" stroke="{INK}" stroke-width="1.6"/>'
          f'<line x1="{hx-1}" y1="{hy-1}" x2="{hx+2}" y2="{hy-1}" stroke="{INK}" stroke-width="1.6"/>')
    a(f'<circle cx="{hx-6}" cy="{hy-1}" r="1.8" fill="{INK}"/><circle cx="{hx+7}" cy="{hy-1}" r="1.8" fill="{INK}"/>')
    if mood == "smile":
        a(f'<path d="M{hx-6},{hy+7} Q{hx+1},{hy+13} {hx+8},{hy+7}" fill="none" stroke="{INK}" stroke-width="1.8"/>')
    elif mood == "worried":
        a(f'<path d="M{hx-5},{hy+10} Q{hx+1},{hy+6} {hx+7},{hy+10}" fill="none" stroke="{INK}" stroke-width="1.8"/>')
        a(f'<path d="M{hx+17},{hy-12} q4,7 0,10 q-4,-3 0,-10" fill="#6f93b3"/>')
    else:   # yell
        a(f'<ellipse cx="{hx+2}" cy="{hy+9}" rx="4" ry="5" fill="{INK}"/>')
        a(f'<path d="M{hx+17},{hy-14} q4,7 0,10 q-4,-3 0,-10 M{hx-20},{hy-10} q4,7 0,10 q-4,-3 0,-10" fill="#6f93b3"/>')
    a(f'<text x="{x}" y="{y + 20}" font-size="13" text-anchor="middle" font-weight="700" fill="{INK}">{name}</text>')
    return "".join(o)


JOHN_HAIR = "M{x},{y} m-17,-3 q1,-17 17,-17 q16,0 17,15 q-8,-8 -17,-7 q-9,-1 -17,9 Z"
VICTOR_HAIR = "M{x},{y} m-17,-2 q-1,-19 18,-19 q17,1 16,18 q-5,-10 -10,-9 q-2,-6 -12,-4 q-8,0 -12,14 Z"


def robot(x, y, carrying=False):
    o = (f'<rect x="{x-14}" y="{y-40}" width="28" height="24" rx="6" fill="#d9773c" stroke="{INK}" stroke-width="2"/>'
         f'<circle cx="{x-6}" cy="{y-29}" r="3" fill="{PAPER}"/><circle cx="{x+6}" cy="{y-29}" r="3" fill="{PAPER}"/>'
         f'<line x1="{x}" y1="{y-40}" x2="{x}" y2="{y-50}" stroke="{INK}" stroke-width="2"/><circle cx="{x}" cy="{y-52}" r="3" fill="{GOLD}"/>'
         f'<rect x="{x-10}" y="{y-16}" width="20" height="12" rx="3" fill="#d9773c" stroke="{INK}" stroke-width="2"/>'
         f'<line x1="{x-6}" y1="{y-4}" x2="{x-8}" y2="{y+4}" stroke="{INK}" stroke-width="3"/>'
         f'<line x1="{x+6}" y1="{y-4}" x2="{x+8}" y2="{y+4}" stroke="{INK}" stroke-width="3"/>')
    if carrying:
        o += (f'<rect x="{x-20}" y="{y-24}" width="40" height="5" fill="{GRAY}" stroke="{INK}" stroke-width="1.5"/>'
              f'<rect x="{x-18}" y="{y-44}" width="36" height="20" fill="#dbe8f5" stroke="{INK}" stroke-width="1.5" transform="rotate(-8 {x} {y-34})"/>')
    o += f'<text x="{x}" y="{y + 20}" font-size="12" text-anchor="middle" fill="{INK}">Claude</text>'
    return o


def boulder(x, y, r, label):
    return (f'<g class="comic-roll" style="transform-origin:{x}px {y - r}px">'
            f'<circle cx="{x}" cy="{y - r}" r="{r}" fill="#b49a6a" stroke="{INK}" stroke-width="2.5"/>'
            f'<path d="M{x - r * 0.5},{y - r * 1.4} q{r * 0.3},{r * 0.2} {r * 0.2},{r * 0.6} M{x + r * 0.2},{y - r * 0.6} q{r * 0.3},{-r * 0.1} {r * 0.4},{r * 0.3}" '
            f'fill="none" stroke="{INK}" stroke-width="1.5"/></g>'
            f'<text x="{x}" y="{y - r + 5}" font-size="14" text-anchor="middle" font-weight="700" fill="{PAPER}">{label}</text>'
            + "".join(f'<line x1="{x - r - 10 - 12 * i}" y1="{y - r * (0.5 + 0.4 * i)}" x2="{x - r - 30 - 12 * i}" '
                      f'y2="{y - r * (0.5 + 0.4 * i)}" stroke="{GRAY}" stroke-width="2" stroke-linecap="round"/>' for i in range(3) if x - r - 30 - 12 * i > 8))


def panel(i, title, caption, body):
    x0 = 10 + i * 297
    return (f'<g transform="translate({x0},10)">'
            f'<rect x="0" y="0" width="285" height="330" rx="10" fill="{PAPER}" stroke="{INK}" stroke-width="2.5"/>'
            f'<text x="142" y="26" font-size="16" text-anchor="middle" font-weight="700" fill="{RED}">{title}</text>'
            f'<line x1="10" y1="250" x2="275" y2="250" stroke="{INK}" stroke-width="1.5"/>'
            f'{body}'
            + "".join(f'<text x="142" y="{294 + 18 * k}" font-size="13" text-anchor="middle" fill="{INK}">{line}</text>'
                      for k, line in enumerate(caption))
            + "</g>")


def build() -> str:
    g = 250   # ground line inside a panel
    p1 = (f'<rect x="30" y="42" width="150" height="104" rx="4" fill="#ffffff" stroke="{INK}" stroke-width="2"/>'
          f'<text x="40" y="64" font-size="12" fill="{INK}">THE PLAN</text>'
          f'<text x="40" y="84" font-size="12" fill="{BLUE}">26 lectures</text>'
          f'<text x="40" y="102" font-size="12" fill="{BLUE}">A1 to A11 + miniproject</text>'
          f'<text x="40" y="120" font-size="12" fill="{BLUE}">2 mini-project days</text>'
          f'<text x="40" y="138" font-size="12" fill="{BLUE}">stay a week ahead</text>'
          + person(205, g, RED, "John", "stand", JOHN_HAIR, glasses=True)
          + person(250, g, BLUE, "Victor", "stand", VICTOR_HAIR)
          + robot(110, g, carrying=False)
          + f'<text x="230" y="70" font-size="20" fill="{GOLD}">☀</text>')
    p2 = (person(200, g, RED, "John", "walk", JOHN_HAIR, glasses=True)
          + person(245, g, BLUE, "Victor", "walk", VICTOR_HAIR)
          + robot(150, g)
          + boulder(45, g, 24, "L+7")
          + f'<text x="100" y="80" font-size="13" fill="{GRAY}" font-style="italic">a comfortable week</text>')
    p3 = (person(190, g, RED, "John", "run", JOHN_HAIR, glasses=True, mood="worried")
          + person(240, g, BLUE, "Victor", "run", VICTOR_HAIR, mood="worried")
          + robot(140, g, carrying=True)
          + boulder(70, g, 36, "L+1")
          + f'<rect x="196" y="48" width="72" height="56" fill="#ffffff" stroke="{INK}" stroke-width="1.5" transform="rotate(10 232 76)"/>'
          + f'<text x="204" y="72" font-size="11" fill="{RED}" transform="rotate(10 232 76)">A6, A8, A9</text>'
          + f'<text x="210" y="90" font-size="11" fill="{RED}" transform="rotate(10 232 76)">on hold</text>')
    p4 = (person(190, g, RED, "John", "sprint", JOHN_HAIR, glasses=True, mood="yell")
          + person(232, g, BLUE, "Victor", "sprint", VICTOR_HAIR, mood="yell")
          + robot(150, g, carrying=True)
          + boulder(78, g, 50, "L19")
          + f'<path d="M212,108 l10,-14 l4,8 l12,-10" fill="none" stroke="{GOLD}" stroke-width="3"/>'
          + f'<text x="20" y="60" font-size="13" fill="{INK}" font-weight="700">12:34 pm</text>'
          + f'<text x="20" y="76" font-size="12" fill="{INK}">"Release Lecture 19"</text>')
    panels = [
        panel(0, "July 20", ["Twelve assignments!", "What could go wrong?"], p1),
        panel(1, "August", ["A week ahead, as planned.", "L3 went up 4 days early"], p2),
        panel(2, "October", ["A day or two ahead.", "Content first; assignments wait"], p3),
        panel(3, "November 4", ["Published the day of.", "7 of 17 lectures: same day"], p4),
    ]
    label = ("A four-panel comic. July 20: two cartoon instructors, John and Victor, relax beside a plan of 26 "
             "lectures, eleven assignments plus a miniproject, and staying a week ahead. August: they walk "
             "comfortably ahead of a small boulder labelled L+7. October: they run, worried, as a larger boulder "
             "labelled L+1 closes in and a note says A6, A8 and A9 are on hold. November 4: they sprint, shouting, "
             "with a robot named Claude carrying a laptop, as a huge boulder labelled L19 rolls at their heels; "
             "the caption says Release Lecture 19 at 12:34 pm, and seven of seventeen lectures went out the same day.")
    return (f'<svg id="race-comic" data-when-active viewBox="0 0 1200 350" width="100%" role="img" aria-label="{label}" '
            "style=\"font-family: 'Comic Sans MS', 'Comic Neue', 'Chalkboard SE', sans-serif; display:block; margin: 0 auto;\">"
            + "".join(panels) + "</svg>")


PATTERN = re.compile(r'<svg id="race-comic".*?</svg>', re.S)


def main() -> int:
    text = SLIDES.read_text()
    if not PATTERN.search(text):
        print(f'no <svg id="race-comic"> in {SLIDES}', file=sys.stderr)
        return 1
    new = PATTERN.sub(lambda _: build(), text, count=1)
    if "--check" in sys.argv:
        if new != text:
            print(f"{SLIDES} is stale; run {Path(__file__).name}", file=sys.stderr)
            return 1
        return 0
    SLIDES.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
