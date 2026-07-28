# Course Schedule — Systems & Toolchains for AI in Engineering

14 weeks · 2 sessions/week (28 sessions total): 26 numbered lectures (L1–L26) plus a
dedicated **mini-project week** (Week 8, sessions MP-1/MP-2). Assignment release/due dates
assume a release-then-due-one-week-later cadence; adjust to the academic calendar per
offering.

| Session                     | Topic                                                                                                     | Deliverables                                               |
|-----------------------------|-----------------------------------------------------------------------------------------------------------|------------------------------------------------------------|
| L1  [2026-08-24 Mon]        | AI engineering landscape & the system view; the modern toolchain                                          | **A1 released**                                            |
| L2  [2026-08-26 Wed]        | Reproducible environments (uv), version control for code/data/models, notebooks→scripts→packages          |                                                            |
| L3  [2026-08-31 Mon]        | Relational data & PostgreSQL for engineering/time-series data; SQL essentials                             | A1 due · **A2 released**                                   |
| L4  [2026-09-02 Wed]        | Beyond relational: document/NoSQL, columnar/Parquet, DuckDB; vector-store preview                         |                                                            |
| [2026-09-07 Mon]            | LABOR DAY                                                                                                 |                                                            |
| L5  [2026-09-09 Wed]        | Dataframes & scalable processing (pandas/Polars); batch pipelines; distributed concepts (Spark/Dask demo) | A2 due · **A3 released**                                   |
| L6  [2026-09-14 Mon]        | Streaming concepts for sensor data; data validation (pandera/Great Expectations)                          |                                                            |
| L7  [2026-09-16 Wed]        | Features for time-series/physical data; transforms, scaling, leakage                                      | A3 due · **A4 released**                                   |
| L8  [2026-09-21 Mon]        | Data quality, versioning, splits; data-centric iteration                                                  |                                                            |
| L9  [2026-09-23 Wed]        | ML workflow: train/validate/select, cross-validation, metrics, strong baselines                           | A4 due · **A5 released**                                   |
| L10 [2026-09-28 Mon]        | Experiment tracking (MLflow) + hyperparameter search                                                      |                                                            |
| L11 [2026-09-30 Wed]        | Deep learning with PyTorch: tensors, autodiff, training loops, GPUs                                       | A5 due · **A6 released**                                   |
| L12 [2026-10-05 Mon]        | Architectures for engineering data (MLP, CNN for fields/images, sequence models)                          |                                                            |
| L13 [2026-10-07 Wed]        | Applied engineering ML: surrogate modeling, physics-informed/constrained models, UQ                       | A6 due · **Miniproject launched (A7)**                     |
| [2026-10-12 Mon]            | FALL BREAK                                                                                                |                                                            |
| [2026-10-14 Wed]            | FALL BREAK                                                                                                |                                                            |
| L14 [2026-10-19 Mon]        | Bayesian optimization & active learning for design                                                        |                                                            |
| MP-1 [2026-10-21 Wed]       | **Mini-project week — build / studio day** (supervised work + clinic)                                     |                                                            |
| MP-2 [2026-10-26 Mon]       | **Mini-project week — demo day** (walkthroughs + peer feedback)                                           | **Miniproject due (end of week)**                          |
| L15  [2026-10-28 Wed]       | Foundation models & LLMs at a systems level: architecture, tokenization, embeddings                       | **A8 released**                                            |
| L16  [2026-11-02 Mon]       | API / prompt / structured-output interface; context, cost, latency; prompting                             |                                                            |
| L17  [2026-11-04 Wed]       | Retrieval-augmented generation & vector databases (chunking, retrieval, grounding, retrieval eval)        | A8 due · **A9 released**                                   |
| L18  [2026-11-09 Mon] AICHE | Adaptation: prompting vs RAG vs fine-tuning; LoRA/PEFT hands-on                                           |                                                            |
| L19  [2026-11-11 Wed] AICHE | Agent fundamentals: tool use, function calling, planning/execution loops                                  | A9 due · **A10 released** · **Final-project proposal due** |
| L20  [2026-11-16 Mon]       | Multi-agent orchestration, frameworks, guardrails; agents over engineering tools/data                     |                                                            |
| L21  [2026-11-18 Wed]       | Evaluating ML & LLM/agent systems: eval harnesses, LLM-as-judge, tracing/observability                    | A10 due · **A11 released**                                 |
| L22   [2026-11-23 Mon]      | Deployment: FastAPI, Docker, cloud serving, latency/cost                                                  |                                                            |
| [2026-11-25 Wed]            | THANKSGIVING                                                                                              |                                                            |
| L23  [2026-11-30 Mon]       | MLOps: CI/CD for ML, drift/regression monitoring, cost; safety, failure modes, responsible AI             | A11 due                                                    |
| L24  [2026-12-02 Wed]       | Capstone studio: integration, evaluation & deployment clinic (final-project work time)                    |                                                            |
| L25                         | **Final project presentations — Day 1**                                                                   |                                                            |
| L26                         | **Final project presentations — Day 2 + course wrap**                                                     | **Final project due**                                      |

## Assessment map

- **A1–A11**: one assignment per teaching module (Weeks 1–13; the Week-8 mini-project week
  and Week-14 presentation week carry no separate weekly assignment). **A7 is the
  miniproject.**
- **Miniproject**: launched Wk 7 (L13) → dedicated **Week 8** (MP-1 build + MP-2 demos) →
  **due end of Week 8**.
- **Final project**: proposal due Wk 11 → build/evaluate/deploy Wks 12–13 → **presented &
  due Week 14** (L25–L26).

## Pillar balance (design check)

- **Data infrastructure & engineering:** Wks 1–4 (~4 wks)
- **ML / DL / applied engineering ML:** Wks 5–7 (~3 wks)
- **Mini-project week (integrative checkpoint):** Wk 8
- **LLM & agentic engineering:** Wks 9–11 (~3 wks)
- **Production & responsibility:** Wks 12–13 (~2 wks)
- **Final presentations:** Wk 14
