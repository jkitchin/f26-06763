# Lecture 2: Reproducible environments, version control, and experiment hygiene

:::{admonition} Overview
:class: tip

- **Session** Lecture 2, Week 1
- **Arc** Foundations
- **Slides** <a href="../../slides/l02/">Deck for this session</a>
- **Practice** <a href="../../game/#/l02">Practice module for this session</a>
- **Demo** [`l02-scaffold.ipynb`](l02-scaffold.ipynb), building a tracked project from an empty folder
- **Assignment 1**, released this week and due about a week later (08-31-2026)
:::

## Why this matters

In 2006 a team at Duke University published a result in [*Nature Medicine*](https://www.nature.com/articles/nm1491). Their models read a tumor's gene-expression profile and predicted which chemotherapy drug the patient would respond to. The promise was huge: a genomic test that could spare a patient the use of the wrong drug. The work was persuasive enough that, beginning in 2007, **three** clinical trials used this research to help assign real patients to treatments, and 117 patients participated. The stakes were about as high as they get for a machine-learning result, because the models were steering real chemotherapy decisions.

Two statisticians at a different research center set out to build on this work. They could not reproduce it. When they rebuilt the analysis from the data the papers provided, the reported numbers would not come back. Investigation took them months. What they eventually found was a pair of ordinary mistakes. One was an [off-by-one error](https://projecteuclid.org/journals/annals-of-applied-statistics/volume-3/issue-4/Deriving-chemosensitivity-from-cell-lines--Forensic-bioinformatics-and-reproducible/10.1214/09-AOAS291.full) that shifted an entire list of genes down by one row, so the reported genes were the wrong ones. The second mistake was a set of sample labels in which **"responds to the drug" and "resists the drug" had been swapped.** Careful people make errors of exactly this kind every day, in every lab. What made these matter is that nobody caught them. Nobody caught them because the work could not be checked in the first place.

The consequences extended for years. A [later National Academies review](https://www.ncbi.nlm.nih.gov/books/NBK475955/) reconstructed how the original work that could not be reproduced had reached patients at all. The main paper was [retracted](https://www.nature.com/articles/nm0111-135) in 2011, and the authors' own stated reason was that they could not reproduce their results either. A [federal investigation](https://retractionwatch.com/2015/11/07/its-official-anil-potti-faked-data-say-feds/) eventually found that the lead author had committed research misconduct. The investigation's finding was about intent, but intent is not the subject of this lecture. The engineering lesson sits underneath that question and holds regardless of the answer: for years, a flawed analysis could not be told apart from a sound one, and there was no way to take its data and its code and get its numbers back.

This session is about building that ability in from the start: taking the data and the code and getting the numbers back. This is **reproducibility**.

:::{admonition} Definition: reproducibility
:class: tip

A result is **reproducible** if someone else can take your data, your model, and your code, run them, and get the same numbers you reported. It is the underlying condition for checking work at all. If a result cannot be regenerated, it cannot be examined, corrected, or defended. That includes you, months later, when you are the stranger.
:::

An NCI statistician who reviewed the Duke case said as plainly as it can be [put](https://pmc.ncbi.nlm.nih.gov/articles/PMC3474449/): "There is computer code that evaluates the algorithm. There is data. And when you plug the data into that code, you should be able to get the answers back that you have reported." 

This does not seem to be a high standard in principle. However, it is exactly the bar the Duke work failed. It is also the bar you will be held to the moment your work touches a decision anyone cares about. In a regulated or safety-critical engineering setting, someone will eventually point at a number your system produced and ask potentially the following questions in a row:

1. Which data produced this? 
2. Which code produced it? 
3. Can you produce it again, exactly? 

This session is about making the answer to all three a systematic and automatic **"yes"**. We will use the tools we will rely on for the rest of the semester and the same UCI air-quality sensor data from Lecture 1: 

- A locked environment, 
- Version control, 
- A run you can point to. 


## Learning objectives

By the end of this session you should be able to:

- Build and lock a project environment with `uv`, and rebuild it exactly on a fresh machine.
- Choose the right versioning tool for code, data, and models, and explain why large binary
  files do not belong in plain git.
- Turn an exploratory notebook into a script or package with a tested command-line entry
  point.
- Log a run to MLflow so that one run equals one fact you can reproduce.

## Environments you can rebuild

```{index} virtual environment, uv, dependency resolution, lockfile
```

A project's **environment** is the exact Python interpreter and set of packages you install to run it. Reproducing a result begins with reproducing that environment exactly, perhaps on a different machine from the one that first produced the results. 

This environment is more than the packages you named. It includes the exact version of the Python interpreter. It also includes every package you installed directly. In addition, it should also include every package those packages pulled in underneath them, each one at a specific version. A dependency you never selected directly can totally change a number you report. That is why "I installed pandas and scikit-learn" is not a description anyone can rebuild from.

Small version differences produce real, silent changes in behavior. The Lecture 1 demo showed one live. A function's behavior can shift between two minor releases. A default argument in a function signature can move. A dependency of a dependency can resolve to a newer version on a Tuesday than it did on the Monday you last ran the code. "Newest version that satisfies the constraints" is a moving target and we should not trust in this type of information alone. Worse, sometimes, none of these announce themselves. They surface later (literally, when someone is trying to reproduce your results), as a result that will not reproduce, and by then "the trail is cold."

:::{admonition} Definition: dependency
:class: tip

A **dependency** is a package your project needs in order to run. Each dependency usually has dependencies of its own, called *transitive* dependencies. A project that names three packages can easily pull in fifty. The full, resolved set is what actually determines your results. It is far larger than the list you wrote.
:::

The tool this course standardizes on for managing all of this is `uv`. It works through three files. Understand them as a unit before touching the commands. The first, `pyproject.toml`, records what you *asked for*: your direct dependencies, usually at loose version constraints like "pandas, at least this version." 

The second, `uv.lock`, records what you actually *got*: the entire resolved dependency graph, transitive packages included, every one pinned to an exact version, resolved once and then reused. The third, `.python-version`, pins the interpreter itself. Python 3.11 and Python 3.13 are genuinely different environments, and a result that depends on which one ran is a result you cannot yet reproduce. Together these three files make a rebuild provably the same rather than probably the same.

In day-to-day use you drive `uv` with a handful of commands. For example:

1.  `uv init` creates a project and writes the first `pyproject.toml` and `.python-version`. 
2. `uv add pandas scikit-learn mlflow` adds dependencies, resolves the whole graph, and updates both `pyproject.toml` and the lockfile in one step. 
3. `uv run python -m sensorlab.train` runs a command inside the project's environment. Before it does, it checks that the lockfile is consistent with `pyproject.toml`, so the environment can never quietly drift out from under you. 

On a fresh checkout of the project, on your laptop or a colleague's or a continuous-integration server:

4. `uv sync` reconstructs the environment from the lockfile: the same interpreter, the same packages, the same versions, with no interpretation required. That last command is where the payoff lives. It is the end of "works on my machine" as an acceptable answer.

### Lockfiles and requirements files

```{index} resolver
```

The point of this section is what a lockfile gives us, in this journey of reproducibility. In our opinion, the clearest way to see it is against the older tool it replaces, a `requirements.txt`. 

A `requirements.txt` file is, simply put, a list of packages. In most projects it lists only the direct ones, often at loose versions. The file is valid, but it is not necessarily reproducible. Install the same `requirements.txt` on two machines a month apart and you can easily get two different sets of packages. The **resolver** is free to pick whatever is newest within the loose constraints, and for example, a month is plenty of time for "the newest version" to change. 

:::{admonition} Definition: resolver
:class: tip

A **resolver** is the part of a package manager that turns your loose requirements ("pandas, at least this version") into one concrete set of exact versions to install, choosing a version for each of your direct dependencies and for every transitive one underneath them so that nothing conflicts. Left to itself, it takes the newest versions that satisfy your constraints, so running it a month apart can hand you two different environments. A lockfile is simply that resolved output, frozen so the next run cannot pick differently.
:::

:::{admonition} Definition: lockfile
:class: tip

A **lockfile** records the complete set of packages your project resolved to, every one pinned to an exact version. Installing from it reproduces an **identical environment** every time. `uv` writes and maintains `uv.lock` for you as you add dependencies. It is not a file you edit by hand.
:::

The difference from a requirements file is significant. `uv.lock` is a *universal* resolution. It is computed once to be valid across platforms, pinned exactly, and owned by `uv` rather than by you, which reduces errors. A `requirements.txt` still has a legitimate role as an *export format*, a way to hand a package list to a tool or a service that expects that shape, and `uv` can actually generate one on request. In short, the lockfile is what makes `uv sync` give the same answer twice.

:::{admonition} Common pitfall
:class: warning

The most common way to miss the point of `uv` is to treat it as a faster `pip` and stop after `uv add`. Speed is indeed a nice feature of `uv`, for sure. But the actual important feature for our context here is the pin. What ensures reproducibility is the lockfile together with the fixed interpreter. Without both, you have only found a quicker way to build an environment you still cannot rebuild. The one-line test settles it in class: delete `.venv`, run `uv sync`, and confirm you get the same thing back. Watching an environment reconstruct itself from nothing is more convincing than being told that it will.
:::

## A project layout that scales

```{index} project scaffold, pyproject.toml
```

An exploratory analysis can live in a single notebook and a folder of loose files. For the first afternoon of a project you are working on, that is fine. But for longer projects or a whole system implementation, it cannot stay this way. Some reasons are:

1. A system's code has to be imported by other code, 
2. exercised by tests,
3. run by people who are not you and who are not sitting in the folder where you happened to save it. 

A small, conventional project layout gives all three of those desired features. Hence, it is a good idea to set it up on the very first day. 
It costs almost nothing then, and it is genuinely tedious to do this manually afterwards, once you have many scripts later in development.

:::{admonition} Definition: scaffolding
:class: tip

To **scaffold** a project is to set up its skeleton before you write a lot of code: the folders, the configuration files, and an empty, importable package. Like the scaffolding around a building, it is the temporary-feeling frame that everything real gets built against. Assignment 1 has you scaffold one project and then reuse it all semester.
:::

The convention this course uses is the **src layout**. It repays a moment of understanding rather than blind copying. Your code lives in a *package*, which is a folder of Python files that other code can import by name. That package sits under a top-level `src/` directory. Putting it there means your code is imported the way an installed library is, by its name. It is not imported as whatever files happen to sit next to the script you launched. That single indirection removes a bug that bites beginners hard. It is the analysis that runs perfectly from one directory and mysteriously fails from another, because it was quietly depending on the current folder to resolve its imports. Around the package sits `pyproject.toml`, the project's manifest. It declares the dependencies, the command-line entry points, and the metadata that make the package installable. The remaining folders give each kind of file one obvious home:

```text
sensorlab/
├── pyproject.toml   uv.lock   .python-version
├── src/sensorlab/   # the importable package: load, clean, featurize, train
├── data/            # raw data, kept out of git
├── notebooks/       # exploration
├── scripts/         # entry points
└── tests/           # tests
```

The specific folder names matter far less than the principle underneath them. The boundary between throwaway exploration and the code that actually runs is drawn in the directory tree, where anyone can see it. It does not live in one person's memory of which notebook is the "real" one. The Assignment 1 scaffold is exactly this shape. You reuse it all semester, so an hour spent understanding it now is repaid many times over.

## Versioning code, data, and models are three different problems

```{index} data versioning, content hash, DVC, provenance, version control
```

Git is excellent at versioning code. It is close to useless at versioning a 200 MB data file. The instinct is to solve the problem by putting everything into one repository. That is exactly how repositories become slow, enormous, and unpleasant to clone. A project produces three kinds of artifact: its code, its data, and its models. They differ in size, in how often they change, and in what is worth recording about them. Those differences mean they belong in three different tools. Getting this split right early is far cheaper than untangling it later.

:::{admonition} Definition: version control
:class: tip

**Version control** records the changes to a set of files over time, so you can see what changed, return to any earlier state, and say exactly which version produced a given result. **Git** is the version-control tool this course uses: it saves the project's history as a sequence of **commits**, each a labeled snapshot identified by a Secure Hash Algorithm (SHA). If you have not used git before, the Pro Git chapters in the resources are the place to start.
:::

**Code** belongs in git, which was built for it. Code is small and it is text. Git can show you exactly what changed, line by line, between any two points in the project's history. Each commit is a labeled, permanent save point. Its identifier is a short string called a SHA, and the SHA is itself a piece of provenance. The question "which version of the code produced this number" is answered completely by a commit SHA. This is the cheapest and most reliable versioning you will do all semester. It costs nothing but the discipline of committing in meaningful units.

:::{admonition} Definition: provenance
:class: tip

**Provenance** is the record of where a result came from: which data, which code, and which settings produced it. Reproducibility is the ability to make the result *again*. Provenance is the ability to say *how it was made* in the first place. You want both. They are recorded by different means: git for the code, a hash for the data, an experiment tracker for the tie between them.
:::

**Data** does not belong in plain git. Understanding why is worth more than the rule. Git keeps every version of every file forever, by design, so that history is complete and nothing is lost. Commit a large binary file and you have committed it permanently. Even after you delete it, it lives on in the history, and every future clone of the repository pays to download it. A raw sensor export is large and binary. It often carries license or privacy constraints that a public copy of the repository would violate outright. So the discipline is to keep the raw data out of git with a `.gitignore` file, which is a list of paths git should refuse to track. In its place you commit a small sample or a description of the columns, so the shape is documented. You also commit a record of where the real data came from and a *content hash* of it. A content hash is a short fingerprint computed from the bytes of a file. Change a single byte and the fingerprint changes. Two runs can then be checked, cheaply and exactly, for having used the same data. Set up the `.gitignore` before your first commit rather than after. Once a large file is in the history, removing it means rewriting that history, which is far more work than never adding it. This repository's own `.gitignore` already excludes `data/`, `*.parquet`, and `*.duckdb` for exactly these reasons. The heavier tools for versioning large data by content are `git-lfs` and data version control (DVC).

**Models** are large binary files too. They differ from data in one way that changes what you should record: a model is an *output*. The thing worth saving is the recipe that produced the model, more than the weights themselves. That recipe is the code SHA, the data hash, and the configuration together. Recreate those three and you can recreate the model. Save only the weights and you have an artifact nobody can regenerate or trust. Recording that recipe is what an experiment tracker is for, which is the next section.

| Artifact | How it changes | Tool | What you actually version |
|---|---|---|---|
| Code | constantly, in small diffs | git | the source, as commits |
| Data | rarely, large and binary | git-ignored, plus a content hash; git-lfs/DVC | a pointer and a hash, never the raw bytes |
| Models | one per run, large binary | an MLflow run | the inputs that produced it |

## From notebook to module

```{index} random seed, notebook to module
```

A notebook is the right tool for looking at data. It is the wrong tool for anything that has to run again reliably. The reason is structural. In a notebook, cells run in whatever order you clicked them, not top to bottom. State accumulates invisibly between runs. A variable defined in a cell you have since deleted can keep a later cell working long after the code that created it is gone. "It worked a minute ago" is a true statement about a notebook. It tells you almost nothing about whether it will work on a fresh start. Turning the notebook into a module is how an exploration becomes something you can test, schedule, and trust. It is the step where most of the Lecture 1 failures are designed out rather than merely warned against.

This is the normal state of shared analysis code, and it happens to careful people all the time. Researchers collected about 1.45 million Jupyter notebooks from GitHub. After removing duplicates they kept about 1.16 million to study. Of the [863,878 valid Python notebooks](https://leomurta.github.io/papers/pimentel2019a.pdf) they could actually attempt to run, only about a quarter ran to completion without an error. Only about four percent reproduced the results the notebook itself had saved. A separate audit of [601 computer-science papers](http://reproducibility.cs.arizona.edu/v2/RepeatabilityTR.pdf) looked at the 402 whose results were produced by code. For under a third of those, the code could be obtained and built within half an hour. Simply getting hold of the code at all was often the hard part. The next person who cannot run your notebook is, more often than not, you, half a year from now.

```{figure} figures/notebook-repro.png
:alt: A funnel: about 864,000 valid Python notebooks attempted, about 24 percent ran without error, about 4 percent reproduced the recorded result
:width: 80%
:align: center

Of the 863,878 valid Python notebooks that could be run (from about 1.45 million collected on
GitHub, and 1.16 million after removing duplicates), about 24% ran to completion without error.
About 4% reproduced the result the notebook had saved. Data from Pimentel et al. (2019).
```

The refactor that fixes this is mechanical, which is the good news. You pull the logic out of the cells and into functions, such as `load`, `clean`, `featurize`, and `train`. Each function takes its inputs as arguments and returns a value. It can then be imported and tested in isolation rather than depending on the ambient state of a notebook. You add an entry point behind the `if __name__ == "__main__"` guard, the block Python runs only when a file is launched directly. You give it an argument parser, so the analysis runs from the command line as `uv run python -m sensorlab.train --seed 0` rather than by clicking cells in an order you have to remember. And you fix the seed for anything that draws on randomness.

:::{admonition} Definition: seed
:class: tip

A **seed** is the starting number for a pseudo-random process. Fix the seed and the "random" choices come out identically on every run. Those choices include a train/test split and the initialization of a model. Leave the seed unset and they vary each time. That variation is exactly the Lecture 1 demo's silent failure. Nothing raised an error. The score simply moved from run to run. A number that will not sit still cannot be reproduced.
:::

The notebook does not have to disappear when you do this. It becomes a thin front-end that imports the same functions the command-line entry point calls. Exploration and the code that runs in production then share a single path. They cannot drift apart into two subtly different analyses. The habit that catches the hidden-state problem is running the whole thing from a clean start. For a module that means a fresh process. For a notebook it means the "Restart and Run All" command. Make that reflexive before you trust any notebook result, including your own.

## Experiment hygiene: one run, one fact

```{index} experiment tracking, MLflow
```

Once the analysis runs from the command line, you will run it many times, with different seeds, different features, and different parameters. Within a day, the question "which settings produced this particular number" becomes unanswerable from memory. **Experiment tracking** is the infrastructure that answers it for you. It records each run as it happens, so the run becomes a fact you can point to rather than a recollection you have to trust. It is the smallest and most immediately useful unit of the provenance discipline from earlier in the session.

MLflow is the tracker this course uses. For each run it records the parameters you chose, the metrics you measured, and any artifacts you attach, such as a figure or a saved model. It stores all of this locally, with no server to stand up in Week 1. One wrinkle is worth knowing, because it surprises people mid-demo. Recent versions of MLflow have put the old bare-directory store into maintenance mode and will refuse to use it. They steer you instead toward a small local SQLite database, which is a single file on disk and still needs no server. Pointed at that file, the `mlflow ui` command shows your runs side by side in a browser. The interface you actually touch is small:

```python
import mlflow

mlflow.set_tracking_uri("sqlite:///mlflow.db")  # local store, no server
with mlflow.start_run():
    mlflow.log_params({"seed": seed, "data_date": data_date})
    r2 = train_and_score(seed=seed)
    mlflow.log_metric("r2", r2)
    # also log the code SHA and a data hash, so the run is reconstructible
```

Run the trainer twice with two different seeds. The two runs appear as two rows you can compare directly. The small difference between them is the lesson. It is why the seed has to be logged: without it, neither number is reconstructible. The habit worth building is to log enough that the run could be *rebuilt* from its record. That means the git commit SHA of the code, a hash or version of the data, and the seed, all sitting next to the metric. That triple is the provenance the Duke work never had. With it, a run becomes one reproducible fact, which is the phrase this section is named for. Get in the habit of recording all three, a git SHA, a data hash, and a seed, next to every metric you log.

## Where reproducibility pushes back

```{index} pair: failure mode; reproducible but wrong
```

Everything so far has been an argument for a discipline. The argument is sound. A course that only sold its tools would be teaching advocacy rather than engineering. Reproducibility is necessary infrastructure. It is not a cure-all. Knowing this well means knowing what it does not give you and where the effort stops being worth it. Several of its limits are worth meeting here, on paper, rather than later, under deadline.

### Reproducible is not the same as correct

This is the limit that matters most. Making a result reproducible does not make it right. Suppose your pipeline contains the same off-by-one error the Duke code did. Locking the environment, pinning the seed, and tracking the run will then reproduce the *wrong* answer, every time, with perfect fidelity. Reproducibility makes a result *checkable*. It is a precondition for catching errors. The catching itself is a separate step. Notice how the Duke errors were actually caught. Re-running the original code would simply have reproduced its mistakes. Outside statisticians re-implemented the analysis from scratch and found that the two versions disagreed. Reproduction confirms you can regenerate a number. Confirming the number is right is a separate act, and it is called validation.

### A lockfile pins versions, not the whole world

A lockfile is a strong guarantee. It is not a total one. It pins the exact version of every Python package. A package version is not the same as the compiled code that actually runs. Many packages ship as platform-specific binary wheels. The bytes installed for your locked version of NumPy differ between macOS and Linux. The lockfile says nothing about the system C libraries, the CUDA toolkit, or the operating system underneath. A pinned version can even become unavailable if it is later removed from the package index. For most engineering work the lockfile is enough. When you need to freeze the entire stack down to the system libraries, the tool is a container, which packages the operating-system layer as well. So `uv` gives you a reproducible *Python environment*. That is most of what you need, and not quite all of it.

### The discipline has a cost, and sometimes it is overkill

Setting up a locked, tracked, packaged project is not free. There is a real judgment call about when to pay for it. Consider a genuinely throwaway exploration, twenty minutes of poking at a file to decide whether an idea is worth pursuing. Full scaffolding there is friction that buys you nothing, and insisting on it would be its own kind of over-engineering. The skill is proportion. The moment an analysis is going to be rerun, shared, built upon, or believed by anyone, including your future self, it has crossed the line into needing this discipline. The trap is that results almost always cross that line quietly, without anyone deciding that they have. When in doubt, scaffold. Retrofitting is the expensive direction.

### A hash tells you that data changed, not what or why

The content hash that lets you detect whether two runs used the same data is a blunt instrument on purpose. It will tell you, with certainty, that the file is different. It will not tell you which rows changed, whether the change was a fix or a corruption, or whether it matters for your result. Detecting change is only the floor of data provenance. The tools that go further version data by content and keep a readable history of what changed and why. Those tools are `git-lfs` and DVC. A hash tells you something changed. It does not tell you what or why.

### Tracking records; it does not enforce

MLflow will record whatever you log. That includes a run whose environment was never locked and whose seed was never pinned. Logging a seed does not make an environment reproducible. It only documents one input to a run that may still be irreproducible for other reasons. The tracker is a filing system. A filing system is only as trustworthy as the discipline of the person filing. The habits in this session are what make the thing you filed worth retrieving: the lockfile, the pinned interpreter, the fixed seed, and the recorded SHA and hash.

:::{admonition} What a practitioner should take from this
:class: tip

Treat reproducibility as the foundation you build on, not the building itself. It is necessary. Without it, no result can be checked, corrected, or defended, and the Duke case is what its absence costs. It is not sufficient. A reproducible result can still be wrong. It buys you the ability to validate. Validation itself is still your job. It is also not free. Invest in proportion to how much the result will be reused or believed, and default to more discipline rather than less, because retrofitting is the costly direction. What you build this week is the layer everything else assumes.
:::

## In-class demo

We build the Assignment 1 scaffold live, starting from an empty folder and ending with a tracked run in about fifteen minutes. The path runs `uv init` to create the project. It adds pandas, scikit-learn, and mlflow. It moves the Lecture 1 exploratory cells into `src/sensorlab/` as importable functions, adds a command-line entry point, runs the trainer twice with two different seeds, and opens the MLflow UI to see the two runs side by side. The demo is deliberately the same shape as Assignment 1, so it is a preview of the assignment rather than a separate exercise.

Two moments carry the lesson. The first is when we delete `.venv` and rebuild it from the lockfile. That is what "a reproducible environment" means once you do it rather than merely claim it. The second is when the two seeded runs become two logged, comparable facts, instead of two numbers you would otherwise have to hold in your head and would misremember by the afternoon. The runnable version is [`l02-scaffold.ipynb`](l02-scaffold.ipynb).

## Summary

Reproducibility is the ability to say which data, which code, and which settings produced a number, and then to produce that number again. The Duke chemotherapy predictors are the case for taking it as seriously as this session does. Two ordinary errors, a shifted index and a swapped label, reached a clinical trial and stood for years, because the work was never reproducible enough for anyone to check. Each tool in the session closes one part of the gap. `uv` pins the interpreter and locks the dependency graph, so a rebuild comes out the same rather than merely similar. A conventional `src` layout and a disciplined `.gitignore` keep code, data, and models in the tools that suit each. They also keep the boundary between exploration and production visible in the tree. Refactoring the notebook into a module makes the analysis run again for someone who is not you. MLflow turns each run into a fact you can point to, carrying the SHA, the data hash, and the seed that make it rebuildable. The closing section is the other half of the story. Reproducibility is necessary and not sufficient. A lockfile pins Python and not the whole machine. The discipline is worth paying for in proportion to how much a result will be trusted.

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

Assignment 1, the reproducible project scaffold, was released in Week 1 and is due about a week later (08-31-2026). It asks you to take the Lecture 1 demo notebook, fix the three defects that stop it reproducing, and land it in a `uv`-managed, git-tracked project: a package of importable functions, a seeded command-line entry point, and two runs logged to MLflow. The loader and the snippets you have not been shown yet are given to you, so the work is the scaffold rather than the syntax. It is the scaffold you reuse all semester, so it is worth doing carefully the first time. It is also a direct extension of the demo we build in class. This is a pointer; the assignment page carries the details.

## Practice module

<a href="../../game/#/l02"><strong>Practice module for this session</strong></a>, about ten
minutes of questions drawn from the numbers and the pitfalls above. It runs entirely in your
browser, the questions are selected from your Andrew ID, and it ends by producing a PDF you
upload for participation credit.
