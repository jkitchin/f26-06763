---
marp: true
theme: course
paginate: true
header: "06-763 · L23"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L23 · MLOps, drift, safety & responsible AI

## Week 13 · Production & responsibility

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why this matters: one sensor, no cross-check, no disclosure
2. CI/CD for ML and LLM systems
3. Detecting drift without waiting for labels
4. Cost in production, tracked over time
5. Failure modes and concrete guardrails
6. Responsible AI for engineering decisions
7. Live demo: an eval gate that fails CI, and drift measured before it costs you

<!-- 110 min. Budget roughly 15/15/20/10/15/15/20 demo.
     No live GitHub Actions run in the demo -- the workflow file is validated
     for correct YAML/logic, not watched turning red in a real CI UI.
     Real Intel Lab data (L3/L4) for the drift half. If running long, cut the
     cost-in-production slides, not the demo. -->

---

<!-- _class: section -->

# Why this matters

---

## Two aircraft, five months apart

Lion Air 610, October 2018: 189 dead.
Ethiopian Airlines 302, March 2019: 157 dead.

Investigators converged on the same
automated system both times.

---

## MCAS

Maneuvering Characteristics Augmentation System.

Pushes the nose down automatically to
compensate for the plane's redesigned engines.

---

## One input, no cross-check

Decided to act based on **one** angle-of-attack
sensor. Two existed on the plane.

No requirement that they agree before it acted.

---

## What investigators found

A faulty sensor fed MCAS an erroneous reading.

Pilots weren't told the system existed.
Not trained to counteract it.

---

## What certification missed

Failure modes not adequately analyzed
before the system reached production.

Disclosure to airlines, pilots, regulators
found insufficient.

[FAA Joint Authorities Technical Review, Oct 2019](https://www.faa.gov/foia/electronic_reading_room/boeing_737_max_faa_review)

---

## The fleet was grounded worldwide

~20 months, while MCAS was redesigned to
compare both sensors and limit its own authority.

---

## Every finding maps to this session

Single unredundant input, no cross-check
→ **guardrail failure.**

Failure modes not analyzed before shipping
→ **responsible-AI / documentation failure.**

---

## And the third mapping

Authority to act repeatedly on a physical
control, no human confirmation required
→ **human-in-the-loop, in its most literal form.**

---

## This isn't about aviation

It's about what happens in *any* system that
automates a consequential decision, when nobody
was required to ask "what if this input is wrong."

---

<!-- _class: section -->

# CI/CD
## for ML and LLM systems

---

## What's different from normal CI

Ordinary CI: does the code still pass its tests?

ML/LLM: the code can be **unchanged** while
behavior degrades. A prompt edit. A rebuilt index.

---

## You test behavior on data, not just code

That needs a pipeline stage ordinary
software CI doesn't have.

---

## The pipeline, in order

1. Lint + unit tests (cheap, fail fast)
2. Build the container
3. Run the eval harness on the **frozen set**
4. **Gate on a metric threshold**
5. Deploy, only on pass

---

## The gate makes this an ML pipeline

Not "report the number and hope someone notices."

**Fail the build.** RAG faithfulness < 0.9?
Surrogate MAE regressed > X%? Red, not yellow.

---

## Nondeterminism: don't pretend it away

Pin every seed. `temperature=0` wherever the
provider allows it, for anything you gate on.

Can't get true determinism? Gate on a
**distribution or tolerance band**, not `==`.

---

<!-- _class: section -->

# Detecting drift
## without waiting for labels

---

## Ground truth arrives late, or never

Did the part actually fail? Was the maintenance
call correct? Could be weeks. Could be never.

Monitor input distributions instead.

---

## Three kinds, one name each

**Data drift**: inputs move outside training distribution.
**Concept drift**: same inputs, the right answer changed.
**Prediction drift**: output distribution shifts, no label needed.

---

## Concept drift is the sneaky one

Inputs look completely familiar.

A catalyst deactivates. A "low" voltage reading
means something different in week 4 than week 1.

---

## PSI and the KS test

**PSI**: how much probability mass moved between
reference bins and a new sample. <0.1 fine, >0.25 alert.

**KS test**: do two samples plausibly come from
the same distribution? A p-value, not a vibe.

---

## Three real comparisons, real Intel Lab data

| Comparison | PSI |
|---|---|
| Random split (no drift) | 0.001 |
| First week vs. last week (real, unforced) | 1.26 to 9.03 |
| Injected sudden shift | 5.35 |

---

## The instructive part

PSI can't tell "battery aging on schedule"
from "something changed overnight."

**Both alert. Both look the same to the metric.**

---

## LLM/agent drift signals

Refusal rate. Tool-error rate. Judge scores,
**tracked over time**, not measured once.

Latency, cost, and output-length creep.

---

## Static threshold vs. rolling baseline

Static: simple, auditable, wrong if the normal
range genuinely varies by season.

Rolling: adapts, but can dilute a sudden shift
into the very baseline it's compared against.

---

## The trade-off you're actually choosing

False alarms → alarm fatigue → people stop
responding to real ones.

Missed drift → silent until it's expensive.

---

## The pitfall

A drift alert says a distribution moved.
It does **not** say the model is now wrong.

First response: which drift type is this
consistent with? Not: panic.

---

<!-- _class: section -->

# Cost in production
## tracked over time

---

## Cost moves. Usually up.

**Prompt/context bloat**: the corpus grows,
the system prompt accumulates "just one more rule."

**Retry storms**: a downstream degrades,
retries multiply cost exactly when stressed.

---

## Runaway agent loops

L19's bounded loop exists for exactly this:
one user request, dozens of billed calls,
if nothing stops it.

---

## None of this shows up in a one-time estimate

Log cost as a time series, same as L21 logged
eval metrics. Budgets and rate limits: the backstop
for when monitoring catches it too late.

---

<!-- _class: section -->

# Failure modes
## and concrete guardrails

---

## "We'll add safety checks" is not an answer

A guardrail not tied to a **named** failure mode
is a sentence that sounds like one.

---

## The table, LLM/RAG side

| Failure | Guardrail |
|---|---|
| Hallucinated citation | Faithfulness check (L21) |
| Confident wrong number | Numeric-tolerance reference check |
| Prompt injection | Retrieved/tool content is untrusted, always |
| Unsafe tool action | Allow-list, read-only default, human approval (L19) |

---

## The table, surrogate/ML side

| Failure | Guardrail |
|---|---|
| Extrapolation | Input-range check before every prediction (L7, L13) |
| Over-confident uncertainty | Calibration checked against held-out truth (L13, L21) |
| Stale model | Drift monitoring tied to a retraining trigger |
| Silent unit error | Named, typed columns; assert units at boundaries |

---

## Most of these rows are already yours

A step budget: L19's. A faithfulness check: L21's.
An input-range check: L7's and L13's.

This session's job: name a mechanism for
**every** failure, in a table, on paper.

---

<!-- _class: section -->

# Responsible AI
## for engineering decisions

---

## What makes engineering AI different

Recommendations feed decisions with physical,
safety, environmental, or economic consequences.

A wrong chat response doesn't carry that weight.

---

## Accountability

Who signs off before a recommendation
becomes an action?

Never "the model." A named person or role.

---

## Transparency and appropriate reliance

Can you explain *why*, to a domain expert
without an ML background?

**Automation bias**: a human "in the loop" who's
stopped meaningfully checking. MCAS's pilots, exactly.

---

## Documentation makes it real

**Model card** (Mitchell et al. 2019): intended use,
limits, validated range, performance **by slice**.

**Datasheet** (Gebru et al.): data provenance and bias.
**System card**: what an agent can and can't do.

---

## Not a compliance checkbox

So the next engineer who inherits the system
can find out what it's safe to trust it with,
without re-deriving that from an incident.

---

## NIST AI RMF: a process, not a one-time list

**Govern** → who's accountable
**Map** → this system's context, who it affects
**Measure** → the evaluation this whole session builds
**Manage** → acting on what measurement finds

---

## The theme most often skipped

**Knowing when not to deploy AI at all.**

Rare, severe, hard-to-detect failure + data that
can't rule it out → simpler method, or a human fully in charge.

---

## What a practitioner should take from this

Write the model/system card before it ships,
not after someone asks.

Name every failure mode in a table.
"Should a human approve this" gets a real answer.

---

<!-- _class: demo -->

# Demo

## `l23-mlops.ipynb`

An eval gate that fails CI. Drift measured
on real data, three ways.

---

## What to watch

- The gate passing on L21's real numbers, failing on two named regressions
- A real GitHub Actions YAML: the build job can't start until the gate job passes
- PSI/KS: no drift, real unforced drift, and an injected shift, read side by side

---

## Recap

- Test behavior on data, not just code: gate the merge on a frozen metric, don't just report it
- Drift monitoring catches a model leaving its training world before a labeled failure ever shows
- A guardrail is a named failure mode plus a named mechanism, not a sentence of good intentions
- Documentation (model cards, system cards) is what lets the next person know what to trust
- Some decisions are a case for a human fully in charge, not a more sophisticated model

---

## Next

**No new assignment**, effort goes to the final project
**L24**: capstone studio/clinic. Wire a CI gate, a drift hook, and your
guardrail table onto your own system before Week 14's presentations

Full notes, with all sources: `lectures/l23/notes.md`
