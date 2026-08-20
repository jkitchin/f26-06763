---
marp: true
theme: course
paginate: true
header: "06-763 / L21"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# Lecture 21: Evaluating ML & LLM/agent systems

## Week 12, Production & responsibility

**Systems and Toolchains for AI Engineers**

---

## Roadmap

1. Why this matters: an algorithm, a housing market, a write-down
2. The eval mindset: a frozen, versioned test set
3. ML metrics, and why one number hides the failure that matters
4. LLM and agent evaluation, three ways
5. LLM-as-judge, done carefully
6. Observability and tracing
7. Live demo: an eval harness, a judge you validate, a surrogate you audit

<!-- 110 min. Budget roughly 10/15/15/15/15/10/30 demo.
     No hosted LLM in the demo -- the "judge" is an explicit, naive heuristic.
     Real Intel Lab data (Lecture 3/Lecture 4) for the ML-eval half; real MLflow logging.
     If running long, cut the observability slides, not the demo. -->

---

<!-- _class: section -->

# Why this matters

---

## Why this matters

Zillow Offers: buy houses using the company's
own valuation model, renovate, resell.

The model didn't just advise the price.
It **set** it.

---

## Why this matters, november 2021

Q3 earnings: an inventory write-down in the
hundreds of millions, on homes bought at the
model's own prices.

~25% of staff cut as the business wound down.

---

## Why this matters, what the CEO said

In substance: the algorithm couldn't forecast
future prices accurately enough, at that scale,
once the market started moving differently.

[CNBC, 2 Nov 2021](https://www.cnbc.com/2021/11/02/zillow-shares-plunge-after-earnings-miss-zillow-offers-news.html)

---

## Why this matters, what did NOT fail

Not an untested model. Years of real
transaction data, real financial stakes.

---

## Why this matters, what actually failed

The gap between "scores well on our historical
backtest" and "still scoring well, right now."

Nobody was measuring that gap continuously
enough to catch it before the losses were booked.

---

## Why this matters, this is Lecture 13's second half, at a company's scale

A surrogate that quietly stops matching the
world it was trained on.

Ships. Nobody keeps watching.

---

## Why this matters, what would have caught it

Not a better model. **A frozen, rerunnable eval
harness** + **observability into what's happening now.**

The difference between finding a problem
in a notebook, and finding it in an earnings call.

---

<!-- _class: section -->

# A frozen, versioned test set

---

## A frozen, versioned test set

<div class="definition">

**Frozen test set**: a fixed, versioned set of cases that does not change between runs, so two scores are comparable.

</div>

**Frozen**: questions, references, scoring rule
don't change without a deliberate, recorded decision.

**Versioned**: committed to the repo, so a run
from 3 months ago is comparable to one from today.

---

## A frozen, versioned test set, two ways this gets violated

**Tuning on the test set**: adjust a prompt because
it improved the eval score, keep reporting that
same score as final. Quietly becomes a validation set.

**Silent drift**: "just fixed a typo" in a reference
answer, not treated as the version bump it is.

---

## A frozen, versioned test set, two mechanical habits

**Deterministic scoring**: same inputs, same score, every time.

**Log every run to MLflow**: so runs are
comparable across code changes, not just "this run."

---

<!-- _class: section -->

# ML metrics and what one number hides

---

## ML metrics and what one number hides

**MAE**: same units as the target, easy to explain
**RMSE**: penalizes large errors more
**MAPE**: useful across orders of magnitude

A parity plot and residuals-vs-operating-range
show more than any one of these alone.

---

## ML metrics and what one number hides, classification: decompose "accuracy"

**Precision / recall / F1**: how many positives
caught, how many positive calls were real.

A **PR curve** shows the trade-off across
every threshold, not just the one you picked.

---

## ML metrics and what one number hides, calibration asks a different question

Not "is the prediction close."

**"When the model says 90% confident,
is it right about 90% of the time?"**

---

## ML metrics and what one number hides, measured, not assumed

Random forest tree-spread as a "95% interval,"
checked against real Intel Lab data:

**Empirical coverage: ~14%.**

---

## ML metrics and what one number hides, a badly miscalibrated interval

Fails the one job an interval has to do.

Training tells you nothing about this.
Only checking coverage against held-out truth does.

---

## ML metrics and what one number hides, uncertainty in the metric itself

"MAE = 2.49" is a point estimate from one split.

**Bootstrap the residuals** → "MAE = 2.49,
95% CI [2.47, 2.51]." A different, defensible claim.

---

## ML metrics and what one number hides, per-slice metrics: what aggregates hide

Same fitted model. Same data source.

| Slice | MAE |
|---|---|
| Good voltage (≥2.4V, Lecture 3's threshold) | 2.49 |
| Low voltage (<2.4V) | 6.11 |

**2.5× worse**, hidden by any aggregate number.

---

## ML metrics and what one number hides, the pitfall

An aggregate metric is a weighted average over
whatever slices happen to be in your test set.

The weights are an accident of data collection,
not a statement about which failures matter.

---

<!-- _class: section -->

# LLM and agent evaluation

---

## LLM and agent evaluation

Exact match, F1, embedding similarity,
numeric tolerance. Cheapest, most reliable.

Only works when a single correct answer
genuinely exists.

---

## LLM and agent evaluation, exact match's specific fragility

Source: "1.5 times **the vessel's** maximum
allowable working pressure"

Reference: "1.5 times **the** maximum..."

One possessive. Exact match fails a **correct** answer.

---

## LLM and agent evaluation, rubric / programmatic checks

Did the output validate against its schema?
Did the agent call the right tool?
Is the cited source actually in what it retrieved?

No model required. Cheapest, fastest, most reliable
of the three that actually apply here.

---

## LLM and agent evaluation, faithfulness, demonstrated

Inject a citation that points at a chunk
**not** in the retrieved set.

The check catches it immediately:
"is this id in this list" needs no judgment at all.

---

## LLM and agent evaluation, LLM-as-judge

For what's left: open-ended text, no single
reference answer. Explanations, summaries, rationale.

Most expensive. Least reliable.
The only one that can grade open-ended output at all.

---

## LLM and agent evaluation, agent-specific evaluation

Task success rate. Tool-call correctness.
Steps and cost per task.

**Failure taxonomy**: wrong tool, hallucinated
argument, infinite loop, gave up.

---

<!-- _class: section -->

# LLM-as-judge, done carefully

---

## LLM-as-judge, done carefully

<div class="definition">

**LLM-as-judge**: using a model to score another model's output against a rubric, which is a measurement instrument with known systematic biases.

</div>

**Position bias**: favors whichever answer it saw first.
**Length bias**: rewards longer, even when it adds nothing.
**Self-preference**: favors its own model family's output.

Not reasons to abandon judging. Reasons to calibrate it.

---

## LLM-as-judge, done carefully, doing it carefully

Write an **explicit rubric**, fixed scale, precise
enough two humans would score the same way.

Ask for **structured output**: score + justification.

Use a **stronger model** as judge than the one being judged.

---

## LLM-as-judge, done carefully, the non-negotiable step

**Validate the judge against humans
before you trust it on anything else.**

Hand-label 20-50 examples. Measure agreement.
Cohen's kappa, not just eyeballing it.

---

## LLM-as-judge, done carefully, measured, not assumed (again)

This session's demo: 8 constructed cases,
a deliberately naive lexical-overlap judge.

**Cohen's kappa: -0.11.**
No better than chance.

---

## LLM-as-judge, done carefully, every disagreement traces to a real blind spot

Can't tell a citation that supports the answer
from one that doesn't: never looks at it.

Can't tell "48 mm" from "36 mm" in an
otherwise-identical sentence: word overlap doesn't care.

---

## LLM-as-judge, done carefully, what a real LLM judge would and wouldn't fix

Would likely close the paraphrase gap.

Whether it closes the citation-blindness gap
depends entirely on whether your **rubric** asked it to check.

---

## LLM-as-judge, done carefully, what a practitioner should take from this

Validation exists to catch a failing kappa
like this one.

Fix: a sharper rubric or an added programmatic check.
Not, by default, a bigger model.

---

<!-- _class: section -->

# Observability and tracing

---

## Observability and tracing

<div class="definition">

**Trace**: the recorded sequence of prompts, tool calls, and results for one request, which turns "it did something odd" into a debuggable incident.

</div>

Not "a log line when something looks wrong."

A specific, concrete list of fields,
captured on **every single request**.

---

## Observability and tracing, what to capture

Prompt/inputs. Retrieved context. Every tool call
+ args + result. Final output.

Token counts (in/out). **Per-step** latency, not
just end-to-end. Model + version. Cost.

---

## Observability and tracing, why per-step latency

"Where did the time go, retrieval, generation,
a tool call?" is usually the actionable question.
End-to-end alone can't answer it.

---

## Observability and tracing, two formats, both work

**Structured logs** (JSON lines): simple, no new
infra, trivially greppable.

**A tracing tool** (OpenTelemetry: traces + spans):
structured queries, latency breakdowns, visualization.

---

<!-- _class: section -->

# Where this pushes back

---

## Where this pushes back

The world it was written against changes.
A manual gets revised. A regulation changes.

"Frozen" ≠ "never revisited." That trades one
failure (tuning on it) for another (testing stale).

---

## Where this pushes back, programmatic checks only check what they check

Faithfulness catches a wrong citation.

It says nothing about whether the cited
content actually *supports* the claim.

---

## Where this pushes back, a judge score can look precise while being noise

A judge that gives everything a 3 or 4 produces
a tidy histogram that tells you nothing.

Only the human-agreement check catches that.

---

## Where this pushes back, traces only help if someone reads them

Logging every trace costs nothing if nobody
queries it.

Useful tracing implies a habit of reviewing,
especially traces attached to a low score or complaint.

---

## Where this pushes back, eval infrastructure has a cost, proportionate to stakes

Zillow's algorithm priced purchases in the
hundreds of thousands each. Deserved every check.

A low-stakes internal tool may reasonably
get a lighter version of the same idea.

---

<!-- _class: demo -->

# Demo

## `l21-eval.ipynb`

An eval harness for a RAG assistant + a judge
you validate + a surrogate you audit by slice.

---

## What to watch

- Faithfulness check catching an injected hallucinated citation
- Exact-match failing a *correct* answer (one possessive)
- Judge vs. human: kappa = -0.11, every disagreement explained
- Real Intel Lab data: MAE 2.49 → 6.11 across the voltage slice
- A "95%" interval that covers the truth ~14% of the time

---

## Recap

- Frozen + versioned, or the number means nothing
- Per-slice metrics find what aggregates hide: 2.5x, measured, not assumed
- Reference-based → programmatic → LLM-as-judge, in that order of cost and reliability
- Validate every judge against human labels before trusting it on anything else
- Observability turns "it seemed to get worse" into a traceable claim

---

## Next

**Assignment 11** released today (lighter; folds into the final project)
**Reading** Huyen, *Designing ML Systems* (eval/monitoring); Zheng et al. 2023

Full notes, with all sources: `lectures/l21/notes.md`
