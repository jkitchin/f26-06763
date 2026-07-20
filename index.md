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

## Toolchain

Python with `uv` for environments, PyTorch for deep learning, MLflow for experiment
tracking, and PostgreSQL, DuckDB, and Parquet with a vector store for data. The LLM and
agent material is deliberately framework-agnostic and provider-agnostic, since that part
of the ecosystem turns over faster than a semester.
