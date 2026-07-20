# L1 · The AI-engineering landscape and the modern toolchain

:::{admonition} At a glance
:class: tip

**Session** L1, Week 1 · **Arc** Foundations
**Slides** <a href="../../slides/l01.html">Deck for this session</a>
**Demo** `demo.ipynb`, the UCI Air Quality notebook that fails to reproduce
**Assignment** A1 released at L2
:::

## Why this matters

In 2015 a group of Google engineers published a paper with an unusually blunt diagram. It
showed the components of a production machine learning system as boxes, sized by how much
code each one actually required. The box labeled "ML code" was a small dark square in the
middle, surrounded by much larger boxes for configuration, data collection, feature
extraction, serving infrastructure, and monitoring. The point of the picture was that the
model, the part everyone talks about, is a rounding error in the engineering.

That gap is where this course lives. You have almost certainly trained a model in a
notebook. You may not have had to answer the question a regulator, a safety reviewer, or a
colleague joining in eighteen months will ask: can you rebuild this exact result, and can
you show me where the numbers came from. Those questions are not satisfied by a better
architecture. They are satisfied by infrastructure.

Engineering data makes the gap wider than it is in the domains where machine learning
methodology is usually taught. A sensor is not a static dataset. It drifts, it needs
recalibration, it samples irregularly, it reports in physical units that must be tracked
or the analysis is nonsense, and its output may end up in a safety case that has to be
defensible years later. A pipeline that quietly loses provenance is not merely untidy in
that setting; it is unusable.

## Learning objectives

By the end of this session you should be able to:

- Map the end-to-end lifecycle of an engineering ML system and identify the standardized
  toolchain used throughout the semester.
- Contrast "a model in a notebook" with "a system," naming the data contracts, drift, and
  monitoring concerns that separate them.
- Explain why engineering data imposes provenance and traceability requirements that
  general-purpose ML tutorials ignore.
- Justify each component of the course toolchain in terms of the failure it prevents.

## The system view

It helps to name the stages explicitly, because each one becomes a later arc of the
course: data acquisition, storage, pipelines, features, training, evaluation, deployment,
and monitoring. Read left to right that looks like a linear process, which is the first
thing to unlearn. Real systems iterate hard between features and evaluation, and the
monitoring stage feeds back into data acquisition when drift shows up in production.

The stages also tell you where the failures cluster, and it is not where students expect.
Very few production incidents are caused by choosing the wrong model class. Most are
caused by a schema that changed upstream without warning, a feature computed one way in
training and another way in serving, or a data source that silently started returning
nulls. These are integration failures, and they are invisible to any methodology that
stops at cross-validation.

Sculley and colleagues gave the general pattern a name: hidden technical debt. Their
specific mechanisms are worth carrying with you. Glue code, the vast connective tissue
that exists only to move data between systems, tends to dominate the codebase. Pipeline
jungles emerge when that glue accretes without anyone redesigning it. Undeclared consumers
are the worst of the three: some downstream team depends on your output, you do not know
they exist, and you break them.

## Why engineering data is different

Physical units and calibration are the first difference. A model that ingests a raw sensor
voltage and a model that ingests a calibrated concentration are not the same model, even
with identical weights, and the difference will not show up in your validation metric. It
shows up when someone recalibrates the instrument.

Drift is the second. In the dataset we use today, a metal-oxide gas sensor array was
deployed on an Italian roadside for just over a year. The sensors degrade measurably over
that period. A model trained on the first three months and validated on a random split of
those same months will look excellent and will be worthless by month eleven. The random
split hid the problem by letting the model see the future.

Provenance and traceability are the third, and they are the reason reproducibility is
treated as an engineering requirement in this course rather than as good hygiene. In a
regulated or safety-relevant setting you may be asked to reconstruct which data, which
code, and which parameters produced a specific number. If the answer involves a notebook
someone ran out of order on a laptop that has since been reimaged, there is no answer.

## The standardized toolchain

We fix one toolchain for the semester so that class time is spent on concepts rather than
on tool selection. Each choice exists to prevent a specific failure.

Python with `uv` handles environments and dependencies, because a lockfile plus a pinned
interpreter is what makes a rebuild deterministic rather than merely likely. PyTorch
covers deep learning from Week 6. MLflow tracks experiments starting in Week 5, on the
principle that one run should equal one reproducible fact. Storage spans PostgreSQL,
DuckDB, and Parquet, introduced in Week 2, with a vector store added when retrieval
arrives in Week 10. Dataframe work uses pandas and Polars from Week 3.

The LLM and agent material in Weeks 9 through 11 is deliberately framework-agnostic and
provider-agnostic. That part of the ecosystem turns over faster than a semester, so the
course teaches the interfaces and the evaluation discipline rather than a specific vendor's
abstractions.

:::{admonition} Common pitfall
:class: warning

The most frequent reproducibility break is not an exotic dependency conflict. It is an
absolute file path, an unpinned random seed, or hidden notebook state from running cells
out of order. Get in the habit of "Restart and Run All" before you trust any notebook
result, including your own.
:::

## In-class demo

We walk a single notebook that ingests the UCI Air Quality data, plots a reference CO
measurement against the corresponding sensor response, and fits a naive train/test split.
It works, and it looks convincing.

Then we run the same notebook on a fresh checkout, where it breaks three times. Your job
is to diagnose each break before I do: one is a missing package version, one is an
unpinned seed producing different numbers, and one is an absolute path that existed only
on my machine. Every one of these is mundane. That is the point.

The runnable version is `demo.ipynb`.

## Summary

A model is a small component inside a system whose bulk is data infrastructure,
evaluation, and operations, and that is where both the engineering effort and the failures
concentrate. Engineering data sharpens the problem by adding units, calibration, drift, and
traceability requirements that general ML tutorials do not address. The toolchain we
standardize on is not arbitrary; each piece answers a specific way that undisciplined work
falls apart. Next session we build the reproducible scaffold for real, from an empty
directory to a tracked, rerunnable experiment.

## Resources

- [Hidden Technical Debt in Machine Learning Systems](https://papers.nips.cc/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html) — Sculley et al., NeurIPS 2015. The source of the framing above. Short, and worth reading in full.
- [Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml) — Zinkevich's field guide. Rules 1 through 15 are the relevant ones now; the later rules will make more sense after Week 5.
- [uv documentation, Getting started](https://docs.astral.sh/uv/getting-started/) — install it before L2, since we build live.
- [UCI Air Quality Data Set](https://archive.ics.uci.edu/dataset/360/air+quality) — dataset description and citation. Skim the sensor drift discussion.
- [The Turing Way, Reproducible Research](https://book.the-turing-way.org/reproducible-research/reproducible-research) — the broader case, if the motivation section left you unconvinced.

## Assignment

A1, the reproducible project scaffold, is released at L2 and due roughly one week later.
It asks you to stand up a `uv`-managed, git-tracked project that pulls an engineering
dataset and converts an exploratory notebook into a runnable module. The full spec and
rubric are in `course/assignments/a01.md`.
