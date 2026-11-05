#!/usr/bin/env python3
"""Generate lectures/l22/l22-git-history.ipynb, the L22 worked example.

Reads the history of a git repository with `git log` and plots it: commits per week, the
co-author trailers on those commits, the merged pull requests, and the length of one file over
time. In class it runs on this course's repository; the point is for students to run it on
their own final-project repository, which is why REPO and FILE are the first thing in it, and
why it can also clone a repository by URL (on Colab there is no local checkout to read).

Only the standard library and matplotlib, so it runs anywhere git does. The numbers it prints for
this repository match figures/make_figures.py when CUTOFF is the same.

Kept in a generator for deterministic cell ids and no hand-edited JSON. After regenerating,
execute it from the repository root's checkout so REPO = "../.." resolves:

    python3 lectures/l22/build_notebook.py
    export JUPYTER_DATA_DIR=$(mktemp -d)
    cd lectures/l22 && uv run --no-project --python 3.12 --with matplotlib --with nbclient \
        --with nbformat --with ipykernel python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l22-git-history.ipynb', as_version=4)
NotebookClient(nb, timeout=300, kernel_name='python3', resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l22-git-history.ipynb')
"
    cd ../.. && python3 tools/colab_setup.py --write "$PWD/lectures/l22/l22-git-history.ipynb"
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l22-git-history.ipynb"
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells, n = [], 0


def md(text):
    global n
    n += 1
    cells.append({"cell_type": "markdown", "id": f"md-{n:02d}", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    global n
    n += 1
    cells.append({"cell_type": "code", "id": f"code-{n:02d}", "execution_count": None,
                  "metadata": {}, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


md(r"""
# L22 worked example: reading a project's history from git

Every commit records a date, an author and a message, and many carry trailer lines such as
`Co-Authored-By:` at the end of the message. Read back with `git log`, the history of a
repository becomes data you can plot. This notebook asks four questions of one repository:

1. **When did the work happen?** Commits per week.
2. **Who or what wrote it?** The co-author trailers on those commits.
3. **How did it arrive?** The pull requests merged into the main branch.
4. **How did one file grow?** The length of a file, such as `README.md` or `CLAUDE.md`, at every
   commit that changed it.

In class it reads this course's repository. Then point it at your own final-project repository,
and ask of your project what the lecture asked of the course: when did the work happen, where
did it change direction, and which of your fixes should have become a rule written down.
""")

md(r"""
## Choose the repository

Set `REPO` to a local checkout, or set `REPO_URL` to a repository to clone (on Colab there is no
local checkout, so cloning is the way in; a private repository needs a token in the URL, which
you should not save in the notebook). `FILE` is the file whose growth to plot, and `CUTOFF`
freezes the history at a date so that the numbers do not move as commits land.
""")

code(r"""
REPO = "../.."          # this course's repository, when the notebook runs from lectures/l22
REPO_URL = ""           # e.g. "https://github.com/you/your-project.git" to clone instead
FILE = "CLAUDE.md"      # try "README.md" on your own project
CUTOFF = "2026-11-04T23:59:59"   # "" for everything up to now
""")

code(r"""
import collections, datetime as dt, re, subprocess, tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

if REPO_URL:
    REPO = tempfile.mkdtemp(prefix="repo-")
    subprocess.run(["git", "clone", "--quiet", REPO_URL, REPO], check=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


until = [f"--until={CUTOFF}"] if CUTOFF else []
print(git("log", "-1", "--format=%h %ad %s", "--date=short", *until).strip())
""")

md(r"""
## 1. When did the work happen?

`--no-merges` drops the merge commits that pull requests create, so each commit counted is a
change somebody made. `%x1f` and `%x1e` are unit and record separators, characters that do not
appear in commit messages, so a message containing a comma or a newline cannot break the parse.
""")

code(r"""
raw = git("log", "--no-merges", *until, "--format=%h%x1f%ad%x1f%an%x1f%B%x1e", "--date=short")
commits = []
for rec in raw.split("\x1e"):
    rec = rec.strip()
    if not rec:
        continue
    h, day, author, body = rec.split("\x1f", 3)
    co = re.findall(r"Co-Authored-By:\s*([^<\n]+)", body, re.I)
    commits.append({"hash": h, "day": dt.date.fromisoformat(day), "author": author,
                    "coauthor": re.sub(r"\s*\(.*?\)", "", co[0]).strip() if co else "none"})

days = [c["day"] for c in commits]
print(f"{len(commits)} commits from {min(days)} to {max(days)}")
for author, k in collections.Counter(c["author"] for c in commits).most_common():
    print(f"  {k:5d}  {author}")
""")

code(r"""
def monday(d):
    return d - dt.timedelta(days=d.weekday())

weeks = collections.Counter(monday(d) for d in days)
first, last = min(weeks), max(weeks)
xs = [first + dt.timedelta(weeks=i) for i in range((last - first).days // 7 + 1)]
fig, ax = plt.subplots(figsize=(11, 3.6))
ax.bar(xs, [weeks[w] for w in xs], width=5.5, color="#1f5c99")
ax.set_ylabel("commits per week")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.spines[["top", "right"]].set_visible(False)
plt.show()
busiest = max(xs, key=lambda w: weeks[w])
print(f"busiest week: {busiest} with {weeks[busiest]} commits")
""")

md(r"""
## 2. Who or what wrote it?

The `Co-Authored-By:` trailer is how Git records a second author, and AI coding assistants
add one naming the model. A trailer is only as honest as the person who left it in: a commit
with no trailer may still have had help, so read this as what the project declared.
""")

code(r"""
by = collections.Counter(c["coauthor"] for c in commits)
for name, k in by.most_common():
    print(f"  {k:5d}  {100 * k / len(commits):5.1f}%  {name}")

names = [n for n, _ in by.most_common()]
fig, ax = plt.subplots(figsize=(11, 3.6))
bottom = [0] * len(xs)
for name in names:
    per = collections.Counter(monday(c["day"]) for c in commits if c["coauthor"] == name)
    h = [per[w] for w in xs]
    ax.bar(xs, h, width=5.5, bottom=bottom, label=name)
    bottom = [b + v for b, v in zip(bottom, h)]
ax.set_ylabel("commits per week")
ax.legend(frameon=False, fontsize=9, ncol=3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.spines[["top", "right"]].set_visible(False)
plt.show()
""")

md(r"""
## 3. How did it arrive?

On GitHub a merged pull request leaves a merge commit on the main branch whose message starts
"Merge pull request #". `--first-parent` follows the main branch only, so commits inside each
pull request are not double counted. A project that pushes straight to main will show none,
which is itself worth knowing.
""")

code(r"""
merges = git("log", "--first-parent", "--merges", *until, "--format=%ad %s", "--date=short").splitlines()
prs = [m for m in merges if "Merge pull request #" in m]
print(f"{len(prs)} pull requests merged into the main line")
print("the five most recent:")
for line in prs[:5]:
    print("  ", line[:100])
""")

md(r"""
## 4. How did one file grow?

`git log -- FILE` lists the commits that changed the file, and `git show HASH:FILE` prints the
file as it was at that commit. For a conventions file, the steps in this plot are the rules
being written; the commit messages say which mistake each one came from.
""")

code(r"""
hist = []
for line in git("log", "--reverse", *until, "--format=%h %ad", "--date=short", "--", FILE).splitlines():
    h, day = line.split()
    try:
        text = git("show", f"{h}:{FILE}")
    except subprocess.CalledProcessError:   # the commit deleted or renamed the file
        continue
    hist.append((dt.date.fromisoformat(day), text.count("\n"), h))

if not hist:
    print(f"{FILE} has no history in this repository; set FILE to a file that exists")
else:
    print(f"{FILE}: {len(hist)} revisions, {hist[0][1]} lines on {hist[0][0]}, {hist[-1][1]} on {hist[-1][0]}")
    fig, ax = plt.subplots(figsize=(11, 3.4))
    ax.step([d for d, _, _ in hist], [n for _, n, _ in hist], where="post", color="#c41230", lw=2)
    ax.set_ylabel(f"lines in {FILE}")
    ax.set_ylim(0, None)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.spines[["top", "right"]].set_visible(False)
    plt.show()
""")

code(r"""
# The five commits that added the most lines to FILE, and what their messages say.
jumps = sorted(((b[1] - a[1], b[2]) for a, b in zip(hist, hist[1:])), reverse=True)[:5]
for added, h in jumps:
    print(f"+{added:4d}  {git('log', '-1', '--format=%ad %s', '--date=short', h).strip()[:100]}")
""")

md(r"""
## Try it

- Point `REPO` (or `REPO_URL`) at your final-project repository. Which week did most of the work
  happen in, and does that match your memory of the project?
- Set `FILE` to your `README.md`. When did it last change, and does it still describe the project
  you built?
- Read the messages of your ten most recent commits. Could a teammate tell from them why each
  change was made? Rewrite one that could not.
- Find one bug you fixed twice. Write the rule that would have stopped the second one in a file at
  the root of your project, and commit it with a message saying where it came from.
""")

cells = with_colab_cell(cells, OUT)
nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT.name} ({len(cells)} cells)")
