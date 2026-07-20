# Course Schedule — Systems & Toolchains for AI in Engineering

14 weeks · 2 sessions/week (28 sessions total): 26 numbered lectures (L1–L26) plus a
dedicated **mini-project week** (Week 8, sessions MP-1/MP-2). Assignment release/due dates
assume a release-then-due-one-week-later cadence; adjust to the academic calendar per
offering.

| Wk     | Session | Topic                                                                                                     | Deliverables                                               |
|--------|---------|-----------------------------------------------------------------------------------------------------------|------------------------------------------------------------|
| **1**  | L1      | AI engineering landscape & the system view; the modern toolchain                                          | **A1 released**                                            |
|        | L2      | Reproducible environments (uv), version control for code/data/models, notebooks→scripts→packages          |                                                            |
| **2**  | L3      | Relational data & PostgreSQL for engineering/time-series data; SQL essentials                             | A1 due · **A2 released**                                   |
|        | L4      | Beyond relational: document/NoSQL, columnar/Parquet, DuckDB; vector-store preview                         |                                                            |
| **3**  | L5      | Dataframes & scalable processing (pandas/Polars); batch pipelines; distributed concepts (Spark/Dask demo) | A2 due · **A3 released**                                   |
|        | L6      | Streaming concepts for sensor data; data validation (pandera/Great Expectations)                          |                                                            |
| **4**  | L7      | Features for time-series/physical data; transforms, scaling, leakage                                      | A3 due · **A4 released**                                   |
|        | L8      | Data quality, versioning, splits; data-centric iteration                                                  |                                                            |
| **5**  | L9      | ML workflow: train/validate/select, cross-validation, metrics, strong baselines                           | A4 due · **A5 released**                                   |
|        | L10     | Experiment tracking (MLflow) + hyperparameter search                                                      |                                                            |
| **6**  | L11     | Deep learning with PyTorch: tensors, autodiff, training loops, GPUs                                       | A5 due · **A6 released**                                   |
|        | L12     | Architectures for engineering data (MLP, CNN for fields/images, sequence models)                          |                                                            |
| **7**  | L13     | Applied engineering ML: surrogate modeling, physics-informed/constrained models, UQ                       | A6 due · **Miniproject launched (A7)**                     |
|        | L14     | Bayesian optimization & active learning for design                                                        |                                                            |
| **8**  | MP-1    | **Mini-project week — build / studio day** (supervised work + clinic)                                     |                                                            |
|        | MP-2    | **Mini-project week — demo day** (walkthroughs + peer feedback)                                           | **Miniproject due (end of week)**                          |
| **9**  | L15     | Foundation models & LLMs at a systems level: architecture, tokenization, embeddings                       | **A8 released**                                            |
|        | L16     | API / prompt / structured-output interface; context, cost, latency; prompting                             |                                                            |
| **10** | L17     | Retrieval-augmented generation & vector databases (chunking, retrieval, grounding, retrieval eval)        | A8 due · **A9 released**                                   |
|        | L18     | Adaptation: prompting vs RAG vs fine-tuning; LoRA/PEFT hands-on                                           |                                                            |
| **11** | L19     | Agent fundamentals: tool use, function calling, planning/execution loops                                  | A9 due · **A10 released** · **Final-project proposal due** |
|        | L20     | Multi-agent orchestration, frameworks, guardrails; agents over engineering tools/data                     |                                                            |
| **12** | L21     | Evaluating ML & LLM/agent systems: eval harnesses, LLM-as-judge, tracing/observability                    | A10 due · **A11 released**                                 |
|        | L22     | Deployment: FastAPI, Docker, cloud serving, latency/cost                                                  |                                                            |
| **13** | L23     | MLOps: CI/CD for ML, drift/regression monitoring, cost; safety, failure modes, responsible AI             | A11 due                                                    |
|        | L24     | Capstone studio: integration, evaluation & deployment clinic (final-project work time)                    |                                                            |
| **14** | L25     | **Final project presentations — Day 1**                                                                   |                                                            |
|        | L26     | **Final project presentations — Day 2 + course wrap**                                                     | **Final project due**                                      |

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
