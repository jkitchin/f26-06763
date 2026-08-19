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
and toolchains** an AI engineer uses, grounded throughout in **engineering problems**:
time-series and IoT sensor data, simulation surrogates, design optimization, and
technical-document reasoning.

The course is balanced across three pillars:

1. **Data infrastructure & engineering:** storage, pipelines, features, validation.
2. **Machine learning & deep learning:** the ML workflow, PyTorch, and applied
   engineering ML (surrogates, physics-informed models, uncertainty, Bayesian
   optimization).
3. **LLM & agentic engineering:** foundation models, retrieval, adaptation, and building
   evaluated, tool-using agents.

A production-and-responsibility arc ties them together: evaluation, deployment, MLOps,
monitoring, and responsible AI for engineering decisions.

## Learning Objectives

By the end of the course, students will be able to:

- Stand up a **reproducible AI project** (environments, versioning of code/data/models,
  experiment tracking) and defend engineering design choices.
- Acquire, store, and process engineering data across relational, columnar, document, and
  vector stores; build **validated data pipelines**.
- Execute the full **ML workflow** (baselines, training, cross-validation, model
  selection, and honest evaluation) and train deep networks in **PyTorch** on
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
- **LLM / agentic:** framework- and provider-**agnostic**. Students may
  choose their agent framework. Concepts are taught so they transfer across providers.

## Assessment

| Component                            | Weight | 
|--------------------------------------|--------|
| Module assignments                   | 25%    |
| Miniproject                          | 20%    |
| Final project (open, student-chosen) | 40%    |
| Participation & quizzes              | 15%    |


There is **no proctored final exam**; assessment is project- and portfolio-based.

- **Assignments:** one focused assignment per module, each reinforcing that
  week's tools. Submitted via Canvas. Typically due one week after
  release. Assignments use **per-module datasets** chosen to fit the topic.
- **Miniproject:**  Integrates the data → train →
  evaluate arc into a **surrogate/predictive model on an engineering dataset**, with a
  short report and a code walkthrough.
- **Final project:** **student-chosen**. Must
  integrate back-half topics: an **LLM/agentic system** with real **evaluation and
  deployment**. Deliverables: proposal, build (repo), recorded demo, and in-class
  presentation.
- **Participation & quizzes:** one short practice module per week, tied to that week's lectures and notes. Completing a module produces a PDF that you upload, and it is scored on completion rather than on your answers.

  

### Grading scale

Grades are absolute; no curve is applied. Each letter is the minimum overall score that earns it.

| Grade | Minimum score |
|-------|---------------|
| A     | 95 |
| A-    | 90 |
| B+    | 85 |
| B     | 80 |
| B-    | 75 |
| C     | 60 |


## Policies

- **Late work:** assignments lose 15 percentage points for each day late, down to a floor
  of 60%, and are accepted up to three days late; after that they are not accepted.
  Final-project work is not accepted after the presentation date. Plan for compute or queue
  delays; they are not grounds for an extension.
- **Regrade requests:** bring a regrade request to the instructors within one week of the
  grade being returned. We will review it with the grader who marked the work. A regrade
  re-examines the whole submission, so a score can move in either direction.
- **Collaboration:** working together is allowed and encouraged on all coursework, the
  assignments, the miniproject, and the final project alike. Disclose your collaborators
  and any outside sources in your repository, and make sure you personally understand and
  can defend everything you submit.
- **Generative-AI use:** *permitted and encouraged as an engineering tool*: this is a
  course about building with AI. You must (a) **disclose** where and how you used AI
  assistants, (b) **cite** generated code/text in comments or a `CREDITS` file, and (c) be
  able to **explain and defend** everything you submit. Using AI to bypass learning an
  assignment's core skill (e.g., having it write an entire graded pipeline you can't
  explain) is not permitted. When in doubt, disclose.
- **Academic integrity:** governed by program/university policy; violations are reported.

## Other Policies and Procedures

**Accommodations for Students with Disabilities:** If you have a disability and have an
accommodations approval from the Disability Resources office, I encourage you to discuss
your accommodations and needs with me as early in the semester as possible. I will work
with you to ensure that the appropriate accommodations are provided. If you suspect that you
may have a disability and would benefit from accommodations but are not yet registered with
the Office of Disability Resources, I encourage you to follow the online procedures for
obtaining accommodations at
<https://www.cmu.edu/disability-resources/students/obtaining-accommodations.html>.

**Statement of Support for Students' Health and Well-Being:** I understand that, at times,
we may be under increased stress and challenges, and I will do my best to be accommodating.
All of us benefit from support during stressful times, and I will do my best to help if you
choose to come to me with any concerns. There are many helpful resources available on
campus, and an important part of the college experience is learning how to ask for help. If
you or anyone you know experiences any academic stress, difficult life events, or feelings
of anxiety or depression, we strongly encourage you to seek support. Counseling and
Psychological Services (CaPS) is here to help: call 412-268-2922 and visit their website at
<http://www.cmu.edu/counseling/>. Consider reaching out to a friend, faculty, or family
member you trust for help getting connected to the support that can help. If you are feeling
desperate, call the Re:solve Crisis Network at 888-796-8226. If the situation is
life-threatening, call the police: on campus, CMU Police at 412-268-2323; off campus, 911.

**Statement of Support for Our Diverse Campus Community:** I am committed to treating every
individual with respect, and I expect Carnegie Mellon University students to do the same. I
personally recognize that we are diverse in many ways, and I believe that this diversity is
reflective of society and brings value to our campus. I agree with the university's
statement that diversity can refer to multiple ways that we identify ourselves, including
but not limited to race, color, national origin, language, sex, disability, age, sexual
orientation, gender identity, religion, creed, ancestry, belief, veteran status, or genetic
information. I am personally committed to ensuring that Carnegie Mellon provides an
inclusive and welcoming environment. If you feel that you have not been treated with respect
in this course, I encourage you to express that, and I hope you will feel comfortable
contacting me directly. If you do not feel comfortable, I would encourage you to reach out
to our Chemical Engineering Department Head, Professor Carl Laird, and request anonymity if
you prefer. I encourage anyone who experiences or observes unfair or hostile treatment on
the basis of identity to speak out for justice and support. Anyone can share these
experiences using the following resources:

- Center for Student Diversity and Inclusion: csdi@andrew.cmu.edu, (412) 268-2150.
- Report-It online anonymous reporting platform: <http://www.reportit.net> (username:
  tartans, password: plaid). All reports will be documented and deliberated to determine if
  there should be any following actions. Regardless of incident type, the university will
  use all shared experiences to transform our campus climate to be more equitable and just.

**Academic Policies:** Students are expected to adhere to the Carnegie Mellon University
policy on academic integrity, published online at
<http://www.cmu.edu/policies/documents/AcademicIntegrity.htm>.

## Schedule

See [schedule.md](./schedule.md) for the full calendar.

