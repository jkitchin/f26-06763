#!/usr/bin/env python3
"""Generate the L15 figures: tokenization, context budget, sampling, embeddings.

Run with:
    uv run --with numpy,matplotlib,scikit-learn,tiktoken,openai,pypdf python make_figures.py

Every number quoted in notes.md and slides.md is printed by this script.

Six of these measurements changed what the lecture says.

  1. The "40-page PDF blows past the context window" framing in the module file
     is out of date, and the honest version is better. NASA RP-1218 is 146 pages
     and comes to 126,452 tokens under the Claude Opus 5 tokenizer. That is 13%
     of a 1M-token window: it fits. What it does not do is fit *cheaply*, and it
     fills half of a 200K-token window, so the constraint moved from "will it
     load" to "what does each question cost and which model can you route to."

  2. The latency measurement was drafted expecting long inputs to be slow. They
     are not. On Claude Haiku 4.5, going from 769 to 100,456 input tokens (130x)
     added about one second. Going from 16 to 2,048 output tokens added 22.5.
     One output token costs roughly a thousand input tokens of latency, which is
     the opposite of the intuition most students arrive with.

  3. The hallucination panel was drafted expecting a fabricated part number to
     produce a confident, low-entropy wrong answer. Measured, it produces 1.85
     bits and a 50/35 split between "1" and "2" as the leading digit. The model
     is not confident; it is also not declining. The lesson is not "entropy
     detects hallucination", it is "the model has no token for I-do-not-know
     unless the prompt gives it one" -- and when it is given one, the same
     question collapses to NOT FOUND at probability 1.000.

  4. The embedding negation probe was drafted as a footnote and turned into the
     centrepiece of the limits section. "Mechanical seal leaking" against "seal
     inspected, no leak found" scores 0.694, and "brg vibration p101 high" against
     "Operator reports growling from the drive end bearing" scores 0.532. A pair
     that means the opposite scores HIGHER than a pair that means the same thing.
     No cosine threshold separates them, and the figure shows the overlap rather
     than asserting it.

  5. The Matryoshka truncation sweep was drafted as a smooth decay curve. It is
     not monotonic on 34 records: 512 dimensions preserves 100% of the top-1
     neighbours while 1024 preserves 97%. Reported as measured, because the
     non-monotonicity is the warning -- a storage decision tuned on 34 rows is
     tuned on noise.

  6. The tokenizer-disagreement figure was drafted with two OpenAI encodings and
     one Anthropic model. Adding a second Anthropic model was the surprise:
     Claude Haiku 4.5 and Claude Opus 5 disagree with each other by 26% on the
     same datasheet, because the tokenizer changed within the vendor's own line.
     "Use the provider's tokenizer" is not enough. Use the *model's*.

Outputs (committed alongside this script):
    tokenization.png     engineering strings fragmenting, and four tokenizers disagreeing
    context-cost.png     one real report against context windows, cost, and measured latency
    next-token.png       real next-token distributions, and what grounding does to them
    embeddings.png       cosine structure of a maintenance log, against a lexical baseline
    embedding-limits.png negation, units, thresholds, and the storage trade

API calls (token counting, chat completions, embeddings) are cached in .cache/,
which is gitignored. Re-running this script after the first time costs nothing.
Set ANTHROPIC_API_KEY and OPENAI_API_KEY. Without them the script skips the
panels that need them and says so.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import time
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import tiktoken
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
AMBER = "#b8860b"
PURPLE = "#6b3fa0"
TEAL = "#0f7d8c"

plt.rcParams.update({
    "font.size": 13,
    "axes.labelsize": 13,
    "axes.titlesize": 15,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": MUTED,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})

# Model ids and prices are pinned here so the figures are reproducible. Prices
# are US dollars per million tokens, read from the providers' pricing pages on
# 2026-08-06. They change; the point of the figure is the shape, not the digits.
ANTHROPIC_MODELS = {"claude-opus-5": 5.00, "claude-haiku-4-5": 1.00}
LATENCY_MODEL = "claude-haiku-4-5"
LOGPROB_MODEL = "gpt-4.1-mini"
EMBED_MODEL = "text-embedding-3-small"

NASA_URL = "https://ntrs.nasa.gov/api/citations/19890016302/downloads/19890016302.pdf"


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------
# A pump datasheet in the register vendors actually use: units everywhere,
# tables flattened into prose, part numbers, tolerances. Written for this course
# rather than copied, so it can be redistributed, but every convention in it
# (ASME flange classes, AISI/ASTM designations, IP ratings, ISO fits) is real.
DATASHEET = """\
CENTRIFUGAL PROCESS PUMP - MODEL CP-4L/2200-XG
Document 4L-2200-XG-DS Rev. C

1. GENERAL
Single-stage, end-suction centrifugal pump conforming to ASME B73.1. Foot-mounted,
back pull-out design. Nominal capacity 2200 L/min at 45 m total dynamic head.
Maximum working pressure 10.5 MPa (1523 psig) at 20 degC. Operating temperature
range -40 degC to +120 degC. Hydrostatic test pressure 15.8 MPa held for 30 min.

2. MATERIALS OF CONSTRUCTION
Casing: ASTM A216 WCB carbon steel. Impeller: SS316L, investment cast, Ra 0.8 um
finish on wetted surfaces. Shaft: AISI 4140 quenched and tempered, 28-32 HRC.
Shaft sleeve: Alloy 20. Wear rings: Ni-resist Type 2, replaceable. Gaskets: PTFE
envelope with aramid filler. Fasteners: 1/4-20 UNC and M8x1.25 per ISO 898-1
Class 8.8.

3. DIMENSIONS AND TOLERANCES
Suction NPS 4 Class 300 RF flange per ASME B16.5. Discharge NPS 2 Class 300 RF.
Impeller bore diameter 25 mm +0.021/-0.000 (H7). Shaft diameter at coupling
25.000 mm +/-0.005 mm. Bearing housing bore 72.000 mm H7. Axial float 0.0015 in
maximum. Impeller trim range 178 mm to 210 mm; supplied trim 197 mm unless
otherwise specified on the order.

4. DRIVER AND ELECTRICALS
Motor: 3.5 kW, 3-phase, 460 V, 60 Hz, 1750 rpm nominal, TEFC, IP66, IE3 premium
efficiency. Full-load current 5.8 A. Service factor 1.15. Motor frame 132M per
IEC 60072. Terminal box torque 4.5 N-m.

5. PERFORMANCE
Best efficiency point 2200 L/min at 45 m, efficiency 78 percent, NPSHr 3.2 m.
Shutoff head 52 m. Minimum continuous stable flow 660 L/min. Flow coefficient
Cv 12.4 for the bypass control valve supplied with the skid. Vibration limit
4.5 mm/s RMS per ISO 10816-3 measured at the bearing housing.

6. INSTRUMENTATION
Bearing temperature: two K-type thermocouples, one per bearing, 4-20 mA
transmitters, range 0-150 degC, accuracy +/-0.5 percent of span. Discharge
pressure: piezoresistive transmitter, range 0-16 MPa, accuracy +/-0.25 percent
FS. Suction pressure: 0-2.5 MPa, same accuracy class.

7. SEALING
Single mechanical seal per API 682 Category 1, Type A, Arrangement 1, Plan 11
flush. Seal faces: sintered SiC vs carbon graphite. Elastomers: FKM, -20 degC to
+200 degC. Maximum seal chamber pressure 2.5 MPa.

8. MASS AND SHIPPING
Bare pump mass 148 kg. Baseplate 96 kg. Motor 62 kg. Total shipping mass 341 kg
including crate. Crate dimensions 1400 mm x 800 mm x 900 mm.
"""

# Technical English with almost no numerals, for the chars-per-token contrast.
PROSE = """\
The pump should be started against a partly closed discharge valve and brought up
to speed before the valve is opened. Opening the valve too quickly can drive the
operating point far to the right of the best efficiency point, where the radial
load on the impeller rises sharply and the shaft deflects enough to shorten seal
life. Operators sometimes assume that a wide open discharge valve is the gentlest
way to start a machine, because it presents the least resistance. The opposite is
true for a centrifugal pump, and the reason is that the power drawn rises with
flow rather than falling with it. Whenever the machine is going to be idle for an
extended period, the casing should be drained and the shaft rotated by hand at
intervals so that the bearings are not left carrying a static load in one place.
"""

# An alarm table flattened into text, which is what a PDF extractor hands you.
TABLE = """\
Tag  Service          Set point  Units  Lo-Lo  Lo     Hi     Hi-Hi
PT-101  Discharge     8.5        MPa    2.0    4.0    9.5    10.2
PT-102  Suction       0.35       MPa    0.10   0.15   1.80   2.20
TT-201  Brg NDE       65         degC   -      -      85     95
TT-202  Brg DE        65         degC   -      -      85     95
FT-301  Flow          2200       L/min  660    900    2600   2900
VT-401  Vibration     2.8        mm/s   -      -      4.5    7.1
ZT-501  Seal pot lvl  60         pct    20     30     85     92
"""

CODE = """\
def npsha(p_suction_pa, p_vapor_pa, rho, v_ms, z_m, g=9.80665):
    \"\"\"Net positive suction head available, in metres of fluid.\"\"\"
    static = (p_suction_pa - p_vapor_pa) / (rho * g)
    velocity = v_ms**2 / (2 * g)
    return static + velocity + z_m


assert abs(npsha(101325.0, 2339.0, 998.2, 1.5, 0.0) - 10.23) < 0.05
"""

# Free-text maintenance log entries, written to contain the three things that
# matter for the embeddings section: near-duplicates with no words in common,
# negations that invert the meaning, and unit variants that change the number.
# Index ranges are load-bearing for the cluster colouring below.
LOGS = [
    # 0-4: bearing noise, five ways
    "Bearing noise on pump P-101 drive end during startup",
    "Noisy bearing, P-101 DE, audible at start",
    "brg vibration p101 high at startup",
    "Operator reports growling from the drive end bearing on P-101",
    "P-101 DE bearing running rough on morning start",
    # 5-8: seal leak
    "Mechanical seal leaking, approx 8 drops/min, pump P-101",
    "Seal drip observed at P-101 seal chamber, catch pan wet",
    "P-101 mech seal weeping, no visible spray",
    "Leak from the seal gland on P-101, product on the baseplate",
    # 9-11: motor overheating
    "Motor M-101 winding temperature high, 118 degC at full load",
    "M-101 running hot, winding RTD reading 118 C",
    "Overtemperature on pump motor M-101 under load",
    # 12-14: coupling and alignment
    "Coupling guard loose, fasteners backed out on P-101",
    "Misalignment suspected P-101, laser check requested",
    "Shaft alignment out of tolerance after grout repair, P-101",
    # 15-17: instrument faults
    "PT-101 reading 0.0 MPa with pump running, transmitter suspect",
    "Discharge pressure transmitter appears failed low on P-101",
    "TT-201 thermocouple open circuit, reading drove to upscale burnout",
    # 18-21: negations and completions, same vocabulary, opposite meaning
    "P-101 seal inspected, no leak found",
    "Bearing checked, no abnormal noise detected on P-101",
    "P-101 DE bearing replaced, vibration back to 1.8 mm/s",
    "Motor M-101 temperature normal after fan cowl cleaned",
    # 22-29: unrelated events
    "Strainer differential 45 kPa, basket cleaned and refitted",
    "Impeller wear ring clearance measured 0.55 mm, above 0.40 mm limit",
    "Baseplate grout cracked at the northeast anchor bolt",
    "Suction line support hanger found detached from the pipe rack",
    "Lube oil sample taken, ISO 4406 code 20/18/15, filter changed",
    "Spare pump P-102 exercised for 30 min, no findings",
    "Painted casing where insulation had been removed for inspection",
    "Annual relief valve PSV-110 bench tested, set 11.0 MPa, passed",
    # 30-33: unit variants, same digits, different physical claim
    "Discharge pressure trending at 10.5 MPa, near the 10.2 MPa Hi-Hi",
    "Discharge pressure trending at 10.5 bar, well below the trip",
    "Bearing temperature 85 degC steady on the drive end",
    "Bearing temperature 85 degF steady on the drive end",
]

CLUSTERS = {
    "bearing noise": range(0, 5),
    "seal leak": range(5, 9),
    "motor hot": range(9, 12),
    "alignment": range(12, 15),
    "instrument": range(15, 18),
    "resolved / negated": range(18, 22),
    "other": range(22, 30),
    "unit variants": range(30, 34),
}

# Pairs the notes quote. (i, j, label) with labels used by the limits figure.
SAME_MEANING = [(0, 1), (0, 2), (1, 2), (0, 3), (2, 3), (3, 4), (5, 6), (5, 7),
                (6, 8), (9, 10), (9, 11), (13, 14), (15, 16)]
OPPOSITE_MEANING = [(5, 18), (0, 19), (1, 19), (0, 20), (2, 20), (9, 21), (30, 31), (32, 33)]

CL100K = tiktoken.get_encoding("cl100k_base")
O200K = tiktoken.get_encoding("o200k_base")


# --------------------------------------------------------------------------
# Cached provider calls
# --------------------------------------------------------------------------
def _cache_path(kind: str, payload: str) -> Path:
    h = hashlib.sha1(payload.encode()).hexdigest()[:20]
    return CACHE / f"{kind}_{h}.json"


def have(var: str) -> bool:
    return bool(os.environ.get(var))


def anthropic_count(model: str, text: str) -> int:
    """Tokens as the provider counts them, for the model you will actually call.

    This is a network call. There is no offline Anthropic tokenizer, which is a
    design fact worth noticing rather than a gap to work around.
    """
    path = _cache_path("count", model + "|" + str(len(text)) + "|" + text[:400])
    if path.exists():
        return json.loads(path.read_text())["input_tokens"]
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages/count_tokens",
        data=body,
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.load(resp)
    path.write_text(json.dumps(out))
    return out["input_tokens"]


def anthropic_message(text: str, max_tokens: int) -> tuple[float, dict]:
    """One uncached round trip, timed. Used only by the latency sweep."""
    body = json.dumps({
        "model": LATENCY_MODEL, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        out = json.load(resp)
    return time.perf_counter() - t0, out["usage"]


def openai_top_logprobs(prompt: str, n: int = 20, rep: int = 0) -> list[tuple[str, float]]:
    """The next-token distribution the sampler actually draws from.

    `rep` exists only so the same prompt can be asked more than once: the
    provider does not return a bit-identical distribution on repeat calls, and
    measuring that spread is part of the point.
    """
    path = _cache_path("logprob", f"{LOGPROB_MODEL}|{rep}|{prompt}")
    if path.exists():
        return [(t, p) for t, p in json.loads(path.read_text())]
    from openai import OpenAI

    resp = OpenAI().chat.completions.create(
        model=LOGPROB_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1, temperature=1.0, logprobs=True, top_logprobs=n,
    )
    dist = [(t.token, math.exp(t.logprob))
            for t in resp.choices[0].logprobs.content[0].top_logprobs]
    path.write_text(json.dumps(dist))
    return dist


def openai_embed(texts: list[str], dims: int | None = None) -> np.ndarray:
    path = CACHE / f"embed_{EMBED_MODEL}_{dims}_{hashlib.sha1(json.dumps(texts).encode()).hexdigest()[:16]}.npy"
    if path.exists():
        return np.load(path)
    from openai import OpenAI

    kwargs = {"model": EMBED_MODEL, "input": texts}
    if dims:
        kwargs["dimensions"] = dims
    resp = OpenAI().embeddings.create(**kwargs)
    vecs = np.array([d.embedding for d in resp.data], dtype=np.float64)
    np.save(path, vecs)
    return vecs


def unit_rows(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def load_report_text() -> tuple[str, list[str]]:
    """NASA RP-1218, the report behind the airfoil dataset used in L9 and L13.

    A 1989 scan, so the text layer is OCR. That is the realistic case and it is
    the point: you pay tokens for whatever your extractor produces, including
    the noise.
    """
    txt = CACHE / "rp1218.txt"
    pages_file = CACHE / "rp1218_pages.json"
    if txt.exists() and pages_file.exists():
        return txt.read_text(), json.loads(pages_file.read_text())
    pdf = CACHE / "rp1218.pdf"
    if not pdf.exists():
        urllib.request.urlretrieve(NASA_URL, pdf)
    import pypdf

    reader = pypdf.PdfReader(str(pdf))
    pages = [p.extract_text() or "" for p in reader.pages]
    txt.write_text("\n".join(pages))
    pages_file.write_text(json.dumps(pages))
    return "\n".join(pages), pages


# --------------------------------------------------------------------------
# Figure 1: tokenization
# --------------------------------------------------------------------------
FRAGMENT_STRINGS = [
    "10.5 MPa",
    "AISI 4140",
    "Ø25",
    "±0.05 mm",
    "P/N 4L-2200-XG",
    "1500 rpm",
    "SS316L",
    "Ra 0.8 µm",
]

TEXT_KINDS = [
    ("technical\nprose", PROSE),
    ("maintenance\nlog", "\n".join(LOGS)),
    ("pump\ndatasheet", DATASHEET),
    ("python\ncode", CODE),
    ("alarm\ntable", TABLE),
]


def figure_tokenization() -> dict:
    print("\n=== figure 1: tokenization ===")

    print("\n  engineering strings, cl100k_base:")
    frags = []
    for s in FRAGMENT_STRINGS:
        toks = [CL100K.decode([t]) for t in CL100K.encode(s)]
        o = [O200K.decode([t]) for t in O200K.encode(s)]
        frags.append((s, toks))
        print(f"    {s!r:20s} {len(s):3d} chars -> {len(toks):2d} tokens {toks}"
              f"   (o200k: {len(o)})")

    print("\n  characters per token by text kind:")
    kinds = []
    for label, text in TEXT_KINDS:
        n = len(CL100K.encode(text))
        kinds.append((label.replace("\n", " "), len(text), n, len(text) / n))
        print(f"    {label.replace(chr(10),' '):20s} {len(text):6d} chars"
              f" {n:5d} tokens  {len(text)/n:5.2f} chars/token")

    disagreement = {}
    if have("ANTHROPIC_API_KEY"):
        print("\n  the same datasheet, four tokenizers:")
        disagreement["cl100k_base (OpenAI)"] = len(CL100K.encode(DATASHEET))
        disagreement["o200k_base (OpenAI)"] = len(O200K.encode(DATASHEET))
        for m in ANTHROPIC_MODELS:
            disagreement[m] = anthropic_count(m, DATASHEET)
        base = disagreement["cl100k_base (OpenAI)"]
        for k, v in disagreement.items():
            print(f"    {k:24s} {v:6d} tokens  ({v/base:+.2f}x cl100k)")
    else:
        print("\n  [skipped tokenizer disagreement: no ANTHROPIC_API_KEY]")

    fig = plt.figure(figsize=(16.4, 5.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.60, 0.82, 0.92], wspace=0.40)

    # -- left: fragments as boxes --------------------------------------------
    ax = fig.add_subplot(gs[0])
    ax.set_xlim(0, 1.06)
    ax.set_ylim(-0.6, len(frags) - 0.3)
    ax.axis("off")
    ax.set_title("Engineering strings, tokenized", loc="left", pad=14)
    for row, (s, toks) in enumerate(frags):
        y = len(frags) - 1 - row
        ax.text(-0.005, y + 0.22, s, ha="right", va="center", fontsize=12.5,
                family="monospace", color=INK, transform=ax.transData)
        x = 0.30
        for k, t in enumerate(toks):
            shown = t.replace(" ", "␣")
            if not shown.strip("�"):
                shown = "??"          # a byte fragment that is not a character
            w = max(0.030, 0.021 * len(shown) + 0.020)
            colour = CMU_RED if "�" in t else (BLUE if k % 2 == 0 else TEAL)
            ax.add_patch(mpatches.FancyBboxPatch(
                (x, y - 0.02), w, 0.46, boxstyle="round,pad=0.008",
                linewidth=0, facecolor=colour, alpha=0.16))
            ax.text(x + w / 2, y + 0.21, shown, ha="center", va="center",
                    fontsize=11, family="monospace", color=colour)
            x += w + 0.008
        ax.text(x + 0.018, y + 0.21, f"{len(toks)}", ha="left", va="center",
                fontsize=12.5, color=INK, fontweight="bold")
    ax.text(0.30, -0.44, "cl100k_base tokens   ␣ = leading space   red = broken byte pair",
            ha="left", va="center", fontsize=10.5, color=MUTED)

    # -- middle: chars per token ---------------------------------------------
    ax2 = fig.add_subplot(gs[1])
    names = [k[0].replace("\n", " ") for k in TEXT_KINDS]
    vals = [k[3] for k in kinds]
    colours = [GREEN, TEAL, BLUE, PURPLE, CMU_RED]
    bars = ax2.barh(range(len(vals))[::-1], vals, color=colours, alpha=0.85, height=0.62)
    ax2.set_yticks(range(len(vals))[::-1])
    ax2.set_yticklabels(names, fontsize=11.5)
    ax2.set_xlabel("characters per token")
    ax2.set_title("What a token is worth", loc="left", pad=14)
    ax2.set_xlim(0, max(vals) * 1.30)
    for b, v in zip(bars, vals):
        ax2.text(v + 0.09, b.get_y() + b.get_height() / 2, f"{v:.2f}",
                 va="center", fontsize=11.5, color=INK)
    ax2.axvline(vals[0], color=MUTED, lw=1, ls=":")

    # -- right: tokenizer disagreement ---------------------------------------
    ax3 = fig.add_subplot(gs[2])
    if disagreement:
        order = ["cl100k_base (OpenAI)", "o200k_base (OpenAI)",
                 "claude-haiku-4-5", "claude-opus-5"]
        vals3 = [disagreement[k] for k in order]
        cols3 = [MUTED, MUTED, AMBER, CMU_RED]
        short = ["cl100k\nOpenAI", "o200k\nOpenAI", "Haiku 4.5\nAnthropic",
                 "Opus 5\nAnthropic"]
        bars3 = ax3.bar(range(4), vals3, color=cols3, alpha=0.85, width=0.64)
        ax3.set_xticks(range(4))
        ax3.set_xticklabels(short, fontsize=10.5)
        ax3.set_ylabel("tokens in the datasheet")
        ax3.set_ylim(0, max(vals3) * 1.30)
        base = vals3[0]
        for k, (b, v) in enumerate(zip(bars3, vals3)):
            rel = "baseline" if k == 0 else f"{v/base - 1:+.0%}"
            ax3.text(b.get_x() + b.get_width() / 2, v + max(vals3) * 0.025,
                     f"{v:,}\n{rel}", ha="center", fontsize=11, color=INK)
        ax3.set_title(f"The same {len(DATASHEET):,} characters", loc="left", pad=14)
    else:
        ax3.axis("off")
        ax3.text(0.5, 0.5, "needs ANTHROPIC_API_KEY", ha="center", color=MUTED)

    fig.savefig(HERE / "tokenization.png")
    plt.close(fig)
    return {"kinds": kinds, "disagreement": disagreement, "fragments": frags}


# --------------------------------------------------------------------------
# Figure 2: context budget, cost, latency
# --------------------------------------------------------------------------
CONTEXT_WINDOWS = {"Claude Haiku 4.5\n200K": 200_000, "Claude Opus 5\n1M": 1_000_000}


def figure_context_cost() -> dict:
    print("\n=== figure 2: context, cost, latency ===")
    text, pages = load_report_text()
    per_page = [len(CL100K.encode(p)) for p in pages]
    cum = np.cumsum(per_page)
    print(f"  NASA RP-1218: {len(pages)} pages, {len(text):,} characters")
    print(f"    cl100k_base           {len(CL100K.encode(text)):,} tokens")
    counts = {"cl100k_base": len(CL100K.encode(text))}
    if have("ANTHROPIC_API_KEY"):
        for m in ANTHROPIC_MODELS:
            counts[m] = anthropic_count(m, text)
            print(f"    {m:22s}{counts[m]:,} tokens")
        under = 1 - counts["cl100k_base"] / counts["claude-opus-5"]
        print(f"    estimating Opus 5 with tiktoken understates by {under:.1%}")
    print(f"    median tokens/page {int(np.median(per_page))}, "
          f"max {max(per_page)}, chars/token {len(text)/counts['cl100k_base']:.2f}")

    lat = measure_latency()

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16.0, 5.3),
                                        gridspec_kw={"wspace": 0.30})

    # -- left: cumulative tokens vs windows -----------------------------------
    pages_x = np.arange(1, len(cum) + 1)
    total_o = counts.get("claude-opus-5")
    ax1.plot(pages_x, cum / 1000, color=BLUE, lw=2.2,
             label=f"tiktoken's guess ({counts['cl100k_base']/1000:.0f}K)")
    ax1.fill_between(pages_x, 0, cum / 1000, color=BLUE, alpha=0.10)
    if total_o:
        scale = total_o / counts["cl100k_base"]
        ax1.plot(pages_x, cum * scale / 1000, color=CMU_RED, lw=2.2,
                 label=f"what Claude Opus 5 bills ({total_o/1000:.0f}K)")
        ax1.fill_between(pages_x, cum / 1000, cum * scale / 1000,
                         color=CMU_RED, alpha=0.10)
        ax1.annotate("31% of the bill,\ninvisible to tiktoken",
                     xy=(len(cum) * 0.86, (cum[-1] * (1 + scale) / 2) / 1000),
                     xytext=(len(cum) * 0.30, 150), fontsize=11, color=CMU_RED,
                     arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))
    ax1.axhline(200, color=AMBER, lw=1.4, ls="--")
    ax1.text(len(cum), 204, "Claude Haiku 4.5 context window, 200K",
             ha="right", fontsize=10.5, color=AMBER)
    ax1.set_xlabel("pages of the report, cumulative")
    ax1.set_ylabel("thousands of tokens")
    ax1.set_title(f"One {len(pages)}-page report", loc="left", pad=12)
    ax1.set_ylim(0, 235)
    ax1.set_xlim(0, len(cum) + 2)
    ax1.legend(fontsize=10, frameon=False, loc="upper left")

    # -- middle: cost per question -------------------------------------------
    doc = np.logspace(3, 6, 60)
    for name, price, colour in [("Claude Opus 5, $5/MTok", 5.0, CMU_RED),
                                ("Claude Haiku 4.5, $1/MTok", 1.0, AMBER)]:
        ax2.plot(doc, doc * price / 1e6, color=colour, lw=2.2, label=name)
        ax2.plot(doc, doc * price * 0.1 / 1e6, color=colour, lw=1.6, ls=":",
                 label=name.split(",")[0] + ", cached read")
    if total_o:
        ax2.axvline(total_o, color=MUTED, lw=1, ls="--")
        ax2.text(total_o * 0.90, 2e-4, "this report", rotation=90, ha="right",
                 va="bottom", fontsize=10.5, color=MUTED)
        ax2.plot([total_o], [total_o * 5 / 1e6], "o", color=CMU_RED, ms=7, zorder=5)
        ax2.annotate(f"${total_o*5/1e6:.2f} every time\nyou ask a question",
                     xy=(total_o, total_o * 5 / 1e6),
                     xytext=(1.6e3, 0.9), fontsize=11, color=CMU_RED,
                     arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))
    ax2.set_xscale("log")
    ax2.set_yscale("log")
    ax2.set_ylim(5e-5, 8.0)
    ax2.set_xlabel("input tokens in the prompt")
    ax2.set_ylabel("US dollars per call")
    ax2.set_title("What re-sending it costs", loc="left", pad=12)
    ax2.legend(fontsize=9.5, frameon=False, loc="lower right")

    # -- right: latency -------------------------------------------------------
    if lat:
        for pts, colour, label, key in [
            (lat["input_sweep"], BLUE, "input tokens (max_tokens = 16)", "in"),
            (lat["output_sweep"], CMU_RED, "output tokens (39-token prompt)", "out"),
        ]:
            xs = [p[0] if key == "in" else p[1] for p in pts]
            for x, p in zip(xs, pts):
                ax3.plot([x] * len(p[3]), p[3], "o", color=colour, ms=4.5, alpha=0.30)
            ax3.plot(xs, [p[2] for p in pts], "-o", color=colour, lw=2.2, ms=7, label=label)
        d_in = lat["input_sweep"][-1][2] - lat["input_sweep"][0][2]
        d_out = lat["output_sweep"][-1][2] - lat["output_sweep"][0][2]
        ax3.set_xscale("log")
        ax3.set_xlabel("tokens")
        ax3.set_ylabel("wall-clock seconds per call")
        ax3.set_title(f"Latency, measured on {LATENCY_MODEL}", loc="left", pad=12)
        ax3.legend(fontsize=10, frameon=False, loc="upper left")
        ax3.text(0.97, 0.42,
                 f"130x more input:  {d_in:+.1f} s\n128x more output: {d_out:+.0f} s",
                 transform=ax3.transAxes, ha="right", fontsize=11.5, color=INK)
        ax3.text(0.97, 0.30, "faint dots are the individual repeats",
                 transform=ax3.transAxes, ha="right", fontsize=10, color=MUTED)
    else:
        ax3.axis("off")
        ax3.text(0.5, 0.5, "needs ANTHROPIC_API_KEY", ha="center", color=MUTED)

    fig.savefig(HERE / "context-cost.png")
    plt.close(fig)
    return {"counts": counts, "pages": len(pages), "chars": len(text),
            "per_page": per_page, "latency": lat}


def measure_latency(reps: int = 3) -> dict | None:
    """Wall clock against input length and against output length.

    Cached, because it is the one part of this script that spends real money and
    real time. Delete .cache/latency.json to re-measure.
    """
    path = CACHE / "latency.json"
    if path.exists():
        d = json.loads(path.read_text())
        print(f"  latency (cached, {d['model']}):")
        for p in d["input_sweep"]:
            print(f"    in={p[0]:7,d} out={p[1]:5d}  median {p[2]:5.2f}s")
        for p in d["output_sweep"]:
            print(f"    in={p[0]:7,d} out={p[1]:5d}  median {p[2]:5.2f}s")
        return d
    if not have("ANTHROPIC_API_KEY"):
        print("  [skipped latency: no ANTHROPIC_API_KEY]")
        return None
    text, _ = load_report_text()
    rows_in, rows_out = [], []
    for frac in [0.01, 0.04, 0.16, 0.5, 1.0]:
        prompt = text[: int(len(text) * frac)] + "\n\nReply with the single word OK."
        ts, usage = [], None
        for _ in range(reps):
            dt, usage = anthropic_message(prompt, 16)
            ts.append(round(dt, 3))
        rows_in.append([usage["input_tokens"], usage["output_tokens"],
                        statistics.median(ts), ts])
    for n in [16, 64, 256, 1024, 2048]:
        prompt = ("Write a maintenance procedure for a centrifugal pump mechanical "
                  "seal replacement. Write continuously until you are cut off; aim "
                  f"for about {n*4} words.")
        ts, usage = [], None
        for _ in range(reps):
            dt, usage = anthropic_message(prompt, n)
            ts.append(round(dt, 3))
        rows_out.append([usage["input_tokens"], usage["output_tokens"],
                         statistics.median(ts), ts])
    d = {"model": LATENCY_MODEL, "input_sweep": rows_in, "output_sweep": rows_out}
    path.write_text(json.dumps(d, indent=1))
    return d


# --------------------------------------------------------------------------
# Figure 3: next-token distributions
# --------------------------------------------------------------------------
CASES = {
    "grounded": (
        "the value is in the prompt",
        "Answer with a number only.\n"
        "Datasheet: CENTRIFUGAL PROCESS PUMP MODEL CP-4L/2200-XG. "
        "Maximum working pressure 10.5 MPa at 20 C. Motor 3.5 kW.\n"
        "Question: what is the maximum working pressure in MPa?\nAnswer:"),
    "fabricated": (
        "the part number does not exist",
        "Answer with a number only.\n"
        "Question: what is the maximum working pressure in MPa of the "
        "Kessler-Voss KV-7710/B process pump?\nAnswer:"),
    "escape_hatch": (
        "same gap, but NOT FOUND is allowed",
        "Answer with a number only, or with the words NOT FOUND if the answer "
        "is not in the text below.\n"
        "Datasheet: CENTRIFUGAL PROCESS PUMP MODEL CP-4L/2200-XG. Motor 3.5 kW, "
        "1750 rpm. Impeller SS316L.\n"
        "Question: what is the maximum working pressure in MPa?\nAnswer:"),
}


def entropy_bits(dist: list[tuple[str, float]]) -> float:
    total = sum(p for _, p in dist)
    return -sum((p / total) * math.log2(p / total) for _, p in dist if p > 0)


def resample(dist: list[tuple[str, float]], temperature: float, top_p: float = 1.0):
    """Apply the two sampling knobs to a measured distribution, offline."""
    toks = [t for t, _ in dist]
    p = np.array([q for _, q in dist], dtype=float)
    p = np.clip(p, 1e-12, None)
    logits = np.log(p)
    z = logits / max(temperature, 1e-6)
    q = np.exp(z - z.max())
    q /= q.sum()
    order = np.argsort(-q)
    keep, run = [], 0.0
    for idx in order:
        keep.append(idx)
        run += q[idx]
        if run >= top_p:
            break
    mask = np.zeros_like(q)
    mask[keep] = q[keep]
    if mask.sum() > 0:
        mask /= mask.sum()
    return toks, mask


def figure_next_token() -> dict:
    print("\n=== figure 3: next-token distributions ===")
    if not have("OPENAI_API_KEY"):
        print("  [skipped: no OPENAI_API_KEY]")
        return {}
    dists, ents = {}, {}
    for key, (label, prompt) in CASES.items():
        d = openai_top_logprobs(prompt)
        dists[key] = d
        ents[key] = entropy_bits(d)
        print(f"  {key:14s} entropy {ents[key]:5.2f} bits   top: "
              + ", ".join(f"{t!r}={p:.3f}" for t, p in d[:4]))

    open_prompt = ("Complete this sentence with one word and nothing else.\n"
                   "The most common cause of premature bearing failure in "
                   "process pumps is")
    open_d = openai_top_logprobs(open_prompt)
    ents["open"] = entropy_bits(open_d)
    print(f"  {'open-ended':14s} entropy {ents['open']:5.2f} bits   top: "
          + ", ".join(f"{t!r}={p:.3f}" for t, p in open_d[:4]))

    # The same prompt, asked five times. The distribution is not reproducible.
    reps = [openai_top_logprobs(open_prompt, rep=r) for r in range(5)]
    lead = [d[0][1] for d in reps]
    rep_ent = [entropy_bits(d) for d in reps]
    print(f"  same prompt x5: leading-token probability {min(lead):.3f} to {max(lead):.3f}, "
          f"entropy {min(rep_ent):.2f} to {max(rep_ent):.2f} bits")

    fig, axes = plt.subplots(1, 4, figsize=(17.0, 4.9),
                             gridspec_kw={"wspace": 0.44})
    panels = [("grounded", GREEN), ("fabricated", CMU_RED), ("escape_hatch", BLUE)]
    for ax, (key, colour) in zip(axes[:3], panels):
        d = [(t, p) for t, p in dists[key] if p >= 0.004][:8]
        hidden = len(dists[key]) - len(d)
        toks = [repr(t)[1:-1] for t, _ in d]
        ps = [p for _, p in d]
        ys = [-r for r in range(len(ps))]
        ax.barh(ys, ps, color=colour, alpha=0.85, height=0.62)
        ax.set_yticks(ys)
        ax.set_yticklabels(toks, fontsize=11.5, family="monospace")
        ax.set_xlim(0, 1.08)
        ax.set_ylim(-7.6, 1.1)
        ax.set_xlabel("probability of coming next")
        ax.set_title(CASES[key][0], loc="left", pad=12, fontsize=12.5)
        ax.text(1.06, -7.3, f"+ {hidden} more below 0.4%", ha="right",
                fontsize=10, color=MUTED)
        ax.text(1.06, 0.75, f"{ents[key]:.2f} bits", ha="right", va="center",
                fontsize=12.5, color=colour, fontweight="bold")

    ax = axes[3]
    top = open_d[:4]
    labels = [repr(t)[1:-1] for t, _ in top]
    width = 0.2
    for k, (temp, top_p, colour, label) in enumerate([
            (0.0001, 1.0, BLUE, "T = 0"),
            (1.0, 1.0, PURPLE, "T = 1 (measured)"),
            (2.0, 1.0, AMBER, "T = 2"),
            (1.0, 0.9, GREEN, "T = 1, top-p 0.9")]):
        _, q = resample(open_d, temp, top_p)
        ax.bar(np.arange(len(top)) + (k - 1.5) * width, q[:len(top)],
               width=width, color=colour, alpha=0.85, label=label)
    ax.set_xticks(range(len(top)))
    ax.set_xticklabels(labels, fontsize=11, family="monospace")
    ax.set_xlabel("the four most likely next tokens")
    ax.set_ylabel("probability after the knob")
    ax.set_title("Two sampling knobs", loc="left", pad=12, fontsize=12.5)
    ax.legend(fontsize=9.5, frameon=False)
    ax.set_ylim(0, 1.12)

    fig.savefig(HERE / "next-token.png")
    plt.close(fig)
    return {"entropies": ents, "dists": {k: v[:8] for k, v in dists.items()},
            "open": open_d[:8], "repeat_lead": lead, "repeat_entropy": rep_ent}


# --------------------------------------------------------------------------
# Figures 4 and 5: embeddings
# --------------------------------------------------------------------------
def figure_embeddings() -> dict:
    print("\n=== figures 4 and 5: embeddings ===")
    if not have("OPENAI_API_KEY"):
        print("  [skipped: no OPENAI_API_KEY]")
        return {}
    E = unit_rows(openai_embed(LOGS))
    S = E @ E.T
    tf = TfidfVectorizer().fit_transform(LOGS)
    T = unit_rows(np.asarray(tf.todense()))
    L = T @ T.T
    print(f"  {len(LOGS)} log entries, {E.shape[1]}-dimensional embeddings")

    iu = np.triu_indices(len(LOGS), 1)
    same = np.array([S[i, j] for i, j in SAME_MEANING])
    opp = np.array([S[i, j] for i, j in OPPOSITE_MEANING])
    same_l = np.array([L[i, j] for i, j in SAME_MEANING])
    labelled = set(map(tuple, SAME_MEANING)) | set(map(tuple, OPPOSITE_MEANING))
    other = np.array([S[i, j] for i, j in zip(*iu) if (i, j) not in labelled])

    print("\n  pairs that describe the same event:")
    for i, j in SAME_MEANING:
        print(f"    cos {S[i,j]:.3f}  tf-idf {L[i,j]:.3f}   {LOGS[i][:40]:42s} | {LOGS[j][:40]}")
    print("\n  pairs that describe the opposite:")
    for i, j in OPPOSITE_MEANING:
        print(f"    cos {S[i,j]:.3f}  tf-idf {L[i,j]:.3f}   {LOGS[i][:40]:42s} | {LOGS[j][:40]}")
    print(f"\n  same-event   cos: min {same.min():.3f}  median {np.median(same):.3f}  max {same.max():.3f}")
    print(f"  opposite     cos: min {opp.min():.3f}  median {np.median(opp):.3f}  max {opp.max():.3f}")
    print(f"  everything else : median {np.median(other):.3f}  max {other.max():.3f}")
    print(f"  overlap: {(opp > same.min()).sum()}/{len(opp)} opposite-meaning pairs score "
          f"above the weakest true match ({same.min():.3f})")

    # dimension sweep
    nn_full = [int(np.argsort(-S[i])[1]) for i in range(len(LOGS))]
    dims = [1536, 1024, 512, 256, 128, 64, 32]
    sweep = []
    print("\n  truncating the vector (Matryoshka):")
    for d in dims:
        Ed = E if d == E.shape[1] else unit_rows(openai_embed(LOGS, dims=d))
        Sd = Ed @ Ed.T
        nn_d = [int(np.argsort(-Sd[i])[1]) for i in range(len(LOGS))]
        agree = float(np.mean([a == b for a, b in zip(nn_full, nn_d)]))
        drift = float(np.abs(Sd - S)[iu].mean())
        sweep.append((d, agree, drift))
        print(f"    {d:5d} dims  {d*4:6d} bytes/vector  top-1 neighbour agreement "
              f"{agree:6.1%}  mean |Δcos| {drift:.4f}")

    _plot_embedding_structure(S, L, E)
    _plot_embedding_limits(S, same, opp, other, sweep)
    return {"S": S, "L": L, "same": same, "opp": opp, "other": other, "sweep": sweep,
            "same_lex": same_l}


def _plot_embedding_structure(S, L, E):
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16.2, 5.2),
                                        gridspec_kw={"wspace": 0.30})

    im = ax1.imshow(S, cmap="magma", vmin=0.15, vmax=1.0)
    ax1.set_title("Cosine similarity, 34 log entries", loc="left", pad=12)
    bounds, labels = [], []
    for name, rng in CLUSTERS.items():
        bounds.append(rng.stop)
        labels.append((name, (rng.start + rng.stop - 1) / 2))
    for b in bounds[:-1]:
        ax1.axhline(b - 0.5, color="white", lw=1.1)
        ax1.axvline(b - 0.5, color="white", lw=1.1)
    ax1.set_yticks([c for _, c in labels])
    ax1.set_yticklabels([n for n, _ in labels], fontsize=10)
    ax1.set_xticks([c for _, c in labels])
    ax1.set_xticklabels([n for n, _ in labels], fontsize=9, rotation=45, ha="right")
    fig.colorbar(im, ax=ax1, fraction=0.046, pad=0.03)

    iu = np.triu_indices(len(LOGS), 1)
    ax2.scatter(L[iu], S[iu], s=16, color=MUTED, alpha=0.35, label="all pairs")
    sx = [L[i, j] for i, j in SAME_MEANING]
    sy = [S[i, j] for i, j in SAME_MEANING]
    ax2.scatter(sx, sy, s=58, color=GREEN, zorder=4, label="same event")
    ox = [L[i, j] for i, j in OPPOSITE_MEANING]
    oy = [S[i, j] for i, j in OPPOSITE_MEANING]
    ax2.scatter(ox, oy, s=58, color=CMU_RED, marker="X", zorder=4, label="opposite meaning")
    worst = min(zip(sx, sy), key=lambda p: p[0])
    ax2.annotate(f"not one word in common,\nand still {worst[1]:.2f}",
                 xy=worst, xytext=(0.26, 0.36), fontsize=10.5, color=GREEN,
                 arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.2))
    hottest = max(zip(ox, oy), key=lambda p: p[1])
    ax2.annotate('"85 degC" against\n"85 degF": 0.97',
                 xy=hottest, xytext=(0.44, 0.86), fontsize=10.5, color=CMU_RED,
                 ha="right",
                 arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))
    ax2.set_xlabel("TF-IDF cosine (words in common)")
    ax2.set_ylabel("embedding cosine")
    ax2.set_title("Embeddings against a lexical baseline", loc="left", pad=12)
    ax2.legend(fontsize=10, frameon=False, loc="lower right")

    xy = PCA(n_components=2, random_state=0).fit_transform(E)
    palette = [CMU_RED, BLUE, AMBER, GREEN, PURPLE, TEAL, MUTED, "#8b5a00"]
    for (name, rng), colour in zip(CLUSTERS.items(), palette):
        idx = list(rng)
        ax3.scatter(xy[idx, 0], xy[idx, 1], s=70, color=colour, alpha=0.85, label=name)
    ax3.set_xlabel("first principal component")
    ax3.set_ylabel("second principal component")
    ax3.set_title("The same vectors, projected to 2-D", loc="left", pad=12)
    ax3.legend(fontsize=9, frameon=False, ncol=2, loc="best")

    fig.savefig(HERE / "embeddings.png")
    plt.close(fig)


def _plot_embedding_limits(S, same, opp, other, sweep):
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16.2, 5.2),
                                        gridspec_kw={"wspace": 0.30})

    rng = np.random.default_rng(0)
    for k, (vals, colour, name) in enumerate([
            (other, MUTED, "unrelated"), (same, GREEN, "same event"),
            (opp, CMU_RED, "opposite meaning")]):
        ax1.scatter(np.full(len(vals), k) + rng.normal(0, 0.055, len(vals)), vals,
                    s=48, color=colour, alpha=0.75)
        ax1.plot([k - 0.28, k + 0.28], [np.median(vals)] * 2, color=colour, lw=2.6)
    ax1.set_xticks(range(3))
    ax1.set_xticklabels(["unrelated", "same event", "opposite meaning"], fontsize=11)
    ax1.set_ylabel("embedding cosine")
    ax1.set_title("Cosine does not know about negation", loc="left", pad=12)
    ax1.axhspan(same.min(), opp.max(), color=CMU_RED, alpha=0.07)
    ax1.set_ylim(0.05, 1.16)
    ax1.text(0.02, 0.965, "every cut through the shaded band\ngets something wrong",
             transform=ax1.transAxes, va="top", fontsize=10.5, color=CMU_RED)

    # Restricted to the hand-labelled pairs: given two entries about the same
    # equipment and symptom, can a threshold tell "it happened" from "it did not"?
    thresholds = np.linspace(0.50, 0.80, 200)
    prec, rec = [], []
    for t in thresholds:
        tp = (same >= t).sum()
        fp = (opp >= t).sum()
        prec.append(tp / (tp + fp) if tp + fp else np.nan)
        rec.append(tp / len(same))
    ax2.plot(thresholds, rec, color=GREEN, lw=2.2, label="recall of true matches")
    ax2.plot(thresholds, prec, color=CMU_RED, lw=2.2, label="precision")
    best_p = float(np.nanmax(prec))
    at = float(thresholds[int(np.nanargmax(prec))])
    ax2.axhline(best_p, color=MUTED, lw=1, ls=":")
    ax2.annotate(f"precision never gets above {best_p:.2f}.\n"
                 f"Wherever you cut, you are either\nmissing true matches or "
                 f"admitting\npairs that mean the opposite.",
                 xy=(0.52, best_p), xytext=(0.545, 0.22), fontsize=10.5, color=INK,
                 arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1))
    ax2.set_xlabel("cosine threshold for calling a pair a duplicate")
    ax2.set_ylabel("fraction, on the 21 labelled pairs")
    ax2.set_title("Choosing the threshold", loc="left", pad=12)
    ax2.legend(fontsize=10, frameon=False, loc="lower left")
    ax2.set_ylim(-0.03, 1.08)
    print(f"  best precision over the sweep {best_p:.2f} (at threshold {at:.2f}); "
          f"{(opp >= 0.6).sum()}/{len(opp)} opposite pairs survive a 0.60 cut")

    dims = [d for d, _, _ in sweep]
    agree = [a for _, a, _ in sweep]
    ax3.plot(dims, [a * 100 for a in agree], "-o", color=BLUE, lw=2.2, ms=7)
    ax3.set_xscale("log", base=2)
    ax3.set_xticks(dims)
    ax3.set_xticklabels([f"{d}\n{d*4//1024}KB" if d * 4 >= 1024 else f"{d}\n{d*4}B"
                         for d in dims], fontsize=9.5)
    ax3.set_xlabel("dimensions kept, bytes per vector below")
    ax3.set_ylabel("top-1 neighbour unchanged, %")
    ax3.set_title("Storage against fidelity", loc="left", pad=12)
    ax3.set_ylim(50, 108)
    ax3.annotate("512 dimensions is a third of the\nstorage and loses nothing here.\n"
                 "1024 loses more than 512 does:\n34 records is not enough to tune on.",
                 xy=(512, 100), xytext=(34, 62), fontsize=10.5, color=INK,
                 arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1))

    fig.savefig(HERE / "embedding-limits.png")
    plt.close(fig)


# --------------------------------------------------------------------------
def main() -> None:
    print("L15 figures. Cached provider calls live in .cache/ and are gitignored.")
    print(f"  ANTHROPIC_API_KEY set: {have('ANTHROPIC_API_KEY')}")
    print(f"  OPENAI_API_KEY set:    {have('OPENAI_API_KEY')}")
    figure_tokenization()
    figure_context_cost()
    figure_next_token()
    figure_embeddings()
    print("\ndone.")


if __name__ == "__main__":
    main()
