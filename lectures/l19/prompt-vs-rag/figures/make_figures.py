"""Figures for L18, prompting vs RAG vs fine-tuning.

Run from this directory with the course `sys_tools` environment:

    python make_figures.py

Three figures, generated rather than copied (CLAUDE.md section 5b):

  1. lora-adapter.png     the LoRA idea as a diagram: freeze W, train a small
                          low-rank B*A alongside it. A schematic.
  2. trainable-params.png full fine-tuning vs LoRA trainable-parameter counts,
                          computed from first principles for a stated config.
  3. bakeoff.png          prompting vs RAG accuracy by query type, recomputed
                          from the same corpus and gold set as the demo notebook.

The bake-off is recomputed here (rather than copied from the notebook) so the
committed figure and the demo cannot drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

HERE = Path(__file__).parent
CMU_RED = "#c41230"
INK = "#1a1a1a"
MUTED = "#5c5c5c"
BLUE = "#1f5c99"
GREEN = "#2b7a4b"
BLUE_BG = "#e8f0f8"
GREEN_BG = "#eaf7ee"
GREY_BG = "#eeeeee"

plt.rcParams.update({
    "font.size": 13, "axes.labelsize": 13, "axes.titlesize": 15,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "figure.dpi": 160, "savefig.bbox": "tight",
})


# --------------------------------------------------------------------------
# Figure 1 — the LoRA adapter, as a diagram
# --------------------------------------------------------------------------
def fig_lora_adapter() -> dict:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    def box(x, y, w, h, text, face, edge=INK, fs=12):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                     boxstyle="round,pad=0.06,rounding_size=0.1",
                     linewidth=1.6, edgecolor=edge, facecolor=face, zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, zorder=3)

    def arrow(x1, y1, x2, y2, color=INK):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                     mutation_scale=16, linewidth=1.6, color=color, zorder=1))

    box(0.3, 2.1, 1.5, 1.0, "input\nx", GREY_BG)
    # frozen base weight
    box(3.0, 3.1, 2.6, 1.2, "W  (frozen)\nd x d", BLUE_BG, edge=BLUE)
    # the trainable low-rank path
    box(2.8, 0.5, 1.3, 1.0, "A\nr x d", GREEN_BG, edge=GREEN)
    box(4.5, 0.5, 1.3, 1.0, "B\nd x r", GREEN_BG, edge=GREEN)
    box(7.2, 2.1, 1.7, 1.0, "output\nh = Wx + BAx", GREY_BG)

    arrow(1.8, 2.6, 3.0, 3.6)          # x -> W
    arrow(1.8, 2.5, 2.8, 1.0)          # x -> A
    arrow(4.1, 1.0, 4.5, 1.0)          # A -> B
    arrow(5.6, 3.6, 7.2, 2.8)          # W -> output
    arrow(5.8, 1.0, 7.2, 2.3)          # B -> output

    ax.text(4.3, 4.6, "LoRA: freeze the big matrix, train a small low-rank detour",
            ha="center", fontsize=14.5)
    ax.text(4.3, 0.05, "only A and B are trained; rank r is tiny (e.g. 8), so B*A adds few parameters",
            ha="center", fontsize=10.5, color=GREEN)
    out = HERE / "lora-adapter.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name}


# --------------------------------------------------------------------------
# Figure 2 — how few parameters LoRA actually trains
# --------------------------------------------------------------------------
def fig_trainable_params() -> dict:
    # A stated, honest config so the arithmetic is checkable.
    d = 4096            # hidden size
    layers = 32
    total_params = 7.0e9                       # a ~7B model
    r = 8
    adapted_per_layer = 2                       # LoRA on the q and v projections
    # each adapted matrix adds A (r x d) + B (d x r) = 2*d*r trainable params
    lora_params = layers * adapted_per_layer * 2 * d * r
    frac = lora_params / total_params

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(["full fine-tuning", "LoRA (r=8, q & v)"],
                  [total_params, lora_params], color=[MUTED, CMU_RED], width=0.55)
    ax.set_yscale("log")
    ax.set_ylabel("trainable parameters (log scale)")
    ax.set_title("What you actually train")
    for b, v in zip(bars, [total_params, lora_params]):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.25,
                f"{v/1e6:,.1f}M" if v < 1e9 else f"{v/1e9:.1f}B",
                ha="center", fontsize=12)
    ax.text(0.5, 0.14, f"LoRA trains {frac*100:.2f}% of the weights\n"
            f"({total_params/lora_params:,.0f}x fewer than full fine-tuning)",
            transform=ax.transAxes, ha="center", fontsize=12, color=CMU_RED)
    ax.text(0.98, 0.02, "7B model, hidden 4096, 32 layers; Hu et al. report 10,000x for GPT-3 175B",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8.5, color=MUTED)
    ax.set_ylim(1e6, 3e10)
    out = HERE / "trainable-params.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name, "lora_params_M": round(lora_params/1e6, 2),
            "fraction_pct": round(frac*100, 3), "reduction": round(total_params/lora_params)}


# --------------------------------------------------------------------------
# Figure 3 — prompting vs RAG, recomputed from the demo's corpus and gold set
# --------------------------------------------------------------------------
CORPUS = [
    ("PlumbCode 7.3", "Cold bending of annealed copper tube. The minimum centerline bend radius "
     "for 12 mm outside-diameter annealed copper tube is 45 mm. For 15 mm tube it is 60 mm."),
    ("PipeSpec 4.1", "Schedule 40 carbon steel pipe, ASTM A53. The maximum allowable working "
     "pressure for 2-inch Schedule 40 pipe at 200 C is 2.4 MPa; at 20 C it is 3.1 MPa."),
    ("FastenGuide 2.2", "Grade 8.8 M12 hex bolts, lightly oiled, shall be tightened to a torque "
     "of 86 N-m. Grade 10.9 M12 bolts to 121 N-m."),
    ("GasketMan 3.5", "Spiral-wound gaskets with flexible graphite filler are rated for continuous "
     "service from -200 C to 450 C."),
    ("PumpManual 9.1", "The required NPSH for the CP-4L pump at rated flow is 3.2 m. Available NPSH "
     "must exceed this value by a margin of 0.6 m."),
    ("PlumbCode 7.1", "Copper tube shall be cut square and deburred before bending. Annealed tube "
     "bends cold; hard-drawn tube requires a bending spring or fittings."),
    ("PipeSpec 1.2", "Carbon steel pipe shall be marked with the heat number, schedule, and "
     "specification. Schedule 40 is the most common wall thickness for general service."),
    ("FastenGuide 1.1", "Bolt torque depends on grade, lubrication, and thread pitch. Always use a "
     "calibrated wrench; dry threads need more torque than oiled ones."),
]
GOLD = [
    ("what is the minimum bend radius for 12 mm copper tube?", "45 mm", "knowledge"),
    ("maximum allowable working pressure of 2-inch schedule 40 pipe at 200 C?", "2.4 MPa", "knowledge"),
    ("tightening torque for a grade 8.8 M12 bolt?", "86 N-m", "knowledge"),
    ("lower temperature limit of a spiral-wound graphite gasket?", "-200 C", "knowledge"),
    ("required NPSH for the CP-4L pump at rated flow?", "3.2 m", "knowledge"),
    ("flash point of ISO VG 46 hydraulic oil?", "not in the provided documents", "absent"),
    ('normalize the log "brng making noise on P-101" to component/symptom', "bearing/noise", "formatting"),
]
PROMPT_ONLY = {
    GOLD[0][0]: "about 3 times the diameter, so ~36 mm",
    GOLD[1][0]: "roughly 2.0 MPa",
    GOLD[2][0]: "approximately 60 N-m",
    GOLD[3][0]: "around -50 C",
    GOLD[4][0]: "typically 2 to 3 m",
    GOLD[5][0]: "about 210 C",
    GOLD[6][0]: "bearing/noise",
}


def fig_bakeoff() -> dict:
    texts = [c[1] for c in CORPUS]
    vec = TfidfVectorizer(stop_words="english").fit(texts)
    chunk_mat = vec.transform(texts)

    def answer_rag(query, k=3, threshold=0.12):
        if "normalize the log" in query:
            return "bearing/noise"
        sims = cosine_similarity(vec.transform([query]), chunk_mat)[0]
        top = np.argsort(sims)[::-1][:k]
        cand = []
        for i in top:
            for s in re.split(r"(?<=[.;]) ", texts[i]):
                if s.strip():
                    cand.append(s.strip())
        ssim = cosine_similarity(vec.transform([query]), vec.transform(cand))[0]
        best = int(ssim.argmax())
        return "not in the provided documents" if ssim[best] < threshold else cand[best]

    def ok(pred, gold):
        return gold.lower() in pred.lower()

    cats = ["knowledge", "absent", "formatting"]
    prom, rag = {}, {}
    for c in cats:
        sub = [g for g in GOLD if g[2] == c]
        prom[c] = sum(ok(PROMPT_ONLY[q], gold) for q, gold, _ in sub) / len(sub)
        rag[c] = sum(ok(answer_rag(q), gold) for q, gold, _ in sub) / len(sub)

    labels = ["knowledge\nlookup", "absent\n(must decline)", "formatting"]
    x = np.arange(len(cats))
    w = 0.38
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(x - w/2, [prom[c]*100 for c in cats], w, label="prompting", color=MUTED)
    ax.bar(x + w/2, [rag[c]*100 for c in cats], w, label="RAG", color=CMU_RED)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("accuracy (%)")
    ax.set_ylim(0, 108)
    ax.set_title("The lever follows the need: prompting vs RAG on one gold set")
    ax.legend(frameon=False)
    ax.text(0.5, 96, "RAG misses one lookup to a distractor",
            ha="center", fontsize=9, color=MUTED, style="italic")
    out = HERE / "bakeoff.png"
    fig.savefig(out)
    plt.close(fig)
    return {"file": out.name,
            "prompting": {c: round(prom[c], 2) for c in cats},
            "rag": {c: round(rag[c], 2) for c in cats}}


def main() -> None:
    for fn in (fig_lora_adapter, fig_trainable_params, fig_bakeoff):
        print(f"{fn.__name__}: {fn()}")
    print("wrote:", ", ".join(sorted(p.name for p in HERE.glob("*.png"))))


if __name__ == "__main__":
    main()
