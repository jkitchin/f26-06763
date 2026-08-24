# Final Project — AI-in-Engineering system: build, evaluate, deploy
**Arc:** Capstone · **Weight:** 30% of course grade · **Proposed:** Week 11 · **Presented & due:** Week 14 (L25–L26)

## Overview & goals
Design, build, evaluate, and deploy a complete **AI-in-engineering system** of your own choosing. This is where the back half of the course comes together: an LLM/agentic (or surrogate-integrated) system that solves a real engineering-flavored task, is measured with a **real evaluation harness**, and is **deployed** behind an API. The project is open — you pick the problem — but it must clear the constraints below. You may (and are encouraged to) build on your A9 (RAG), A10 (agent), or Week-7 surrogate work.

Goals:
- Prove you can take an AI system from prototype to a measured, deployed artifact.
- Make and defend engineering trade-offs (accuracy vs. latency vs. cost; automation vs. human-in-the-loop).
- Communicate the system, its evaluation, and its limitations honestly to a technical audience.

## Constraints (required)
Your system **must** integrate all three:
1. **LLM/agentic component** — at least one of: an agent that uses tools, a RAG system, structured-output extraction/reasoning over natural language, or an LLM orchestrating a surrogate/optimizer. (A pure surrogate with no LLM/agent element does not satisfy this; wrap it in an agent, a natural-language interface, or an LLM-driven design loop.)
2. **Real evaluation** — a frozen, versioned eval set and a harness producing defensible metrics (programmatic checks + LLM-as-judge with human validation, or ML metrics with per-slice error bars). Results logged to MLflow. Cherry-picked demos do not count.
3. **Deployment** — the system runs behind a FastAPI + Docker service on the cloud, with reported latency (p50/p95) and cost per request.

**Engineering flavor is strongly encouraged** (process, mechanical, materials, energy, controls, manufacturing, reliability, design). Non-engineering projects are allowed only with instructor sign-off at proposal time and still must satisfy all three constraints.

Also expected: reproducibility (uv, pinned deps, runs from a clean clone), secrets handled properly (no keys in git/images), and at least one explicit **safety guardrail** appropriate to the system (bounds check, allow-list, retrieval grounding, human sign-off, loop limit).

## Example project ideas (concrete, engineering-flavored)
1. **Design-loop agent over a surrogate.** An agent that takes a natural-language design goal ("maximize yield subject to T < 450 K"), queries a **sensor/operating-conditions database**, calls your **Wk7 surrogate** as a tool (served as its own microservice), runs a small optimization loop, and returns a recommended operating point with predicted uncertainty. Evaluate: does it respect constraints, how good are its recommendations vs. a brute-force baseline, tool-call correctness, cost per query. Deploy the agent and the surrogate as two services.
2. **Maintenance/troubleshooting RAG assistant.** A RAG system over **equipment manuals, P&IDs text, and maintenance logs** that answers operator questions and cites the source procedure. Evaluate: retrieval faithfulness, answer quality (LLM-as-judge validated against expert labels), must-cite compliance, refusal on out-of-scope questions. Deploy behind an API with a `/healthz` check and per-request cost reporting.
3. **Spec/datasheet extraction agent.** An agent that ingests component **datasheets or material spec PDFs** and produces validated structured records (schema-checked), flags out-of-range or inconsistent values, and answers comparison queries. Evaluate: extraction accuracy vs. a labeled gold set, schema-validity rate, and hallucination rate on absent fields. Deploy as a batch + query API.
4. **Anomaly-triage agent for sensor streams.** An agent that watches a **time-series sensor feed** (provided), calls a detector/surrogate tool to flag anomalies, retrieves relevant procedures, and drafts a triage recommendation with a required human-sign-off step. Evaluate: detection precision/recall, recommendation quality (judge), and an input-**drift** monitor. Deploy the scoring + triage endpoint.
5. **Simulation/optimization copilot.** An LLM interface that translates a natural-language engineering question into a call to a **physics simulation or optimization** (or your surrogate of one), runs it, and explains the result with caveats about validity range. Evaluate: correctness of the generated call/params against a test suite, plausibility of explanations (judge), and guardrails that block extrapolation outside the valid domain. Deploy behind an API.
6. **Compliance/standards checker.** A RAG + reasoning system over a **standards/code corpus** (e.g., pressure-vessel or electrical-code excerpts, provided) that checks a described design against relevant clauses and cites them. Evaluate: clause-retrieval accuracy, correctness of pass/fail judgments vs. labeled cases, and citation faithfulness. Deploy with a report-generating endpoint.

You are not limited to these — a different engineering problem is welcome if it meets the constraints.

## Building on prior work
- **From A9 (RAG):** extend your corpus, add a proper eval suite (faithfulness + validated judge), and deploy it. The "system" grows from a notebook into a service.
- **From A10 (agent):** add tool-call evaluation, a failure taxonomy, guardrails, and deployment; consider giving it a surrogate or database tool to add engineering depth.
- **From Wk7 (surrogate):** serve it as a microservice and put an **LLM/agent layer** on top (a design-loop agent or a natural-language interface) so it satisfies the LLM/agent constraint, then evaluate the combined system.
- Reusing prior code is expected and encouraged; the grade rewards the *integration, evaluation, and deployment* you add, not novelty of the base model. Cite what you carried over.

## Deliverables
1. **Written proposal (Week 11)** — see the template below. ~1–2 pages. Instructor feedback returned before you build.
2. **Repository** — uv-managed, runs from a clean clone; contains the system code, the versioned eval set, the eval harness, the FastAPI app, the `Dockerfile`, and a `README` with exact setup/run/deploy commands. Reproducibility is graded.
3. **Recorded demo** — 3–5 minutes showing the deployed system working end-to-end (real requests hitting the live/containerized service). Due **before** your Week-14 presentation slot so grading does not depend on a live demo surviving.
4. **Short report (~4–6 pages)** — problem & engineering framing; system architecture (diagram); evaluation (eval set, metrics, results with error bars/agreement, at least one honest failure case); deployment (architecture, latency p50/p95, cost/request); safety/guardrails & responsible-AI considerations; limitations & next steps.
5. **In-class presentation (Week 14, L25–L26)** — 8-minute talk + 3-minute Q&A (see `modules/wk14.md` for format and the required content beats). Peer feedback submitted for others' talks.

## Timeline
- **Week 11 — Proposal due.** Submit the filled proposal template; get scoped and approved (feasibility, that it meets the three constraints, data availability).
- **Week 12 — Build + evaluate + deploy.** Lectures cover exactly what you need (eval harness, observability, FastAPI/Docker/cloud, latency/cost). A11 can be done *as* your project's eval + deployment slice.
- **Week 13 — Finalize & harden.** Have the build substantially complete by the last week of lectures; add an eval gate, and a drift-monitoring or safety element if your system warrants one, drawing on the optional [MLOps and responsible AI](optional/mlops.md) page.
- **Week 14 — Present & submit.** Submit repo + recorded demo + report before your slot; present across L25–L26.

## Rubric (100 pts) — 30% of course grade

| Criterion | Pts | What we look for |
|---|---|---|
| Problem framing & engineering relevance | 12 | A real, well-scoped engineering task; clear why AI is the right tool and what decision it supports |
| System engineering & integration | 20 | LLM/agentic (or surrogate-integrated) system that actually works end-to-end; sensible architecture, tools, data handling; guardrail present |
| Evaluation rigor | 22 | Frozen versioned eval set; valid metrics; error bars / judge–human agreement; honest failure analysis; MLflow logging |
| Deployment | 16 | FastAPI + Docker on cloud; typed schemas + health check; model loaded once; secrets handled; p50/p95 latency + cost/request reported; harness run against the live endpoint |
| Demo & presentation | 15 | Clear talk hitting the required beats; working recorded demo; time discipline; useful Q&A; quality peer reviews given |
| Reproducibility & responsibility | 15 | Runs from clean clone (uv, pinned); README; no secrets in git/images; responsible-AI/safety discussion tied to the system's actual decision and consequence |

Missing a hard constraint (LLM/agent element, real evaluation, or deployment) caps the relevant sections and the overall grade.

## Proposal template (fill in — Week 11, ~1–2 pages)
```
Title:
Team (names) / solo:

1. Problem & engineering context
   - What engineering task/decision does this support? Who is the user?
   - Why is an AI/LLM/agent system appropriate here?

2. System design
   - LLM/agentic (or surrogate-integrated) component(s) and tools/data used
   - Which constraint does the LLM/agent element satisfy? (agent / RAG / structured extraction / LLM-orchestrated surrogate)
   - Architecture sketch (1–2 sentences or a small diagram)
   - Building on prior work? (A9 / A10 / Wk7 / new)

3. Data / system under test
   - Where the data comes from; what your eval set will be and how you'll freeze/version it

4. Evaluation plan
   - Metrics and why they're valid for this system; judge + validation OR ML metrics + slices/CI
   - What "good enough" looks like; a baseline to compare against

5. Deployment plan
   - Service shape (endpoints/schemas); CPU vs. GPU; expected latency/cost sensitivity

6. Safety / guardrails / responsible-AI
   - Key failure mode(s) and the concrete guardrail; any human-in-the-loop step

7. Risks & scope
   - Biggest feasibility risk and fallback; what's in scope vs. out for the Week 12–13 build
```

## Allowed tools & AI-use note
Use the standardized toolchain: Python + uv, PyTorch, MLflow, FastAPI + Docker + course cloud (GPU available where justified). LLM/agent work is framework- and provider-agnostic — pick what fits. AI coding assistants are permitted and expected, but **you own and must be able to explain every part of your system**, especially the evaluation logic, the deployment configuration, and the guardrails. Cite external code, datasets, and any prior-assignment code you reuse. The evaluation section is graded on honesty as much as numbers: report real metrics, real error bars, and at least one real failure case — over-claiming costs more points than a modest, well-measured result.
