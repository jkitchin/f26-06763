# Systems & Toolchains for AI in Engineering

Course notes for the MS in AI in Engineering. Fourteen weeks, two sessions per week:
twenty-six lectures, a dedicated mini-project week, and a student-chosen capstone.

The course is organized around one claim: a model in a notebook is not a system. Most of
the engineering effort in a deployed AI system lives in the data infrastructure around the
model, in the evaluation that tells you whether it works, and in the operational practice
that tells you when it has stopped working. The semester walks that whole path with
engineering data throughout, meaning sensor and IoT time series, simulation output,
experimental measurements, and surrogate models.

## Where to start

Read the [syllabus](course/syllabus.md) for objectives, the standardized toolchain, and
grading. The [schedule](course/schedule.md) maps every session to its topic and to the
assignment released or due that week.

Lecture notes are the narrative record of each session. They are written to be read before
or after class rather than projected during it, so they carry the full argument and the
links to primary sources. The slides used in class are linked from the top of each set of
notes.

Every technology, format, method, failure mode, and case study the course names is
collected in the {ref}`general index <genindex>`, with each term linked to the section that
introduces it. When you remember the idea but not which of the twenty-six sessions covered
it, start there rather than with search.

:::{admonition} The whole course as two PDFs
:class: tip

<a href="course.pdf"><strong>Download course.pdf</strong></a>, rebuilt on every change to
this site.

It contains the syllabus, the schedule, every set of notes, every demo notebook, the
assignments, and the optional material, with a table of contents, numbered sections and
figures, and page numbers. Useful for reading offline, for annotating, and for searching
the whole semester at once.

The slide decks are not in it. They are published separately, as
<a href="slides.pdf"><strong>slides.pdf</strong></a>, every deck in session order with a
bookmark per session, and as the live HTML decks linked from the top of each set of notes.
:::

## Toolchain

Python with `uv` for environments, PyTorch for deep learning, MLflow for experiment
tracking, and PostgreSQL, DuckDB, and Parquet with a vector store for data. The LLM and
agent material is deliberately framework-agnostic and provider-agnostic, since that part
of the ecosystem turns over faster than a semester.
