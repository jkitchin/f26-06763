#!/usr/bin/env python3
"""Generate the L2 figures.

Run with:  uv run --with matplotlib python make_figures.py

Like L1, every figure here is generated rather than copied. This one needs no
dataset: the numbers are the published counts from Pimentel et al., "A
Large-scale Study About Quality and Reproducibility of Jupyter Notebooks"
(MSR 2019), hard-coded here with the source so the claim can be checked.

The percentages are deliberately anchored on the 863,878 *attempted* notebooks,
not on the 1.45M collected, because that is the denominator the paper uses and
conflating the two is exactly the overstatement the notes avoid.

Outputs (committed alongside this script):
    notebook-repro.png    the funnel from attempted, to ran, to reproduced
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).parent

CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
RULE = "#d8d8d8"

plt.rcParams.update({
    "font.size": 13,
    "axes.labelsize": 13,
    "axes.titlesize": 15,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.spines.bottom": False,
    "axes.edgecolor": MUTED,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})

# Pimentel et al. (2019), Section IV. 1,450,071 notebooks collected from GitHub;
# 1,159,166 unique after deduplication; 863,878 valid Python notebooks (defined
# Python version and unambiguous execution order) were attempted for execution;
# of those, 24.11% ran without errors and 4.03% reproduced the recorded results.
COLLECTED = 1_450_071
UNIQUE = 1_159_166
ATTEMPTED = 863_878
RAN_FRAC = 0.2411
REPRO_FRAC = 0.0403


def fig_notebook_repro() -> None:
    """A funnel: of the notebooks that could be attempted, few run and fewer reproduce."""
    stages = [
        ("Valid notebooks attempted", ATTEMPTED, 1.0, MUTED),
        ("Ran without error", round(ATTEMPTED * RAN_FRAC), RAN_FRAC, MUTED),
        ("Reproduced the recorded result", round(ATTEMPTED * REPRO_FRAC), REPRO_FRAC, CMU_RED),
    ]

    fig, ax = plt.subplots(figsize=(9, 3.6))
    y = list(range(len(stages)))[::-1]  # first stage on top
    for yi, (label, count, frac, color) in zip(y, stages):
        ax.barh(yi, frac, color=color, height=0.62)
        ax.text(frac + 0.015, yi, f"{count:,}  ({frac * 100:.0f}%)",
                va="center", ha="left", fontsize=12,
                color=(CMU_RED if color == CMU_RED else INK),
                fontweight="bold" if color == CMU_RED else "normal")
        ax.text(-0.015, yi, label, va="center", ha="right", fontsize=12, color=INK)

    ax.set_xlim(0, 1.18)
    ax.set_ylim(-0.55, len(stages) - 0.45)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("Most shared notebooks do not run, and far fewer reproduce",
                 color=INK, pad=12, loc="left")
    fig.savefig(HERE / "notebook-repro.png")
    plt.close(fig)
    print(f"wrote notebook-repro.png  "
          f"(attempted {ATTEMPTED:,}, ran {round(ATTEMPTED * RAN_FRAC):,} = {RAN_FRAC:.2%}, "
          f"reproduced {round(ATTEMPTED * REPRO_FRAC):,} = {REPRO_FRAC:.2%})")


if __name__ == "__main__":
    fig_notebook_repro()
