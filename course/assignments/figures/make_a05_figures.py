# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "matplotlib", "pillow", "python-pptx"]
# ///
"""Figures for Assignment 5.

    uv run --no-project course/assignments/figures/make_a05_figures.py

    a05-reactor.png  Victor Alves's bioreactor drawing (cmu-seminar slide 35, the
                     same picture as Lecture 13's fedbatch-reactor.png), relabeled
                     for continuous operation: feed in, outflow out, constant volume.
                     Needs attic/cmu-seminar.pptx, which is not in the repository;
                     without it the committed PNG is kept.
    a05-data.png     The five experiments of a05-bioreactor.csv.
"""
import csv
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
DATA = HERE.parent / "a05-bioreactor.csv"

INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
ORANGE = "#c2410c"
STYLE = {
    "font.size": 14, "axes.labelsize": 14, "axes.titlesize": 15,
    "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 12,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "savefig.dpi": 150, "savefig.bbox": "tight",
}
X_SS, S_SS = 3.46198, 45.6033      # the steady state, kg/m3 and mol/m3


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"wrote {name}")


def reactor():
    deck = REPO / "attic" / "cmu-seminar.pptx"
    if not deck.exists():
        print(f"skipped a05-reactor.png: {deck} is not here")
        return
    from PIL import Image, ImageDraw
    from pptx import Presentation

    shape = next(s for s in Presentation(str(deck)).slides[34].shapes if s.name == "Picture 17")
    img = Image.open(io.BytesIO(shape.image.blob)).convert("RGBA")
    img = Image.alpha_composite(Image.new("RGBA", img.size, "white"), img).convert("RGB")
    d = ImageDraw.Draw(img)
    d.rectangle((205, 46, 248, 73), fill="white")        # the drawing's [M_i]
    d.rectangle((70, 167, 99, 191), fill="white")        # and its X_v
    arr = np.asarray(img)

    with plt.rc_context(STYLE):
        fig, ax = plt.subplots(figsize=(8.4, 5.6))
        ax.imshow(arr, extent=(0, arr.shape[1], arr.shape[0], 0))
        ax.set_xlim(-300, arr.shape[1] + 300)
        ax.set_ylim(arr.shape[0] + 10, -70)
        ax.axis("off")
        # feed: into the top of the vessel
        ax.annotate("feed: $F$ (m³/s)\nsubstrate $S_F$ (mol/m³)", xy=(70, 92), xytext=(-290, -20),
                    fontsize=15, color=BLUE,
                    arrowprops=dict(arrowstyle="-|>", color=BLUE, lw=2.6, mutation_scale=22))
        # outflow: a pipe through the right wall at the liquid level
        ax.plot([240, 268], [178, 178], color=INK, lw=2)
        ax.plot([240, 268], [194, 194], color=INK, lw=2)
        ax.annotate("", xy=(380, 186), xytext=(262, 186),
                    arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=2.6, mutation_scale=22))
        ax.text(392, 186, "outflow: $F$ (m³/s)\nwith $X$ and $S$", fontsize=15, color=ORANGE,
                va="center")
        ax.annotate("cells: biomass $X$ (kg/m³)", xy=(205, 215), xytext=(300, 80), fontsize=15,
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
        ax.annotate("substrate $S$ (mol/m³)", xy=(135, 285), xytext=(300, 300), fontsize=15,
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
        ax.annotate("volume $V$ (m³)\nconstant: in = out", xy=(34, 178), xytext=(-290, 290),
                    fontsize=15, arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))
        save(fig, "a05-reactor.png")


def data():
    rows = {}
    with open(DATA, newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(int(r["experiment"]), []).append((float(r["t"]), float(r["X"]), float(r["S"])))
    colors = {1: "#1f77b4", 2: "#2ca02c", 3: "#9467bd", 4: "#e377c2"}

    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
        for ax, j, name, unit, ss in [(axes[0], 1, "biomass $X$", "kg/m³", X_SS),
                                      (axes[1], 2, "substrate $S$", "mol/m³", S_SS)]:
            for exp, vals in rows.items():
                v = np.array(vals)
                if exp == 5:
                    ax.plot(v[:, 0], v[:, j], "-o", color=INK, lw=0.8, mfc="white", mec=INK,
                            ms=5, mew=1.3, label="experiment 5 (test)", zorder=3)
                else:
                    ax.plot(v[:, 0], v[:, j], "-o", color=colors[exp], lw=0.8, ms=3.5,
                            label=f"experiment {exp}")
            ax.axhline(ss, color=MUTED, lw=1.2, ls="--", label="steady state", zorder=0)
            ax.set_xlabel("time $t$ (s)")
            ax.set_ylabel(f"{name} ({unit})")
            ax.set_xlim(-5, 305)
        axes[1].legend(loc="upper right", fontsize=11, ncol=1)
        fig.tight_layout()
        save(fig, "a05-data.png")


if __name__ == "__main__":
    reactor()
    data()
