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
                 "trace" widget data, tokens.png and caching.png. caching.png prices the same
                 run with Anthropic's cache multipliers (write 1.25x, read 0.1x the input price)
                 and extends it to 30 calls with the measured prefix and growth per call.
    diagrams     coscientist.png (redrawn from the Coscientist paper's description of its
                 modules), workflow-agent.png, agent-loop.png, harness.png, cache-prefix.png,
                 coding-loop.png, coding-agent.png, context.png and multi-agent.png.
    timeline     timeline.png: LLM agents from ReAct to today, every date from a primary source.
    evidence     metr.png: the forecast, believed and measured change in task time in METR's
                 2025 randomized trial (Becker et al., arXiv 2507.09089), and the returning
                 developers' estimate from METR's February 2026 re-run, which METR itself calls
                 an unreliable signal (metr.org/blog/2026-02-24-uplift-update/).
    course       claude-md.png: the length of this course's CLAUDE.md over its git history, and
                 the commit counts the deck quotes.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates  # noqa: E402
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

    # caching.png: the same run with a prompt cache. Call k+1 starts with everything call k sent,
    # so that part can be read from the cache; only what is new since call k is written.
    WRITE, READ = 1.25, 0.10
    inputs = [c["input"] for c in calls]
    hit = [0] + inputs[:-1]
    new = [i - h for i, h in zip(inputs, hit)]
    billed = sum(WRITE * w + READ * h for w, h in zip(new, hit))
    print(f"  with a cache: {sum(hit)} of {total_in} tokens read from the cache; billed as "
          f"{billed:,.0f} full-price tokens ({billed / total_in:.0%})")
    K = 30
    ext = [inputs[0] + m_avg * k for k in range(K)]
    plain = [sum(ext[:k]) for k in range(1, K + 1)]
    cached = [WRITE * ext[0] + sum(READ * ext[j - 1] + WRITE * (ext[j] - ext[j - 1]) for j in range(1, k))
              for k in range(1, K + 1)]
    print(f"  {K} calls: {plain[-1]:,.0f} tokens without a cache, {cached[-1]:,.0f} with ({cached[-1] / plain[-1]:.0%})")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.4, 4.3), gridspec_kw={"width_ratios": [1, 1.15]})
    x = range(1, n + 1)
    a1.bar(x, hit, color=FILL["green"], edgecolor=GREEN, label="Same as the last call: read from the cache")
    a1.bar(x, new, bottom=hit, color=FILL["gold"], edgecolor=GOLD, label="New since the last call: written")
    for i, (h, w) in enumerate(zip(hit, new), 1):
        a1.text(i, h + w + 18, f"{w}", ha="center", fontsize=11, color=GOLD)
    a1.set_xticks(list(x))
    a1.set_xlabel("Model call")
    a1.set_ylabel("Input tokens")
    a1.set_ylim(0, max(inputs) * 1.42)
    a1.legend(frameon=False, loc="upper left", fontsize=10.5)
    a1.set_title("Our run: most of each call was sent before", fontsize=12.5)
    kk = range(1, K + 1)
    a2.plot(kk, plain, color=RED, lw=2.6)
    a2.plot(kk, cached, color=GREEN, lw=2.6)
    a2.text(K + 0.6, plain[-1], f"no cache\n{plain[-1]:,.0f}", color=RED, va="center", fontsize=11)
    a2.text(K + 0.6, cached[-1], f"with a cache\n{cached[-1]:,.0f}", color=GREEN, va="center", fontsize=11)
    a2.set_xlim(0, K + 7)
    a2.set_xlabel("Model calls in the run")
    a2.set_ylabel("Input cost, in full-price tokens")
    a2.set_title(f"The same growth, extended to {K} calls", fontsize=12.5)
    a2.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    fig.tight_layout(w_pad=3)
    save(fig, "caching.png")


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
    ax.text(6.0, 0.15, "Claude Code, Codex CLI and opencode are harnesses. So is the 30-line loop of the worked example.",
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


# ------------------------------------------------------------------------------ evidence
def group_evidence():
    # METR, Becker et al. (2025), and METR's February 2026 re-run: change in the time to finish a
    # task when AI tools are allowed. Negative is faster. Bars with whiskers are measured, with the
    # 95% confidence interval METR reports; the 2026 row is the developers who returned from 2025.
    rows = [("2025: forecast by the\ndevelopers, before", -24, None, BLUE),
            ("2025: estimated by the\ndevelopers, after", -20, None, GOLD),
            ("2025: measured", 19, (2, 39), RED),
            ("2026 re-run, same developers:\nmeasured, \"unreliable\"", -18, (-38, 9), GRAY)]
    fig, ax = plt.subplots(figsize=(10, 4.3))
    for i, (label, v, ci, c) in enumerate(rows):
        y = 3 - i
        ax.barh(y, v, color=c, height=0.55, alpha=0.9 if c != GRAY else 0.55)
        if ci:
            ax.plot(ci, [y, y], color="black", lw=1.4)
            for e in ci:
                ax.plot([e, e], [y - 0.12, y + 0.12], color="black", lw=1.4)
        edge = (ci[1] if v > 0 else ci[0]) if ci else v
        ax.text(edge + (1.5 if v > 0 else -1.5), y, f"{abs(v)}% {'slower' if v > 0 else 'faster'}",
                ha="left" if v > 0 else "right", va="center", fontsize=14, fontweight="bold",
                color=c if c != GRAY else "#5c5c5c")
    ax.set_yticks([3, 2, 1, 0])
    ax.set_yticklabels([r[0] for r in rows], fontsize=12.5)
    ax.axvline(0, color="black", lw=1)
    ax.set_xlim(-62, 55)
    ax.set_xticks([-40, -20, 0, 20, 40])
    ax.set_xticklabels(["-40%", "-20%", "0", "+20%", "+40%"])
    ax.set_xlabel("Change in the time to finish a task when AI tools are allowed (whiskers: 95% interval)")
    ax.text(-61, -0.75, "faster", fontsize=11, color="#3c3c3c", style="italic")
    ax.text(54, -0.75, "slower", fontsize=11, color="#3c3c3c", style="italic", ha="right")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    save(fig, "metr.png")


# -------------------------------------------------------------------------------- course
def group_course():
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout

    total = len(git("log", "--no-merges", "--format=%H").split())
    claude = len(git("log", "--no-merges", "-i", "--grep=Co-Authored-By: Claude", "--format=%H").split())
    lines = len((REPO / "CLAUDE.md").read_text().splitlines())
    print(f"  {claude} of {total} commits (no merges) carry a Co-Authored-By: Claude line; CLAUDE.md has {lines} lines")

    # CLAUDE.md's length at every commit that changed it.
    import datetime as dt
    hist = []
    for line in git("log", "--reverse", "--format=%h %as", "--", "CLAUDE.md").splitlines():
        h, d = line.split()
        n = len(git("show", f"{h}:CLAUDE.md").splitlines())
        hist.append((dt.date.fromisoformat(d), n))
    print(f"  CLAUDE.md: {len(hist)} commits, {hist[0][1]} lines on {hist[0][0]}, {hist[-1][1]} on {hist[-1][0]}")

    def first(text):
        """The date of the commit that added this text to CLAUDE.md."""
        out = git("log", "--reverse", "--format=%as", "-S", text, "--", "CLAUDE.md").split()
        return dt.date.fromisoformat(out[0])

    rules = [("Verify every link and every number", "check every number against its source:\na quoted claim was not in its paper", 240),
             ("deployment_queued", "check the live site, not the green run:\nthe site served an old build for hours", 470),
             ("Never judge past work", "never judge past work by present content:\na quiz bug failed students who did nothing wrong", 700)]
    days = [d for d, _ in hist]
    fig, ax = plt.subplots(figsize=(10.5, 4.0))
    ax.step(days + [dt.date(2026, 11, 3)], [n for _, n in hist] + [hist[-1][1]], where="post", color=BLUE, lw=2.6)
    for key, label, ty in rules:
        d = first(key)
        y = max(n for dd, n in hist if dd <= d)
        ax.plot([d], [y], "o", color=RED, ms=8, mec="white", zorder=5)
        ax.annotate(label, xy=(d, y), xytext=(dt.date(2026, 10, 1), ty), fontsize=10.5, color=RED,
                    ha="center", va="center", arrowprops={"arrowstyle": "->", "color": RED, "lw": 1.1})
        print(f"  rule added {d}: {key}")
    ax.set_ylabel("Lines in CLAUDE.md")
    ax.set_ylim(0, 1150)
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax.set_title("The course's instructions file grew one rule at a time, most of them after a mistake", fontsize=12.5)
    save(fig, "claude-md.png")


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


# ------------------------------------------------------------------------ widget data
def write_widget_data():
    data = {}
    p = CACHE / "trace.json"
    if p.exists():
        data["trace"] = json.loads(p.read_text())
    text = ("/* Generated by lectures/l19/figures/make_figures.py. Do not edit. */\n"
            "window.COURSE_WIDGET_DATA = window.COURSE_WIDGET_DATA || {};\n"
            "window.COURSE_WIDGET_DATA.l19 = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n")
    WIDGET_JS.write_text(text)
    print(f"  wrote {WIDGET_JS.relative_to(REPO)} ({len(text) / 1024:.0f} KB)")


GROUPS = {"trace": group_trace, "diagrams": group_diagrams, "timeline": group_timeline,
          "evidence": group_evidence, "course": group_course}

if __name__ == "__main__":
    names = sys.argv[1:] or list(GROUPS)
    for name in names:
        print(name)
        GROUPS[name]()
    write_widget_data()
