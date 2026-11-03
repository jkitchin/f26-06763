#!/usr/bin/env python3
"""Generate the L19 figures, and print every number the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with duckdb --with numpy --with matplotlib \
        --with tiktoken --with nbformat --with squarify python make_figures.py

Name groups to regenerate only those; with no names, every group runs.

    trace        runs the scripted agent of ../l19-agents.ipynb (its code cells, executed here),
                 counts the tokens of every message with tiktoken (o200k_base, the GPT-4o
                 tokenizer; other providers count a little differently), and writes run.png,
                 tokens.png and caching.png. caching.png prices the same run with Anthropic's
                 cache multipliers (write 1.25x, read 0.1x the input price) and extends it to 30
                 calls with the measured prefix and growth per call. caching-1.png and
                 caching-2.png are the deck's build-up of the same figure.
    diagrams     solar.png (the energy model of the notebook), coscientist.png (redrawn from the
                 Coscientist paper's description of its modules), workflow-agent.png,
                 agent-loop.png, harness.png, cache-prefix.png, coding-loop.png, coding-agent.png,
                 context.png, multi-agent.png and project.png.
    codex        small-box.png: Lecture 1's "ML code is a small box" figure next to Codex, the
                 open-source coding agent, sized by its lines of Rust. Counts openai/codex at a
                 pinned commit; set CODEX_SRC to an existing checkout, or it is cloned into .cache.
    timeline     timeline.png: LLM agents from ReAct to today, every date from a primary source.
    evidence     metr.png and its build-up metr-1.png to metr-3.png: the forecast, believed and
                 measured change in task time in METR's 2025 randomized trial (Becker et al.,
                 arXiv 2507.09089), and the returning developers' estimate from METR's February
                 2026 re-run, which METR itself calls an unreliable signal
                 (metr.org/blog/2026-02-24-uplift-update/).
    course       course-history.png (every pull request merged into this course's repository, as
                 a branch off main) and course-build.png (how one change reaches the site), from
                 the repository's own git history.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

HERE = Path(__file__).resolve().parent
LECTURE = HERE.parent
REPO = HERE.parents[2]
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)
NOTEBOOK = LECTURE / "l19-agents.ipynb"
CODEX_COMMIT = "a47a5189281806e669053434975a399b05c5e275"   # openai/codex main on 2026-11-03

RED, BLUE, GOLD, GREEN, GRAY = "#c41230", "#1f5c99", "#b07d12", "#2e7d32", "#8a8a8a"
FILL = {"blue": "#dbe8f5", "gold": "#f7e3c3", "green": "#dcefdc", "red": "#f6d9de", "gray": "#ececec",
        "purple": "#e8e0f2"}
plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 150, "savefig.bbox": "tight"})


def save(fig, name, tight=True, close=True):
    """Write a figure. tight=False keeps the canvas fixed, so the frames of a build-up stack."""
    with plt.rc_context({"savefig.bbox": "tight" if tight else "standard"}):
        fig.savefig(HERE / name)
    if close:
        plt.close(fig)
    print(f"  wrote {name}")


def notebook_namespace(skip=()):
    """Execute the notebook's code cells (not the Colab cell)."""
    import nbformat
    nb = nbformat.read(NOTEBOOK, 4)
    ns = {}
    cwd = os.getcwd()
    os.chdir(LECTURE)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            for cell in nb.cells:
                if cell.cell_type != "code" or cell.get("id") == "colab-setup":
                    continue
                if any(s in cell.source for s in skip):
                    continue
                exec(cell.source, ns)
    finally:
        os.chdir(cwd)
    return ns


# --------------------------------------------------------------------------------- trace
def group_trace():
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")

    def count(text):
        return len(enc.encode(text))

    ns = notebook_namespace()
    run = ns["good"]
    system, tools = ns["SYSTEM"], ns["TOOLS"]
    prefix = {"system": count(system), "tools": count(json.dumps(tools))}
    P = prefix["system"] + prefix["tools"]

    # What each model call reads: the prefix, then every message before its reply.
    calls, history = [], 0
    for m in run["messages"]:
        c = m["content"]
        if m["role"] == "assistant":
            calls.append({"input": P + history, "history": history})
        history += count(c if m["role"] == "user" else json.dumps(c))
    total_in = sum(c["input"] for c in calls)
    n = len(calls)
    m_avg = calls[-1]["history"] / (n - 1)
    print(f"  prefix: system {prefix['system']} + tools {prefix['tools']} = {P} tokens")
    for i, c in enumerate(calls, 1):
        print(f"  call {i}: reads {c['input']} tokens ({P} prefix + {c['history']} history)")
    print(f"  {n} calls read {total_in} input tokens in total; history grows about {m_avg:.0f} tokens per call")

    # run.png: the run, call by call, for the notes.
    rows = []
    msgs = run["messages"]
    for i, m in enumerate(msgs):
        if m["role"] != "assistant":
            continue
        c = m["content"]
        if "answer" in c:
            rows.append(("answer", c["answer"], None))
            continue
        req = f'{c["tool"]}({", ".join(f"{k}={json.dumps(v)}" for k, v in c["input"].items())})'
        res = msgs[i + 1]["content"]
        if "error" in res:
            out = "error: " + res["error"]
        elif "rows" in res:
            out = f"rows: {res['rows']}"
        elif "kwh_per_day" in res:
            out = "kWh/day: " + ", ".join(f"{k}°: {v}" for k, v in res["kwh_per_day"].items())
        else:
            out = f"moved from {res['old_tilt_deg']:g}° to {res['new_tilt_deg']:g}°"
        rows.append(("tool", req, out))
    fig, ax = canvas(12.6, 1.25 * len(rows) + 0.35)
    for j, (kind, req, out) in enumerate(rows):
        y = 1.25 * (len(rows) - j) - 0.45
        ax.text(0.15, y, f"Call {j + 1}", fontsize=12.5, fontweight="bold", va="center")
        if kind == "answer":
            box(ax, 7.0, y, 11.0, 0.72, textwrap.fill("Answer: " + req, 112), "green", GREEN, size=10.5)
            continue
        box(ax, 4.45, y, 5.4, 0.62, textwrap.fill(req, 58), "red", RED, size=9.6)
        gate = "harness: asks the operator, who says yes" if req.startswith("set_tilt") else "harness: runs it"
        ax.text(4.45, y - 0.5, gate, ha="center", fontsize=9.5, color="#3c3c3c", style="italic")
        arrow(ax, (7.2, y), (7.6, y), GRAY)
        box(ax, 10.1, y, 4.9, 0.62, textwrap.fill(out, 54), "blue", BLUE, size=9.6)
    ax.text(4.45, 1.25 * len(rows) + 0.0, "The model asks", ha="center", fontsize=12, color=RED, fontweight="bold")
    ax.text(10.1, 1.25 * len(rows) + 0.0, "The tool's result goes back", ha="center", fontsize=12, color=BLUE,
            fontweight="bold")
    save(fig, "run.png")

    # tokens.png: what each call reads
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    x = range(1, n + 1)
    ax.bar(x, [P] * n, color=FILL["blue"], edgecolor=BLUE, label="System prompt and tool definitions")
    ax.bar(x, [c["history"] for c in calls], bottom=[P] * n, color=FILL["gold"], edgecolor=GOLD,
           label="The conversation so far")
    for i, c in enumerate(calls, 1):
        ax.text(i, c["input"] + 25, f"{c['input']}", ha="center", fontsize=12)
    ax.set_xticks(list(x))
    ax.set_xlabel("Model call")
    ax.set_ylabel("Input tokens read")
    ax.set_ylim(0, max(c["input"] for c in calls) * 1.18)
    ax.legend(frameon=False, loc="upper left", fontsize=11)
    ax.set_title(f"Five calls read {total_in:,} tokens: every call re-reads everything before it",
                 fontsize=13)
    save(fig, "tokens.png")

    # caching.png: the same run with a prompt cache. Call k+1 starts with everything call k sent,
    # so that part can be read from the cache; only what is new since call k is written.
    # caching-1.png and caching-2.png are the same canvas with less drawn, for the deck.
    WRITE, READ = 1.25, 0.10
    inputs = [c["input"] for c in calls]
    hit = [0] + inputs[:-1]
    new = [i - h for i, h in zip(inputs, hit)]
    billed = sum(WRITE * w + READ * h for w, h in zip(new, hit))
    share = billed / total_in
    print(f"  with a cache: {sum(hit)} of {total_in} tokens read from the cache; billed as "
          f"{billed:,.0f} full-price tokens ({share:.0%})")
    K = 30
    ext = [inputs[0] + m_avg * k for k in range(K)]
    plain = [sum(ext[:k]) for k in range(1, K + 1)]
    cached = [WRITE * ext[0] + sum(READ * ext[j - 1] + WRITE * (ext[j] - ext[j - 1]) for j in range(1, k))
              for k in range(1, K + 1)]
    print(f"  {K} calls: {plain[-1]:,.0f} tokens without a cache, {cached[-1]:,.0f} with ({cached[-1] / plain[-1]:.0%})")
    for frame in (1, 2, 3):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.4, 4.6), gridspec_kw={"width_ratios": [1, 1.15]})
        fig.subplots_adjust(left=0.07, right=0.9, bottom=0.14, top=0.86, wspace=0.32)
        x = range(1, n + 1)
        if frame == 1:
            a1.bar(x, inputs, color=FILL["gold"], edgecolor=GOLD, label="Processed at full price")
            a1.set_title(f"No cache: all {total_in:,} tokens at full price", fontsize=13)
        else:
            a1.bar(x, hit, color=FILL["green"], edgecolor=GREEN, label="Sent before: read from the cache, 0.1x")
            a1.bar(x, new, bottom=hit, color=FILL["gold"], edgecolor=GOLD, label="New: processed, 1.25x")
            for i, (h, w) in enumerate(zip(hit, new), 1):
                a1.text(i, h + w + 18, f"+{w}", ha="center", fontsize=11, color=GOLD, fontweight="bold")
            a1.set_title(f"With a cache: the run costs {share:.0%} as much", fontsize=13, color=GREEN)
        a1.set_xticks(list(x))
        a1.set_xlabel("Model call")
        a1.set_ylabel("Input tokens")
        a1.set_ylim(0, max(inputs) * 1.42)
        a1.legend(frameon=False, loc="upper left", fontsize=10.5)
        kk = range(1, K + 1)
        a2.plot(kk, plain, color=RED, lw=2.6)
        a2.plot(kk, cached, color=GREEN, lw=2.6)
        a2.text(K + 0.6, plain[-1], f"no cache\n{plain[-1]:,.0f}", color=RED, va="center", fontsize=11)
        a2.text(K + 0.6, cached[-1], f"with a cache\n{cached[-1]:,.0f}\n({cached[-1] / plain[-1]:.0%})",
                color=GREEN, va="center", fontsize=11)
        a2.set_xlim(0, K + 7)
        a2.set_xlabel("Model calls in the run")
        a2.set_ylabel("Input cost, in full-price tokens")
        a2.set_title(f"A longer run saves more: {K} calls", fontsize=13)
        a2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        if frame < 3:
            a2.set_visible(False)
        save(fig, "caching.png" if frame == 3 else f"caching-{frame}.png", tight=False)


# ------------------------------------------------------------------------------ diagrams
def box(ax, x, y, w, h, text, fill="gray", edge=GRAY, size=12, weight="normal", color="black"):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=FILL.get(fill, fill), ec=edge, lw=1.8))
    ax.text(x, y, text, ha="center", va="center", fontsize=size, fontweight=weight, color=color,
            linespacing=1.25)


def arrow(ax, a, b, color=GRAY, text=None, size=11, rad=0.0, tx=0.0, ty=0.0, style="-|>"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=16, color=color, lw=1.8,
                                 connectionstyle=f"arc3,rad={rad}", shrinkA=2, shrinkB=2))
    if text:
        ax.text((a[0] + b[0]) / 2 + tx, (a[1] + b[1]) / 2 + ty, text, ha="center", va="center",
                fontsize=size, color=color)


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def group_diagrams():
    # The example: a solar array whose tilt can change, and the notebook's own energy model.
    ns = notebook_namespace()
    E = ns["energy_kwh"]
    import math
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.6, 4.3), gridspec_kw={"width_ratios": [1, 1.15]})
    a1.set_xlim(-0.2, 6.6)
    a1.set_ylim(-0.4, 3.9)
    a1.set_aspect("equal")
    a1.axis("off")
    a1.add_patch(Rectangle((-0.2, -0.4), 6.8, 0.55, fc="#e4e4e4", ec="none"))
    a1.plot([-0.2, 6.6], [0.15, 0.15], color="#5c5c5c", lw=2)
    a1.text(0.0, -0.17, "roof in Pittsburgh: a 5 kW array", fontsize=11, color="#5c5c5c", va="center")
    px, py, L = 3.1, 0.75, 2.4
    a1.plot([px, px], [0.15, py], color="#5c5c5c", lw=3)
    for tilt, c, lw, ls in ((20, GRAY, 4, "--"), (50, GOLD, 6, "-")):
        t = math.radians(tilt)
        a1.plot([px + 0.35 * math.cos(t), px - L * math.cos(t)], [py - 0.35 * math.sin(t), py + L * math.sin(t)],
                color=c, lw=lw, ls=ls, solid_capstyle="butt")
    t = [math.radians(v) for v in range(0, 51)]
    a1.plot([px - 0.75 * math.cos(v) for v in t], [py + 0.75 * math.sin(v) for v in t], color=GOLD, lw=1.4)
    a1.plot([px - 1.0, px], [py, py], color=GOLD, lw=1, ls=":")
    a1.text(px - 0.95, py + 0.04, "tilt", fontsize=11, color=GOLD, ha="center", va="bottom", fontweight="bold")
    a1.text(0.0, 1.75, "last week: 20°", fontsize=11.5, color="#5c5c5c", ha="left")
    a1.text(px - L * math.cos(math.radians(50)) + 0.05, py + L * math.sin(math.radians(50)) + 0.12,
            "best: 50°", fontsize=12, color=GOLD, ha="left", fontweight="bold")
    sun = (6.0, 3.25)
    a1.add_patch(plt.Circle(sun, 0.33, color="#f2b705", zorder=3))
    el = math.radians(34)
    for off in (-0.55, 0.0, 0.55):
        sx, sy = sun[0] - 0.5 + off * math.sin(el), sun[1] - 0.35 - off * math.cos(el)
        a1.annotate("", xy=(sx - 2.4 * math.cos(el), sy - 2.4 * math.sin(el)), xytext=(sx, sy),
                    arrowprops={"arrowstyle": "->", "color": "#e0a000", "lw": 1.6})
    a1.text(sun[0] + 0.1, sun[1] + 0.5, "noon sun in November:\nlow, 34° above the horizon", fontsize=11,
            ha="center", color="#8a6a00")
    T = [0.5 * i for i in range(181)]
    a2.axvspan(60, 90, color="#ececec")
    a2.text(75, 6.2, "outside the\nmount's range", ha="center", fontsize=11, color="#5c5c5c")
    a2.plot(T, [E(v) for v in T], color=BLUE, lw=2.8)
    for v, c, label, dy in ((20, GRAY, "last week", -1.5), (50, GOLD, "best", -1.7)):
        a2.plot([v], [E(v)], "o", color=c, ms=10, mec="white", zorder=5)
        a2.annotate(f"{label}: {v}°\n{E(v):.1f} kWh/day", xy=(v, E(v)), xytext=(v, E(v) + dy), ha="center",
                    va="top", fontsize=11.5, color=c, fontweight="bold",
                    arrowprops={"arrowstyle": "->", "color": c})
    a2.set_xlim(0, 90)
    a2.set_ylim(5, 13)
    a2.set_xticks(range(0, 91, 15))
    a2.set_xlabel("Tilt (degrees from horizontal)")
    a2.set_ylabel("Energy per day (kWh)")
    a2.set_title("The energy model: average early-November day", fontsize=13)
    fig.tight_layout(w_pad=2.5)
    save(fig, "solar.png")

    # Coscientist, redrawn from the paper's text: a GPT-4 Planner with four commands.
    fig, ax = canvas(11.8, 5.2)
    box(ax, 5.9, 4.5, 5.6, 0.8, "Goal, in plain English\n\"perform Suzuki and Sonogashira couplings\"", "gray", size=11)
    box(ax, 5.9, 3.1, 2.6, 0.9, "Planner\n(GPT-4)", "blue", BLUE, size=13, weight="bold")
    arrow(ax, (5.9, 4.08), (5.9, 3.58))
    mods = [(1.45, "GOOGLE", "Web searcher\n(searches the internet)"),
            (4.4, "PYTHON", "Code execution\n(calculations, in Docker)"),
            (7.4, "DOCUMENTATION", "Docs searcher\n(reads the robot's API)"),
            (10.35, "EXPERIMENT", "Automation\n(runs the protocol)")]
    for x, cmd, label in mods:
        box(ax, x, 1.55, 2.6, 0.95, label, "gold", GOLD, size=11)
        arrow(ax, (5.9, 2.62), (x, 2.06), color=GRAY, rad=0.0)
        ax.text(x, 2.25, cmd, ha="center", fontsize=9.5, color=GOLD, fontweight="bold",
                bbox={"fc": "white", "ec": "none", "pad": 1})
    box(ax, 10.35, 0.35, 2.6, 0.55, "Opentrons OT-2\nliquid handler", "green", GREEN, size=11)
    arrow(ax, (10.35, 1.07), (10.35, 0.64), color=GREEN)
    ax.text(5.9, 0.35, "A person moved plates between instruments; GC-MS, an\ninstrument that identifies compounds, found both products",
            ha="center", va="center", fontsize=10.5, color="#3c3c3c", style="italic")
    save(fig, "coscientist.png")

    # Workflow against agent.
    fig, ax = canvas(11.8, 4.2)
    ax.text(2.9, 3.9, "Workflow: your code decides the steps", ha="center", fontsize=13, fontweight="bold", color=BLUE)
    for i, (y, t) in enumerate([(3.0, "Retrieve passages"), (1.9, "LLM writes the answer"), (0.8, "Check the format")]):
        box(ax, 2.9, y, 3.2, 0.7, t, "blue", BLUE, size=12)
        if i:
            arrow(ax, (2.9, y + 0.75), (2.9, y + 0.37))
    ax.text(2.9, 0.12, "Same path every time (Lecture 18)", ha="center", fontsize=11, color="#3c3c3c", style="italic")
    ax.plot([5.75, 5.75], [0.2, 4.0], color="#d0d0d0", lw=1.5)
    ax.text(8.7, 3.9, "Agent: the model decides the next step", ha="center", fontsize=13, fontweight="bold", color=RED)
    box(ax, 8.7, 2.6, 2.4, 0.8, "LLM", "red", RED, size=13, weight="bold")
    for x, t in [(6.75, "query_log"), (8.7, "predict_energy"), (10.65, "set_tilt")]:
        box(ax, x, 0.9, 1.85, 0.55, t, "gold", GOLD, size=10.5)
        arrow(ax, (8.7 + (x - 8.7) * 0.35, 2.18), (x, 1.2), color=GRAY, style="<|-|>")
    ax.text(8.7, 3.35, "Loop until it answers or a budget runs out", ha="center", fontsize=11, color="#3c3c3c", style="italic")
    save(fig, "workflow-agent.png")

    # The loop, and where the guardrails sit.
    fig, ax = canvas(11, 4.8)
    box(ax, 2.0, 2.4, 2.6, 1.1, "LLM\nreads, then asks\nfor a tool or answers", "red", RED, size=11.5)
    box(ax, 6.2, 2.4, 3.0, 2.6, "", "white", GRAY)
    ax.text(6.2, 3.45, "Your code (the harness)", ha="center", fontsize=12, fontweight="bold")
    for i, t in enumerate(["Step budget left?", "Same call 3 times?", "Needs approval? Ask a person", "Run the tool, log it"]):
        ax.text(6.2, 2.9 - 0.47 * i, t, ha="center", fontsize=11, color=[GOLD, GOLD, GREEN, BLUE][i])
    box(ax, 9.9, 2.4, 1.8, 1.1, "Tool\nquery, model,\nmove panels", "gold", GOLD, size=11)
    arrow(ax, (3.35, 2.75), (4.65, 2.75), RED, "request", ty=0.2)
    arrow(ax, (7.75, 2.75), (8.95, 2.75), GRAY)
    arrow(ax, (8.95, 2.05), (7.75, 2.05), GRAY)
    arrow(ax, (4.65, 2.05), (3.35, 2.05), BLUE, "result", ty=-0.2)
    ax.text(2.0, 1.0, "Answer: the loop ends", ha="center", fontsize=11.5, color=RED)
    arrow(ax, (2.0, 1.82), (2.0, 1.25), RED)
    ax.text(6.2, 0.35, "The model only writes requests. Every check is a line of your code.",
            ha="center", fontsize=11.5, style="italic", color="#3c3c3c")
    save(fig, "agent-loop.png")

    # The harness: everything around the model.
    fig, ax = canvas(12, 5.6)
    ax.add_patch(FancyBboxPatch((0.15, 0.55), 11.7, 4.75, boxstyle="round,pad=0.02,rounding_size=0.2",
                                fc="#fbfbfb", ec=GRAY, lw=1.6, ls="--"))
    ax.text(6.0, 5.0, "The harness: the software around the model", ha="center", fontsize=14, fontweight="bold")
    box(ax, 6.0, 2.85, 2.1, 1.2, "LLM\nreads text,\nwrites requests", "red", RED, size=12)
    left = [("Builds the prompt", "system prompt, tool definitions,\ninstructions file, history", BLUE),
            ("Manages the context", "prompt cache, compaction,\nsubagents", "#7a3db8"),
            ("Ends the run", "answer, step budget,\nstuck, cost cap", GOLD)]
    right = [("Runs the tools", "read and edit files, run commands,\nquery a database", GOLD),
             ("Checks permissions", "allow, ask, deny;\na sandbox; a person approves", GREEN),
             ("Logs every step", "what was asked, what ran,\nwhat came back", GRAY)]
    for i, (title, sub, c) in enumerate(left):
        y = 4.1 - 1.25 * i
        box(ax, 2.2, y, 3.5, 1.0, "", "white", c)
        ax.text(2.2, y + 0.22, title, ha="center", fontsize=12, fontweight="bold", color=c)
        ax.text(2.2, y - 0.2, sub, ha="center", va="center", fontsize=10, color="#3c3c3c", linespacing=1.2)
        arrow(ax, (3.98, y), (4.93, 2.85 + (y - 2.85) * 0.25), c)
    for i, (title, sub, c) in enumerate(right):
        y = 4.1 - 1.25 * i
        box(ax, 9.8, y, 3.5, 1.0, "", "white", c)
        ax.text(9.8, y + 0.22, title, ha="center", fontsize=12, fontweight="bold", color=c)
        ax.text(9.8, y - 0.2, sub, ha="center", va="center", fontsize=10, color="#3c3c3c", linespacing=1.2)
        arrow(ax, (7.07, 2.85 + (y - 2.85) * 0.25), (8.02, y), c)
    ax.text(3.6, 0.82, "what the model reads", ha="center", fontsize=10.5, color="#3c3c3c", style="italic")
    ax.text(8.4, 0.82, "what the model asks for", ha="center", fontsize=10.5, color="#3c3c3c", style="italic")
    ax.text(6.0, 0.15, "Claude Code, Codex and opencode are harnesses. So is the 30-line loop of the worked example.",
            ha="center", fontsize=11, style="italic", color="#3c3c3c")
    save(fig, "harness.png")

    # How a prompt cache works: the next call starts with the last call's whole prompt.
    fig, ax = canvas(12, 4.6)
    rows = [("Call 1", [("Tools + system prompt", 4.0, "w"), ("Task", 1.2, "w")]),
            ("Call 2", [("Tools + system prompt", 4.0, "r"), ("Task", 1.2, "r"), ("Request 1", 1.5, "w"),
                        ("Result 1", 1.7, "w")]),
            ("Call 2, with the\ntime in the prompt", [("10:02 + tools + system", 4.0, "x"), ("Task", 1.2, "w"),
                                                       ("Request 1", 1.5, "w"), ("Result 1", 1.7, "w")])]
    style = {"w": ("gold", GOLD), "r": ("green", GREEN), "x": ("red", RED)}
    for j, (label, blocks) in enumerate(rows):
        y = 3.75 - 1.3 * j
        ax.text(1.35, y, label, ha="right", va="center", fontsize=13, fontweight="bold")
        x0 = 1.6
        for text, w, k in blocks:
            f, e = style[k]
            box(ax, x0 + w / 2, y, w - 0.08, 0.7, text, f, e, size=12.5)
            x0 += w
    ax.text(10.4, 2.45, "cache hit:\nonly the new part\nis processed", fontsize=12, color=GREEN, va="center")
    ax.text(10.4, 1.15, "first block changed:\neverything is\nprocessed again", fontsize=12, color=RED, va="center")
    for x, t, c in ((2.0, "read from the cache (about 0.1x the price)", GREEN),
                    (7.7, "processed and written (about 1.25x)", GOLD)):
        ax.add_patch(FancyBboxPatch((x, 0.12), 0.35, 0.28, boxstyle="round,pad=0.01", fc=FILL[{GREEN: "green", GOLD: "gold"}[c]], ec=c))
        ax.text(x + 0.5, 0.26, t, va="center", fontsize=12, color="#3c3c3c")
    save(fig, "cache-prefix.png")

    # A coding agent's loop: gather context, take action, verify, and you can step in anywhere.
    fig, ax = canvas(11, 5.2)
    pts = {"gather": (2.05, 3.55), "act": (8.95, 3.55), "verify": (5.5, 0.85)}
    spec = {"gather": ("Gather context", "read files, search the code,\nread the docs", BLUE, "blue"),
            "act": ("Take action", "edit files,\nrun commands", GOLD, "gold"),
            "verify": ("Verify the result", "run the tests, the type checker,\nthe linter; read the errors", GREEN, "green")}
    for k, (x, y) in pts.items():
        title, sub, c, f = spec[k]
        box(ax, x, y, 3.7, 1.25, "", f, c)
        ax.text(x, y + 0.27, title, ha="center", fontsize=15, fontweight="bold", color=c)
        ax.text(x, y - 0.22, sub, ha="center", va="center", fontsize=12.5, color="#3c3c3c", linespacing=1.2)
    arrow(ax, (3.95, 3.7), (7.05, 3.7), GRAY)
    arrow(ax, (8.7, 2.9), (7.3, 1.5), GRAY)
    arrow(ax, (3.7, 1.5), (2.3, 2.9), GRAY)
    ax.text(5.5, 2.3, "You: a prompt to start;\nsteer, interrupt or\napprove at any point", ha="center", va="center",
            fontsize=13, color=RED, fontweight="bold")
    ax.text(5.5, 4.75, "Repeat until the task is done, or you stop it", ha="center", fontsize=13,
            style="italic", color="#3c3c3c")
    save(fig, "coding-loop.png")

    # A coding agent: the same loop, with parts you can configure.
    fig, ax = canvas(12, 5.4)
    box(ax, 6.0, 2.75, 2.0, 1.0, "LLM", "red", RED, size=15, weight="bold")
    parts = [(2.1, 4.45, "Instructions file", "AGENTS.md or CLAUDE.md:\nread at the start of every session", BLUE, "blue"),
             (6.0, 4.75, "Tools", "read, search, edit,\nrun commands, fetch a web page", GOLD, "gold"),
             (9.9, 4.45, "Permissions and sandbox", "allow, ask or deny each tool;\nlimit files and network", GREEN, "green"),
             (2.1, 1.05, "Context management", "compaction near the limit;\nsubagents with their own context", "#7a3db8", "purple"),
             (6.0, 0.75, "Extensions", "MCP servers (Lecture 18), skills,\nhooks that run your scripts", GRAY, "gray"),
             (9.9, 1.05, "You", "the prompt, approvals,\nreading every diff", RED, "red")]
    for x, y, title, sub, c, f in parts:
        box(ax, x, y, 3.6, 1.1, "", f, c)
        ax.text(x, y + 0.24, title, ha="center", fontsize=12, fontweight="bold", color=c if c != GRAY else "black")
        ax.text(x, y - 0.18, sub, ha="center", va="center", fontsize=10, color="#3c3c3c", linespacing=1.2)
        tx = 6.0 + (x - 6.0) * 0.13
        ty = 2.75 + (0.55 if y > 2.75 else -0.55)
        arrow(ax, (x + (0.0 if x == 6.0 else (1.0 if x < 6 else -1.0)), y + (-0.58 if y > 2.75 else 0.58)), (tx, ty), c, style="-")
    save(fig, "coding-agent.png")

    # The context window over a session: it fills, compaction makes room, a subagent works apart.
    fig, ax = canvas(12, 5.0)
    W0, W = 2.3, 8.6

    def bar(y, blocks, label, full=None):
        ax.text(W0 - 0.15, y, label, ha="right", va="center", fontsize=12.5, fontweight="bold", linespacing=1.15)
        ax.add_patch(FancyBboxPatch((W0, y - 0.32), W, 0.64, boxstyle="round,pad=0.0,rounding_size=0.05",
                                    fc="white", ec="#b0b0b0", lw=1.2, ls="--"))
        x = W0
        for text, w, f, e in blocks:
            box(ax, x + w / 2, y, w - 0.05, 0.56, text, f, e, size=11.5)
            x += w
        if full:
            ax.text(W0 + W + 0.1, y, full, va="center", fontsize=11.5, color="#3c3c3c")

    sysb = ("System + tools", 1.75, "blue", BLUE)
    mem = ("CLAUDE.md", 1.4, "blue", BLUE)
    bar(4.2, [sysb, mem, ("Your prompt", 1.4, "gold", GOLD)], "Start of a session", "room to work")
    bar(3.0, [sysb, mem, ("Your prompt", 1.4, "gold", GOLD),
              ("Files, command output, test logs ...", 4.0, "gold", GOLD)], "Long session", "near the limit")
    bar(1.8, [sysb, mem, ("Summary of the work", 2.4, "purple", "#7a3db8"), ("Recent", 1.1, "gold", GOLD)],
        "After compaction", "early details\nmay be lost")
    ax.text(W0 - 0.15, 0.55, "Subagent", ha="right", va="center", fontsize=12.5, fontweight="bold")
    box(ax, W0 + 2.6, 0.55, 5.2, 0.56, "Own window: reads 40 files for one question", "gray", GRAY, size=11.5)
    arrow(ax, (W0 + 5.25, 0.85), (W0 + 6.1, 1.47), "#7a3db8", "returns a short answer", size=11.5, tx=1.4)
    ax.text(W0 + W / 2, 4.8, "The context window: everything the model reads on one call", ha="center",
            fontsize=14, fontweight="bold")
    save(fig, "context.png")

    # Multi-agent: a lead agent hands parts to subagents, at a price in tokens.
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.4), gridspec_kw={"width_ratios": [1.35, 1]})
    a1.set_xlim(0, 7)
    a1.set_ylim(0, 4.4)
    a1.axis("off")
    box(a1, 3.5, 3.6, 2.6, 0.75, "Lead agent\nplans, then combines", "red", RED, size=13)
    for x, t in ((1.1, "Subagent 1\nsearch topic A"), (3.5, "Subagent 2\nsearch topic B"), (5.9, "Subagent 3\nsearch topic C")):
        box(a1, x, 1.5, 2.1, 0.85, t, "gold", GOLD, size=12)
        arrow(a1, (3.5 + (x - 3.5) * 0.3, 3.2), (x, 1.92), GRAY)
        a1.text(x, 0.82, "own context window", ha="center", fontsize=11.5, color="#3c3c3c", style="italic")
    a1.text(3.5, 0.2, "They work in parallel; each sends back a summary", ha="center", fontsize=12.5,
            color="#3c3c3c")
    labels, vals, cols = ["Chat", "One agent", "Multi-agent"], [1, 4, 15], [GRAY, GOLD, RED]
    a2.bar(labels, vals, color=[FILL["gray"], FILL["gold"], FILL["red"]], edgecolor=cols, lw=1.8, width=0.6)
    for i, v in enumerate(vals):
        a2.text(i, v + 0.4, f"about {v}x" if v > 1 else "1x", ha="center", fontsize=14, color=cols[i], fontweight="bold")
    a2.set_ylabel("Tokens used, relative to a chat")
    a2.set_ylim(0, 17.5)
    a2.set_title("Anthropic's research system (2025)", fontsize=13.5)
    fig.tight_layout(w_pad=2)
    save(fig, "multi-agent.png")


    # project.png: a project a coding agent can work in, drawn as a blueprint, with the lecture
    # that taught each part.
    fig, ax = canvas(12.4, 5.6)
    ax.add_patch(Rectangle((0, 0), 12.4, 5.6, fc="#18467c", ec="none"))
    for g in range(1, 50):
        ax.plot([g * 0.25, g * 0.25], [0, 5.6], color="#2c5c96", lw=0.5)
    for g in range(1, 23):
        ax.plot([0, 12.4], [g * 0.25, g * 0.25], color="#2c5c96", lw=0.5)
    ax.text(0.35, 5.15, "my-project/", color="white", fontsize=15, family="monospace", fontweight="bold")
    ax.text(12.05, 5.15, "A project a coding agent can work in", color="#cfe0f5", fontsize=13, ha="right",
            style="italic")
    items = [("pyproject.toml, uv.lock", "L2", "one environment for you, the agent and CI"),
             ("AGENTS.md", "L19", "how to set up, how to test, what not to touch"),
             ("src/", "L2", "modules the agent can import and test"),
             ("tests/", "pytest", "pass or fail: the agent knows when it is done"),
             ("data/measurements.duckdb", "L3 L4", "SQL, through a read-only connection"),
             ("schemas/", "L6", "validation catches wrong data before it is used"),
             ("runs/", "L10", "every number traces back to the run that made it"),
             (".git/", "L2", "every change is a diff you can read and undo")]
    for i, (path, lec, why) in enumerate(items):
        y = 4.5 - 0.56 * i
        branch = "└── " if i == len(items) - 1 else "├── "
        ax.text(0.45, y, branch + path, color="white", fontsize=13, family="monospace", va="center")
        ax.plot([4.75, 5.35], [y, y], color="#8fb3de", lw=1, ls=":")
        ax.text(5.5, y, lec, color="#18467c", fontsize=11, fontweight="bold", va="center",
                bbox={"fc": "#ffd166", "ec": "none", "boxstyle": "round,pad=0.25"})
        ax.text(6.6, y, why, color="white", fontsize=12, va="center")
    save(fig, "project.png")


# ------------------------------------------------------------------------------ evidence
def group_evidence():
    # METR, Becker et al. (2025), and METR's February 2026 re-run: change in the time to finish a
    # task when AI tools are allowed. Negative is faster. Bars with whiskers are measured, with the
    # 95% confidence interval METR reports; the 2026 row is the developers who returned from 2025.
    # metr-1.png to metr-3.png reveal one row at a time on the same canvas; metr.png is all four.
    rows = [("2025: forecast by the\ndevelopers, before", -24, None, BLUE),
            ("2025: estimated by the\ndevelopers, after", -20, None, GOLD),
            ("2025: measured", 19, (2, 39), RED),
            ("2026 re-run, same developers:\nmeasured", -18, (-38, 9), GRAY)]
    for frame in (1, 2, 3, 4):
        fig, ax = plt.subplots(figsize=(11, 4.6))
        fig.subplots_adjust(left=0.25, right=0.97, bottom=0.17, top=0.95)
        for i, (label, v, ci, c) in enumerate(rows):
            y = 3 - i
            show = i < frame
            ax.barh(y, v, color=c, height=0.55, alpha=(0.9 if c != GRAY else 0.55) if show else 0)
            if ci and show:
                ax.plot(ci, [y, y], color="black", lw=1.4)
                for e in ci:
                    ax.plot([e, e], [y - 0.12, y + 0.12], color="black", lw=1.4)
            edge = (ci[1] if v > 0 else ci[0]) if ci else v
            if show:
                ax.text(edge + (1.5 if v > 0 else -1.5), y, f"{abs(v)}% {'slower' if v > 0 else 'faster'}",
                        ha="left" if v > 0 else "right", va="center", fontsize=14, fontweight="bold",
                        color=c if c != GRAY else "#5c5c5c")
        if frame >= 3:
            ax.annotate("", xy=(19, 1.27), xytext=(-20, 1.73),
                        arrowprops={"arrowstyle": "->", "color": RED, "lw": 2, "connectionstyle": "arc3,rad=-0.35"})
            ax.text(22, 1.62, "felt faster,\nwas slower", fontsize=12, color=RED, style="italic", va="center")
        if frame == 4:
            ax.text(14, 0, "tasks were skipped: METR calls\nit \"an unreliable signal\"", fontsize=11.5,
                    color="#5c5c5c", style="italic", va="center")
        ax.set_yticks([3, 2, 1, 0])
        ax.set_yticklabels([r[0] for r in rows], fontsize=12.5)
        for i, t in enumerate(ax.get_yticklabels()):
            t.set_color("black" if i < frame else "white")
        ax.axvline(0, color="black", lw=1)
        ax.set_xlim(-62, 55)
        ax.set_ylim(-0.6, 3.5)
        ax.set_xticks([-40, -20, 0, 20, 40])
        ax.set_xticklabels(["-40%", "-20%", "0", "+20%", "+40%"])
        ax.set_xlabel("Change in the time to finish a task when AI tools are allowed (whiskers: 95% interval)")
        ax.text(-61, -0.5, "faster", fontsize=11, color="#3c3c3c", style="italic")
        ax.text(54, -0.5, "slower", fontsize=11, color="#3c3c3c", style="italic", ha="right")
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        save(fig, "metr.png" if frame == 4 else f"metr-{frame}.png", tight=False)


# --------------------------------------------------------------------------------- codex
# Codex's crates, grouped by the job they do in the harness. Anything not listed is "other".
CODEX_GROUPS = [
    ("Talking to the model", ["codex-api", "codex-client", "model-provider", "model-provider-info",
                              "models-manager", "responses-api-proxy", "lmstudio", "ollama"]),
    ("Terminal interface", ["tui", "cli", "voice-host", "ansi-escape", "terminal-detection", "mermaid",
                            "feedback"]),
    ("Agent core: the loop,\nprompts, context", ["core", "core-api", "prompts", "context-fragments", "memories",
                                               "skills", "history", "message-history", "code-mode",
                                               "code-mode-host", "code-mode-protocol", "code-mode-runtime",
                                               "agent-roles", "runtime-agent-instance"]),
    ("Tools: files,\nshell, patches", ["apply-patch", "file-search", "file-system", "file-watcher",
                                      "shell-command", "exec", "tools", "git-utils", "worktree",
                                      "direct-tool-timing", "attachment-store"]),
    ("Permissions\nand sandbox", ["windows-sandbox-rs", "windows-sandbox-service", "linux-sandbox", "sandboxing",
                                  "execpolicy", "network-proxy", "process-hardening", "bwrap", "mxc-sandbox",
                                  "guardian-context", "secrets", "keyring-store", "user-verification"]),
    ("Extensions: MCP,\nplugins, hooks", ["ext", "core-plugins", "core-plugin-common", "plugin", "plugin-host",
                                         "hooks", "rmcp-client", "codex-mcp", "connectors", "message-board",
                                         "message-board-mcp", "agent-message-board-client", "agent-graph-store"]),
    ("Sessions and\nhistory", ["thread-store", "state", "rollout", "rollout-trace", "thread-manager-sample"]),
    ("Editors and apps:\nservers, protocols", ["app-server", "app-server-client", "app-server-daemon",
                                             "app-server-protocol", "app-server-transport",
                                             "app-server-protocol-noop-macros", "exec-server", "exec-server-cli",
                                             "exec-server-protocol", "protocol", "uds", "stdio-to-uds",
                                             "websocket-auth", "websocket-client", "tcp-tunnel",
                                             "realtime-webrtc", "otel-trace-websocket"]),
]


def codex_counts():
    """Lines of Rust per crate of openai/codex at CODEX_COMMIT, test files and test folders excluded."""
    src = Path(os.environ.get("CODEX_SRC", CACHE / "codex"))
    if not (src / "codex-rs").exists():
        src.mkdir(parents=True, exist_ok=True)
        for cmd in (["git", "init", "-q"], ["git", "fetch", "-q", "--depth", "1",
                                            "https://github.com/openai/codex.git", CODEX_COMMIT],
                    ["git", "checkout", "-q", "FETCH_HEAD"]):
            subprocess.run(cmd, cwd=src, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True, text=True).stdout.strip()
    if head != CODEX_COMMIT:
        print(f"  note: {src} is at {head[:9]}, not the pinned {CODEX_COMMIT[:9]}")
    counts = {}
    for crate in sorted((src / "codex-rs").iterdir()):
        n = 0
        for f in crate.rglob("*.rs"):
            if "test" in str(f.relative_to(src)):
                continue
            n += len(f.read_bytes().splitlines())
        if n:
            counts[crate.name] = n
    return counts


def group_codex():
    import squarify
    counts = codex_counts()
    total = sum(counts.values())
    groups = []
    seen = set()
    for name, crates in CODEX_GROUPS:
        groups.append((name, sum(counts.get(c, 0) for c in crates)))
        seen.update(crates)
    groups.append(("Settings, login,\ntelemetry, other", sum(v for k, v in counts.items() if k not in seen)))
    print(f"  Codex at {CODEX_COMMIT[:9]}: {total:,} lines of Rust in {len(counts)} crates, tests excluded")
    for name, v in groups:
        print(f"    {name.replace(chr(10), ' ')}: {v:,} ({v / total:.1%})")

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14.5, 5.4), gridspec_kw={"width_ratios": [1, 1]})
    # Left: Lecture 1's redrawing of the "ML code is a small box" figure, unchanged.
    a1.set_xlim(0, 100)
    a1.set_ylim(-9, 46)
    a1.axis("off")
    for label, x, y, w, h in [("Configuration", 0, 16, 14, 30), ("Process\nmanagement tools", 70, 16, 30, 30),
                              ("Data collection", 14, 30, 22, 16), ("Feature\nextraction", 36, 30, 16, 16),
                              ("Analysis tools", 52, 30, 18, 16), ("Machine resource\nmanagement", 14, 16, 26, 14),
                              ("Monitoring", 52, 16, 18, 14), ("Data verification", 0, 0, 40, 16),
                              ("Serving infrastructure", 40, 0, 60, 16)]:
        a1.add_patch(Rectangle((x, y), w, h, fc="#f2f2f4", ec="#5c5c5c", lw=1.1))
        a1.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=10.5, color="#5c5c5c")
    a1.add_patch(Rectangle((40, 16), 12, 14, fc=RED, ec=RED))
    a1.text(46, 23, "ML\ncode", ha="center", va="center", fontsize=11, color="white", fontweight="bold")
    a1.text(50, -5.5, "Sculley et al. (2015), redrawn", ha="center", va="center", fontsize=11, color="#5c5c5c",
            style="italic")
    a1.set_title("Lecture 1: a production ML system", fontsize=14, pad=12)
    # Right: Codex, sized by lines of code. The red box is the code that talks to the model.
    order = sorted(groups[1:], key=lambda g: -g[1])
    order.insert(3, groups[0])
    W, H = 100, 46
    rects = squarify.squarify(squarify.normalize_sizes([v for _, v in order], W, H), 0, 0, W, H)
    a2.set_xlim(0, W)
    a2.set_ylim(-9, H)
    a2.axis("off")
    for (name, v), r in zip(order, rects):
        red = name == "Talking to the model"
        a2.add_patch(Rectangle((r["x"], r["y"]), r["dx"], r["dy"], fc=RED if red else "#f2f2f4", ec="#5c5c5c",
                               lw=1.1))
        if red:
            a2.annotate(f"Talking to the model: {v / total:.0%} of the code", xy=(r["x"] + r["dx"] / 2, r["y"] + 2),
                        xytext=(r["x"] + r["dx"] / 2, -5.5), ha="center", va="center", fontsize=12, color=RED,
                        fontweight="bold", arrowprops={"arrowstyle": "->", "color": RED, "lw": 1.5})
        else:
            narrow = r["dx"] < 9
            a2.text(r["x"] + r["dx"] / 2, r["y"] + r["dy"] / 2, f"{name}\n{v / total:.0%}", ha="center",
                    va="center", fontsize=10.5, color="#5c5c5c", rotation=90 if narrow else 0,
                    linespacing=1.15)
    a2.set_title(f"Lecture 19: Codex, a coding agent, by lines of code ({total / 1e6:.1f} million)",
                 fontsize=14, pad=12)
    fig.tight_layout(w_pad=3)
    save(fig, "small-box.png")


# -------------------------------------------------------------------------------- course
AREAS = [("Lectures", ("lectures/",), BLUE, 1), ("Course pages and assignments", ("course/", "index.md"), GRAY, 1),
         ("Practice game and map", ("game/",), GREEN, -1), ("Clicker, arcade, Ask", ("clicker/", "arcade/", "chat/"), GOLD, -1),
         ("Build, checks and rules", ("",), "#7a3db8", -1)]
# pull request: (label, extra height, shift in days)
MILESTONES = {29: ("first lecture", 0, 0), 62: ("course map", 0, 0), 89: ("clicker", 0.6, -7), 109: ("arcade", 0, 6),
              105: ("first weekly release", 1.6, 6), 183: ("RAG chat", 0, 0), 203: ("Ask button", 0, 0),
              77: ("weekly release gate", 0, 0)}


def group_course():
    import datetime as dt
    import math

    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout

    total = len(git("log", "--no-merges", "--format=%H", "HEAD").split())
    claude = len(git("log", "--no-merges", "-i", "--grep=Co-Authored-By: Claude", "--format=%H", "HEAD").split())
    print(f"  {claude} of {total} commits (no merges) carry a Co-Authored-By: Claude line")

    # Every pull request merged into main: when its branch started, when it merged, how many
    # commits, and which part of the repository most of its files are in.
    prs = []
    for line in git("log", "--first-parent", "--merges", "--format=%H %cI %s", "HEAD").splitlines():
        h, when, subject = line.split(" ", 2)
        if not subject.startswith("Merge pull request #"):
            continue
        num = int(subject.split("#")[1].split()[0])
        commits = git("log", "--format=%aI", f"{h}^1..{h}^2").split()
        if not commits:
            continue
        files = git("diff", "--name-only", f"{h}^1", h).split()
        votes = {}
        for f in files:
            area = next(name for name, pre, _, _ in AREAS if any(f.startswith(x) for x in pre))
            votes[area] = votes.get(area, 0) + 1
        prs.append({"n": num, "start": dt.datetime.fromisoformat(min(commits)), "end": dt.datetime.fromisoformat(when),
                    "commits": len(commits), "area": max(votes, key=votes.get) if votes else AREAS[-1][0]})
    print(f"  {len(prs)} merged pull requests, {prs[-1]['end']:%Y-%m-%d} to {prs[0]['end']:%Y-%m-%d}")

    fig, ax = plt.subplots(figsize=(14, 5.8))
    num = matplotlib.dates.date2num
    d0, d1 = num(dt.datetime(2026, 7, 14)), num(dt.datetime(2026, 11, 5))
    ax.plot([d0, d1], [0, 0], color="#2b2b2b", lw=3, solid_capstyle="round", zorder=4)
    ax.text(d1 + 1, 0, "main", va="center", fontsize=12, fontweight="bold")
    style = {name: (c, side) for name, _, c, side in AREAS}
    for pr in prs:
        c, side = style[pr["area"]]
        x0, x1 = num(pr["start"]), num(pr["end"])
        if x1 - x0 < 0.8:
            x0 = x1 - 0.8
        h = side * (0.4 + 0.55 * math.sqrt(pr["commits"]))
        t = [i / 40 for i in range(41)]
        ax.plot([x0 + (x1 - x0) * u for u in t], [h * math.sin(math.pi * u) for u in t], color=c, lw=1.6, alpha=0.75)
        ax.plot([x1], [0], "o", color=c, ms=5, zorder=5)
        if pr["n"] in MILESTONES:
            label, up, shift = MILESTONES[pr["n"]]
            ax.annotate(label, xy=((x0 + x1) / 2, h), xytext=((x0 + x1) / 2 + shift, h + (0.5 + up) * side),
                        ha="center", va="bottom" if side > 0 else "top", fontsize=10.5, color=c, fontweight="bold",
                        arrowprops={"arrowstyle": "-", "color": c, "lw": 0.8})
    for name, _, c, side in AREAS:
        ax.plot([], [], color=c, lw=3, label=f"{name} ({'above' if side > 0 else 'below'})")
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=10.5, bbox_to_anchor=(0, 1.12))
    ax.set_xlim(d0, d1 + 6)
    ax.set_ylim(-5.0, 3.3)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%B"))
    ax.text(d1 + 6, -4.8, f"{len(prs)} pull requests, each a branch that merged into main.\n"
            "Taller arcs carry more commits.", ha="right", va="bottom", fontsize=11, color="#3c3c3c", style="italic")
    save(fig, "course-history.png")

    # course-build.png: how one change reaches the site.
    fig, ax = canvas(13.4, 5.5)
    R1, R2 = 3.65, 1.0
    steps = [(1.65, R1, 3.0, "Instructor", "writes the spec:\ntopics, data, examples", GRAY, "gray"),
             (5.0, R1, 3.3, "Claude Code", "reads CLAUDE.md, the rules;\nwrites notes, slides, figures,\nnotebook, practice questions", RED, "red"),
             (8.3, R1, 2.6, "Pull request", "a branch with\nthe change", GOLD, "gold"),
             (11.6, R1, 3.3, "Automatic checks", "strict build, index, quiz quotes\nmatch the notes, figures exist,\nno instructor file published", BLUE, "blue"),
             (11.6, R2, 3.0, "Instructor", "reads it, asks\nfor fixes, merges", GREEN, "green"),
             (8.3, R2, 2.9, "Weekly release", "a bot opens the release\nof the next lecture", "#7a3db8", "purple"),
             (5.0, R2, 3.0, "The public site", "notes, slides, notebooks,\npractice game, map", "#2b2b2b", "gray")]
    for x, y, w, title, sub, c, f in steps:
        box(ax, x, y, w, 1.5, "", f, c)
        ax.text(x, y + 0.45, title, ha="center", fontsize=13, fontweight="bold", color=c)
        ax.text(x, y - 0.18, sub, ha="center", va="center", fontsize=10.2, color="#3c3c3c", linespacing=1.2)
    for x0, x1, y in ((3.15, 3.35, R1), (6.65, 7.0, R1), (9.6, 9.95, R1), (10.1, 9.75, R2), (6.85, 6.5, R2)):
        arrow(ax, (x0, y), (x1, y), GRAY)
    arrow(ax, (11.6, R1 - 0.77), (11.6, R2 + 0.77), GRAY)
    arrow(ax, (11.0, R1 + 0.77), (5.6, R1 + 0.77), RED, rad=0.22)
    ax.text(8.3, 5.3, "a check fails: fix it", ha="center", fontsize=10.5, color=RED)
    arrow(ax, (10.3, R2 + 0.77), (6.0, R1 - 0.79), GREEN)
    ax.text(7.6, 2.08, "changes requested", ha="center", fontsize=10.5, color=GREEN)
    save(fig, "course-build.png")


# ------------------------------------------------------------------------------ timeline
# (date, label, kind, level): level is the height of the label, + above the axis, - below.
# Every date is from a primary source: the arXiv "v1" line, the company's dated announcement, or
# the repository's first commit (Auto-GPT, Codex CLI, agents.md).
TIMELINE = [
    ("2022-10-06", "ReAct: reason,\nthen act", "research", 1.1),
    ("2023-03-14", "GPT-4", "product", -0.9),
    ("2023-03-16", "Auto-GPT\n(open source)", "product", 2.2),
    ("2023-04-11", "Coscientist and ChemCrow\npreprints, same day", "science", -2.0),
    ("2023-06-13", "Function calling\nin OpenAI's API", "standard", 1.1),
    ("2023-10-10", "SWE-bench: real\nGitHub issues", "research", -0.9),
    ("2023-12-20", "Coscientist\nin Nature", "science", 2.2),
    ("2024-03-12", "Devin", "product", -2.0),
    ("2024-05-06", "SWE-agent: the\nagent-computer interface", "research", 1.1),
    ("2024-10-22", "Computer use", "product", -0.9),
    ("2024-11-25", "Model Context\nProtocol (MCP)", "standard", 2.2),
    ("2025-02-24", "Claude Code\n(preview)", "product", -2.0),
    ("2025-04-16", "Codex CLI\n(open source)", "product", 1.1),
    ("2025-08-19", "AGENTS.md\nformat", "standard", -0.9),
    ("2025-12-09", "MCP and AGENTS.md\njoin the Linux Foundation", "standard", 2.2),
    ("2026-02-11", "OpenAI: a product with\n0 hand-written lines", "product", -2.0),
]


def group_timeline():
    import datetime as dt
    colors = {"research": BLUE, "science": RED, "product": GOLD, "standard": GREEN}
    names = {"research": "Research", "science": "Science (chemistry)", "product": "Products",
             "standard": "Standards"}
    fig, ax = plt.subplots(figsize=(13, 4.6))
    d0, d1 = dt.date(2022, 8, 1), dt.date(2026, 5, 1)
    ax.plot([d0, d1], [0, 0], color="#3c3c3c", lw=1.6)
    for y in range(2023, 2027):
        d = dt.date(y, 1, 1)
        ax.plot([d, d], [-0.12, 0.12], color="#3c3c3c", lw=1.6)
        ax.text(d, -0.32, str(y), ha="center", va="top", fontsize=11, color="#3c3c3c", fontweight="bold")
    for date, label, kind, level in TIMELINE:
        d = dt.date.fromisoformat(date)
        c = colors[kind]
        ax.plot([d, d], [0, level * 0.82], color=c, lw=1.2, alpha=0.7)
        ax.plot([d], [0], "o", color=c, ms=8, mec="white", zorder=5)
        ax.text(d, level, f"{d:%b %Y}\n{label}" if level > 0 else f"{label}\n{d:%b %Y}",
                ha="center", va="bottom" if level > 0 else "top", fontsize=9.6, color="black",
                linespacing=1.15, bbox={"fc": "white", "ec": c, "lw": 1.3, "boxstyle": "round,pad=0.25"})
    for i, (k, name) in enumerate(names.items()):
        ax.plot([], [], "o", color=colors[k], ms=9, label=name)
    ax.legend(loc="upper left", ncol=4, frameon=False, fontsize=10.5, bbox_to_anchor=(0.0, 1.13))
    ax.set_xlim(d0, d1)
    ax.set_ylim(-3.3, 3.5)
    ax.axis("off")
    save(fig, "timeline.png")


GROUPS = {"trace": group_trace, "diagrams": group_diagrams, "codex": group_codex, "timeline": group_timeline,
          "evidence": group_evidence, "course": group_course}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(name)
        GROUPS[name]()
