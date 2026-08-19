# Systems & Toolchains for AI in Engineering

**Program:** MS, AI in Engineering
**Units / Format:** 12 units · 2 sessions/week,  in-person, hands-on
**Prerequisites:** Basic programming skill (Python preferred). No prior ML required; a Week-0/Week-1 Python + numerical-computing refresher is provided.

## Class 

The course will be Mondays and Wednesdays from 3:30pm to 4:50pm in [CIC 1201](https://maps.app.goo.gl/93pZEYznGGC6EynS9). Attendance in person is expected. 

The course is run on [Canvas](https://canvas.cmu.edu/courses/54976).

## Instructors
- John Kitchin (jkitchin@andrew.cmu.edu)
- Victor Alves (vcunhaal@andrew.cmu.edu )

## Teaching assistants
- Tirtha Vinchurkar (tvinchur@andrew.cmu.edu)
- Robert Jimenez (robertoj@andrew.cmu.edu)
- Nicolas Smits (nsmits@andrew.cmu.edu)
- TBD


:::{admonition} The whole course as one PDF
:class: tip

<a href="../course.pdf"><strong>Download course.pdf</strong></a>: this syllabus, the
schedule, every set of lecture notes, every demo notebook, the assignments, and the
optional material, in one searchable document with page numbers. Rebuilt on every change
to the site.
:::

---

## Course Description

Building AI in an engineering setting is far more than choosing a model. It is an
engineering discipline in its own right: acquiring and storing messy sensor, simulation,
and experimental data; building reproducible pipelines; training and rigorously evaluating
models; adapting foundation models and wiring up agents; and deploying and monitoring all
of it in production. This course gives MS students hands-on experience with the **systems
and toolchains** an AI engineer uses, grounded throughout in **engineering problems** —
time-series and IoT sensor data, simulation surrogates, design optimization, and
technical-document reasoning.

The course is balanced across three pillars:

1. **Data infrastructure & engineering** — storage, pipelines, features, validation.
2. **Machine learning & deep learning** — the ML workflow, PyTorch, and applied
   engineering ML (surrogates, physics-informed models, uncertainty, Bayesian
   optimization).
3. **LLM & agentic engineering** — foundation models, retrieval, adaptation, and building
   evaluated, tool-using agents.

A production-and-responsibility arc ties them together: evaluation, deployment, MLOps,
monitoring, and responsible AI for engineering decisions.

## Learning Objectives

By the end of the course, students will be able to:

- Stand up a **reproducible AI project** (environments, versioning of code/data/models,
  experiment tracking) and defend engineering design choices.
- Acquire, store, and process engineering data across relational, columnar, document, and
  vector stores; build **validated data pipelines**.
- Execute the full **ML workflow** — baselines, training, cross-validation, model
  selection, and honest evaluation — and train deep networks in **PyTorch** on
  engineering data.
- Build **applied-engineering ML**: surrogate and physics-informed models with
  **uncertainty quantification**, and use **Bayesian optimization / active learning** for
  design.
- Use **foundation models** effectively (prompting, structured output, embeddings), build
  **RAG** systems.
- Engineer **agents** that use tools, plan, and are guarded and **evaluated**.
- **Deploy, monitor, and operate** AI systems, and reason about safety, cost, and
  responsible use in an engineering context.

## The Toolchain (standardized)

To keep the course coherent, the following are standardized across materials; alternatives
are named where relevant so skills transfer.

- **Language & environments:** Python, managed with **uv** (reproducible, lockfile-based).
- **Deep learning:** **PyTorch, jax**.
- **Experiment tracking:** **MLflow**.
- **Data:** PostgreSQL, DuckDB/Parquet, pandas/Polars; a vector store for the LLM arc.
- **LLM / agentic:** framework- and provider-**agnostic** — students may
  choose their agent framework. Concepts are taught so they transfer across providers.

## Assessment

| Component                            | Weight | 
|--------------------------------------|--------|
| Weekly quizzes                       | 15%     |
| Module assignments                   | 25%    |
| Miniproject                          | 20%    |
| Final project (open, student-chosen) | 40%    |


There is **no proctored final exam**; assessment is project- and portfolio-based.

- **Assignments:** one focused assignment per module, each reinforcing that
  week's tools. Submitted via Canvas. Typically due one week after
  release. Assignments use **per-module datasets** chosen to fit the topic.
- **Miniproject:**  Integrates the data → train →
  evaluate arc into a **surrogate/predictive model on an engineering dataset**, with a
  short report and a code walkthrough.
- **Final project:** **student-chosen**. Must
  integrate back-half topics — an **LLM/agentic system** with real **evaluation and
  deployment**. Deliverables: proposal, build (repo), recorded demo, and in-class
  presentation.
- **Participation & quizzes:** one per week based on lectures and notes. Finish a module and it produces a PDF; upload that. 

  

### Grading scale
| letter | grade |
|--------|-------|
| A      | 95    |
| A-     | 90    |
| B+     | 85    |
| B      | 80    |
| B-     | 75    |
| C      | 60    |


## Policies

- **Late work:** Canvas will apply a 15% penalty per late day; final-project late work is not
  accepted after the presentation date. Plan for compute/queue delays — they are not
  grounds for extension.
- **Collaboration:** discussing concepts and strategies is encouraged; submitted code and
  writing must be your own. Disclose collaborators and sources in your repository.
- **Generative-AI use:** *permitted and encouraged as an engineering tool* — this is a
  course about building with AI. You must (a) **disclose** where and how you used AI
  assistants, (b) **cite** generated code/text in comments or a `CREDITS` file, and (c) be
  able to **explain and defend** everything you submit. Using AI to bypass learning an
  assignment's core skill (e.g., having it write an entire graded pipeline you can't
  explain) is not permitted. When in doubt, disclose.
- **Academic integrity:** governed by program/university policy; violations are reported.
- **Accommodations, wellness, and inclusion:** the course follows university policy;
  students needing accommodations should contact the instructor early.

## Schedule

See [schedule.md](./schedule.md) for the full calendar.

