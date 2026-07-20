# Miniproject (A7) — An Engineering Surrogate Model with Uncertainty Quantification
**Launched:** Week 07 (L13/L14) · **Dedicated week:** Week 08 (MP-1 build/studio + MP-2 demos) · **Due:** end of Week 08 · **Weight: 15% of course grade.**

## Overview
This is the integrative capstone of the data → train → evaluate arc. Working (individually,
or in a pair if the instructor approves a larger scope) you will take a real engineering
dataset all the way from raw data to a **surrogate / predictive model that reports calibrated
uncertainty**, tracked end-to-end in MLflow. A surrogate here means a cheap model that stands
in for an expensive simulation, experiment, or measurement — and because engineers act on
these predictions, an *honest uncertainty estimate is a first-class requirement*, not an
add-on. You will deliver a working repo, a short technical report, and a recorded code
walkthrough. This project pulls together everything from Weeks 1–7: reproducible
environments, validated pipelines, leakage-free splits, model selection, PyTorch, MLflow, and
the Week-7 surrogate/UQ ideas.

## Learning outcomes
- Scope and execute a complete applied-ML project on real engineering data with a defensible
  problem framing and evaluation plan.
- Build a surrogate/predictive model (classical, deep, or hybrid) and quantify **aleatoric vs.
  epistemic uncertainty** with a method you can justify.
- **Calibrate and validate** the uncertainty (coverage / reliability), not just the point
  prediction, and test behavior on **extrapolation**, not just random held-out rows.
- Track the full study in MLflow so any result is reproducible from its logged config, data
  hash, and code version.
- Communicate results honestly in writing and in a live code walkthrough, including where the
  model fails.

## What you build
A predictive **surrogate** for an engineering quantity that:
1. is trained on a real engineering dataset through a validated, versioned data pipeline;
2. beats a **strong baseline** on a leakage-free, appropriately grouped/time-aware split;
3. reports **predictive uncertainty** via at least one principled method (deep ensemble,
   MC-dropout, Gaussian process, mean-variance/heteroscedastic net, quantile regression, or
   conformal prediction);
4. has its uncertainty **calibrated and checked** (reliability diagram + prediction-interval
   coverage probability, or conformal coverage);
5. is **fully tracked in MLflow** and reproducible from the repo.

## Suggested datasets (pick one, or bring your own)
All are real and documented. You may use a dataset from a prior week if you take it
meaningfully further (add UQ, extrapolation testing, a design-space analysis).

- **NASA C-MAPSS Turbofan (FD001–FD004)** — remaining-useful-life prediction from
  multivariate run-to-failure sensor streams. Rich UQ story (confidence in RUL matters for
  maintenance decisions); requires GroupKFold-by-engine. (NASA Prognostics Data Repository.)
- **UCI Superconductivity** — predict critical temperature from 81 compositional/derived
  features (21,263 compounds). A materials-discovery surrogate; natural design-loop framing
  (which composition to try next). (Hamidieh 2018.)
- **UCI Concrete Compressive Strength** or **NASA Airfoil Self-Noise** — compact,
  well-behaved surrogate problems where a full UQ + extrapolation study is very achievable in
  two weeks and where a Gaussian process gives clean epistemic uncertainty.
- **Bring your own:** any real engineering dataset (sensor/IoT time series, simulation
  outputs, experimental/materials data) where a cheap model stands in for an expensive
  quantity. Requires instructor approval by the end of Week 7; record source, version, and
  hash.

## Requirements
- **Data pipeline.** Reproducible ingestion into a clean, **validated** feature table
  (reuse your Wk3 validation and Wk4 versioning). Log a dataset hash. Document units,
  ranges, and structure in a data card.
- **Splits done right.** A locked test set plus an appropriate CV/validation scheme —
  GroupKFold by unit/specimen/batch, or a time-aware split, as the data demands. Reserve an
  **extrapolation hold-out**: a region of the input/design space (not random rows) held out
  entirely, to test out-of-envelope behavior.
- **Baseline.** A strong classical baseline (ridge/GBM/GP or persistence for time series) on
  the same split. Your surrogate must beat it or you must explain why not.
- **Surrogate / DL model.** A neural or advanced surrogate (PyTorch MLP/CNN/sequence model,
  GP, or a physics-constrained variant — e.g., a soft physics penalty, or a
  positivity/monotonicity constraint). Full PINNs are welcome but optional and higher-risk.
- **Uncertainty quantification.** At least one principled UQ method, with a clear statement of
  which part of the uncertainty is aleatoric vs. epistemic.
- **Calibration & evaluation.** Point metrics (RMSE/MAE/R² or classification analogs) **and**
  UQ metrics: reliability diagram, PICP at a stated nominal level (e.g., 90%), and
  NLL/CRPS if applicable. Report interpolation vs. extrapolation performance separately.
- **MLflow tracking.** Every run logs params, metrics, seed, git SHA, dataset hash, and
  artifacts (calibration plots, the fitted model). Results reproducible from logged config.
- **Honest error analysis.** Show and discuss the worst predictions and where the uncertainty
  was miscalibrated. State the model's operating envelope and what you would *not* trust it to
  do.

## Deliverables
1. **Repo** — a `uv` project (`pyproject.toml` + `uv.lock`), `src/` with the pipeline, model,
   UQ, and evaluation code, a runnable entry point, a `README` with exact run instructions,
   and MLflow runs (exported or reproducible locally). Include a `CREDITS` file.
2. **Report (~3–5 pages, PDF or `report.md`)** — problem framing and engineering motivation;
   data card; method (baseline, surrogate, UQ choice with justification); evaluation
   (point + UQ metrics, interpolation vs. extrapolation, calibration plots); honest error
   analysis and stated operating envelope; and a reproducibility statement (how to regenerate
   the headline numbers).
3. **Recorded code walkthrough (~5–8 min)** — screen recording where you walk through the
   repo structure, the training/UQ code, and your MLflow runs, and explain one key design
   decision and one failure mode. This is where you demonstrate you can *defend* the work.

## Timeline
Week 8 is a **dedicated mini-project week** (two class sessions): **MP-1 = build/studio day**
and **MP-2 = demo day** (see `modules/wk08.md`).
- **Wk7 L13 (launch):** project released. Choose dataset; scope problem, baseline, and UQ
  method. Bring-your-own datasets approved by end of Week 7.
- **Wk7 L14 → weekend — Milestone 1 (data + baseline):** validated pipeline, locked split
  (with extrapolation hold-out defined), and a tracked baseline in MLflow. A short status
  post/commit.
- **Wk8 MP-1 (build/studio day):** supervised in-class work + clinic slots; goal is a
  surrogate model with a first UQ estimate and calibration check, all tracked, beating (or
  characterized against) the baseline.
- **Wk8 MP-2 (demo day):** ~5-min code + results walkthrough per student/team, with peer
  feedback (mirrors the demo checklist in `modules/wk08.md`).
- **End of Week 8 — due:** repo + report + recorded walkthrough submitted. In-class or
  office-hour spot-checks on the walkthrough may follow.

## Rubric (100 pts) — 15% of course grade

| Criterion | Pts |
|---|---|
| Problem framing + engineering motivation; sensible scope | 10 |
| Reproducible, validated data pipeline + versioned/hashed data | 10 |
| Correct splits: grouped/time-aware + a real extrapolation hold-out | 10 |
| Strong baseline, fairly compared on the same split | 10 |
| Surrogate/DL (or physics-constrained) model, appropriate and well-trained | 15 |
| Uncertainty quantification: principled method, aleatoric vs. epistemic articulated | 15 |
| Calibration & evaluation: point + UQ metrics; interpolation vs. extrapolation reported | 10 |
| MLflow tracking: complete and reproducible (params/metrics/artifacts/SHA/hash/seed) | 5 |
| Honest error analysis + stated operating envelope | 5 |
| Report clarity + recorded walkthrough (defends design + a failure mode) | 10 |
| **Total** | **100** |

## Allowed tools & AI-use note
Python + `uv`, PyTorch, scikit-learn, MLflow, and any of GPyTorch/BoTorch/Ax, Optuna,
`mapie`/conformal libraries, pandas/Polars, matplotlib. GPU is available via the course cloud
environment. Per the syllabus, generative-AI assistants are permitted and encouraged as
engineering tools, but you must (a) **disclose** where and how you used them in `CREDITS`,
(b) **cite** generated code/text, and (c) be able to **explain and defend everything** — the
recorded walkthrough and any spot-check exist precisely to verify this. Using AI to produce a
UQ pipeline you cannot explain defeats the purpose of the miniproject and will be treated as
a policy violation. When in doubt, disclose.
