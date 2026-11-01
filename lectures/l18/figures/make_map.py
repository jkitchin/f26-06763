"""Generate the course map on the second slide of the L18 deck.

The map is an inline SVG rather than an image, because its stops and side paths
are links with hover tooltips, and an <img> cannot carry either. So this script
writes the SVG straight into ../slides.md, replacing the element that starts
with <svg id="course-map"> and runs to the next </svg>.

    python3 lectures/l18/figures/make_map.py           # rewrite slides.md
    python3 lectures/l18/figures/make_map.py --check   # fail if slides.md is stale

The style follows the hand-drawn map in the L14 deck. Two rules from CLAUDE.md
shape the content: nothing past L18 is named (the route ahead is fog), and the
side paths link only to case studies, which themselves link only to released
lectures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

SLIDES = Path(__file__).resolve().parent.parent / "slides.md"

INK = "#5b4a32"
TRAIL = "#8a5a2b"
PAPER = "#fbf7ec"
RED = "#c41230"
WATER = "#6f93b3"
GREEN = "#7d9a5c"
STONE = "#cbbd9a"
FAINT = "#a89878"

# (number, x, y, tooltip title, tooltip subtitle)
STOPS = [
    (1, 50, 420, "The AI-engineering landscape and the modern toolchain",
     "The system view of ML, why engineering data is different, and the course stack: Python, uv, Git, notebooks"),
    (2, 98, 394, "Reproducible environments, version control, and experiment hygiene",
     "uv lockfiles, project layout, Git for code and DVC for data, notebook to module, MLflow run logging"),
    (3, 148, 420, "Relational databases and SQL for engineering time-series",
     "PostgreSQL over the Intel Lab sensor data: schemas, indexes, GROUP BY and window functions"),
    (4, 198, 390, "Columnar storage, Parquet, and DuckDB",
     "Row vs column stores, Parquet row groups and predicate pushdown, DuckDB for OLAP queries"),
    (5, 248, 412, "Dataframes and batch pipelines",
     "The Tennessee Eastman plant in pandas and Polars: lazy plans and pipelines that are safe to rerun"),
    (6, 298, 380, "Streaming concepts and data validation",
     "Event time, windows and watermarks for late data; pandera schemas as a gate that fails loudly"),
    (7, 342, 338, "Features for time-series models",
     "Lags, rolling windows and ARX regressors in Polars, fit with numpy.linalg.lstsq"),
    (8, 384, 300, "The machine learning workflow I, time series",
     "Forecasting reactor pressure at several horizons, time-ordered splits and honest baselines in scikit-learn"),
    (9, 428, 272, "The machine learning workflow II, regression",
     "Model families, cross-validation, capacity and learning curves on concrete strength; NARX forecasts"),
    (10, 474, 252, "The machine learning workflow III, classification, tracking and search",
     "A plant fault classifier in scikit-learn, Optuna hyperparameter search, runs recorded in MLflow"),
    (11, 520, 228, "Tensors, autodiff, training loops, and GPUs",
     "PyTorch tensors and autograd, a training loop by hand, devices and dtypes, four models that looked fine"),
    (12, 566, 208, "Architectures for engineering data: MLP, CNN, and sequence models",
     "Matching architecture to structure: CNNs, RNNs and attention; a 1D-CNN for turbofan RUL vs a tabular baseline"),
    (13, 612, 200, "Scientific machine learning: PINNs, neural ODEs and neural DAEs",
     "A PINN in JAX and Optax, a neural ODE in Diffrax and Equinox, a neural DAE with SiNDAE and Pyomo"),
    (14, 696, 214, "Uncertainty quantification in machine learning",
     "Ensembles, calibration and recalibration, conformal prediction, models with uncertainty built in"),
    (15, 742, 196, "Bayesian optimization",
     "A Gaussian-process surrogate and an acquisition function choose the next experiment, in BoTorch"),
    (16, 790, 214, "Generative AI, learning a distribution and sampling from it",
     "A Gaussian mixture and flow matching that find every root of a cubic by conditional sampling"),
    (17, 838, 262, "Large language models, what they are and how they are trained",
     "A tiny GPT: tokens, a transformer that only looks back, next-token training, sampling with temperature"),
    (18, 884, 318, "Context engineering, tools, search and retrieval",
     "What the model gets to see: tools, keyword and semantic search, re-ranking"),
]
STOP = {n: (x, y) for n, x, y, *_ in STOPS}
CAMP = (654, 222)  # fall break, between L13 and L14

# Side paths to case studies. (key, from lecture, landmark, (x, y), label,
# label anchor, field, page title, one-line summary, slug)
SIDES = [
    ("bridge", 6, "lake", (330, 462), "Civil", "start",
     "Civil and environmental engineering",
     "Separating temperature from damage on the Z24 bridge",
     "Cold weather moved the natural frequencies more than early damage did, so detection had to model temperature first",
     "bridge-health-monitoring"),
    ("bearings", 7, "boulder", (262, 300), "Mechanical", "end",
     "Mechanical and electrical engineering",
     "Near-perfect bearing fault classifiers on the CWRU benchmark",
     "Accuracy near 100% fell sharply once no bearing appeared in both training and test",
     "bearing-fault-benchmark"),
    ("load", 8, "lake", (452, 404), "Energy", "start",
     "Energy systems and policy",
     "Forecasting electricity demand",
     "GEFCom2014: lagged temperature features, weather scenarios, and quantile forecasts scored by pinball loss",
     "electric-load-forecasting"),
    ("ecg", 10, "pass", (540, 334), "Biomedical", "start",
     "Biomedical engineering",
     "Heartbeat classification and the patient split",
     "Splitting MIT-BIH by heartbeat instead of by patient inflated the reported sensitivity",
     "ecg-patient-splits"),
    ("xray", 12, "peak", (540, 132), "Imaging", "end",
     "Biomedical imaging",
     "Chest X-ray models that learned the hospital",
     "A pneumonia CNN scored well on the pooled test set and worse at a hospital it had not trained on",
     "chest-xray-shortcuts"),
    ("sepsis", 14, "glacier", (668, 138), "Health care", "end",
     "Health care analytics",
     "Validating a deployed sepsis alert",
     "An external check of a widely used proprietary alert found AUC 0.63 and sensitivity 33%",
     "sepsis-alert-validation"),
    ("alloy", 15, "peak", (790, 128), "Materials", "start",
     "Materials science and engineering",
     "Searching 800,000 shape memory alloys with expected improvement",
     "Expected improvement on a bootstrap ensemble found low-hysteresis alloys in 36 syntheses",
     "alloy-adaptive-design"),
]

# Faint lines joining related destinations. Endpoints are side keys or ints
# (lecture stops). Each carries a tooltip saying what the two share.
TIES = [
    ("ecg", "bearings",
     "Same mistake, different unit: split by patient in MIT-BIH, by bearing in CWRU (L12 splits by engine)"),
    ("xray", "sepsis",
     "Both looked strong where they were built and weaker at another hospital: validate on the population you deploy to"),
    ("bridge", "load",
     "Temperature drives both signals, so both models put temperature in first and judge what is left"),
    ("alloy", 14,
     "The alloy search took its uncertainty from a bootstrap ensemble, one of the methods in L14"),
]


def f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def smooth(points: list[tuple[float, float]], t: float = 1 / 6) -> str:
    """Catmull-Rom spline through the points, as an SVG cubic path."""
    p = [points[0], *points, points[-1]]
    d = f"M{f(p[1][0])},{f(p[1][1])}"
    for i in range(1, len(p) - 2):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p[i - 1], p[i], p[i + 1], p[i + 2]
        c1 = (x1 + (x2 - x0) * t * 2 / 2, y1 + (y2 - y0) * t * 2 / 2)
        c2 = (x2 - (x3 - x1) * t * 2 / 2, y2 - (y3 - y1) * t * 2 / 2)
        d += f" C{f(c1[0])},{f(c1[1])} {f(c2[0])},{f(c2[1])} {f(x2)},{f(y2)}"
    return d


def tree(x: float, y: float) -> str:
    return (f'<path d="M{x},{y} L{x-7},{y+16} L{x+7},{y+16} Z" fill="{GREEN}" stroke="{INK}" stroke-width="0.8"/>'
            f'<line x1="{x}" y1="{y+16}" x2="{x}" y2="{y+20}" stroke="{INK}" stroke-width="1.2"/>')


def mountain(x: float, base: float, h: float, fill: str = STONE) -> str:
    w = h * 0.75
    cap = h / 3
    return (f'<path d="M{f(x-w)},{f(base)} L{f(x)},{f(base-h)} L{f(x+w)},{f(base)} Z" fill="{fill}" stroke="{INK}" stroke-width="1.2"/>'
            f'<path d="M{f(x-w/3)},{f(base-h+cap)} L{f(x)},{f(base-h)} L{f(x+w/3)},{f(base-h+cap)} Z" fill="{PAPER}"/>')


def landmark(kind: str, x: float, y: float) -> str:
    """A small glyph centred near (x, y). Class jm-lm takes the hover colour."""
    if kind == "lake":
        return (f'<ellipse class="jm-lm" cx="{x}" cy="{y}" rx="26" ry="11" fill="{WATER}" fill-opacity="0.55" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M{x-12},{y} q4,-3 8,0 t8,0" fill="none" stroke="{PAPER}" stroke-width="1.2"/>')
    if kind == "boulder":
        return (f'<path class="jm-lm" d="M{x-16},{y+8} C{x-18},{y-4} {x-8},{y-12} {x},{y-11} C{x+10},{y-12} {x+17},{y-2} {x+15},{y+8} Z" fill="{STONE}" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M{x+12},{y+8} C{x+12},{y+2} {x+18},{y} {x+24},{y+3} L{x+25},{y+8} Z" fill="{STONE}" stroke="{INK}" stroke-width="1"/>')
    if kind == "pass":
        return (f'<path class="jm-lm" d="M{x-30},{y+10} L{x-15},{y-14} L{x-4},{y+2} Q{x},{y+5} {x+4},{y+2} L{x+15},{y-16} L{x+30},{y+10} Z" fill="{STONE}" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M{x-4},{y+2} Q{x},{y+5} {x+4},{y+2}" fill="none" stroke="{TRAIL}" stroke-width="2"/>')
    if kind == "peak":
        return (f'<path class="jm-lm" d="M{x-22},{y+14} L{x},{y-18} L{x+22},{y+14} Z" fill="{STONE}" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M{x-7},{y-8} L{x},{y-18} L{x+7},{y-8} Z" fill="{PAPER}"/>'
                f'<line x1="{x}" y1="{y-18}" x2="{x}" y2="{y-32}" stroke="{INK}" stroke-width="1.5"/>'
                f'<path d="M{x},{y-32} L{x+11},{y-28} L{x},{y-24} Z" fill="{RED}"/>')
    if kind == "glacier":
        return (f'<path class="jm-lm" d="M{x-24},{y+12} L{x-6},{y-16} L{x+4},{y-6} L{x+12},{y-14} L{x+26},{y+12} Z" fill="#dfe8ee" stroke="{INK}" stroke-width="1.2"/>'
                f'<path d="M{x-10},{y+12} L{x-4},{y} M{x+6},{y+12} L{x+10},{y+2}" stroke="{WATER}" stroke-width="1.2"/>')
    raise ValueError(kind)


def point(ref, sides: dict) -> tuple[float, float]:
    return STOP[ref] if isinstance(ref, int) else sides[ref][3]


def build() -> str:
    out: list[str] = []
    a = out.append
    label = ("A map of the course as a journey: a trail through the data lowlands (lectures 1 to 7), "
             "the machine-learning highlands (lectures 8 to 16) and down to the language coast "
             "(lectures 17 and 18), with a pin at lecture 18 marked you are here. Side paths lead from "
             "some lectures to case studies in other fields of engineering, and a dotted trail runs into "
             "fog toward the final projects")
    a(f'<svg id="course-map" viewBox="0 0 1180 500" width="100%" role="img" aria-label="{label}" '
      "style=\"font-family: Georgia, 'Times New Roman', serif; display:block; margin: 0 auto;\">")
    a('<defs><radialGradient id="jm-p" cx="50%" cy="45%" r="75%"><stop offset="0%" stop-color="#f8f1df"/>'
      '<stop offset="100%" stop-color="#e6d6b0"/></radialGradient><linearGradient id="jm-fog" x1="0" x2="1">'
      '<stop offset="0%" stop-color="#f3ead4" stop-opacity="0"/><stop offset="100%" stop-color="#f3ead4" '
      'stop-opacity="0.8"/></linearGradient></defs>')
    a(f'<rect x="4" y="4" width="1172" height="492" rx="14" fill="url(#jm-p)" stroke="{INK}" stroke-width="2"/>')
    a(f'<rect x="12" y="12" width="1156" height="476" rx="10" fill="none" stroke="{FAINT}" stroke-width="1" stroke-dasharray="2 4"/>')

    # Regions: lowland meadow, highland plateau, the sea along the coast.
    a(f'<ellipse cx="205" cy="398" rx="200" ry="76" fill="{GREEN}" opacity="0.18"/>')
    a('<ellipse cx="600" cy="220" rx="240" ry="92" fill="#b49a6a" opacity="0.18"/>')
    a(f'<path d="M630,488 C670,436 730,402 790,394 C840,388 870,372 920,370 C990,368 1080,356 1166,360 '
      f'L1166,478 Q1166,488 1156,488 Z" fill="{WATER}" opacity="0.22"/>')
    # Cliffs along the shore under L17 and L18.
    for cx, cy in ((742, 404), (758, 400), (774, 397), (860, 380), (876, 376), (892, 373)):
        a(f'<path d="M{cx},{cy} l6,-12 l6,12" fill="none" stroke="{INK}" stroke-width="1.2"/>')
    # Lighthouse on the headland.
    lx, ly = 818, 392
    a(f'<path d="M{lx-6},{ly} L{lx-4},{ly-26} L{lx+4},{ly-26} L{lx+6},{ly} Z" fill="{PAPER}" stroke="{INK}" stroke-width="1.2"/>'
      f'<rect x="{lx-5}" y="{ly-18}" width="10" height="5" fill="{RED}"/>'
      f'<rect x="{lx-5}" y="{ly-8}" width="11" height="5" fill="{RED}"/>'
      f'<path d="M{lx-6},{ly-26} L{lx},{ly-33} L{lx+6},{ly-26} Z" fill="{INK}"/>'
      f'<path d="M{lx+8},{ly-29} L{lx+34},{ly-38} L{lx+34},{ly-22} Z" fill="#f2d27a" opacity="0.7"/>')
    for wx in (960, 1010, 1060, 1110):
        a(f'<path d="M{wx},468 q8,-6 16,0 t16,0" fill="none" stroke="{WATER}" stroke-width="1.6"/>')

    for tx, ty in ((140, 452), (60, 344), (30, 234), (210, 448), (402, 380)):
        a(tree(tx, ty))
    for mx, base, h in ((488, 196, 30), (372, 214, 20), (600, 290, 22), (700, 286, 18)):
        a(mountain(mx, base, h))

    a(f'<text x="60" y="490" font-size="21" font-style="italic" fill="{INK}">The data lowlands</text>')
    a(f'<text x="60" y="318" font-size="13" fill="{INK}" opacity="0.85">L1 to L7: toolchain, databases,</text>')
    a(f'<text x="60" y="334" font-size="13" fill="{INK}" opacity="0.85">pipelines, streams, features</text>')
    a(f'<text x="400" y="66" font-size="21" font-style="italic" fill="{INK}">The machine-learning highlands</text>')
    a(f'<text x="400" y="86" font-size="13" fill="{INK}" opacity="0.85">L8 to L16: the ML workflow, deep learning, '
      'scientific ML, uncertainty, design, generative models</text>')
    a(f'<text x="652" y="460" font-size="21" font-style="italic" fill="{INK}">The language coast</text>')
    a(f'<text x="652" y="480" font-size="13" fill="{INK}" opacity="0.85">L17 and L18: language models, context</text>')

    # Ties go under everything else, so they never cover a stop.
    sides = {s[0]: s for s in SIDES}
    for u, v, tip in TIES:
        (x1, y1), (x2, y2) = point(u, sides), point(v, sides)
        a(f'<g class="jm-tie"><title>{escape(tip)}</title>'
          f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="transparent" stroke-width="12"/>'
          f'<line class="jm-tie-line" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{WATER}" stroke-width="1.6" '
          f'stroke-dasharray="1 5" stroke-linecap="round"/></g>')

    # The trail, the fall-break camp, and the dotted route into fog.
    pts = [STOP[n] for n in range(1, 14)] + [CAMP] + [STOP[n] for n in range(14, 19)]
    a(f'<path d="{smooth(pts)}" fill="none" stroke="{TRAIL}" stroke-width="4" stroke-linecap="round" stroke-dasharray="10 6"/>')
    ahead = [STOP[18], (936, 286), (1000, 262), (1060, 226), (1110, 172)]
    a(f'<path d="{smooth(ahead)}" fill="none" stroke="{FAINT}" stroke-width="3" stroke-linecap="round" stroke-dasharray="2 8"/>')
    cx, cy = CAMP
    a(f'<path d="M{cx-11},{cy+2} L{cx},{cy-14} L{cx+11},{cy+2} Z" fill="#d9a441" stroke="{INK}" stroke-width="1.2"/>'
      f'<path d="M{cx},{cy-14} L{cx-2},{cy+2} L{cx+2},{cy+2} Z" fill="{INK}"/>')
    a(f'<text x="{cx}" y="{cy+20}" font-size="11" text-anchor="middle" fill="{INK}" font-style="italic">fall break</text>')

    # Side paths: a thin dotted spur, a landmark, a field label, a link.
    for key, n, kind, (x, y), short, anchor, field, title, summary, slug in SIDES:
        sx, sy = STOP[n]
        tip = f"{field}: {title}\n{summary}\nOpens the case study, which links back to the lectures"
        dx = -32 if anchor == "end" else 32
        tx = x + dx if kind != "lake" else x + (30 if anchor == "start" else -30)
        a(f'<a class="jm-side" href="../../case-studies/{slug}.html" target="_blank"><title>{escape(tip)}</title>'
          f'<path d="M{sx},{sy} L{x},{y}" fill="none" stroke="{TRAIL}" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round"/>'
          f'{landmark(kind, x, y)}'
          f'<text x="{tx}" y="{y+5}" font-size="13" font-style="italic" text-anchor="{anchor}" fill="{INK}">{short}</text></a>')

    for n, x, y, t, sub in STOPS:
        here = n == 18
        a(f'<a class="jm-stop" href="../../lectures/l{n:02d}/notes.html" target="_blank"><title>L{n}: {escape(t)}\n{escape(sub)}</title>'
          f'<circle cx="{x}" cy="{y}" r="11" fill="{RED if here else TRAIL}" stroke="{PAPER}" stroke-width="2"/>'
          f'<text x="{x}" y="{y+4}" font-size="11" text-anchor="middle" fill="{PAPER}" font-family="sans-serif" font-weight="700">{n}</text></a>')

    # Fog past L18, unlabeled except for the signpost and the final projects.
    a('<rect x="930" y="13" width="236" height="474" fill="url(#jm-fog)"/>')
    for ex, ey, s in ((1000, 210, 0.9), (1100, 300, 1.1), (1030, 350, 1.0), (1120, 230, 0.8)):
        a(f'<g opacity="0.85" fill="#fbf8f0"><ellipse cx="{ex}" cy="{ey}" rx="{f(46*s)}" ry="{f(18*s)}"/>'
          f'<ellipse cx="{f(ex-28*s)}" cy="{f(ey+6*s)}" rx="{f(30*s)}" ry="{f(14*s)}"/>'
          f'<ellipse cx="{f(ex+30*s)}" cy="{f(ey+5*s)}" rx="{f(32*s)}" ry="{f(14*s)}"/></g>')
    a(f'<line x1="1000" y1="150" x2="1000" y2="196" stroke="{INK}" stroke-width="2.5"/>')
    a(f'<path d="M996,132 L1092,132 L1104,144 L1092,156 L996,156 Z" fill="#d8c393" stroke="{INK}" stroke-width="1.2"/>')
    a(f'<text x="1048" y="148" font-size="11.5" text-anchor="middle" fill="{INK}">still being surveyed</text>')
    a(f'<line x1="1110" y1="172" x2="1110" y2="124" stroke="{INK}" stroke-width="2.5"/>')
    a(f'<path d="M1110,124 L1144,133 L1110,142 Z" fill="{RED}"/>')
    a(f'<text x="1110" y="194" font-size="15" text-anchor="middle" fill="{INK}" font-weight="700">final projects</text>')

    # You are here.
    px, py = STOP[18]
    a(f'<circle cx="{px}" cy="{py}" r="22" fill="{RED}" opacity="0.18"/>')
    a(f'<rect x="{px+30}" y="{py+14}" width="214" height="50" rx="8" fill="{PAPER}" stroke="{RED}" stroke-width="2"/>')
    a(f'<text x="{px+137}" y="{py+35}" font-size="16" text-anchor="middle" fill="{RED}" font-weight="700">You are here: L18</text>')
    a(f'<text x="{px+137}" y="{py+54}" font-size="13" text-anchor="middle" fill="{INK}">what the model gets to see</text>')

    a(f'<circle cx="1120" cy="62" r="26" fill="{PAPER}" stroke="{INK}" stroke-width="1.2"/>')
    a(f'<path d="M1120,38 L1126,62 L1120,86 L1114,62 Z" fill="{INK}"/>')
    a(f'<path d="M1096,62 L1120,56 L1144,62 L1120,68 Z" fill="{FAINT}"/>')
    a(f'<text x="1120" y="32" font-size="13" text-anchor="middle" fill="{INK}" font-weight="700">N</text>')

    a(f'<line x1="36" y1="36" x2="76" y2="36" stroke="{TRAIL}" stroke-width="4" stroke-dasharray="10 6"/>')
    a(f'<text x="86" y="41" font-size="13" fill="{INK}">the trail so far</text>')
    a(f'<line x1="36" y1="58" x2="76" y2="58" stroke="{FAINT}" stroke-width="3" stroke-dasharray="2 8" stroke-linecap="round"/>')
    a(f'<text x="86" y="63" font-size="13" fill="{INK}">the route ahead, not yet fixed</text>')
    a(f'<line x1="36" y1="80" x2="76" y2="80" stroke="{TRAIL}" stroke-width="2" stroke-dasharray="1 4" stroke-linecap="round"/>')
    a(f'<text x="86" y="85" font-size="13" fill="{INK}">side path to a case study in another field</text>')
    a(f'<line x1="36" y1="102" x2="76" y2="102" stroke="{WATER}" stroke-width="1.6" stroke-dasharray="1 5" stroke-linecap="round"/>')
    a(f'<text x="86" y="107" font-size="13" fill="{INK}">related cases, hover for what they share</text>')
    a("</svg>")
    return "\n".join(out)


PATTERN = re.compile(r'<svg id="course-map".*?</svg>', re.S)


def main() -> int:
    text = SLIDES.read_text()
    svg = build()
    if not PATTERN.search(text):
        print(f"no <svg id=\"course-map\"> in {SLIDES}", file=sys.stderr)
        return 1
    new = PATTERN.sub(lambda _: svg, text, count=1)
    if "--check" in sys.argv:
        if new != text:
            print(f"{SLIDES} is stale; run {Path(__file__).name}", file=sys.stderr)
            return 1
        return 0
    SLIDES.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
