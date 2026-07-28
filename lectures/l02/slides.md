---
marp: true
theme: course
paginate: true
header: "06-763 · L2"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L2 · Reproducible environments

## Week 1 · Foundations

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why reproducibility: a cancer trial
2. Environments you can rebuild: `uv`
3. A project layout that scales
4. Versioning code, data, and models
5. Notebook to module, and tracking runs
6. Live demo: an empty folder to a tracked run

---

<!-- _class: section -->

# Why reproducibility
## a model nobody could rebuild

---

## A model in the clinic

2006, Duke, in *Nature Medicine*:
read a tumor's gene expression,
predict which chemotherapy will work.

By 2007, the predictors were **assigning patients**
in clinical trials.

[Nature Medicine, 2006](https://www.nature.com/articles/nm1491)

---

## Two outsiders tried to check it

Baggerly & Coombes rebuilt the analysis
from the **published data**.

The numbers **did not match**.

[Deriving chemosensitivity from cell lines (2009)](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-3/issue-4/Deriving-chemosensitivity-from-cell-lines--Forensic-bioinformatics-and-reproducible/10.1214/09-AOAS291.full)

---

## Two small errors

- A gene list **shifted down by one row**
- The **labels swapped**: responds vs resists

Easy to make. Easy to miss.
**Invisible** in the published papers.

---

## How far it went

Three trials at Duke. **117 patients** enrolled.

A later **National Academies review**
examined how work that could not be reproduced
had reached patients.

[National Academies case study](https://www.ncbi.nlm.nih.gov/books/NBK475955/)

---

## It reached patients anyway

The paper was **[retracted](https://www.nature.com/articles/nm0111-135)** in 2011,
because even its authors could not reproduce it.

A [federal inquiry](https://retractionwatch.com/2015/11/07/its-official-anil-potti-faked-data-say-feds/) later found research misconduct.

Intent is not our focus. **The engineering lesson holds either way.**

---

## The missing property has a name

> A result is **reproducible** when someone else
> can take your data and your code, run them,
> and get the same numbers you reported.

If they cannot, nobody can check it. **Including you.**

---

## Said plainly

> "There is computer code that evaluates the algorithm.
> There is data. And when you plug the data into that code,
> you should be able to get the answers back
> that you have reported."

An NCI statistician, reviewing the case.
[On the Duke case](https://pmc.ncbi.nlm.nih.gov/articles/PMC3474449/)

---

## Reproducible is not correct

Re-run a buggy pipeline and you get
the **same wrong answer**.

Reproducibility does not make you right.
It makes you **checkable**.

The Duke errors surfaced only because outsiders
could rebuild the work and compare.

---

## The test you will face

Someone points at a number your system produced:

1. **Which data** made it?
2. **Which code** made it?
3. Can you make it **again, exactly**?

In any regulated or safety-critical setting, this is not optional.

---

<!-- _class: section -->

# Environments you can rebuild
## `uv`

---

## Your environment

The exact software a project needs to run:

- the version of **Python** (the interpreter)
- every **package** you installed
- each at a **specific version**

---

## Small differences, real bugs

The L1 demo broke because a version was never recorded.

- a function changes between two releases
- a default value moves
- a **hidden** dependency resolves differently today

Your packages have their own packages underneath them.

---

## Three files carry the guarantee

- `pyproject.toml` — what you **asked for** (loose)
- `uv.lock` — what you **got**: every package, exact
- `.python-version` — the **interpreter**, pinned

Together: a rebuild that is the **same**, not merely similar.

---

## Pin Python too, not just packages

`.python-version` fixes the interpreter.

Python **3.11** and **3.13** are not the same environment:
syntax, defaults, and C extensions differ.

`uv` installs and manages the version for you.

---

## Start a project

```bash
uv init sensorlab && cd sensorlab
uv add pandas scikit-learn mlflow
```

`uv init` writes `pyproject.toml` and `.python-version`.
`uv add` resolves the whole graph into `uv.lock`.

---

## Run and rebuild

```bash
uv run python -m sensorlab.train --seed 0   # checks the lock first
uv sync                                      # rebuild from the lock
```

`uv run` verifies the lockfile is current before it runs.
You rarely touch the virtual environment by hand.

---

## What `uv sync` buys a teammate

A colleague clones the repo and runs one command:

```bash
uv sync
```

Same interpreter, same packages, same versions.
The end of **"works on my machine."**

---

## Lockfile beats a requirements file

| `requirements.txt` | `uv.lock` |
|---|---|
| packages, often loose | the whole graph, exact |
| two installs → two sets | two installs → identical |
| you edit it | the tool maintains it |

[uv: working on projects](https://docs.astral.sh/uv/guides/projects/)

---

## What a lockfile is

> Every package your project resolved to,
> pinned to an exact version.

Install from it → **identical packages every time.**

`uv` writes `uv.lock` for you. Never edit it by hand.

---

## The pitfall

`uv` is not just a faster `pip`.

The pin that buys reproducibility is
the **lockfile + the interpreter**, together.

**The test:** delete `.venv`, run `uv sync`,
get the same thing back. We do this live.

---

<!-- _class: section -->

# A project layout
## that scales

---

## Scaffolding

> Set up the project's skeleton before you write much code:
> the folders, the config, an empty package.

The frame you build on. A1 has you scaffold **once**
and reuse it all semester.

---

## A system needs three things

A notebook and a folder of loose files
cannot be **imported**, **tested**, or **run** by someone else.

A small, standard layout gives all three.
Costs nothing on day one. Painful to add later.

---

## The `src` layout

Your code is a **package**, imported by name:

- imported the same way from anywhere
- no "works only from this folder" bug

A common failure comes from launching a script
from one specific directory. This removes it.

---

## `pyproject.toml` is the manifest

One file declares the project:

- its **dependencies**
- its **entry points**
- its metadata

`uv` keeps it in step with the lockfile.

---

## A place for each thing

```text
sensorlab/
├── pyproject.toml   uv.lock   .python-version
├── src/sensorlab/   # load, clean, featurize, train
├── data/            # raw data, kept out of git
├── notebooks/       # exploration
└── tests/
```

---

## The boundary lives in the tree

The line between **exploration**
and **the code that runs**
is drawn in the folder layout,
not held in your memory.

A1 reuses this exact structure all semester.

---

<!-- _class: section -->

# Versioning
## code, data, and models

---

## Three different problems

Code, data, and models differ in

- **size**
- how often they **change**
- what is worth **recording** about them

So they belong in **different tools**.

---

## Pick the tool per artifact

| Artifact | Tool | What you version |
|---|---|---|
| Code | git | the source, as commits |
| Data | git-ignored + a hash (git-lfs/DVC, Wk4) | a pointer, not the bytes |
| Models | an MLflow run | the inputs that made it |

---

## Code → git

Small, text, diffable.

Each commit is a labeled save point.
Its **SHA** answers a provenance question:

> which version of the code produced this number?

---

## Provenance

> The record of where a result came from:
> which data, which code, which settings.

Reproducibility is making the result **again**.
Provenance is saying **how it was made**.

---

## Data → not plain git

git keeps **every version forever**.
A 200 MB file bloats the repo permanently.

Raw data may also carry **license or privacy** limits
a public copy of the repo would break.

---

## Set up `.gitignore` first

Before the first commit, not after.

- track a small sample + a **content hash**
- keep the raw bytes out

Once a big file is committed, removing it
means **rewriting history**. Far more work.

---

## Big data gets its own tools

git is the wrong home for large binaries.

Tools that version data **by content**,
`git-lfs` and **DVC**, get a real treatment in **Wk4**.

For now: a hash and a source, not the bytes.

---

## Models → version the inputs

A model is an **output**.

Worth saving is what produced it:
the **code SHA**, the **data hash**, the **settings**.

MLflow stores that link. (Next.)

---

<!-- _class: section -->

# Notebook to module
## and tracking runs

---

## Notebooks do not rerun

Great for looking at data.
Wrong tool for code that must run again.

- cells run in whatever order you clicked
- hidden state builds up between runs
- "it worked a minute ago" is not shippable

---

## This is the normal case

[One study](https://leomurta.github.io/papers/pimentel2019a.pdf) ran ~**864k** valid notebooks from GitHub:

- only ~**24%** ran to the end without an error
- only ~**4%** reproduced their saved results

[A separate audit](http://reproducibility.cs.arizona.edu/v2/RepeatabilityTR.pdf): under a third of code-backed
papers could even be **built** in half an hour.

---

![w:1000](figures/notebook-repro.png)

<span class="source">Pimentel et al. (2019): of 863,878 valid Python notebooks that could be run. Generated by <code>figures/make_figures.py</code>.</span>

---

## Step 1: extract functions

Pull the logic out of the cells:

```python
def load(path): ...
def clean(df): ...
def featurize(df): ...
def train(X, y, seed): ...
```

Arguments in, values out. Now you can **import and test** them.

---

## Step 2: add an entry point

```python
if __name__ == "__main__":
    args = parse_args()
    train(X, y, seed=args.seed)
```

Run it from the command line, not by clicking cells:

```bash
uv run python -m sensorlab.train --seed 0
```

---

## The notebook does not disappear

It becomes a **thin front-end**
that imports the same functions.

Exploration and the real run share **one code path**,
so they cannot drift apart.

---

## Pin the randomness

> A **seed** is the starting number for a random process.
> Fix it, and the "random" choices repeat.

L1's problem two: the seed was never fixed,
so the score moved every run.

**The habit:** run from a clean start (Restart and Run All).

---

## Why track runs at all

Run the trainer a hundred times,
changing seeds and settings.

By tomorrow, *"which run made this number?"*
is gone from memory.

Tracking makes each run a **fact**, not a recollection.

---

## Track each run

MLflow records, per run:
**parameters**, **metrics**, **artifacts**.

Local, no server to stand up.
Recent MLflow keeps runs in a small **SQLite** file.

[MLflow tracking quickstart](https://mlflow.org/docs/latest/ml/tracking/quickstart/)

---

## The interface is small

```python
import mlflow
mlflow.set_tracking_uri("sqlite:///mlflow.db")  # local, no server

with mlflow.start_run():
    mlflow.log_params({"seed": seed})
    mlflow.log_metric("r2", train(X, y, seed=seed))
```

Run it with two seeds → two rows to compare.

---

## Compare the two runs

Same data, same code, two seeds:

| seed | R² |
|---|---|
| 0 | 0.786 |
| 1 | 0.785 |

The gap is tiny. That is the point:
**log the seed** or neither number is reconstructible.

---

## One run, one fact

Log enough to **rebuild** the run:

> the git **SHA**, a data **hash**, the **seed**,
> next to the metric.

That triple is the provenance the Duke work lacked.
The miniproject requires exactly it.

---

<!-- _class: demo -->

# Demo

## `l02-scaffold.ipynb`

Empty folder → tracked run in ~15 minutes:
`uv init sensorlab` → add deps → cells into `src/sensorlab/`
→ CLI → two seeds → MLflow UI

---

## What to watch

1. Delete `.venv`, rebuild from the lockfile.
   That is a reproducible environment, for real.

2. Two seeded runs become **two comparable facts**,
   not two numbers you have to remember.

---

## Recap

- Reproducible = your data + your code → your numbers
- Reproducible is **checkable**, not automatically correct
- `uv`: the **lockfile + interpreter** make the rebuild the same
- Code in git; data and models elsewhere; `.gitignore` first
- Notebook → module: functions, a CLI, a **fixed seed**
- MLflow: one run = one fact, with SHA + hash + seed

---

## Next

**Assignment** A1 released today, due ~1 week: scaffold `sensorlab`
**Reading** uv docs; Pro Git ch. 1–2; MLflow quickstart; The Turing Way
**L3** Give the data a real home: relational databases & SQL
for engineering time series

Full notes, with all sources: `lectures/l02/notes.md`
