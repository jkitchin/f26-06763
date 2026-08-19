# Systems and Toolchains for AI Engineers — Course Package

A redesign of CMU's *Systems and Toolchains for AI Engineers* for an **MS in AI in
Engineering** program. 14 weeks · 2 sessions/week (28 sessions: 26 lectures + a dedicated mini-project week) · hands-on, project-based.

## What's here

| File | Purpose |
|---|---|
| `syllabus.md` | Description, objectives, standardized toolchain, assessment, policies |
| `schedule.md` | Full 24-lecture calendar with assignment release/due dates |
| `modules/wk01.md … wk14.md` | Per-module lecture outlines: objectives, topics, live demos, engineering framing, readings (Wk 8 = mini-project week; Wk 14 = final presentations) |
| `assignments/a01.md … a11.md` | One focused assignment per module, with rubrics |
| `miniproject.md` | Integrative surrogate-model miniproject (Wk 7 → Wk 8) |
| `final-project.md` | Open, student-chosen capstone (proposal Wk 10 → present Wk 12) |

## Design at a glance

Three balanced pillars plus a production arc, flavored throughout with engineering data
(sensor/IoT time series, simulation outputs, experimental data, surrogates, design):

- **Data infrastructure & engineering** — Weeks 1–4
- **ML / deep learning / applied engineering ML** — Weeks 5–7
- **Mini-project week** (integrative surrogate-model checkpoint) — Week 8
- **LLM & agentic engineering** (consolidated block) — Weeks 9–11
- **Production & responsibility** — Weeks 12–13
- **Final project presentations** — Week 14

**Standardized toolchain:** Python + **uv**, **PyTorch**, **MLflow**; PostgreSQL/DuckDB/
Parquet + a vector store; LLM/agent work is framework- and provider-agnostic.

**Assessment:** assignments 45% · miniproject 15% · final project 30% · participation &
quizzes 10%. No proctored final exam.

## Using this package

- `[TERM DETAILS]` placeholders in `syllabus.md` are the per-offering logistics to fill in
  (term, room, instructor/TA, office hours, support-resource links, exact dates).
- Datasets are chosen **per module** to fit each topic; each module/assignment names
  specific, publicly available engineering datasets with fallbacks.
- Assignments follow a shared structure (goal → outcomes → dataset → tasks → deliverables
  → 100-pt rubric → AI-use note), so they read consistently across the semester.
