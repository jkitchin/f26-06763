# L2 · Reproducible environments, version control, and experiment hygiene

:::{admonition} At a glance
:class: tip

- **Session** L2, Week 1 · **Arc** Foundations
- **Slides** <a href="../../slides/l02/">Deck for this session</a>
- **Demo** [`l02-scaffold.ipynb`](l02-scaffold.ipynb), building a tracked project from an empty folder
- **Assignment** A1, released this session, due about one week later
:::

## Why this matters

In 2006 a team at Duke University published a striking result in [*Nature Medicine*](https://www.nature.com/articles/nm1491). Their models read a tumor's gene-expression profile and predicted which chemotherapy drug the patient would respond to, and the promise was enormous: a genomic test that could spare a patient a course of the wrong drug. The work was persuasive enough that, beginning in 2007, three clinical trials at Duke used the predictors to help assign real patients to treatment, and 117 patients were ultimately enrolled. This is about as high as the stakes get for a machine-learning result. It was steering chemotherapy.

Two statisticians at a different cancer center, Keith Baggerly and Kevin Coombes, set out to build on the work and could not even reproduce it. When they rebuilt the analysis from the data the papers provided, the numbers would not come back. Pulling the thread took them months, and what they found was not fraud-scale sophistication but a pair of ordinary mistakes. One was an [off-by-one error](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-3/issue-4/Deriving-chemosensitivity-from-cell-lines--Forensic-bioinformatics-and-reproducible/10.1214/09-AOAS291.full) that shifted an entire list of genes down by one row, so that the reported genes were quietly the wrong ones. The other was a set of sample labels in which "responds to the drug" and "resists the drug" had been swapped. Errors of exactly this kind are made every day, in every lab, by careful people. What made these matter is that nobody caught them, and nobody caught them because the work could not be checked.

The consequences played out over years. A [later National Academies review](https://www.ncbi.nlm.nih.gov/books/NBK475955/) reconstructed how work that could not be reproduced had reached patients at all. The central paper was [retracted](https://www.nature.com/articles/nm0111-135) in 2011, and the retraction is worth reading, because the authors' own stated reason was that they could not reproduce their results either. A [federal investigation](https://retractionwatch.com/2015/11/07/its-official-anil-potti-faked-data-say-feds/) eventually found that the lead author had committed research misconduct. That finding is about intent, and intent is not the subject of this course. The engineering lesson sits underneath the question of intent and holds regardless of the answer: for years, a flawed analysis could not be told apart from a sound one, because there was no way to take its data and its code and get its numbers back.

That property, the one whose absence let ordinary errors run for years, is the subject of this whole session.

:::{admonition} Definition: reproducibility
:class: tip

A result is **reproducible** when someone else can take your data and your code, run them, and get the same numbers you reported. It is the precondition for checking work at all. If a result cannot be regenerated, it cannot be examined, corrected, or defended, and that includes by you, six months later, when you are the stranger.
:::

An NCI statistician who reviewed the Duke case put the standard about as plainly as it can be [put](https://pmc.ncbi.nlm.nih.gov/articles/PMC3474449/): "There is computer code that evaluates the algorithm. There is data. And when you plug the data into that code, you should be able to get the answers back that you have reported." That is not a high bar in principle. It is the bar the Duke work failed, and it is the bar you will be held to the moment your work touches a decision anyone cares about. In a regulated or safety-critical engineering setting, someone will eventually point at a number your system produced and ask three questions in a row. Which data produced this? Which code produced it? Can you produce it again, exactly? This session is about making the answer to all three a cheap and automatic yes, using the tools you will use for the rest of the semester and the same UCI air-quality sensor data from L1: a locked environment, disciplined version control, and a run you can point to. It closes with the honest other half, the places where this discipline reaches its limits and what you reach for next.

## Learning objectives

By the end of this session you should be able to:

- Build and lock a project environment with `uv`, and rebuild it exactly on a fresh machine.
- Choose the right versioning tool for code, data, and models, and explain why large binary
  files do not belong in plain git.
- Turn an exploratory notebook into a script or package with a tested command-line entry
  point.
- Log a run to MLflow so that one run equals one fact you can reproduce.

## Environments you can rebuild

```{index} virtual environment, uv, dependency resolution
```

When you install a particular Python together with a particular set of packages to run a project, that whole collection of software is the project's **environment**, and reproducing a result begins with reproducing it. The environment is more than the packages you named. It is the exact version of the Python interpreter, every package you installed directly, and every package those packages pulled in underneath them, each one at a specific version. A dependency you never typed can change a number you report, which is why "I installed pandas and scikit-learn" is not a description anyone can rebuild from.

The reason this matters is that small version differences produce real, silent behavior changes, and the L1 demo was a live demonstration of one. A function's behavior can shift between two minor releases. A default argument can move. A dependency of a dependency can resolve to a newer version on a Tuesday than it did on the Monday you last ran the code, because "newest version that satisfies the constraints" is a moving target. None of these announce themselves. They surface later, as a result that will not reproduce, and by then the trail is cold.

:::{admonition} Definition: dependency
:class: tip

A **dependency** is a package your project needs in order to run. Each dependency usually has dependencies of its own, called *transitive* dependencies, so a project that names three packages can easily pull in fifty. The full, resolved set is what actually determines your results, and it is far larger than the list you wrote.
:::

The tool this course standardizes on for managing all of this is `uv`, and it works through three files that are worth understanding as a unit before touching the commands. The first, `pyproject.toml`, records what you *asked for*: your direct dependencies, usually at loose version constraints like "pandas, at least this version." The second, `uv.lock`, records what you actually *got*: the entire resolved dependency graph, transitive packages included, every one pinned to an exact version, resolved once and then reused. The third, `.python-version`, pins the interpreter itself, because Python 3.11 and Python 3.13 are genuinely different environments and a result that depends on which one ran is a result you cannot yet reproduce. Together these three files turn a rebuild from something that is *probably* the same into something that is *provably* the same.

In day-to-day use you drive `uv` with a handful of commands. `uv init` creates a project and writes the first `pyproject.toml` and `.python-version`. `uv add pandas scikit-learn mlflow` adds dependencies, resolves the whole graph, and updates both `pyproject.toml` and the lockfile in one step. `uv run python -m sensorlab.train` runs a command inside the project's environment, and before it does, it checks that the lockfile is consistent with `pyproject.toml`, so the environment can never quietly drift out from under you. On a fresh checkout of the project, on your laptop or a colleague's or a continuous-integration server, `uv sync` reconstructs the environment from the lockfile: the same interpreter, the same packages, the same versions, with no interpretation required. That last command is where the payoff lives, because it is the end of "works on my machine" as an acceptable answer.

### Lockfiles and requirements files

```{index} lockfile
```

The single idea to carry out of this section is what a lockfile buys you, and the clearest way to see it is against the older tool it replaces. A `requirements.txt` file is a list of packages, and in most projects it lists only the direct ones, often at loose versions. Nothing about it is wrong, but nothing about it is reproducible either: install the same `requirements.txt` on two machines a month apart and you can easily get two different sets of packages, because the resolver is free to pick whatever is newest within the loose constraints, and a month is plenty of time for "newest" to change. The problem is old, and the file is one of a long line of attempts on it, from `pip freeze` through tools like pip-tools and Poetry and now `uv`.

:::{admonition} Definition: lockfile
:class: tip

A **lockfile** records the complete set of packages your project resolved to, every one of them pinned to an exact version, so that installing from it reproduces an identical environment every time. `uv` writes and maintains `uv.lock` for you as you add dependencies, and it is not a file you edit by hand.
:::

The difference from a requirements file is not cosmetic. `uv.lock` is a *universal* resolution, computed once to be valid across platforms and pinned exactly, and the tool owns it rather than you. A `requirements.txt` still has a legitimate role as an *export format*, a way to hand a package list to a tool or a service that expects that shape, and `uv` will generate one on request. It is a shipping label, useful for interoperating with the outside world, while the lockfile is the source of truth your own rebuilds resolve against. The one-sentence version: the lockfile is what makes `uv sync` give the same answer twice.

:::{admonition} Common pitfall
:class: warning

The most common way to miss the point of `uv` is to treat it as a faster `pip` and stop after `uv add`. Speed is not the feature; the feature is the pin. What actually buys reproducibility is the lockfile together with the fixed interpreter, and without both you have only found a quicker way to build an environment you still cannot rebuild. The one-line test settles it in class: delete `.venv`, run `uv sync`, and confirm you get the same thing back. Watching an environment reconstruct itself from nothing is more convincing than being told that it will.
:::

## A project layout that scales

```{index} project scaffold, pyproject.toml
```

An exploratory analysis is happy to live in a single notebook and a folder of loose files, and for the first afternoon of a project that is exactly where it should live. A system cannot stay there. The difference is that a system's code has to be imported by other code, exercised by tests, and run by people who are not you and who are not sitting in the folder where you happened to save it. A small, conventional project layout buys all three of those, and the reason to set it up on the very first day is that it costs almost nothing then and is genuinely tedious to retrofit onto a tangle of scripts later.

:::{admonition} Definition: scaffolding
:class: tip

To **scaffold** a project is to set up its skeleton before you write much code: the folders, the configuration files, and an empty, importable package. Like the scaffolding around a building, it is the temporary-feeling frame that everything real gets built against. A1 has you scaffold one project and then reuse it all semester.
:::

The convention this course uses is the `src` layout, and it repays a moment of understanding rather than blind copying. Your code lives in a *package*, which is just a folder of Python files that other code can import by name, and that package sits under a top-level `src/` directory. The consequence of putting it there is that your code is imported the way an installed library is, by its name, rather than by being whatever files happen to sit next to the script you launched. That single indirection removes a whole category of bug that bites beginners hard: the analysis that runs perfectly from one directory and mysteriously fails from another, because it was quietly depending on the current folder to resolve its imports. Around the package sits `pyproject.toml`, the project's manifest, which declares the dependencies, the command-line entry points, and the metadata that make the package installable in the first place. The remaining folders give each kind of file one obvious home:

```text
sensorlab/
├── pyproject.toml   uv.lock   .python-version
├── src/sensorlab/   # the importable package: load, clean, featurize, train
├── data/            # raw data, kept out of git
├── notebooks/       # exploration
├── scripts/         # entry points
└── tests/           # tests
```

The specific folder names matter far less than the principle underneath them, which is that the boundary between throwaway exploration and the code that actually runs is drawn in the directory tree, where anyone can see it, instead of living in one person's memory of which notebook is the "real" one. The A1 scaffold is exactly this shape, and because you reuse it all semester, an hour spent understanding it now is repaid many times over.

## Versioning code, data, and models are three different problems

```{index} data versioning, content hash, DVC, provenance
```

Git is superb at versioning code and close to useless at versioning a 200 MB data file, and the instinct to solve the problem by putting everything into one repository is precisely how repositories become slow, enormous, and unpleasant to clone. The three kinds of artifact a project produces, its code, its data, and its models, differ in their size, in how often they change, and in what is actually worth recording about them, and those differences mean they belong in three different tools. Getting this split right early is far cheaper than untangling it later.

**Code** belongs in git, which was built for it. It is small, it is text, and git can show you exactly what changed, line by line, between any two points in the project's history. Each commit is a labeled, permanent save point, and its identifier, a short string called a SHA, is itself a piece of provenance: "which version of the code produced this number" is answered completely by a commit SHA. This is the cheapest and most reliable versioning you will do all semester, and it costs nothing but the discipline of committing in meaningful units.

:::{admonition} Definition: provenance
:class: tip

**Provenance** is the record of where a result came from: which data, which code, and which settings produced it. Reproducibility is the ability to make the result *again*; provenance is the ability to say *how it was made* in the first place. You want both, and they are recorded by different means: git for the code, a hash for the data, an experiment tracker for the tie between them.
:::

**Data** does not belong in plain git, and understanding why is worth more than the rule. Git keeps every version of every file forever, by design, so that history is complete and nothing is lost. Commit a large binary file and you have committed it permanently: even after you delete it, it lives on in the history, and every future clone of the repository pays to download it. A raw sensor export is large, binary, and often carries license or privacy constraints that a public copy of the repository would violate outright. The discipline, then, is to keep the raw data out of git with a `.gitignore` file, which is simply a list of paths git should refuse to track, and to commit in its place a small sample or a description of the columns so the shape is documented, together with a record of where the real data came from and a *content hash* of it. A content hash is a short fingerprint computed from the bytes of a file; change a single byte and the fingerprint changes, so two runs can be checked, cheaply and exactly, for having used the same data. Set up the `.gitignore` before your first commit rather than after, because once a large file is in the history, removing it means rewriting that history, which is far more work than never adding it. This repository's own `.gitignore` already excludes `data/`, `*.parquet`, and `*.duckdb` for exactly these reasons. The heavier tools for versioning large data by content, `git-lfs` and DVC, get their proper treatment in Week 4.

**Models** are large binary files too, but they differ from data in a way that changes what you should record about them: a model is an *output*. The thing worth saving is less the weights themselves than the recipe that produced them, which is the code SHA, the data hash, and the configuration together. Recreate those three and you can recreate the model; save only the weights and you have an artifact nobody can regenerate or trust. Recording that recipe is exactly what an experiment tracker is for, which is the next section.

| Artifact | How it changes | Tool | What you actually version |
|---|---|---|---|
| Code | constantly, in small diffs | git | the source, as commits |
| Data | rarely, large and binary | git-ignored, plus a content hash; git-lfs/DVC (Wk4) | a pointer and a hash, never the raw bytes |
| Models | one per run, large binary | an MLflow run | the inputs that produced it |

## From notebook to module

```{index} random seed
```

A notebook is the right tool for looking at data and the wrong tool for anything that has to run again reliably, and the reason is structural rather than a matter of taste. In a notebook, cells run in whatever order you clicked them, not top to bottom, and state accumulates invisibly between runs, so a variable defined in a cell you have since deleted can keep a later cell working long after the code that created it is gone. "It worked a minute ago" is a true statement about a notebook that tells you almost nothing about whether it will work on a fresh start. Turning the notebook into a module is how an exploration becomes something you can test, schedule, and trust, and it is the step where most of the L1 failures are designed out rather than merely warned against.

This is not a rare failing that happens to careless people; it is the normal state of shared analysis code. When researchers collected about 1.45 million Jupyter notebooks from GitHub and, after removing duplicates, kept about 1.16 million to study, they found that of the [863,878 valid Python notebooks](https://leomurta.github.io/papers/pimentel2019a.pdf) they could actually attempt to run, only about a quarter ran to completion without an error, and only about four percent reproduced the results the notebook itself had saved. A separate audit of [601 computer-science papers](http://reproducibility.cs.arizona.edu/v2/RepeatabilityTR.pdf) found that for under a third of the 402 whose results were produced by code, the code could be obtained and built within half an hour, and simply getting hold of the code at all was often the hard part. The next person who cannot run your notebook is, more often than not, you, half a year from now.

```{figure} figures/notebook-repro.png
:alt: A funnel: about 864,000 valid Python notebooks attempted, about 24 percent ran without error, about 4 percent reproduced the recorded result
:width: 80%
:align: center

Of the 863,878 valid Python notebooks that could be run (from about 1.45 million collected on
GitHub, 1.16 million after removing duplicates), about 24% ran to completion without error and
about 4% reproduced the result the notebook had saved. Data from Pimentel et al. (2019);
generated by `figures/make_figures.py`.
```

The refactor that fixes this is mechanical, which is the good news. You pull the logic out of the cells and into functions, such as `load`, `clean`, `featurize`, and `train`, each taking its inputs as arguments and returning a value, so that it can be imported and tested in isolation rather than depending on the ambient state of a notebook. You add an entry point behind the `if __name__ == "__main__"` guard, the block Python runs only when a file is launched directly, and give it an argument parser, so that the analysis runs from the command line as `uv run python -m sensorlab.train --seed 0` rather than by clicking cells in an order you have to remember. And you fix the seed for anything that draws on randomness.

:::{admonition} Definition: seed
:class: tip

A **seed** is the starting number for a pseudo-random process. Fix the seed and the "random" choices, a train/test split, the initialization of a model, come out identically on every run. Leave it unset and they vary each time. That variation is precisely the L1 demo's silent failure: nothing raised an error, the score simply moved from run to run, and a number that will not sit still cannot be reproduced.
:::

The notebook does not have to disappear when you do this. It becomes a thin front-end that imports the very same functions the command-line entry point calls, so that exploration and the code that runs in production share a single path and cannot drift apart into two subtly different analyses. The habit that catches the hidden-state problem is running the whole thing from a clean start, which for a module means a fresh process and for a notebook means the "Restart and Run All" command, and it is worth making that reflexive before you trust any notebook result, including your own.

## Experiment hygiene: one run, one fact

```{index} experiment tracking, MLflow
```

Once the analysis runs from the command line, you will run it many times, with different seeds, different features, and different parameters, and within a day the question "which settings produced this particular number" becomes genuinely unanswerable from memory. Experiment tracking is the infrastructure that answers it for you, by recording each run as it happens so that the run becomes a fact you can point to rather than a recollection you have to trust. It is the smallest, most immediately useful unit of the provenance discipline from earlier in the session.

MLflow, the tracker this course uses, records for each run the parameters you chose, the metrics you measured, and any artifacts you attach, such as a figure or a saved model. It stores all of this locally, with no server to stand up in Week 1. There is a wrinkle worth knowing about, because it is the kind of thing that surprises people mid-demo: recent versions of MLflow have put the old bare-directory store into maintenance mode and will refuse to use it, steering you instead toward a small local SQLite database, which is a single file on disk and still needs no server. Pointed at that file, the `mlflow ui` command shows your runs side by side in a browser. The interface you actually touch is deliberately small:

```python
import mlflow

mlflow.set_tracking_uri("sqlite:///mlflow.db")  # local store, no server
with mlflow.start_run():
    mlflow.log_params({"seed": seed, "data_date": data_date})
    r2 = train_and_score(seed=seed)
    mlflow.log_metric("r2", r2)
    # also log the code SHA and a data hash, so the run is reconstructible
```

Run the trainer twice with two different seeds and the two runs appear as two rows you can compare directly, and the small difference between them is itself the lesson: it is why the seed has to be logged, because without it neither number is reconstructible. The habit worth building is to log enough that the run could be *rebuilt* from its record, which means the git commit SHA of the code, a hash or version of the data, and the seed, all sitting next to the metric. That triple is precisely the provenance the Duke work never had, and with it a run becomes, in the phrase this section is named for, one reproducible fact. It is not a coincidence that the Week 7 miniproject later demands exactly this triple, a git SHA, a data hash, and a seed, as its price of admission; this session is where you build the habit that makes that requirement painless.

## Where reproducibility pushes back

Everything so far has been an argument for a discipline, and it is a sound argument, but a course that only ever sold its tools would be teaching advocacy rather than engineering. Reproducibility is necessary infrastructure, not a cure-all, and the mature version of this knowledge is knowing exactly what it does not give you and where the effort stops being worth it. Several of its limits are worth meeting here, on paper, rather than later, under deadline.

### Reproducible is not the same as correct

```{index} pair: failure mode; reproducible but wrong
```

This is the limit that matters most, and it is genuinely counterintuitive. Making a result reproducible does not make it right. If your pipeline contains the same off-by-one error the Duke code did, then locking the environment, pinning the seed, and tracking the run will faithfully reproduce the *wrong* answer, every time, with perfect fidelity. Reproducibility is what makes a result *checkable*; it is a precondition for catching errors, not a substitute for doing so. Notice, too, how the Duke errors were actually caught: not by re-running the original code, which would simply have reproduced its mistakes, but by outside statisticians *re-implementing* the analysis from scratch and finding that the two versions disagreed. Reproduction confirms you can regenerate a number. Confirming the number is right is a separate act, and it is called validation.

### A lockfile pins versions, not the whole world

A lockfile is a strong guarantee, and it is not a total one. It pins the exact version of every Python package, but a package version is not the same as the compiled code that actually runs. Many packages ship as platform-specific binary wheels, so the bytes installed for your locked version of NumPy differ between macOS and Linux, and the lockfile says nothing about the system C libraries, the CUDA toolkit, or the operating system underneath. A pinned version can even become unavailable if it is later removed from the package index. For most engineering work the lockfile is enough, but when you need to freeze the entire stack down to the system libraries, the tool is a container, which packages the operating-system layer as well, and that is a Week 12 topic. The honest framing is that `uv` gives you a reproducible *Python environment*, which is most of what you need and not quite all of it.

### The discipline has a cost, and sometimes it is overkill

Setting up a locked, tracked, packaged project is not free, and there is a real judgment call about when to pay for it. For a genuinely throwaway exploration, twenty minutes of poking at a file to decide whether an idea is worth pursuing, full scaffolding is friction that buys you nothing, and insisting on it would be its own kind of over-engineering. The skill is proportion. The moment an analysis is going to be rerun, shared, built upon, or believed by anyone, including your future self, it has crossed the line into needing this discipline, and the trap is that results almost always cross that line quietly, without anyone deciding that they have. When in doubt, scaffold, because retrofitting is the expensive direction.

### A hash tells you that data changed, not what or why

The content hash that lets you detect whether two runs used the same data is a blunt instrument on purpose. It will tell you, with certainty, that the file is different; it will not tell you which rows changed, whether the change was a fix or a corruption, or whether it matters for your result. Detecting change is the floor, not the ceiling, of data provenance, and the tools that go further, versioning data by content with a readable history of what changed and why, are `git-lfs` and DVC in Week 4. A hash is a smoke alarm, not an investigation.

### Tracking records; it does not enforce

MLflow will faithfully record whatever you log, including a run whose environment was never locked and whose seed was never pinned. Logging a seed does not make an environment reproducible; it only documents one input to a run that may still be irreproducible for other reasons. The tracker is a filing system, and a filing system is only as trustworthy as the discipline of the person filing. The habits in this session, the lockfile, the pinned interpreter, the fixed seed, the recorded SHA and hash, are what make the thing you filed actually worth retrieving.

:::{admonition} What a practitioner should take from this
:class: tip

Treat reproducibility as the foundation you build on, not the building. It is necessary: without it, no result can be checked, corrected, or defended, and the Duke case is what its absence costs. It is not sufficient: a reproducible result can still be wrong, so it buys you the ability to validate, not validation itself. And it is not free, so invest in proportion to how much the result will be reused or believed, defaulting to more discipline rather than less because retrofitting is the costly direction. The stronger guarantees, whole-stack reproducibility with containers and richer data versioning, come later in the course; what you build this week is the layer everything else assumes.
:::

## In-class demo

We build the A1 scaffold live, starting from an empty folder and ending with a tracked run in about fifteen minutes. The path runs `uv init` to create the project, adds pandas, scikit-learn, and mlflow, moves the L1 exploratory cells into `src/sensorlab/` as importable functions, adds a command-line entry point, runs the trainer twice with two different seeds, and opens the MLflow UI to see the two runs side by side. It is deliberately the same shape as A1, so the demo is a preview of the assignment rather than a separate exercise.

Two moments in it carry the lesson and are worth watching for. The first is when we delete `.venv` and rebuild it from the lockfile, because that is what "a reproducible environment" means once you actually do it rather than merely claim it. The second is when the two seeded runs become two logged, comparable facts, instead of two numbers you would otherwise have to hold in your head and would misremember by the afternoon. The runnable version is [`l02-scaffold.ipynb`](l02-scaffold.ipynb).

## Summary

Reproducibility is the ability to say which data, which code, and which settings produced a number, and then to produce that number again, and the Duke chemotherapy predictors are the case for taking it as seriously as this session does: two ordinary errors, a shifted index and a swapped label, reached a clinical trial and stood for years, because the work was never reproducible enough for anyone to check. Each tool in the session closes one part of the gap. `uv` pins the interpreter and locks the dependency graph, so a rebuild comes out the same rather than merely similar. A conventional `src` layout and a disciplined `.gitignore` keep code, data, and models in the tools that actually suit each, and keep the boundary between exploration and production visible in the tree. Refactoring the notebook into a module makes the analysis run again for someone who is not you. And MLflow turns each run into a fact you can point to, carrying the SHA, the data hash, and the seed that make it rebuildable. The closing section is the honest other half: reproducibility is necessary and not sufficient, a lockfile pins Python and not the whole machine, and the discipline is worth paying for in proportion to how much a result will be trusted. Next session we stop keeping the data in a CSV file and give it a real home, starting with relational databases and SQL for engineering time-series.

## Resources

- [uv documentation, Working on projects](https://docs.astral.sh/uv/guides/projects/). The commands from this session in order: `uv init`, `uv add`, `uv run`, and what each file is for. Start here.
- [uv documentation, Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/). What `uv sync` does, and how the lockfile relates to a `requirements.txt` export. The [resolution page](https://docs.astral.sh/uv/concepts/resolution/) explains why the lockfile works across platforms.
- [MLflow Tracking Quickstart](https://mlflow.org/docs/latest/ml/tracking/quickstart/). Logging parameters and metrics, and viewing runs. Local storage options and the `mlflow ui` command are on the [Tracking overview](https://mlflow.org/docs/latest/ml/tracking/).
- [Pro Git, chapter 1](https://git-scm.com/book/en/v2/Getting-Started-About-Version-Control) and [chapter 2](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository). Free online. The "Ignoring Files" section in chapter 2 is the `.gitignore` reference for this session.
- [The Turing Way, Reproducible Research](https://book.the-turing-way.org/reproducible-research/reproducible-research/). The broader case, and a clean definition: the same data plus the same code should give the same result.
- [Deriving chemosensitivity from cell lines](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-3/issue-4/Deriving-chemosensitivity-from-cell-lines--Forensic-bioinformatics-and-reproducible/10.1214/09-AOAS291.full). Baggerly and Coombes, *Annals of Applied Statistics* 2009, open access. The forensic reconstruction that found the shifted-index and swapped-label errors.
- [Retraction note, *Nature Medicine*](https://www.nature.com/articles/nm0111-135). The 2011 retraction of the 2006 paper, in the authors' own words: they could not reproduce it either.
- [Evolution of Translational Omics](https://www.ncbi.nlm.nih.gov/books/NBK202165/). The 2012 Institute of Medicine report prompted by the case. Its recommendation that data and code be made available for independent review is this session in one sentence.
- [A large-scale study of the quality and reproducibility of Jupyter notebooks](https://leomurta.github.io/papers/pimentel2019a.pdf). Pimentel et al., MSR 2019. Source of the notebook figures above; the 24% and 4% are of the 863,878 valid notebooks that could be run.
- [Repeatability in computer systems research](http://reproducibility.cs.arizona.edu/v2/RepeatabilityTR.pdf). Collberg and Proebsting. Source of the 601-paper build figure; the 32.3% is of the 402 papers whose results were produced by code, which is more papers than actually shared their code.

## Assignment

A1, the reproducible project scaffold, is released this session and due about one week later. It asks you to build a `uv`-managed, git-tracked project that pulls the UCI air-quality dataset and turns an exploratory notebook into a runnable, importable module with a tested entry point and an MLflow-logged run. It is the scaffold you reuse all semester, so it is worth doing carefully the first time, and it is a direct extension of the demo we build in class. The full instructions and grading are in `course/assignments/a01.md`; this paragraph is a pointer, not the rubric.
