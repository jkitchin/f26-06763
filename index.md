# Systems and Toolchains for AI Engineers

Course notes for the MS in AI in Engineering. Fourteen weeks of twice-weekly sessions, a
dedicated mini-project week, and a student-chosen capstone.

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
introduces it. When you remember the idea but not which session covered it, start there
rather than with search.

:::{admonition} The whole course as two PDFs
:class: tip

<a href="course.pdf"><strong>Download course.pdf</strong></a>: the syllabus, the schedule,
every set of notes, every demo notebook, the assignments, and the optional material, in one
searchable file with numbered sections, figures, and pages.

<a href="slides.pdf"><strong>Download slides.pdf</strong></a>: every deck of the semester in
session order, one bookmark per session.

Both are rebuilt on every change to this site. Useful for reading offline, for annotating,
and for searching the whole semester at once. The decks are also published as live HTML,
linked from the top of each set of notes.
:::

:::{admonition} Practice modules
:class: tip

<a href="game/"><strong>Open the practice modules</strong></a>, a short set of
questions for each lecture, tied to the numbers and the pitfalls in that
session's notes.

Each one takes about ten minutes, ends by producing a PDF you upload, and counts
toward participation on completion rather than on score. The questions are
selected from your Andrew ID, so yours are not your neighbour's. Everything runs
in your browser and nothing is uploaded from the page itself.

The same app carries <a href="game/#/map"><strong>a map of the course</strong></a>,
which answers a different question: not "what should I practise" but "which
session covered this, and what does it depend on". Every corridor on it is a
place one lecture actually cites another, so it shows the structure of the
course rather than a picture of it. It is not graded, and nothing on it is
locked.
:::

## Toolchain

- **Environments:** Python, managed with `uv`.
- **Deep learning:** PyTorch.
- **Experiment tracking:** MLflow.
- **Data:** PostgreSQL, DuckDB, and Parquet, with a vector store for the LLM work.
- **LLMs and agents:** framework- and provider-agnostic, since that corner of the ecosystem
  turns over faster than a semester.
