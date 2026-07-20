---
marp: true
theme: course
paginate: true
header: "06-763 · L1"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L1 · The system view

## Week 1 · Foundations

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why the model is the small box
2. What makes engineering data different
3. The toolchain we standardize on
4. Demo: three ways a notebook fails

<!-- Timing: 10 / 20 / 15 / 20, leaving 15 for questions.
     Do not rush section 2, it motivates the whole semester. -->

---

## The picture that started this course

Sculley et al., NeurIPS 2015

- "ML code" is a **small box** in the middle
- Everything around it: config, data collection, feature extraction,
  serving, monitoring
- <10% of the code is the model

> The model is the part everyone talks about.
> It is a rounding error in the engineering.

---

## The stages

**data → storage → pipelines → features → training → evaluation → deployment → monitoring**

- Each stage is a later arc of this course
- Reading it as linear is the first thing to unlearn
- Monitoring feeds back into acquisition

---

## Where failures actually cluster

Not in the model class. In the joints:

- Upstream schema changed, nobody told you
- Feature computed one way in training, another in serving
- A source silently starts returning nulls

**Integration failures.** Invisible to cross-validation.

---

## Three names worth carrying

- **Glue code** — connective tissue that only moves data; dominates the codebase
- **Pipeline jungles** — glue accreting without redesign
- **Undeclared consumers** — someone depends on your output, you do not know they exist

---

<!-- _class: section -->

# Engineering data is different

---

## Units and calibration

- Raw sensor voltage ≠ calibrated concentration
- Same weights, different model
- Your validation metric **will not** tell you

Failure shows up when someone recalibrates the instrument.

---

## Drift

UCI Air Quality: metal-oxide sensors, Italian roadside, ~1 year

- Sensors measurably degrade over the deployment
- Train on months 1–3, random-split validate → looks excellent
- Month 11 → worthless

The random split let the model **see the future**.

---

## Provenance

The question you have to be able to answer:

> Which data, which code, which parameters produced this number?

If the answer is "a notebook run out of order on a laptop that has been
reimaged," there is no answer.

This is why reproducibility is a **requirement**, not hygiene.

---

<!-- _class: section -->

# The toolchain

---

## One stack, all semester

| Concern | Tool | Prevents |
|---|---|---|
| Environments | Python + `uv` | non-deterministic rebuilds |
| Deep learning | PyTorch | — (Wk 6) |
| Tracking | MLflow | unattributable results |
| Storage | Postgres / DuckDB / Parquet | ad hoc CSV sprawl |
| Dataframes | pandas / Polars | — (Wk 3) |

---

## Deliberately not standardized

**LLM and agent frameworks** (Wks 9–11)

- That ecosystem turns over faster than a semester
- We teach interfaces and evaluation discipline
- Not a vendor's abstractions

---

<!-- _class: demo -->

# Demo

## `demo.ipynb`

UCI Air Quality → plot → naive split → fresh checkout

**Diagnose each break before I do.**

---

## What broke

1. Missing package version
2. Unpinned seed, different numbers
3. Absolute path that existed only on my machine

Every one of these is mundane. **That is the point.**

---

## Recap

- The model is a small component; the system is the work
- Engineering data adds units, drift, provenance
- Each tool we standardize on answers a specific failure

---

## Next

**Install before L2** `git`, Python 3.11+, `uv`
**Assignment** A1 released next session
**L2** Reproducible environments, notebook → script → package

Notes: `lectures/l01/notes.md`
