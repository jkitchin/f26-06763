# L2 · Reproducible environments, version control, and experiment hygiene

:::{admonition} At a glance
:class: tip

- **Session** L2, Week 1 · **Arc** Foundations
- **Slides** <a href="../../slides/l02/">Deck for this session</a>
- **Demo** [`l02-scaffold.ipynb`](l02-scaffold.ipynb), building a tracked project from an empty folder
- **Assignment** A1, released this session, due about one week later
:::

## Why this matters

In 2006 a team at Duke University published a striking result in [*Nature Medicine*](https://www.nature.com/articles/nm1491). Their models read a tumor's gene-expression data and predicted which chemotherapy drug a patient would respond to. Doctors soon used these predictors to assign patients in clinical trials.

Two statisticians at a different cancer center, Keith Baggerly and Kevin Coombes, set out to check the work. They [could not reproduce it](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-3/issue-4/Deriving-chemosensitivity-from-cell-lines--Forensic-bioinformatics-and-reproducible/10.1214/09-AOAS291.full). When they rebuilt the analysis from the published data, the numbers did not match. The cause was a pair of simple errors. One shifted every entry in a gene list down by one row. The other swapped the labels that marked which samples responded to a drug and which resisted it. Errors like these are easy to make and easy to miss. None of them were visible in the published papers. The main paper was later [retracted](https://www.nature.com/articles/nm0111-135), because even its own authors could not reproduce it. A [National Academies review](https://www.ncbi.nlm.nih.gov/books/NBK475955/) then examined how work that could not be reproduced had reached patients.

A [federal investigation](https://retractionwatch.com/2015/11/07/its-official-anil-potti-faked-data-say-feds/) later found that the study's lead author had engaged in research misconduct. That finding is about intent, and intent is not the focus here. The engineering lesson holds either way.

The word for that missing property is reproducibility.

:::{admonition} Definition: reproducibility
:class: tip

A result is **reproducible** when someone else can take your data and your code, run them, and get the same numbers you reported. If they cannot, then nobody can check the result, including you.
:::

The Duke errors survived because the work was not reproducible. Nobody could take the published data and code and get the reported numbers back. That is what let two small errors reach a clinical trial. An [NCI statistician who reviewed the case](https://pmc.ncbi.nlm.nih.gov/articles/PMC3474449/) stated the standard plainly: "when you plug the data into that code, you should be able to get the answers back that you have reported."

This is why the course treats reproducibility as a core engineering skill. You will face the same test in any regulated or safety-critical setting. Someone will point at a number your system produced and ask three things. Which data made it? Which code made it? Can you make it again, exactly? This session shows you how to make the answer yes, and to make it automatic. You will use the tools you use all semester, on the same air-quality sensor data from L1: a locked environment, careful version control, and a run you can point to.

## Learning objectives

By the end of this session you should be able to:

- Build and lock a project environment with `uv`, and rebuild it exactly on a fresh machine.
- Choose the right versioning tool for code, data, and models, and explain why large binary
  files do not belong in plain git.
- Turn an exploratory notebook into a script or package with a tested command-line entry
  point.
- Log a run to MLflow so that one run equals one fact you can reproduce.

## Environments you can rebuild

When you install Python and some packages to run a project, that whole collection of software is your environment.

:::{admonition} Definition: environment
:class: tip

Your **environment** is the exact software a project needs in order to run. That means the version of Python you use (the *interpreter*) plus every package you installed, each at a specific version.
:::

An environment you can rebuild is one where every version is written down and fixed. A fresh machine then installs the same Python and the same packages. It does not grab whatever version happens to be newest that day. That difference is exactly why the L1 demo broke. A package version was never recorded, so a later install pulled a slightly different version, and the code behaved differently.

Small version differences cause real bugs. A function can change how it works between two releases. A default setting can move. And your packages have their own packages underneath them.

:::{admonition} Definition: dependency
:class: tip

A **dependency** is a package your project needs. Each dependency usually has its own dependencies, called *transitive* dependencies. A small project can pull in dozens of packages you never asked for directly.
:::

We use a tool called `uv` to manage all of this. It works through three files.

First, `pyproject.toml` lists the packages you asked for, usually with loose version limits. Second, `uv.lock` records what you actually got. It lists every package, including the transitive ones, each pinned to one exact version. Third, `.python-version` fixes the Python interpreter. Together these three files make a rebuild deterministic, which means it produces the same result every time.

You drive `uv` with four commands. `uv init` starts a new project. `uv add pandas scikit-learn mlflow` adds packages and updates both `pyproject.toml` and `uv.lock`. `uv run python -m sensorlab.train` runs a command inside the project environment, and it checks the lockfile is current first. On a fresh copy of the project, `uv sync` rebuilds the whole environment from the lockfile. You rarely touch the underlying virtual environment (the hidden `.venv` folder where the packages actually live) by hand.

### Lockfiles and requirements files

The key idea in this section is what a lockfile gives you. Start with the older tool, a `requirements.txt` file. It lists packages, often at loose versions. Install it on two machines a month apart and you can get two different sets of packages, because "newest allowed version" changes over time.

A lockfile is stricter.

:::{admonition} Definition: lockfile
:class: tip

A **lockfile** records the entire set of packages your project resolved to, every one pinned to an exact version. Install from a lockfile and you get identical packages every time. `uv` writes and updates `uv.lock` for you, so you never edit it by hand.
:::

A `requirements.txt` still has a use. It is a common export format, and `uv` can produce one for tools that expect it. For rebuilding your own project, though, the lockfile is the file that matters. It is what makes `uv sync` give the same answer twice.

:::{admonition} Common pitfall
:class: warning

Many people treat `uv` as a faster `pip` and stop after `uv add`. The pin that actually buys reproducibility is the lockfile together with the fixed interpreter. Without both, you have only found a faster way to build an environment you cannot rebuild. The one-line test is to delete `.venv`, run `uv sync`, and check you get the same thing back. We do this in class, because watching it rebuild from nothing is more convincing than being told it works.
:::

## A project layout that scales

An exploratory analysis can live in one notebook and a folder of loose files. A real system cannot. Its code has to be imported by other code, tested, and run by people who are not you. A small, standard folder layout gives you all three. Set it up on the first day. It costs nothing then and is hard to add later.

:::{admonition} Definition: scaffolding
:class: tip

To **scaffold** a project is to set up its skeleton before you write much code: the folders, the config files, and an empty package. Like scaffolding on a building, it is the frame you build on. A1 has you scaffold one project and reuse it all semester.
:::

The standard shape is the `src` layout. Your code lives in a package under `src/sensorlab/`. A package is just a folder of Python files that other code can import by name. Putting it under `src/` means Python imports the code as an installed package. The code then behaves the same no matter which folder you launch from. That prevents a common bug, where an analysis only works because you started it from one specific folder. The file `pyproject.toml` is the project's manifest. It declares the dependencies, the entry points, and basic metadata. Around the package sit folders that keep each kind of file in its own place:

```text
sensorlab/
├── pyproject.toml        # manifest: dependencies, entry points
├── uv.lock               # the exact resolved environment
├── .python-version       # the pinned interpreter
├── .gitignore
├── src/sensorlab/        # importable package: load, clean, featurize, train
├── data/                 # raw data, kept out of git
├── notebooks/            # exploration
├── scripts/              # entry points
└── tests/                # tests
```

The folder names are not the point. The point is that every kind of file has one place to go. The boundary between quick exploration and the code that really runs is drawn in the folder tree, where you can see it, instead of living in someone's memory.

## Versioning code, data, and models are three different problems

Git works very well for code and not that well for a 200 MB data file. Trying to keep everything in one repository is how repositories become huge and slow to clone. Your three kinds of output differ in size, in how often they change, and in what is worth recording about them. So they belong in different tools.

**Code** goes in git. Code is small, it is text, and git can show you exactly what changed line by line. Each commit is a labeled save point, and its identifier is a short code called a SHA. That SHA answers the question "which version of the code produced this number."

:::{admonition} Definition: provenance
:class: tip

**Provenance** is the record of where a result came from: which data, which code, and which settings produced it. Reproducibility is being able to make the result again. Provenance is being able to say how it was made in the first place.
:::

**Data** does not go in plain git. A raw sensor file is large and binary, and git keeps every version of every file forever, so committing it makes the repository grow without limit. Raw data may also carry license or privacy rules that a public copy of the repository would break. The habit is to keep raw data out of git using a `.gitignore` file (a list of paths git should ignore), track a small sample or a description of the columns so the shape is documented, and record where the real data came from plus a content hash. A content hash is a short fingerprint computed from the bytes of a file. If the file changes, its hash changes, so two runs can be checked for using the same data. Tools that version large data properly, `git-lfs` and DVC, come in Week 4.

**Models** are large binary files too. They are also outputs, so the thing worth saving is what produced them: the code SHA, the data hash, and the settings. MLflow, in the next section, is where that link is stored.

| Artifact | How it changes | Tool | What you actually version |
|---|---|---|---|
| Code | constantly, in small edits | git | the source, as commits |
| Data | rarely, large and binary | git-ignored, plus a hash; git-lfs/DVC (Wk4) | a pointer and a hash, never the raw bytes |
| Models | one per run, large binary | an MLflow run | the inputs that produced it |

Set up the `.gitignore` before your first commit. Once a big file is committed, removing it means rewriting the history, which is far more work. This repository's own `.gitignore` already ignores `data/`, `*.parquet`, and `*.duckdb` for these reasons.

## From notebook to module

A notebook is the right tool for looking at data. It is the wrong tool for code that has to run again reliably. Cells run in whatever order you click them. State builds up between runs without you seeing it. "It worked a minute ago" is not something you can ship. Turning a notebook into a module is how an exploration becomes something you can test, schedule, and trust. This is the step that removes most of the L1 failures for good.

This problem is widespread. [One study](https://leomurta.github.io/papers/pimentel2019a.pdf) collected about 1.45 million Jupyter notebooks from GitHub. After removing duplicates they had about 1.16 million to study. Of the 863,878 that were valid Python and could be run at all, only about a quarter ran to the end without an error. Only about four percent reproduced the results the notebook had saved. [A separate study](http://reproducibility.cs.arizona.edu/v2/RepeatabilityTR.pdf) looked at 601 computer-science papers. Of the 402 whose results were produced by code, the authors' code could be found and built within half an hour for under a third of them. Getting the code at all was often the hard part. The normal state of shared analysis code is that it does not run for the next person. The next person is often you, six months later.

```{figure} figures/notebook-repro.png
:alt: A funnel: about 864,000 valid Python notebooks attempted, about 24 percent ran without error, about 4 percent reproduced the recorded result
:width: 80%
:align: center

Of the 863,878 valid Python notebooks that could be run (from about 1.45 million collected on
GitHub, 1.16 million after removing duplicates), about 24% ran to the end without error and
about 4% reproduced the result the notebook had saved. Data from Pimentel et al. (2019);
generated by `figures/make_figures.py`.
```

The fix is mechanical. Pull the logic out into functions, such as `load`, `clean`, `featurize`, and `train`. Each takes its inputs as arguments and returns a value, so you can import it and test it on its own. Add an entry point behind `if __name__ == "__main__"`, which is the block Python runs when you launch the file directly. Give it an argument parser so the analysis runs from the command line, like `uv run python -m sensorlab.train --seed 0`, instead of by clicking cells. Then fix the seed for anything that uses randomness.

:::{admonition} Definition: seed
:class: tip

A **seed** is a starting number for a random process. Fix the seed and the "random" choices come out the same every run. That is what made problem two in the L1 demo produce a different score each time: the seed was never fixed.
:::

The notebook does not have to disappear. It becomes a thin front-end that imports the same functions, so exploration and the real code share one path and cannot drift apart. The habit that catches hidden state is running the whole thing from a clean start. For a module that means a fresh process. For a notebook it means Restart and Run All.

## Experiment hygiene: one run, one fact

Once the analysis runs from the command line, you will run it many times, with different seeds and settings. Within a day you will not remember which settings produced which number. Experiment tracking is the tool that records each run for you, so a run becomes a fact you can point to instead of a memory you have to trust.

MLflow records, for each run, the settings you chose, the metrics you measured, and any files you attach, such as a figure or a saved model. It stores each run on your own machine, with no server to run. Recent MLflow keeps the runs in a small local SQLite database (a single file on disk). The command `mlflow ui`, pointed at that database, shows the runs side by side in a browser. The core of the interface is small:

```python
import mlflow

mlflow.set_tracking_uri("sqlite:///mlflow.db")  # local store, no server
with mlflow.start_run():
    mlflow.log_params({"seed": seed, "data_date": data_date})
    r2 = train_and_score(seed=seed)
    mlflow.log_metric("r2", r2)
    # also log the code SHA and a data hash, so the run is reconstructible
```

Run the trainer twice with two seeds and you get two rows to compare. The habit worth building is to log enough that you could rebuild the run: the git SHA of the code, a hash or version of the data, and the seed, next to the metric. Those three items are the provenance the Duke work never had. With them, one run equals one fact you can reproduce. The miniproject later asks for exactly these three, a git SHA, a data hash, and a seed, as the price of entry.

## In-class demo

We build the A1 scaffold live, starting from an empty folder and ending with a tracked run in about fifteen minutes. The steps are `uv init`, then add pandas, scikit-learn, and mlflow, then move the L1 exploratory cells into `src/sensorlab/` as functions, then add a command-line entry point, then run it twice with two seeds, then open the MLflow UI to see the two runs side by side.

Watch for two moments. The first is when we delete `.venv` and rebuild it from the lockfile. That is what a reproducible environment means once you actually do it. The second is when the two seeded runs become two saved, comparable facts instead of two numbers you would have to remember. The runnable version is [`l02-scaffold.ipynb`](l02-scaffold.ipynb).

## Summary

Reproducibility is being able to say which data, which code, and which settings produced a number, and then to produce that number again. The Duke chemotherapy predictors show why it matters. Two small errors, a shifted index and a swapped label, reached a clinical trial and stood for years, because nobody could rebuild the analysis and check it. Each tool in this session closes one gap. `uv` fixes the environment so a rebuild comes out the same every time. A standard layout and a careful `.gitignore` keep code, data, and models in the tools that suit each one. Moving the notebook into a module makes the analysis run again for the next person. MLflow turns each run into a fact you can point to. Next session we stop leaving the data in a CSV file and give it a real home, starting with relational databases and SQL for engineering time series.

## Resources

- [uv documentation, Working on projects](https://docs.astral.sh/uv/guides/projects/). The commands from this session in order: `uv init`, `uv add`, `uv run`, and what each file is for. Start here.
- [uv documentation, Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/). What `uv sync` does, and how the lockfile relates to a `requirements.txt` export. The [resolution page](https://docs.astral.sh/uv/concepts/resolution/) explains why the lockfile works across platforms.
- [MLflow Tracking Quickstart](https://mlflow.org/docs/latest/ml/tracking/quickstart/). Logging parameters and metrics, and viewing runs. Local storage options and the `mlflow ui` command are on the [Tracking overview](https://mlflow.org/docs/latest/ml/tracking/).
- [Pro Git, chapter 1](https://git-scm.com/book/en/v2/Getting-Started-About-Version-Control) and [chapter 2](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository). Free online. The "Ignoring Files" section in chapter 2 is the `.gitignore` reference for this session.
- [The Turing Way, Reproducible Research](https://book.the-turing-way.org/reproducible-research/reproducible-research/). The broader case, and a clean definition: the same data plus the same code should give the same result.
- [Deriving chemosensitivity from cell lines](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-3/issue-4/Deriving-chemosensitivity-from-cell-lines--Forensic-bioinformatics-and-reproducible/10.1214/09-AOAS291.full). Baggerly and Coombes, *Annals of Applied Statistics* 2009, open access. The reconstruction that found the shifted-index and swapped-label errors.
- [Retraction note, *Nature Medicine*](https://www.nature.com/articles/nm0111-135). The 2011 retraction of the 2006 paper, in the authors' own words.
- [Evolution of Translational Omics](https://www.ncbi.nlm.nih.gov/books/NBK202165/). The 2012 Institute of Medicine report prompted by the case. Its recommendation that data and code be made available for independent review is this session in one sentence.
- [A large-scale study of the quality and reproducibility of Jupyter notebooks](https://leomurta.github.io/papers/pimentel2019a.pdf). Pimentel et al., MSR 2019. Source of the notebook figures above; the 24% and 4% are of the 863,878 valid notebooks that could be run.
- [Repeatability in computer systems research](http://reproducibility.cs.arizona.edu/v2/RepeatabilityTR.pdf). Collberg and Proebsting. Source of the 601-paper build figure; the 32.3% is of the 402 papers whose results were produced by code, which is more papers than actually shared their code.

## Assignment

A1, the reproducible project scaffold, is released this session and due about one week later. It asks you to build a `uv`-managed, git-tracked project that pulls the UCI air-quality dataset and turns an exploratory notebook into a runnable, importable module with a tested entry point and an MLflow-logged run. It is the scaffold you reuse all semester, so do it carefully the first time. The full instructions and grading are in `course/assignments/a01.md`.
