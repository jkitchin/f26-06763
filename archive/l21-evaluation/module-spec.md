# Module spec for the evaluation lecture (archived)

Cut from `course/modules/wk12.md` on 2026-11-04, when L21 became the optional deployment
session and this lecture left the schedule. The week-12 module objectives, assignment and
teaching notes that were specific to evaluation are kept below the lecture block.

## Lecture L21 — Evaluating ML and LLM/agent systems; observability
**Objectives:**
- Build a repeatable eval harness that turns "it seems to work" into a number with a confidence interval.
- Implement an LLM-as-judge grader and validate it against a small human-labeled set.
- Add tracing so every request's inputs, outputs, tool calls, latency, and cost are recorded and queryable.

**Topics:**
- The eval mindset: a **frozen, versioned test set** (data + expected outputs or rubric) checked into the repo; deterministic scoring; results logged to MLflow so runs are comparable across code changes.
- ML metrics recap for engineering: regression (MAE, RMSE, MAPE, parity plots, residuals vs. operating range), classification (precision/recall/F1, confusion matrix, PR curve), and **calibration** (reliability diagram, expected calibration error) — an over-confident surrogate is dangerous in a design loop.
- **Uncertainty and error bars**: bootstrap confidence intervals on your metric; per-slice metrics (e.g., surrogate error in the extrapolation region vs. interpolation region). "One number for the whole test set" hides the failure that matters.
- LLM/agent eval taxonomy:
  - **Reference-based**: exact match, F1, embedding similarity, numeric tolerance for extracted quantities (works when there's a gold answer).
  - **Rubric/programmatic checks**: did the structured output validate against the schema? did the agent call the right tool? is the cited source actually in the retrieved context (faithfulness)? did it stay within a numeric bound?
  - **LLM-as-judge**: a model scores a response against a written rubric. Useful when there's no single gold answer (explanations, summaries, design rationale).
- **LLM-as-judge, done carefully**: write an explicit rubric with a fixed scale; ask for structured output (score + justification); use a strong model as judge; control known biases (position bias in pairwise comparison, length bias, self-preference). **Validate the judge**: label 20–50 examples by hand, measure judge–human agreement (Cohen's kappa / % agreement) before trusting it on hundreds.
- **Agent-specific eval**: task success rate, number of steps/tool calls, tool-call correctness, cost per task, and failure taxonomy (wrong tool, hallucinated argument, infinite loop, gave up).
- **Observability/tracing**: what to capture per request — prompt/inputs, retrieved chunks, tool calls + arguments + results, final output, token counts (in/out), wall-clock latency per step, model + version, and cost. Structured logs (JSON lines) or a tracing tool. Why: you cannot debug or improve a system you cannot see.

**Live demo / in-class activity:** Build a ~60-line eval harness for the Wk10 RAG assistant. (1) Load a versioned `eval_set.jsonl` of {question, reference_answer, must_cite}. (2) Run the RAG pipeline, capture per-question trace (retrieved chunks, tokens, latency). (3) Score with two graders: a programmatic faithfulness check (is the cited passage in the retrieved set?) and an LLM-as-judge for answer quality against the rubric. (4) Log aggregate + per-question results to MLflow, plot score distribution. Then hand-label 10 of the judge's scores live and compute agreement — show where the judge and humans disagree.

**Engineering framing / dataset:** RAG assistant over a corpus of **pump/compressor equipment manuals + maintenance procedures**; eval set is real maintenance questions with reference answers written by "domain experts" (provided). Parallel ML track: the **Wk7 surrogate** (e.g., a heat-exchanger or reaction-yield surrogate) evaluated with parity plots, per-region MAE, and a calibration check on its predictive uncertainty.

**Readings & resources:**
- Chip Huyen, *Designing Machine Learning Systems* (O'Reilly, 2022) — chapters on evaluation and monitoring.
- Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (NeurIPS 2023) — judge biases and agreement with humans.
- Anthropic, "Building effective agents" and Anthropic docs on evaluation / prompt evaluation (developer documentation).
- OpenTelemetry documentation — traces and spans concepts (the vocabulary generalizes to LLM tracing tools).
- MLflow documentation — logging metrics/artifacts and comparing runs; MLflow LLM evaluation utilities.
- Guo et al., "A Survey on LLM-as-a-Judge" (2024) — methods and pitfalls.

## Week-12 module material specific to evaluation

**Module learning objectives** (the evaluation half of the week-12 list):
- Design an **evaluation harness** that scores a system on a fixed, versioned test set and reports metrics you can defend to an engineer or reviewer.
- Distinguish **ML evaluation** (regression/classification metrics, calibration, error bars) from **LLM/agent evaluation** (reference-based, rubric-based, and LLM-as-judge), and know when each is valid.
- Build an **LLM-as-judge** grader with a written rubric, and quantify how much to trust it (agreement with human labels, bias checks).
- Instrument a system with **tracing/observability**: capture inputs, outputs, tool calls, token counts, latency, and cost per request.

**Assignment:** A11, "Eval harness + deployed API", was released with this lecture. It was
dropped with it; the spec is `a11.md` in this folder.

**Teaching notes / common pitfalls:**
- **The judge is not ground truth.** Students over-trust LLM-as-judge. Require the human-agreement check every time; if kappa is low, the metric is noise. Push them to add cheap programmatic checks (schema validation, faithfulness, numeric bounds) alongside the judge.
- **Frozen eval set or it doesn't count.** A test set the model has seen, or one that changes every run, measures nothing. Version it (commit it), keep it separate from any few-shot/prompt examples, and never tune prompts on the final held-out set.
- **Aggregate metrics lie.** Insist on per-slice reporting (extrapolation vs. interpolation region for surrogates; easy vs. hard questions for RAG) and a confidence interval, not a single decimal.
- **Test the thing you shipped.** Running eval only against the local Python function, never the deployed HTTP endpoint, hides serialization, timeout, and concurrency bugs. Point the harness at the URL.
