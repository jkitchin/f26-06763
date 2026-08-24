# Systems and Toolchains for AI Engineers

These are the course notes for Systems and Toolchains for AI Engineers.

Our course is organized around one central idea: 

That most of
the engineering effort in a deployed artificial intelligence (AI) system lives in the data infrastructure around the
model, in the systematic evaluation that tells you whether it works, and in the operational practice
that tells you when it has stopped working. This course goes through this whole path with
engineering data and case studies in mind.

## Where to start

Read the [syllabus](course/syllabus.md) for objectives, the toolchain we will be considering in our course, and
grading. The [schedule](course/schedule.md) maps every session to its topic and to the
assignment released or due the specific week we will be.

The lecture notes are the "textbook" of each session. They are written to be read before
or after class, containing extended information and the
links to primary sources we considered while preparing this material. The slides used in class are linked from the top of each set of notes.

Every technology, format, method, and case study the course uses is
collected in the {ref}`general index <genindex>`, with each term linked to the section that
introduces it. When you remember the idea but not which session covered it, we suggest you start there rather than with search.

:::{admonition} Practice modules
:class: tip

<a href="game/"><strong>Open the practice modules</strong></a>, a short set of
questions for each lecture, tied to the numbers and the pitfalls in that
session's notes.

Each module takes about ten minutes, ends by producing a PDF you upload to Canvas, and these will count toward participation. The questions are
randomly selected from your Andrew ID, so the questions you get are not the same of other students.

The same app we created has <a href="game/#/map"><strong>a "map" of the course</strong></a>,
which answers a different question: not "what should I practice" but instead: "which
session covered this, and what does it depend on?". Every corridor on it is a
place one lecture actually cites another, so it shows the structure of the
course rather than a picture of it. It is not graded, and nothing on it is
locked.
:::

## Toolchain

- **Environments:** Python, managed with `uv`.
- **Deep learning:** PyTorch and/or JAX.
- **Experiment tracking:** MLflow.
- **Data:** PostgreSQL, DuckDB, and Parquet.
- **LLMs and agents:** framework- and provider-agnostic, since this field changes faster than a semester, in your experience.
