"""Figures for L16, the API/prompt/structured-output interface.

Run from this directory with the course `sys_tools` environment:

    python make_figures.py

Three figures, all generated rather than copied (CLAUDE.md section 5b):

  1. repair-loop.png     the extract -> validate -> repair control flow, the
                         idea that a schema-validation failure is a retry, not a
                         crash. A schematic, no data.
  2. prompt-caching.png  cost against number of calls that reuse one large fixed
                         context, with and without prompt caching. Computed from
                         published cache multipliers (see PRICING below).
  3. lost-in-the-middle.png  a redraw of the accuracy-vs-position finding from
                         Liu et al. (2023), from the numbers reported there.

The pricing and the Liu et al. numbers are filled in from verified sources and
are dated in the captions; providers change both, so treat them as a snapshot.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = Path(__file__).parent

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
AMBER = "#b8860b"
GREEN_BG = "#eaf7ee"
BLUE_BG = "#e8f0f8"
RED_BG = "#fbe9ec"

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


# --------------------------------------------------------------------------
# Figure 1 — the extract / validate / repair control flow
# --------------------------------------------------------------------------
def fig_repair_loop() -> dict:
    fig, ax = plt.subplots(figsize=(11, 5.2))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    def box(x, y, w, h, text, face, edge=INK, fs=12):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                     boxstyle="round,pad=0.08,rounding_size=0.12",
                     linewidth=1.6, edgecolor=edge, facecolor=face, zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, zorder=3)

    def arrow(x1, y1, x2, y2, text="", color=INK, rad=0.0):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2),
                     connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
                     mutation_scale=16, linewidth=1.6, color=color, zorder=1))
        if text:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.22, text, ha="center",
                    va="center", fontsize=10.5, color=color, zorder=4)

    box(0.2, 2.1, 2.0, 1.0, "datasheet\ntext", BLUE_BG)
    box(2.9, 2.1, 2.1, 1.0, "LLM call\n(schema-constrained)", BLUE_BG)
    box(5.7, 2.1, 2.0, 1.0, "validate\n(Pydantic)", GREEN_BG)
    box(8.4, 3.3, 2.3, 1.0, "valid record\n-> parts table", GREEN_BG, edge=GREEN)
    box(8.4, 0.7, 2.3, 1.0, "give up after\nN tries -> flag", RED_BG, edge=CMU_RED)

    arrow(2.2, 2.6, 2.9, 2.6)
    arrow(5.0, 2.6, 5.7, 2.6)
    arrow(7.7, 2.9, 8.4, 3.6, "valid", GREEN)
    arrow(7.7, 2.3, 8.4, 1.5, "still invalid", CMU_RED)

    # the repair loop: invalid -> back to the LLM call with the error
    arrow(6.7, 2.1, 3.95, 2.1, "", AMBER, rad=-0.5)
    ax.text(5.3, 1.05, "invalid: send the error back and ask it to fix",
            ha="center", va="center", fontsize=10.5, color=AMBER)

    ax.text(5.5, 4.7, "Extract, validate, repair: a failure loops back",
            ha="center", va="center", fontsize=15, color=INK)
    out = HERE / "repair-loop.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name}


# --------------------------------------------------------------------------
# Figure 2 — prompt caching pays off when a big context is reused
# --------------------------------------------------------------------------
# Anthropic pricing, observed 2026-08-18 (drift-prone, dated in the caption):
#   Claude Sonnet 5: input $2 / MTok, output $10 / MTok.
#   5-minute cache write = 1.25x base input; cache read = 0.1x base input.
IN_PER_MTOK = 2.0
OUT_PER_MTOK = 10.0
CACHE_WRITE = 1.25
CACHE_READ = 0.10


def fig_prompt_caching() -> dict:
    fixed_ctx = 20_000     # a spec/manual + instructions + few-shot, reused every call
    per_call_in = 500      # the one datasheet that changes each call
    per_call_out = 300
    n = np.arange(1, 31)

    def dollars(tok, per_mtok):
        return tok / 1e6 * per_mtok

    out_cost = dollars(per_call_out, OUT_PER_MTOK)
    var_in = dollars(per_call_in, IN_PER_MTOK)

    # No caching: pay full input for the fixed context on every call.
    no_cache = n * (dollars(fixed_ctx, IN_PER_MTOK) + var_in + out_cost)

    # Caching: first call writes the cache (1.25x), the rest read it (0.1x).
    first = dollars(fixed_ctx, IN_PER_MTOK) * CACHE_WRITE + var_in + out_cost
    later = dollars(fixed_ctx, IN_PER_MTOK) * CACHE_READ + var_in + out_cost
    cached = first + (n - 1) * later

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(n, no_cache * 100, color=MUTED, lw=2.4, label="no caching")
    ax.plot(n, cached * 100, color=CMU_RED, lw=2.4, label="prompt caching")
    ax.fill_between(n, cached * 100, no_cache * 100, color=CMU_RED, alpha=0.08)
    ax.set_xlabel("calls that reuse the same 20k-token context")
    ax.set_ylabel("cumulative cost (US cents)")
    ax.set_title("Prompt caching, when a large fixed context is reused")
    ax.legend(frameon=False, fontsize=11)
    at30 = no_cache[-1] / cached[-1]
    ax.annotate(f"{at30:.1f}x cheaper at 30 calls",
                xy=(30, cached[-1] * 100), xytext=(16, no_cache[-1] * 100 * 0.55),
                fontsize=10.5, color=CMU_RED,
                arrowprops=dict(arrowstyle="->", color=CMU_RED, lw=1.2))
    ax.text(0.98, 0.02, "Claude Sonnet 5 pricing, 2026-08-18 (providers change this)",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color=MUTED)
    out = HERE / "prompt-caching.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name, "ratio_at_30": round(float(at30), 2),
            "no_cache_30_cents": round(float(no_cache[-1] * 100), 2),
            "cached_30_cents": round(float(cached[-1] * 100), 2)}


# --------------------------------------------------------------------------
# Figure 3 — lost in the middle (Liu et al. 2023, Table 6)
# --------------------------------------------------------------------------
def fig_lost_in_the_middle() -> dict:
    # GPT-3.5-Turbo, 20-document multi-document QA, verified from Table 6.
    positions = [1, 10, 20]
    acc = [75.8, 53.8, 63.2]
    closed_book = 56.1
    oracle = 88.3

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(positions, acc, color=CMU_RED, lw=2.6, marker="o", markersize=9,
            zorder=4, label="accuracy vs position of the answer")
    for x, y in zip(positions, acc):
        ax.annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                    xytext=(0, 12), ha="center", fontsize=11, color=INK)
    ax.axhline(oracle, color=GREEN, ls="--", lw=1.6)
    ax.text(20, oracle + 0.6, f"oracle, gold document only: {oracle:.1f}%",
            ha="right", va="bottom", fontsize=10, color=GREEN)
    ax.axhline(closed_book, color=MUTED, ls=":", lw=1.6)
    ax.text(1, closed_book - 2.2, f"closed book, no documents at all: {closed_book:.1f}%",
            ha="left", va="top", fontsize=10, color=MUTED)
    ax.set_xticks(positions)
    ax.set_xticklabels(["first", "middle (10th)", "last"])
    ax.set_xlabel("position of the relevant document among 20")
    ax.set_ylabel("answer accuracy (%)")
    ax.set_ylim(45, 92)
    ax.set_title("Lost in the middle: burying the answer costs 22 points")
    ax.text(0.98, 0.02, "GPT-3.5-Turbo, Liu et al. (2023), Table 6",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color=MUTED)
    out = HERE / "lost-in-the-middle.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name, "first": acc[0], "middle": acc[1], "last": acc[2],
            "closed_book": closed_book, "drop_pts": round(acc[0] - acc[1], 1)}


def main() -> None:
    results = {}
    for fn in (fig_repair_loop, fig_prompt_caching, fig_lost_in_the_middle):
        results[fn.__name__] = fn()
        print(f"{fn.__name__}: {results[fn.__name__]}")
    print("wrote:", ", ".join(sorted(p.name for p in HERE.glob("*.png"))))


if __name__ == "__main__":
    main()
