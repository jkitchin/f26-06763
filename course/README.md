# Systems and Toolchains for AI Engineers, course package

CMU's *Systems and Toolchains for AI Engineers*, redesigned for the MS in AI in
Engineering. Fourteen weeks of twice-weekly, hands-on, project-based sessions, with a
dedicated mini-project week.

## What's here

| File | Purpose |
|---|---|
| `syllabus.md` | Description, objectives, standardized toolchain, assessment, policies |
| `schedule.md` | The full session calendar with assignment release and due dates |
| `modules/wk01.md … wk14.md` | Per-module lecture outlines: objectives, topics, live demos, engineering framing, readings (Wk 8 is the mini-project week; Wk 14 is final presentations) |
| `assignments/a01.md … a11.md` | One focused assignment per module, with rubrics |
| `miniproject.md` | Integrative surrogate-model mini-project (Weeks 7–8) |
| `final-project.md` | Open, student-chosen capstone (proposed Week 11, presented Week 14) |

## Design at a glance

Three balanced areas plus a production-and-responsibility thread, grounded throughout in
engineering data (sensor and IoT time series, simulation output, experimental data,
surrogates, design):

- **Data infrastructure and engineering:** Weeks 1–4
- **ML, deep learning, and applied engineering ML:** Weeks 5–7
- **Mini-project week** (integrative surrogate-model checkpoint): Week 8
- **LLM and agentic engineering:** Weeks 9–11
- **Production and responsibility:** Weeks 12–13
- **Final project presentations:** Week 14

**Standardized toolchain:** Python and **uv**, **PyTorch**, **MLflow**; PostgreSQL,
DuckDB, and Parquet with a vector store; the LLM and agent work is framework- and
provider-agnostic.

**Assessment:** module assignments 25%, mini-project 20%, final project 40%, participation
and quizzes 15%. No proctored final exam.

## Using this package

- Datasets are chosen **per module** to fit each topic; each module and assignment names
  specific, publicly available engineering datasets with fallbacks.
- Assignments follow a shared structure (goal, outcomes, dataset, tasks, deliverables, a
  100-point rubric, and an AI-use note), so they read consistently across the semester.
