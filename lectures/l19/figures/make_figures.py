#!/usr/bin/env python3
"""Generate the L19 figures and the data behind its interactive figures, and print every number
the notes and the deck quote.

Run from this directory:
    uv run --no-project --python 3.12 --with duckdb --with numpy --with matplotlib \
        --with tiktoken --with nbformat python make_figures.py

Name groups to regenerate only those; with no names, every group runs.

    trace        runs the scripted agent of ../l19-agents.ipynb (its code cells, executed here),
                 counts the tokens of every message with tiktoken (o200k_base, the GPT-4o
                 tokenizer; other providers count a little differently), and writes the
                 "trace" widget data and tokens.png.
    reliability  reliability.png: p^n against the number of tool calls, with the success rates
                 the notebook's ten-task evaluation measures at p = 0.9 (200 runs per task).
    diagrams     coscientist.png (redrawn from the Coscientist paper's description of its
                 modules), workflow-agent.png, agent-loop.png and coding-agent.png.
    course       the commit counts the deck quotes for this course's own history.
"""
import contextlib
import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

HERE = Path(__file__).resolve().parent
LECTURE = HERE.parent
REPO = HERE.parents[2]
CACHE = HERE / ".cache"
CACHE.mkdir(exist_ok=True)
NOTEBOOK = LECTURE / "l19-agents.ipynb"
WIDGET_JS = REPO / "_static" / "l19-widget-data.js"

RED, BLUE, GOLD, GREEN, GRAY = "#c41230", "#1f5c99", "#b07d12", "#2e7d32", "#8a8a8a"
FILL = {"blue": "#dbe8f5", "gold": "#f7e3c3", "green": "#dcefdc", "red": "#f6d9de", "gray": "#ececec",
        "purple": "#e8e0f2"}
plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 150, "savefig.bbox": "tight"})


def save(fig, name):
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"  wrote {name}")


def cache_put(name, obj):
    (CACHE / f"{name}.json").write_text(json.dumps(obj))


def notebook_namespace(skip=("evaluate(p=", "pass_hat_k(w")):
    """Execute the notebook's code cells (not the Colab cell, not the slow evaluation printouts)."""
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

    # The conversation, message by message, and what each model call reads.
    steps, calls, history = [], [], 0
    for m in run["messages"]:
        if m["role"] == "user":
            text, kind = m["content"], "user"
        elif m["role"] == "assistant":
            c = m["content"]
            if "answer" in c:
                text, kind = c["answer"], "answer"
            else:
                text, kind = f'{c["tool"]}({json.dumps(c["input"])})', "request"
            # this reply came from a model call that read the prefix and everything before it
            calls.append({"input": P + history, "history": history, "output": count(json.dumps(c))})
        else:
            text, kind = json.dumps(m["content"]), "result"
        tokens = count(text if kind == "user" else json.dumps(m["content"]))
        steps.append({"kind": kind, "text": text, "tokens": tokens, "call": len(calls)})
        history += tokens
    # mark which tool request needed approval: the log says so
    for s in steps:
        if s["kind"] == "request" and s["text"].startswith("set_temperature"):
            s["approval"] = "operator says yes"
    total_in = sum(c["input"] for c in calls)
    n = len(calls)
    m_avg = (calls[-1]["history"]) / (n - 1)
    print(f"  prefix: system {prefix['system']} + tools {prefix['tools']} = {P} tokens")
    for i, c in enumerate(calls, 1):
        print(f"  call {i}: reads {c['input']} tokens ({P} prefix + {c['history']} history), writes {c['output']}")
    print(f"  {n} calls read {total_in} input tokens in total; the last conversation alone is "
          f"{calls[-1]['input']}; history grows about {m_avg:.0f} tokens per call")
    print(f"  formula n*P + m*n(n-1)/2 = {n * P + m_avg * n * (n - 1) / 2:.0f}")
    for k in (10, 30):
        print(f"  at {k} calls with the same P and m: {k * P + m_avg * k * (k - 1) / 2:,.0f} input tokens")
    cache_put("trace", {"steps": steps, "calls": calls, "prefix": prefix, "task": run["messages"][0]["content"],
                        "tokenizer": "o200k_base", "m": round(m_avg)})

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


# --------------------------------------------------------------------------- reliability
def group_reliability():
    ns = notebook_namespace()
    cwd = os.getcwd()
    os.chdir(LECTURE)
    try:
        rows = ns["evaluate"](p=0.9)
    finally:
        os.chdir(cwd)
    by_n = {}
    for _, n, wins in rows:
        by_n.setdefault(n, []).append(wins / 200)
    measured = {n: sum(v) / len(v) for n, v in sorted(by_n.items())}
    pass_k = {k: sum(math.comb(w, k) / math.comb(200, k) for *_, w in rows) / len(rows) for k in (1, 2, 4, 8)}
    for n, v in measured.items():
        print(f"  p = 0.9, {n} tool call(s): measured {v:.2f} over {len(by_n[n])} tasks, p^n = {0.9 ** n:.2f}")
    print("  " + ", ".join(f"pass^{k} = {v:.2f}" for k, v in pass_k.items()))
    for p in (0.99, 0.95, 0.9):
        print(f"  p = {p}: 10 calls {p ** 10:.2f}, 20 calls {p ** 20:.2f}, 50 calls {p ** 50:.2f}")
    cache_put("reliability", {"measured": measured, "pass_k": pass_k})

    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    n = list(range(1, 51))
    for p, c in ((0.99, GREEN), (0.95, BLUE), (0.9, RED)):
        ax.plot(n, [p ** k for k in n], color=c, lw=2.5)
        ax.text(51, max(p ** 50, 0.035), f"p = {p}", color=c, va="center", fontsize=12)
    ax.plot(list(measured), list(measured.values()), "o", color=RED, ms=8, mec="white", zorder=5)
    ax.annotate("measured in the notebook\n(p = 0.9, 200 runs per task)", xy=(3, measured[3]),
                xytext=(29, 0.43), fontsize=11, color=RED, arrowprops={"arrowstyle": "->", "color": RED})
    ax.annotate(f"20 calls at p = 0.95:\n{0.95 ** 20:.2f}", xy=(20, 0.95 ** 20), xytext=(26, 0.55),
                fontsize=11, color=BLUE, arrowprops={"arrowstyle": "->", "color": BLUE})
    ax.set_xlim(0, 56)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Tool calls in the task, n")
    ax.set_ylabel("Chance the whole task succeeds, $p^n$")
    save(fig, "reliability.png")


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
    # The tank of Lecture 15: the yield of B against temperature, from the notebook's own model.
    ns = notebook_namespace()
    yB = ns["yield_B"]
    T = [20 + 0.5 * i for i in range(241)]
    y = [yB(t, 10) for t in T]
    fig, ax = plt.subplots(figsize=(8.2, 3.8))
    ax.plot(T, y, color=BLUE, lw=2.8)
    for t, c, label, dx in ((65, GRAY, "last week, 65 °C", -4), (80, GOLD, "best, 80 °C", 4)):
        ax.plot([t], [yB(t, 10)], "o", color=c, ms=10, mec="white", zorder=5)
        ax.annotate(f"{label}\nyield {yB(t, 10):.2f}", xy=(t, yB(t, 10)), xytext=(t + dx * 6, yB(t, 10) - 0.13),
                    ha="center", fontsize=11.5, color=c, arrowprops={"arrowstyle": "->", "color": c})
    ax.set_xlabel("Temperature (°C), residence time 10 min")
    ax.set_ylabel("Yield of B")
    ax.set_ylim(0, 0.55)
    save(fig, "tank.png")

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
    ax.text(5.9, 0.35, "A person moved plates between instruments;\nGC-MS confirmed the products",
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
    for x, t in [(6.75, "query_log"), (8.7, "predict_yield"), (10.65, "set_temperature")]:
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
    box(ax, 9.9, 2.4, 1.8, 1.1, "Tool\nquery, model,\nsetpoint", "gold", GOLD, size=11)
    arrow(ax, (3.35, 2.75), (4.65, 2.75), RED, "request", ty=0.2)
    arrow(ax, (7.75, 2.75), (8.95, 2.75), GRAY)
    arrow(ax, (8.95, 2.05), (7.75, 2.05), GRAY)
    arrow(ax, (4.65, 2.05), (3.35, 2.05), BLUE, "result", ty=-0.2)
    ax.text(2.0, 1.0, "Answer: the loop ends", ha="center", fontsize=11.5, color=RED)
    arrow(ax, (2.0, 1.82), (2.0, 1.25), RED)
    ax.text(6.2, 0.35, "The model only writes requests. Every check is a line of your code.",
            ha="center", fontsize=11.5, style="italic", color="#3c3c3c")
    save(fig, "agent-loop.png")

    # A coding agent: the same loop, different tools.
    fig, ax = canvas(11, 4.8)
    box(ax, 5.5, 2.5, 2.2, 1.0, "LLM", "red", RED, size=14, weight="bold")
    box(ax, 1.9, 3.9, 3.2, 0.9, "Instructions file (system prompt)\nAGENTS.md, CLAUDE.md", "blue", BLUE, size=11)
    box(ax, 9.1, 3.9, 3.2, 0.9, "Tools: read, search,\nedit, run commands", "gold", GOLD, size=11)
    box(ax, 1.9, 1.1, 3.2, 0.9, "Context management:\nsummaries, subagents", "purple", "#7a3db8", size=11)
    box(ax, 9.1, 1.1, 3.2, 0.9, "Permissions: allow, ask, deny\nchecked before a tool runs", "green", GREEN, size=11)
    arrow(ax, (3.5, 3.6), (4.4, 2.85), BLUE)
    arrow(ax, (6.6, 2.85), (7.5, 3.6), GOLD)
    arrow(ax, (7.5, 1.4), (6.6, 2.15), GREEN)
    arrow(ax, (3.5, 1.4), (4.4, 2.15), "#7a3db8")
    ax.text(5.5, 0.2, "Claude Code, opencode, Codex CLI, Copilot's agent mode: the loop of this lecture",
            ha="center", fontsize=11, style="italic", color="#3c3c3c")
    save(fig, "coding-agent.png")


# -------------------------------------------------------------------------------- course
def group_course():
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout

    total = len(git("log", "--no-merges", "--format=%H").split())
    claude = len(git("log", "--no-merges", "-i", "--grep=Co-Authored-By: Claude", "--format=%H").split())
    lines = len((REPO / "CLAUDE.md").read_text().splitlines())
    print(f"  {claude} of {total} commits (no merges) carry a Co-Authored-By: Claude line; CLAUDE.md has {lines} lines")


# ------------------------------------------------------------------------ widget data
def write_widget_data():
    data = {}
    for name in ("trace", "reliability"):
        p = CACHE / f"{name}.json"
        if p.exists():
            data[name] = json.loads(p.read_text())
    text = ("/* Generated by lectures/l19/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l19 = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB)")


GROUPS = {"trace": group_trace, "reliability": group_reliability, "diagrams": group_diagrams,
          "course": group_course}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(name)
        GROUPS[name]()
    write_widget_data()
