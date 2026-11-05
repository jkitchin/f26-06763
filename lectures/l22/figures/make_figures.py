#!/usr/bin/env python3
"""Generate the L22 figures from this repository's own history, and print every number the
notes and the deck quote.

Run from the repository root:

    uv run --no-project --python 3.12 --with matplotlib python lectures/l22/figures/make_figures.py

Everything is read from git with a fixed cutoff (CUTOFF below), so re-running after more
commits land reproduces the same figures. Move the cutoff on purpose, and re-read the notes
when you do, because the numbers in them are the ones this script prints.

    commits.png     commits per week, split by the model named in each commit's
                    Co-Authored-By trailer, with the first day of class marked
    milestones.png  the day each piece of course infrastructure first appeared, taken from the
                    first commit that added its file
    ratchet.png     the length of CLAUDE.md, the conventions file, at every commit that changed it
    decks.png       what each lecture's slide deck contains, counted from the deck files on disk:
                    figures, interactive figures, clicker questions and links

    releases.png    how many days before its class each lecture was published, from the commit that
                    uncommented it in _toc.yml (release gating began on 2026-08-20, so L1 and L2,
                    published before then, are shown as before the semester)
    rereading.png   Roediger and Karpicke (2006), Experiment 1: recall after rereading against after a
                    test, at three delays (Psychological Science 17(3), 249-255)
    tutor.png       Bastani et al. (2025), PNAS 122(26): practice and exam grades for the two AI
                    tutors, relative to students without one
    trio.png        Shen and Tamkin (2026), arXiv:2601.20245: quiz scores with and without an AI
                    assistant while learning the Trio library
                    These three are redrawn from the numbers the papers report, not from their data.

What measuring changed. The plan said the decks "got more interactive as the term went on", and
the count agrees only in part: interactive figures start at L12 and appear in most decks after
it, but clicker questions peak at L3 (six) and several later decks have none, because the
clicker arrived on 2026-08-25 and was then used where a question fitted rather than everywhere.
The plan also expected the conventions file to keep growing through the semester. It did not:
it grew from 241 to 859 lines before the first class, most of that in the two weeks when the
practice game, the style guide and the map arrived, and then by only about 125 lines in the ten
weeks of teaching. The rules were mostly written before the students arrived.
"""
from __future__ import annotations

import collections
import datetime as dt
import re
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CUTOFF = "2026-11-04T23:59:59"
FIRST_CLASS = dt.date(2026, 8, 24)

RED, BLUE, GOLD, GREEN, GRAY, PURPLE = "#c41230", "#1f5c99", "#b07d12", "#2e7d32", "#8a8a8a", "#6a4c93"
plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 150, "savefig.bbox": "tight"})

# Infrastructure, with the path whose first commit dates it. Lectures are not on this list:
# they are the content, and the point of the figure is what was built around them.
MILESTONES = [
    ("Conventions file, CLAUDE.md", "CLAUDE.md"),
    ("Writing style guide", "scientific_writing.md"),
    ("Practice game", "game/content"),
    ("Course map", "game/src/map"),
    ("Open in Colab buttons", "tools/colab_setup.py"),
    ("Clicker", "clicker"),
    ("One lecture released at a time", "tools/release_lecture.py"),
    ("Arcade minigames", "arcade"),
    ("Interactive figures (L12)", "_static/widgets.js"),
    ("Narrated slides (L20)", "_static/narration.js"),
    ("Ask button", "_static/ask.js"),
    ("Case studies from other fields", "case-studies"),
    ("Agent skill for the course", "skills"),
]

MODELS = ["Claude Opus 4.8", "Claude Opus 5", "Claude Sonnet 5", "Claude Opus 5.5"]
MODEL_COLORS = {"Claude Opus 4.8": GOLD, "Claude Opus 5": BLUE, "Claude Sonnet 5": GREEN,
                "Claude Opus 5.5": RED, "Claude, no model named": PURPLE, "no Claude trailer": GRAY}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def save(fig, name: str) -> None:
    fig.savefig(HERE / name)
    plt.close(fig)
    print(f"wrote {name}")


def commits() -> list[dict]:
    """Every non-merge commit up to the cutoff: date, author, and the model it credits."""
    sep = "\x1e"
    out = git("log", "--no-merges", f"--until={CUTOFF}", f"--format=%H%x1f%ad%x1f%an%x1f%B{sep}",
              "--date=short", "HEAD")
    rows = []
    for chunk in out.split(sep):
        chunk = chunk.strip()
        if not chunk:
            continue
        h, day, author, body = chunk.split("\x1f", 3)
        trailer = re.findall(r"Co-Authored-By:\s*(Claude[^<\n]*)", body, re.I)
        model = "no Claude trailer"
        if trailer:
            name = re.sub(r"\s*\(.*?\)", "", trailer[0]).strip()   # "Claude Opus 5 (1M context)"
            model = next((m for m in MODELS if name.lower() == m.lower()), "Claude, no model named")
        rows.append({"hash": h, "day": dt.date.fromisoformat(day), "author": author, "model": model})
    return rows


def first_added(path: str) -> tuple[dt.date, str]:
    out = git("log", "--diff-filter=A", "--reverse", f"--until={CUTOFF}", "--format=%ad %h",
              "--date=short", "HEAD", "--", path).split("\n")[0]
    day, h = out.split()
    return dt.date.fromisoformat(day), h


def week_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def fig_commits(rows: list[dict]) -> None:
    weeks = sorted({week_of(r["day"]) for r in rows})
    weeks = [weeks[0] + dt.timedelta(weeks=i) for i in range((weeks[-1] - weeks[0]).days // 7 + 1)]
    order = MODELS + ["Claude, no model named", "no Claude trailer"]
    counts = {m: collections.Counter() for m in order}
    for r in rows:
        counts[r["model"]][week_of(r["day"])] += 1

    fig, ax = plt.subplots(figsize=(13, 4.8))
    x = mdates.date2num([w + dt.timedelta(days=3) for w in weeks])
    bottom = [0] * len(weeks)
    for m in order:
        h = [counts[m][w] for w in weeks]
        if not any(h):
            continue
        ax.bar(x, h, width=5.6, bottom=bottom, color=MODEL_COLORS[m], label=m, edgecolor="white", lw=0.5)
        bottom = [b + v for b, v in zip(bottom, h)]
    ax.axvline(mdates.date2num(FIRST_CLASS), color="black", lw=1.2, ls="--")
    ax.text(mdates.date2num(FIRST_CLASS) + 1, max(bottom) * 0.97, "first class, 2026-08-24",
            va="top", fontsize=11)
    ax.set_ylabel("commits per week")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%B"))
    ax.legend(frameon=False, fontsize=10.5, ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.set_title("Commits per week, by the model named in each commit's co-author line", fontsize=13, loc="left")
    save(fig, "commits.png")


def fig_milestones(found: list[tuple[str, dt.date, str]]) -> None:
    fig, ax = plt.subplots(figsize=(13, 5.2))
    d0, d1 = dt.date(2026, 7, 14), dt.date(2026, 11, 8)
    ax.plot([mdates.date2num(d0), mdates.date2num(d1)], [0, 0], color="#2b2b2b", lw=3, zorder=1)
    ax.axvspan(mdates.date2num(d0), mdates.date2num(FIRST_CLASS), color="#f1ead8", zorder=0)
    ax.text(mdates.date2num(dt.date(2026, 7, 16)), -4.6, "before the semester", fontsize=11, style="italic",
            color="#5b4a32")
    ax.text(mdates.date2num(dt.date(2026, 9, 12)), -4.6, "during the semester", fontsize=11, style="italic",
            color="#5b4a32")
    # Label heights, in MILESTONES order, chosen so labels on nearby days do not collide.
    levels = [3.6, 2.4, -1.2, -2.6, -1.2, -3.6, 3.6, 2.4, 1.2, -1.2, -2.4, -3.6, 3.6]
    shift = {"Open in Colab buttons": 5}   # days to move a label sideways, off its neighbour
    for (label, day, _), y in zip(found, levels):
        xv = mdates.date2num(day)
        ax.plot([xv, xv], [0, y], color=GRAY, lw=0.8, zorder=1)
        ax.plot([xv], [0], "o", color=RED, ms=7, zorder=3)
        ax.text(xv + shift.get(label, 0), y + (0.12 if y > 0 else -0.12), f"{label}\n{day:%b %-d}", ha="center",
                va="bottom" if y > 0 else "top", fontsize=10.5)
    ax.set_ylim(-4.8, 5.0)
    ax.set_xlim(mdates.date2num(d0), mdates.date2num(d1))
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%B"))
    save(fig, "milestones.png")


def claude_md_history() -> list[tuple[dt.date, int, str]]:
    out = git("log", "--reverse", f"--until={CUTOFF}", "--format=%H %ad", "--date=short", "HEAD", "--", "CLAUDE.md")
    hist = []
    for line in out.splitlines():
        h, day = line.split()
        text = git("show", f"{h}:CLAUDE.md")
        hist.append((dt.date.fromisoformat(day), text.count("\n"), h[:7]))
    return hist


def fig_ratchet(hist: list[tuple[dt.date, int, str]]) -> None:
    fig, ax = plt.subplots(figsize=(13, 4.2))
    xs = [mdates.date2num(d) for d, _, _ in hist]
    ys = [n for _, n, _ in hist]
    ax.step(xs, ys, where="post", color=RED, lw=2.2)
    ax.plot(xs, ys, "o", color=RED, ms=3.5)
    ax.axvline(mdates.date2num(FIRST_CLASS), color="black", lw=1.2, ls="--")
    ax.text(mdates.date2num(FIRST_CLASS) + 1, max(ys) * 0.12, "first class", fontsize=11)
    ax.set_ylabel("lines in CLAUDE.md")
    ax.set_ylim(0, max(ys) * 1.08)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%B"))
    ax.set_title(f"The conventions file, at each of the {len(hist)} commits that changed it", fontsize=13, loc="left")
    save(fig, "ratchet.png")


def deck_counts() -> list[dict]:
    rows = []
    for d in sorted((REPO / "lectures").glob("l[0-9][0-9]")):
        deck = d / "slides.md"
        if not deck.exists():
            continue
        s = deck.read_text()
        n = int(d.name[1:])
        if n >= 22:
            continue
        rows.append({
            "n": n,
            "slides": len(re.findall(r"^---$", s, re.M)) - 1,   # the first --- opens the frontmatter
            "figures": len(re.findall(r"!\[[^\]]*\]\(", s)),
            "drawn": len(re.findall(r"<svg\b", s)),
            "interactive": len(re.findall(r'data-widget="', s)),
            "clicker": len(re.findall(r'<div class="clicker"', s)),
            "links": len(re.findall(r"\]\(https?://|href=\"https?://", s)),
            "narrated": 'class="narration"' in s,
        })
    return rows


def fig_decks(rows: list[dict]) -> None:
    fig, axes = plt.subplots(5, 1, figsize=(13, 8.4), sharex=True)
    ns = [r["n"] for r in rows]
    for ax, (key, label, c) in zip(axes, [("figures", "image\nfigures", BLUE), ("drawn", "diagrams drawn\nin the slide", PURPLE),
                                          ("interactive", "interactive\nfigures", RED),
                                          ("clicker", "clicker\nquestions", GOLD), ("links", "links to\nsources", GREEN)]):
        v = [r[key] for r in rows]
        ax.bar(ns, v, color=c, width=0.7)
        ax.set_ylabel(label, rotation=0, ha="right", va="center", fontsize=12)
        for n, val in zip(ns, v):
            if val:
                ax.text(n, val, str(val), ha="center", va="bottom", fontsize=9)
        ax.set_ylim(0, max(v + [1]) * 1.3)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
    axes[-1].set_xticks(ns)
    axes[-1].set_xticklabels([f"L{n}" for n in ns])
    axes[0].set_title("What each slide deck contains, counted from the deck files", fontsize=13, loc="left")
    save(fig, "decks.png")


def releases() -> list[tuple[int, dt.date, dt.datetime]]:
    """(lecture, class date, publication time) for every lecture released since gating began."""
    sched = (REPO / "course" / "schedule.md").read_text()
    days = {int(n): dt.date(int(y), int(mo), int(d)) for n, mo, d, y in
            re.findall(r"Lecture (\d+): (\d\d)-(\d\d)-(\d{4})", sched)}
    out = []
    for n in sorted(days):
        log = git("log", "--reverse", "--since=2026-08-21", f"--until={CUTOFF}", "--format=%aI",
                  f"-G^      - file: lectures/l{n:02d}/notes", "HEAD", "--", "_toc.yml").split()
        if log:
            out.append((n, days[n], dt.datetime.fromisoformat(log[0])))
    return out


def fig_releases(rel) -> None:
    fig, ax = plt.subplots(figsize=(13, 4.4))
    ns = [n for n, _, _ in rel]
    ahead = [(day - when.date()).days for _, day, when in rel]
    ax.bar(ns, ahead, color=[RED if a == 0 else BLUE for a in ahead], width=0.7)
    for n, a in zip(ns, ahead):
        ax.text(n, a + 0.15, "same\nday" if a == 0 else f"{a} d", ha="center", fontsize=9, color=RED if a == 0 else "black")
    ax.axhline(7, color=GOLD, lw=2.5, ls="--")
    ax.text(min(ns) - 0.4, 7.25, "the plan: a week ahead", color=GOLD, fontsize=12, fontweight="bold")
    ax.set_xticks(ns, [f"L{n}" for n in ns])
    ax.set_ylim(0, 8.5)
    ax.set_ylabel("days published\nbefore the class")
    ax.set_title("How far ahead each lecture went public (L1 and L2 were up before the semester)",
                 fontsize=13, loc="left")
    save(fig, "releases.png")


def fig_learning() -> None:
    """The three learning studies, redrawn from the numbers each paper reports."""
    # Roediger and Karpicke 2006, Experiment 1: proportion recalled on the final test.
    delays = ["5 minutes", "2 days", "1 week"]
    reread, tested = [81, 54, 42], [75, 68, 56]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = range(len(delays))
    ax.plot(x, reread, "o-", color=GRAY, lw=3, ms=10, label="read it again")
    ax.plot(x, tested, "o-", color=RED, lw=3, ms=10, label="took a recall test")
    for i in x:
        ax.text(i, reread[i] + (2.5 if reread[i] > tested[i] else -5), f"{reread[i]}%", ha="center", color=GRAY, fontsize=12)
        ax.text(i, tested[i] + (2.5 if tested[i] > reread[i] else -5), f"{tested[i]}%", ha="center", color=RED, fontsize=12)
    ax.set_xticks(list(x), delays)
    ax.set_xlabel("time until the final test")
    ax.set_ylabel("recalled on the final test")
    ax.set_ylim(30, 90)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "rereading.png")

    # Bastani et al. 2025: change in grades relative to the control arm, in percent.
    fig, ax = plt.subplots(figsize=(9, 4.6))
    groups = ["GPT Base\n(a plain chat)", "GPT Tutor\n(built to tutor)"]
    practice, exam = [48, 127], [-17, 0]
    w = 0.36
    ax.bar([i - w / 2 for i in range(2)], practice, w, color=BLUE, label="practice, with the AI")
    ax.bar([i + w / 2 for i in range(2)], exam, w, color=RED, label="exam, without it")
    for i in range(2):
        ax.text(i - w / 2, practice[i] + 3, f"+{practice[i]}%", ha="center", fontsize=12)
        ax.text(i + w / 2, exam[i] + (3 if exam[i] >= 0 else -12), "no change" if exam[i] == 0 else f"{exam[i]}%",
                ha="center", fontsize=12)
    ax.axhline(0, color="black", lw=1)
    ax.set_xticks(range(2), groups)
    ax.set_ylabel("grade change against\nstudents with no AI")
    ax.set_ylim(-30, 145)
    ax.legend(frameon=False, loc="upper left")
    save(fig, "tutor.png")

    # Shen and Tamkin 2026: mean quiz score after learning Trio.
    fig, ax = plt.subplots(figsize=(7, 4.4))
    ax.bar([0, 1], [50, 67], 0.55, color=[RED, BLUE])
    for i, v in enumerate([50, 67]):
        ax.text(i, v + 2, f"{v}%", ha="center", fontsize=14, fontweight="bold")
    ax.set_xticks([0, 1], ["with an AI assistant", "coding by hand"])
    ax.set_ylabel("quiz score right after the task")
    ax.set_ylim(0, 80)
    save(fig, "trio.png")


def main() -> None:
    rows = commits()
    total = len(rows)
    by_model = collections.Counter(r["model"] for r in rows)
    by_author = collections.Counter(r["author"] for r in rows)
    claude = total - by_model["no Claude trailer"]
    prs = [ln for ln in git("log", "--first-parent", "--merges", f"--until={CUTOFF}", "--format=%s", "HEAD").splitlines()
           if ln.startswith("Merge pull request #")]
    first, last = min(r["day"] for r in rows), max(r["day"] for r in rows)
    before = sum(1 for r in rows if r["day"] < FIRST_CLASS)
    print(f"cutoff {CUTOFF}: {total} commits (no merges), {first} to {last}; {before} before the first class")
    print(f"  {len(prs)} pull requests merged into main")
    print(f"  {claude} commits ({100 * claude / total:.0f}%) carry a Co-Authored-By: Claude line")
    for m, c in by_model.most_common():
        days = sorted(r["day"] for r in rows if r["model"] == m)
        print(f"    {m:24s} {c:4d}   {days[0]} to {days[-1]}")
    print("  commits by author:", dict(by_author.most_common()))

    found = []
    for label, path in MILESTONES:
        day, h = first_added(path)
        found.append((label, day, h))
        print(f"  first appeared: {day} {h}  {label} ({path})")

    hist = claude_md_history()
    print(f"  CLAUDE.md: {len(hist)} revisions, {hist[0][1]} lines on {hist[0][0]} to {hist[-1][1]} on {hist[-1][0]}")
    at_class = [n for d, n, _ in hist if d < FIRST_CLASS][-1]
    print(f"    {at_class} lines on the day before the first class")
    flat = [(a, b) for (a, _, _), (b, _, _) in zip(hist, hist[1:])]
    gap = max(flat, key=lambda p: (p[1] - p[0]).days)
    print(f"    longest gap between changes: {gap[0]} to {gap[1]} ({(gap[1] - gap[0]).days} days)")

    decks = deck_counts()
    for r in decks:
        print(f"  L{r['n']:<2d} slides {r['slides']:3d}  figures {r['figures']:3d}  drawn {r['drawn']:3d}  interactive {r['interactive']:3d}"
              f"  clicker {r['clicker']:2d}  links {r['links']:3d}{'  narrated' if r['narrated'] else ''}")
    print(f"  totals: {sum(r['figures'] for r in decks)} figures, {sum(r['drawn'] for r in decks)} drawn,"
          f" {sum(r['interactive'] for r in decks)} interactive,"
          f" {sum(r['clicker'] for r in decks)} clicker questions over {len(decks)} decks")
    notes = sorted((REPO / "lectures").glob("l[0-2][0-9]/notes.md"))
    words = {p.parent.name: len(p.read_text().split()) for p in notes if p.parent.name != "l22"}
    print(f"  notes: {len(words)} sets, {sum(words.values()):,} words")
    banks = sorted((REPO / "game" / "content").glob("l[0-9][0-9].yml"))
    items = sum(len(re.findall(r"^  - id: ", b.read_text(), re.M)) for b in banks)
    print(f"  practice banks: {len(banks)}, {items} items")
    cases = [p for p in (REPO / "case-studies").glob("*.md") if p.name != "index.md"]
    print(f"  case studies: {len(cases)}")

    fig_commits(rows)
    fig_milestones(found)
    fig_ratchet(hist)
    fig_decks(decks)
    rel = releases()
    for n, day, when in rel:
        print(f"  L{n:<2d} class {day}  published {when:%Y-%m-%d %H:%M}  {(day - when.date()).days} days ahead")
    fig_releases(rel)
    fig_learning()


if __name__ == "__main__":
    main()
