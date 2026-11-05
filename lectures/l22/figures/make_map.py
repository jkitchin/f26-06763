"""Generate the course map on the second slide of the L22 deck.

The L18 deck opened with a map of the course as a journey, with the route past L18 in fog.
This is the same map with the fog lifted: L19 on the language coast, the two optional
sessions on the AIChE dates as a loop off the main trail, this lecture, the two presentation
days, and the guest speakers at the end of the trail. The drawing code, the stops for L1 to
L18, the case-study side paths and their tie lines are imported from the L18 generator, so a
change to a stop or a case study there reaches this map too.

    python3 lectures/l22/figures/make_map.py           # rewrite ../slides.md
    python3 lectures/l22/figures/make_map.py --check   # fail if slides.md is stale

Like the L18 version, it writes the SVG straight into the deck, replacing the element that
starts with <svg id="course-map">, because the stops are links with tooltips and an <img>
can carry neither.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
SLIDES = HERE.parent / "slides.md"

_spec = importlib.util.spec_from_file_location("l18_map", HERE.parents[1] / "l18" / "figures" / "make_map.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
INK, TRAIL, PAPER, RED, WATER, GREEN, FAINT = m.INK, m.TRAIL, m.PAPER, m.RED, m.WATER, m.GREEN, m.FAINT

# The stops past L18. (number, x, y, title, subtitle, optional)
MORE = [
    (19, 930, 296, "LLM agents: tools, loops, harnesses and coding agents",
     "The agent loop, the harness around it, coding agents, and how this course was built with one", False),
    (20, 968, 350, "Reinforcement learning, learning to act from rewards (optional)",
     "An MDP written out as a table and two matrices, value iteration, Q-learning on the tank", True),
    (21, 1030, 330, "Deployment: serving models, containers, latency and cost (optional)",
     "FastAPI, Docker with uv, percentiles and the tail, batching, and five production incidents", True),
    (22, 1040, 244, "Course overview and how this course was built",
     "The course in a few slides, its git history, and how to learn the next field yourself", False),
]
STOP = dict(m.STOP)
STOP.update({n: (x, y) for n, x, y, *_ in MORE})
DAYS = [("Presentations, day 1", "Wednesday 11-18", 1084, 196), ("Presentations, day 2", "Monday 11-23", 1108, 156)]
HOLIDAY = (1124, 122)   # Thanksgiving, 11-25
SUMMIT = (1134, 74)     # guest speakers, 11-30 and 12-02


def build() -> str:
    out: list[str] = []
    a = out.append
    label = ("A map of the whole course as a journey: a trail through the data lowlands (lectures 1 to 7), "
             "the machine-learning highlands (lectures 8 to 16) and along the language coast (lectures 17 "
             "to 19). The optional lectures 20 and 21 make a loop off the trail that rejoins it at lecture 22, "
             "marked you are here. Beyond it are two days of project presentations and, at the summit, a week "
             "of guest speakers. Side paths lead from some lectures to case studies in other fields")
    a(f'<svg id="course-map" viewBox="0 0 1180 500" width="100%" role="img" aria-label="{label}" '
      "style=\"font-family: Georgia, 'Times New Roman', serif; display:block; margin: 0 auto;\">")
    a('<defs><radialGradient id="jm-p" cx="50%" cy="45%" r="75%"><stop offset="0%" stop-color="#f8f1df"/>'
      '<stop offset="100%" stop-color="#e6d6b0"/></radialGradient></defs>')
    a(f'<rect x="4" y="4" width="1172" height="492" rx="14" fill="url(#jm-p)" stroke="{INK}" stroke-width="2"/>')
    a(f'<rect x="12" y="12" width="1156" height="476" rx="10" fill="none" stroke="{FAINT}" stroke-width="1" stroke-dasharray="2 4"/>')

    # Regions, as in L18: lowland meadow, highland plateau, the sea along the coast.
    a(f'<ellipse cx="205" cy="398" rx="200" ry="76" fill="{GREEN}" opacity="0.18"/>')
    a('<ellipse cx="600" cy="220" rx="240" ry="92" fill="#b49a6a" opacity="0.18"/>')
    a(f'<path d="M630,488 C670,436 730,402 790,394 C840,388 870,372 920,380 C990,392 1080,376 1166,370 '
      f'L1166,478 Q1166,488 1156,488 Z" fill="{WATER}" opacity="0.22"/>')
    for cx, cy in ((742, 404), (758, 400), (774, 397), (860, 380), (876, 376), (892, 377)):
        a(f'<path d="M{cx},{cy} l6,-12 l6,12" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    lx, ly = 818, 392
    a(f'<path d="M{lx-6},{ly} L{lx-4},{ly-26} L{lx+4},{ly-26} L{lx+6},{ly} Z" fill="{PAPER}" stroke="{INK}" stroke-width="1.2"/>'
      f'<rect x="{lx-5}" y="{ly-18}" width="10" height="5" fill="{RED}"/>'
      f'<rect x="{lx-5}" y="{ly-8}" width="11" height="5" fill="{RED}"/>'
      f'<path d="M{lx-6},{ly-26} L{lx},{ly-33} L{lx+6},{ly-26} Z" fill="{INK}"/>'
      f'<path d="M{lx+8},{ly-29} L{lx+34},{ly-38} L{lx+34},{ly-22} Z" fill="#f2d27a" opacity="0.7"/>')
    for wx in (960, 1010, 1060, 1110):
        a(f'<path d="M{wx},468 q8,-6 16,0 t16,0" fill="none" stroke="{WATER}" stroke-width="1.6"/>')
    for tx, ty in ((140, 452), (60, 344), (30, 234), (210, 448), (402, 380)):
        a(m.tree(tx, ty))
    for mx, base, h in ((488, 196, 30), (372, 214, 20), (600, 290, 22), (700, 286, 18), (1000, 150, 24)):
        a(m.mountain(mx, base, h))
    # The summit at the end of the trail.
    sx, sy = SUMMIT
    a(m.mountain(sx, sy + 34, 44))

    a(f'<text x="60" y="490" font-size="21" font-style="italic" fill="{INK}">The data lowlands</text>')
    a(f'<text x="60" y="318" font-size="13" fill="{INK}" opacity="0.85">L1 to L7: toolchain, databases,</text>')
    a(f'<text x="60" y="334" font-size="13" fill="{INK}" opacity="0.85">pipelines, streams, features</text>')
    a(f'<text x="400" y="66" font-size="21" font-style="italic" fill="{INK}">The machine-learning highlands</text>')
    a(f'<text x="400" y="86" font-size="13" fill="{INK}" opacity="0.85">L8 to L16: the ML workflow, deep learning, '
      'scientific ML, uncertainty, design, generative models</text>')
    a(f'<text x="652" y="460" font-size="21" font-style="italic" fill="{INK}">The language coast</text>')
    a(f'<text x="652" y="480" font-size="13" fill="{INK}" opacity="0.85">L17 to L19: language models, context, agents</text>')
    a(f'<text x="1000" y="380" font-size="13" text-anchor="middle" font-style="italic" fill="{INK}">optional, AIChE week</text>')

    sides = {s[0]: s for s in m.SIDES}
    for u, v, tip in m.TIES:
        (x1, y1), (x2, y2) = m.point(u, sides), m.point(v, sides)
        a(f'<g class="jm-tie"><title>{escape(tip)}</title>'
          f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="transparent" stroke-width="12"/>'
          f'<line class="jm-tie-line" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{WATER}" stroke-width="1.6" '
          f'stroke-dasharray="1 5" stroke-linecap="round"/></g>')

    # The whole trail is walked now: L1 to L19, then straight on to L22 and up to the summit.
    pts = [STOP[n] for n in range(1, 14)] + [m.CAMP] + [STOP[n] for n in range(14, 20)] + [STOP[22]]
    pts += [(x, y) for *_, x, y in DAYS] + [HOLIDAY, (sx, sy + 8)]
    TRAIL_PTS[:] = pts
    a(f'<path id="trail" d="{m.smooth(pts)}" fill="none" stroke="{TRAIL}" stroke-width="4" stroke-linecap="round" stroke-dasharray="10 6"/>')
    loop = [STOP[19], STOP[20], STOP[21], STOP[22]]
    a(f'<path d="{m.smooth(loop)}" fill="none" stroke="{TRAIL}" stroke-width="2.5" stroke-linecap="round" '
      'stroke-dasharray="2 6" opacity="0.8"/>')
    cx, cy = m.CAMP
    a(f'<path d="M{cx-11},{cy+2} L{cx},{cy-14} L{cx+11},{cy+2} Z" fill="#d9a441" stroke="{INK}" stroke-width="1.2"/>'
      f'<path d="M{cx},{cy-14} L{cx-2},{cy+2} L{cx+2},{cy+2} Z" fill="{INK}"/>')
    a(f'<text x="{cx}" y="{cy+20}" font-size="11" text-anchor="middle" fill="{INK}" font-style="italic">fall break</text>')
    hx, hy = HOLIDAY
    a(f'<path d="M{hx-9},{hy+2} L{hx},{hy-11} L{hx+9},{hy+2} Z" fill="#d9a441" stroke="{INK}" stroke-width="1.1"/>')
    a(f'<text x="{hx-14}" y="{hy+2}" font-size="11" text-anchor="end" fill="{INK}" font-style="italic">Thanksgiving</text>')

    for key, n, kind, (x, y), short, anchor, field, title, summary, slug in m.SIDES:
        px, py = STOP[n]
        tip = f"{field}: {title}\n{summary}\nOpens the case study, which links back to the lectures"
        dx = -32 if anchor == "end" else 32
        tx = x + dx if kind != "lake" else x + (30 if anchor == "start" else -30)
        a(f'<a class="jm-side" href="../../case-studies/{slug}.html" target="_blank"><title>{escape(tip)}</title>'
          f'<path d="M{px},{py} L{x},{y}" fill="none" stroke="{TRAIL}" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round"/>'
          f'{m.landmark(kind, x, y)}'
          f'<text x="{tx}" y="{y+5}" font-size="13" font-style="italic" text-anchor="{anchor}" fill="{INK}">{short}</text></a>')

    stops = [(n, x, y, t, sub, False) for n, x, y, t, sub in m.STOPS] + MORE
    for n, x, y, t, sub, optional in stops:
        here = n == 22
        fill = RED if here else (PAPER if optional else TRAIL)
        ink = TRAIL if optional else PAPER
        a(f'<a class="jm-stop" href="../../lectures/l{n:02d}/notes.html" target="_blank"><title>L{n}: {escape(t)}\n{escape(sub)}</title>'
          f'<circle cx="{x}" cy="{y}" r="11" fill="{fill}" stroke="{TRAIL if optional else PAPER}" stroke-width="2"/>'
          f'<text x="{x}" y="{y+4}" font-size="11" text-anchor="middle" fill="{ink}" font-family="sans-serif" font-weight="700">{n}</text></a>')

    # The presentation days: small flags on the trail, with a tooltip each.
    for name, when, x, y in DAYS:
        a(f'<g><title>{name}, {when}</title>'
          f'<line x1="{x}" y1="{y+8}" x2="{x}" y2="{y-14}" stroke="{INK}" stroke-width="2"/>'
          f'<path d="M{x},{y-14} L{x+16},{y-9} L{x},{y-4} Z" fill="{RED}"/>'
          f'<circle cx="{x}" cy="{y+8}" r="3" fill="{INK}"/></g>')
    a(f'<text x="1160" y="232" font-size="13" text-anchor="end" fill="{INK}" font-weight="700">project</text>')
    a(f'<text x="1160" y="247" font-size="13" text-anchor="end" fill="{INK}" font-weight="700">presentations</text>')
    a(f'<g><title>Guest speakers, Monday 11-30 and Wednesday 12-02</title>'
      f'<line x1="{sx}" y1="{sy-10}" x2="{sx}" y2="{sy-40}" stroke="{INK}" stroke-width="2.5"/>'
      f'<path d="M{sx},{sy-40} L{sx+26},{sy-32} L{sx},{sy-24} Z" fill="{RED}"/></g>')
    a(f'<text x="{sx-34}" y="{sy-24}" font-size="14" text-anchor="end" fill="{INK}" font-weight="700">guest speakers</text>')

    px, py = STOP[22]
    a(f'<circle cx="{px}" cy="{py}" r="22" fill="{RED}" opacity="0.18"/>')
    a(f'<rect x="858" y="160" width="160" height="50" rx="8" fill="{PAPER}" stroke="{RED}" stroke-width="2"/>')
    a(f'<text x="938" y="181" font-size="16" text-anchor="middle" fill="{RED}" font-weight="700">You are here: L22</text>')
    a(f'<text x="938" y="200" font-size="13" text-anchor="middle" fill="{INK}">looking back</text>')
    a(f'<line x1="1018" y1="200" x2="{px-12}" y2="{py-8}" stroke="{RED}" stroke-width="1.5"/>')

    a(f'<circle cx="1120" cy="440" r="22" fill="{PAPER}" stroke="{INK}" stroke-width="1.2"/>')
    a(f'<path d="M1120,420 L1125,440 L1120,460 L1115,440 Z" fill="{INK}"/>')
    a(f'<path d="M1100,440 L1120,435 L1140,440 L1120,445 Z" fill="{FAINT}"/>')
    a(f'<text x="1120" y="414" font-size="12" text-anchor="middle" fill="{INK}" font-weight="700">N</text>')

    a(f'<line x1="36" y1="36" x2="76" y2="36" stroke="{TRAIL}" stroke-width="4" stroke-dasharray="10 6"/>')
    a(f'<text x="86" y="41" font-size="13" fill="{INK}">the trail, walked</text>')
    a(f'<line x1="36" y1="58" x2="76" y2="58" stroke="{TRAIL}" stroke-width="2.5" stroke-dasharray="2 6" stroke-linecap="round"/>')
    a(f'<circle cx="56" cy="58" r="6" fill="{PAPER}" stroke="{TRAIL}" stroke-width="2"/>')
    a(f'<text x="86" y="63" font-size="13" fill="{INK}">optional sessions</text>')
    a(f'<line x1="36" y1="80" x2="76" y2="80" stroke="{TRAIL}" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round"/>')
    a(f'<text x="86" y="85" font-size="13" fill="{INK}">side path to a case study in another field</text>')
    a(f'<line x1="36" y1="102" x2="76" y2="102" stroke="{WATER}" stroke-width="1.6" stroke-dasharray="1 5" stroke-linecap="round"/>')
    a(f'<text x="86" y="107" font-size="13" fill="{INK}">related cases, hover for what they share</text>')
    a("</svg>")
    return "\n".join(out)


# Scotty, an original Scottish terrier, walks the trail from L1 to the summit once. He is his own
# layer over the map, moved by a CSS transform with one keyframe per step of equal length along
# the trail, so the browser composites him and never repaints the map under him (animating him
# inside the map's SVG repainted all of it every frame, and he juddered). CSS alone, so he also
# walks in a preview that runs no scripts; in the HTML deck the script at the end marks the layer
# .wait while its slide is hidden, which replays the walk each time the slide opens.
TRAIL_PTS: list[tuple[float, float]] = []
W, H = 1180, 500          # the map's viewBox
DOG_W, DOG_H = 66, 41     # Scotty's drawn size in map units; paws at the bottom of the box
WALK, BEGIN, STEP = 14, 1.5, 0.44   # seconds: the walk, the wait before it, one stride


def trail_samples(n: int = 160) -> list[tuple[float, float]]:
    """n + 1 points spaced evenly by arc length along m.smooth(TRAIL_PTS)."""
    p = [TRAIL_PTS[0], *TRAIL_PTS, TRAIL_PTS[-1]]
    dense = [p[1]]
    for i in range(1, len(p) - 2):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (x1 + (x2 - x0) / 6, y1 + (y2 - y0) / 6)
        c2 = (x2 - (x3 - x1) / 6, y2 - (y3 - y1) / 6)
        for k in range(1, 41):
            t = k / 40
            u = 1 - t
            dense.append((u**3 * x1 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * x2,
                          u**3 * y1 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * y2))
    cum = [0.0]
    for (xa, ya), (xb, yb) in zip(dense, dense[1:]):
        cum.append(cum[-1] + ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5)
    out, j = [], 0
    for k in range(n + 1):
        target = cum[-1] * k / n
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j] or 1.0
        f = (target - cum[j]) / seg
        (xa, ya), (xb, yb) = dense[j], dense[j + 1]
        out.append((xa + f * (xb - xa), ya + f * (yb - ya)))
    return out


def scotty_layer() -> str:
    pts = trail_samples()
    n = len(pts) - 1
    frames = " ".join(
        f"{100 * k / n:.4g}%{{transform:translate({100 * (x - DOG_W / 2) / W:.3f}%,{100 * (y - DOG_H) / H:.3f}%)}}"
        for k, (x, y) in enumerate(pts))
    strides = round(WALK / STEP)
    style = (
        "<style>"
        ".map-wrap{position:relative}"
        ".scotty-layer{position:absolute;inset:0;pointer-events:none;will-change:transform;"
        f"animation:scotty-trail {WALK}s linear {BEGIN}s both}}"
        f".scotty-layer svg{{position:absolute;left:0;top:0;width:{100 * DOG_W / W:.3f}%;height:auto;overflow:visible}}"
        ".scotty-layer .leg{transform-box:fill-box;transform-origin:50% 0;"
        f"animation:scotty-stride {STEP}s linear {BEGIN}s {strides}}}"
        f".scotty-layer .leg.b{{animation-delay:{BEGIN + STEP / 2}s}}"
        ".scotty-layer.wait,.scotty-layer.wait .leg{animation:none}"
        "@keyframes scotty-stride{0%,100%{transform:rotate(28deg)}50%{transform:rotate(-28deg)}}"
        f"@keyframes scotty-trail{{{frames}}}"
        "</style>")
    leg = lambda x, b: f'<rect class="leg{" b" if b else ""}" x="{x}" y="60" width="12" height="28" rx="5" fill="#1b1b1b"/>'
    dog = (
        '<svg viewBox="0 0 160 100" aria-hidden="true">'
        '<path d="M24,42 L12,6 L33,36 Z" fill="#1b1b1b"/>'
        + leg(28, True) + leg(44, False) + leg(92, False) + leg(106, True)
        + '<rect x="20" y="32" width="98" height="38" rx="15" fill="#1b1b1b"/>'
        '<path d="M22,62 l6,12 l6,-10 l6,12 l6,-10 l6,12 l6,-10 l6,12 l6,-10 l6,12 l6,-10 l6,12 l6,-10 l6,12 l6,-14 Z" fill="#1b1b1b"/>'
        '<path d="M102,26 L134,20 Q150,22 154,34 L157,44 Q150,54 136,56 L116,62 L104,52 Z" fill="#1b1b1b"/>'
        '<path d="M106,28 L109,2 L121,24 Z M119,23 L126,0 L132,21 Z" fill="#1b1b1b"/>'
        '<path d="M136,46 L157,44 L151,64 L139,60 Z" fill="#1b1b1b"/>'
        '<path d="M104,34 L116,30 L121,60 L108,62 Z" fill="#c41230"/>'
        '<path d="M107,36 L118,33 M108,44 L119,41 M109,52 L120,49 M110,34 L113,61" stroke="#f2d27a" stroke-width="1.6"/>'
        '<circle cx="133" cy="31" r="2.6" fill="#fbf7ec"/><circle cx="156" cy="38" r="3.6" fill="#000"/>'
        '</svg>')
    return style + f'<div class="scotty-layer" data-when-active aria-hidden="true">{dog}</div>'


def block() -> str:
    """The map and Scotty's layer, in the wrapper the deck carries."""
    svg = build()
    return f'<div class="map-wrap">\n{svg}\n{scotty_layer()}<span class="map-end"></span></div>'


# The generated block runs from the wrapper to the marker span at its end.
PATTERN = re.compile(r'<div class="map-wrap">.*?<span class="map-end"></span></div>', re.S)
# The bare map that the deck carried before Scotty had a layer of his own.
OLD = re.compile(r'<svg id="course-map".*?</svg>(?!</g>)', re.S)


def main() -> int:
    text = SLIDES.read_text()
    out = block()
    pat = PATTERN if PATTERN.search(text) else OLD
    if not pat.search(text):
        print(f"no map block in {SLIDES}", file=sys.stderr)
        return 1
    new = pat.sub(lambda _: out, text, count=1)
    if "--check" in sys.argv:
        if new != text:
            print(f"{SLIDES} is stale; run {Path(__file__).name}", file=sys.stderr)
            return 1
        return 0
    SLIDES.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
