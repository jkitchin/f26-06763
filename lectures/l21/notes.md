# L21 · Evaluating ML and LLM/agent systems; observability

:::{admonition} At a glance
:class: tip

- **Session** L21, Week 12 · **Arc** Production & responsibility
- **Slides** <a href="../../slides/l21/">Deck for this session</a>
- **Demo** [`l21-eval.ipynb`](l21-eval.ipynb), an eval harness, a judge you validate, a surrogate you audit by slice
- **Assignment** A11 released this session
:::

## Why this matters

In November 2021, Zillow shut down Zillow Offers, the division that used the company's own
home-valuation model to buy houses directly from sellers, renovate them, and resell them at a
profit. The algorithm was the business: it priced every offer, and the company's ability to
make money depended on that price being right often enough, and wrong by a bounded amount when
it was not. It stopped being either. Zillow's own third-quarter earnings call that year
disclosed an inventory write-down in the hundreds of millions of dollars on homes the company
had already bought at prices the model had set, and the company announced it would cut
roughly a quarter of its workforce as it wound the business down. CEO Rich Barton told
investors, in substance, that the algorithm could not forecast future home prices accurately
enough to run a business at that scale, particularly once the pandemic-era housing market
started moving in ways the model's training data had not prepared it for.

Notice what did not fail here. The model was not untested; Zillow had been running Zestimate
and its buying algorithm for years, on enormous amounts of real transaction data, with real
financial stakes from the start. What failed was narrower and more specific to this session's
subject: the gap between "this model scores well against our historical backtest" and "this
model is still scoring well against reality, right now, at the volume we are currently
operating it," was a gap nobody was measuring continuously enough, on the actual slice of the
market, at the actual pace of deployment, to catch before the losses were already large. A
surrogate model that quietly stops matching the world it was trained on is not a hypothetical
in this course. It is the entire second half of L13, and it is what happens when a company
builds the model, ships it, and stops watching.

That is the argument for everything in this session. An evaluation you run once, before
shipping, tells you whether a system was good enough on the day you checked. A frozen,
versioned eval harness you can rerun against every change, and observability that shows you
what a live system is actually doing on every real request, are what would have told Zillow
the ground had shifted while there was still time to do something about it rather than after a
quarter's earnings call did. The tools this session builds, a test set you do not let drift, a
judge you validate before you trust it, and traces you actually keep, are not process for its
own sake. They are the difference between a number you can defend and a number you found out
was wrong from a write-down.

## Learning objectives

By the end of this session you should be able to:

- Build a repeatable eval harness that turns "it seems to work" into a number with a
  confidence interval.
- Implement an LLM-as-judge grader and validate it against a small human-labeled set.
- Add tracing so every request's inputs, outputs, tool calls, latency, and cost are recorded
  and queryable.

## The eval mindset: a frozen, versioned test set

```{index} eval harness, frozen test set, deterministic scoring
```

Everything else in this session rests on one discipline that costs nothing to state and is
constantly violated in practice: the test set has to be **frozen** and **versioned**, or the
number it produces means nothing. Frozen means the questions, the reference answers, and the
scoring rule do not change between one run and the next, ever, without a deliberate, recorded
decision to update them. Versioned means that set lives in the repository, committed alongside
the code, so a run from three months ago and a run from this morning were scored against the
literal same target and are actually comparable. The demo's `EVAL_SET`, four questions with
fixed reference answers and a required citation for each, is small enough to read in ten
seconds and is exactly the kind of artifact this session is arguing for: not because four
questions are enough for a real system, A11 asks for more, but because the *shape*, a checked-
in file scoring never wanders away from, is the point.

The module's own teaching note names the two ways this discipline gets violated in practice,
and both are worth watching for in your own habits. The first is tuning on the test set: if you
adjust a prompt, a chunking parameter, or a model choice because it improved the score on your
eval set, and then keep using that same eval set to report the final number, you have quietly
turned your test set into a validation set, and the number it now reports is optimistic in a
way you cannot easily undo. The second is a test set that silently drifts, because someone
"just fixed a typo" in a reference answer, or added a question, without treating that edit as
the version bump it actually is. **Deterministic scoring**, the same inputs always producing
the same score, and **logging every run to MLflow** so that runs are comparable across code
changes, are the two mechanical habits that make "frozen and versioned" something you can prove
rather than something you promise.

## ML metrics recap, and why one number hides the failure that matters

```{index} parity plot, probability calibration, reliability diagram, per-slice metric, bootstrap confidence interval
```
```{index} pair: metric; F1
```
```{index} pair: metric; expected calibration error
```

For a regression surrogate, the standard vocabulary is short: **MAE** (mean absolute error,
in the same units as the target, easy to explain to a non-specialist), **RMSE** (root mean
squared error, which penalizes large errors more than MAE does), and **MAPE** (mean absolute
percentage error, useful when the target spans orders of magnitude and an absolute error means
different things at different scales). A **parity plot**, predicted value against true value
with a 45-degree reference line, and a plot of **residuals against the operating range**, are
worth more than any single number, because a model can have an excellent MAE overall while
being reliably wrong in one region of its input space, which is exactly the failure a single
scalar cannot show you. For classification, **precision, recall, and F1** decompose "accuracy"
into "how many of the positives did we catch" and "how many of our positive calls were real,"
which matters enormously whenever the classes are imbalanced, and a **PR curve** shows that
trade-off across every possible threshold rather than the one you happened to pick.

**Calibration** deserves its own mention because it answers a different question than accuracy
does entirely: not "is the prediction close," but "when the model says 90% confident, is it
actually right about 90% of the time." A **reliability diagram** plots claimed confidence
against observed accuracy, and **expected calibration error (ECE)** summarizes the gap between
them in one number. This session's demo makes the case for checking this concretely rather
than trusting it: a random forest's tree-to-tree spread is a common, convenient way to produce
a predictive interval, and on real Intel Lab sensor data, checking its stated 95% interval
against what actually happened shows it capturing the true value only about 14% of the time.
That is not a slightly optimistic interval. It is an interval that is not doing the job an
interval exists to do, and nothing about the training process would have told you that; only
checking coverage against held-out truth does. An over-confident surrogate is genuinely
dangerous specifically because a design loop or an optimizer that trusts a stated 95% interval
will take chances the model's real reliability does not support, exactly the Zillow failure
mode at a smaller scale.

**Uncertainty in the metric itself** is the piece a single reported decimal always omits. A
**bootstrap confidence interval**, resampling your test set's residuals with replacement and
recomputing the metric many times, turns "MAE = 2.49" into "MAE = 2.49, 95% CI roughly
[2.47, 2.51] on this test set," which is an honestly different and more defensible claim.
**Per-slice metrics** are the single most important idea in this section, and the demo proves
the point with real numbers rather than an illustration: the same fitted model, evaluated on
sensor readings above L3's 2.4-volt trustworthiness threshold, scores an MAE of 2.49; evaluated
on readings below that threshold, the same model scores 6.11, roughly two and a half times
worse. A report that only ever states the aggregate number, computed across both slices at
once, would land somewhere in between and hide both the fact that a large fraction of the data
is being handled badly and exactly which fraction it is.

:::{admonition} Common pitfall
:class: warning

An aggregate metric is a weighted average over whatever slices happen to be in your test set,
and the weights are usually an accident of how the data was collected, not a statement about
which failures matter. A model that is excellent on 90% of your traffic and useless on the
other 10% can post the same overall MAE as one that is mediocre everywhere, and only a per-
slice breakdown tells you which one you actually built.
:::

## LLM and agent evaluation, three ways

```{index} reference-based scoring, faithfulness check, failure taxonomy
```
```{index} pair: metric; task success rate
```

Once a system's output is free text or a sequence of tool calls rather than a single number,
"is this correct" stops being a comparison you can automate with equality, and the field has
settled on three genuinely different tools for it, each valid in a different situation.

**Reference-based** evaluation compares the system's output against a known-good answer:
exact string match, token-level F1, embedding similarity for paraphrase-tolerant comparison, or
numeric tolerance when the answer is a quantity with an expected value and an acceptable error
band. It is the cheapest and most reliable of the three, and it only works when a single
correct answer genuinely exists to compare against. This session's demo shows exact match's
specific fragility directly: a system answer that is factually correct fails a literal
substring check because the source text says "1.5 times **the vessel's** maximum allowable
working pressure" and the reference string says "1.5 times **the** maximum allowable working
pressure," a difference of exactly one possessive. Exact match is not wrong to use; it is
narrow, and the module lists it alongside embedding similarity and numeric tolerance
specifically because none of the three alone covers every case reference-based checking needs
to handle.

**Rubric and programmatic checks** ask a yes/no or pass/fail question a script can answer
without any model in the loop at all: did the structured output actually validate against its
schema, did the agent call the tool the task required, is the source it cited actually present
in what it retrieved, did a numeric output stay within a physically plausible bound. This
session's demo builds exactly one of these, a **faithfulness check**: is the chunk id a RAG
answer cites among the chunks it actually retrieved. Deployed against a genuinely deceptive
input, a system whose answer text is correct but whose citation has been swapped for a
different chunk, the check catches it immediately and for free, because "is this id a member of
this list" requires no judgment at all, only a lookup. Programmatic checks are the cheapest,
fastest, and most reliable evaluation you can run, and the discipline worth adopting is to push
as much of your evaluation into this category as the task allows before reaching for anything
more expensive.

**LLM-as-judge** is what remains once neither of the first two applies: open-ended text where
no single reference answer exists, explanations, summaries, design rationale, where a second
model scores the response against a written rubric because nothing simpler can. It is the most
expensive and least reliable of the three, in exchange for being the only one that can grade
open-ended output at all, and the next section is entirely about the discipline required to
use it responsibly rather than as a shortcut.

**Agent-specific evaluation** extends this taxonomy with metrics that only make sense once a
system takes more than one step: **task success rate** against a fixed suite with known-good
outcomes, **tool-call correctness** (right tool, right arguments), **steps and cost per task**,
and a **failure taxonomy** that names how an agent failed rather than only that it did, wrong
tool selected, a hallucinated argument, an infinite loop, or the agent simply giving up. L19's
harness already logs everything a failure taxonomy needs, every tool call, every result, every
stop condition; this session's contribution is turning that log into the aggregate numbers a
reviewer can actually act on.

## LLM-as-judge, done carefully

```{index} LLM-as-judge
```
```{index} pair: failure mode; position bias
```
```{index} pair: failure mode; self-preference bias
```

A judge call is a model call, and it inherits every failure mode a model call has, plus a few
specific to the judging setup itself. **Position bias** means a judge comparing two answers
side by side can favor whichever one it saw first, independent of quality. **Length bias**
means judges frequently reward longer answers even when the extra length adds nothing.
**Self-preference** means a model asked to judge output, including its own family's output,
tends to score it more favorably than an independent judge would. None of these make LLM-as-
judge useless; they make it a measurement instrument with known systematic errors, which is a
reason to calibrate it, not a reason to throw it out.

Doing it carefully has a specific, checkable shape. Write an **explicit rubric** with a fixed
scale, precise enough that two different people reading it would score the same answer the
same way, because a vague rubric produces a vague judge. Ask for **structured output**, a score
plus a written justification, not prose you then have to parse, both because it is more
reliable to extract and because writing the justification is frequently what makes the judge's
reasoning inspectable at all. Use a **strong model as judge**, generally stronger than the
model being judged, since a judge has to be at least as capable as the system it is grading to
catch its mistakes. And **control the known biases** directly: randomize answer order in
pairwise comparisons to cancel out position bias, and consider a length-normalized rubric
criterion if longer answers keep winning for the wrong reason.

None of that, however, substitutes for the step this session treats as non-negotiable:
**validate the judge against humans before you trust it on anything you have not personally
checked.** Hand-label twenty to fifty examples yourself, run the judge on the same examples,
and measure agreement, percent agreement at minimum and Cohen's kappa if you want a number that
corrects for the agreement you would expect from chance alone. This session's demo runs exactly
this exercise on eight constructed cases and gets a kappa of about -0.11, agreement no better
than chance, against a judge deliberately built to be naive (a lexical-overlap heuristic, since
this session has no hosted model to call). Every disagreement traces to a specific, nameable
blind spot: the heuristic cannot tell a citation that actually supports the answer from one that
does not, because it never looks at the citation at all, and it cannot tell a right number from
a wrong one sitting inside an otherwise identical sentence, because word overlap does not
distinguish "48 mm" from "36 mm" as sharply as a person instantly does. A real LLM judge, given
the right rubric, would likely close some of these gaps and not others, and the entire point of
running the validation is that you find out which, on your rubric, with your judge, rather than
assuming.

:::{admonition} What a practitioner should take from this
:class: tip

Treat a judge's kappa against human labels the way you would treat a surrogate's calibration
coverage: a number you check, not a property you assume. A judge that fails validation is not
a reason to skip validation next time, it is what validation exists to catch, and the fix is
almost always a sharper rubric or an added programmatic check for the specific dimension the
judge is blind to, not a bigger model.
:::

## Observability and tracing

```{index} observability, tracing, structured logging
```

You cannot debug or improve a system you cannot see, and "see" here means a specific, concrete
list of fields captured on every single request, not a log line when something looks wrong.
For an LLM or agent system: the prompt and inputs, any retrieved context, every tool call with
its arguments and result, the final output, input and output token counts, wall-clock latency
per step (not just end to end, since "where did the time go, retrieval or generation or a tool
call" is usually the actionable question), the model name and version, and the cost. This
session's demo builds the smallest honest version of this, a plain dictionary per request with
the retrieved candidates, the cited chunk, a latency measurement from `time.perf_counter`, and
a word-count stand-in for a token count, structured so it could be written as one JSON line per
request with no changes.

Two format choices dominate practice, and both work. **Structured logs**, JSON lines written
to a file or a log aggregator, are simple, require no new infrastructure, and are trivially
greppable. A dedicated **tracing tool** built around OpenTelemetry's vocabulary of traces and
spans, a trace being one end-to-end request and a span being one step within it, adds
structured querying, latency breakdowns per span, and visualization, at the cost of an
additional system to run. Either choice beats the alternative, which is finding out a system
misbehaved from a user's complaint with no record of what it actually saw or did on that
request.

## Where this pushes back

Every evaluation tool in this session answers a real question and creates a new one worth
naming before you lean on it.

**A frozen eval set is a permanent commitment, and it ages.** The world the test set was
written against changes; a maintenance manual gets revised, a regulation changes, a model's
training cutoff moves past the point where an answer that used to be current no longer is. A
test set frozen in March and still unquestioned in December is not automatically wrong, but
treating "frozen" as "never revisited" trades one failure mode, tuning on the test set, for
another, testing against a target that has quietly stopped being the right one.

**Programmatic checks are only as good as what they check for.** The faithfulness check in
this session's demo catches a citation that points at the wrong chunk. It says nothing about
whether the cited chunk's *content* actually supports the claim attached to it, a real and
different failure mode, nor does it know a chunk is stale relative to a newer document revision.
A programmatic check that passes tells you one specific thing did not go wrong, not that
nothing did.

**LLM-as-judge scores can look precise while being unreliable, and a low kappa can hide behind
a plausible-looking score distribution.** A judge that gives every answer a 3 or a 4 will
produce a tidy, narrow-looking histogram that tells you nothing, and it takes the human-
agreement check, not a glance at the scores, to catch a judge that is not actually discriminating
between good and bad answers.

**Observability that is not looked at is just storage.** Logging every request's trace costs
you nothing if nobody ever queries it, and a genuinely useful tracing setup implies a habit of
actually reviewing traces, especially the ones attached to a low score or a user complaint, not
merely the infrastructure to produce them.

**Evaluation infrastructure itself has a cost that scales with how seriously you take it.**
Hand-labeling fifty examples, maintaining a judge rubric, and reviewing traces are real
engineering time, and the discipline this session argues for is proportionate to the stakes,
Zillow's algorithm was pricing purchases in the hundreds of thousands of dollars each and
deserved every one of these checks; a low-stakes internal tool may reasonably get a lighter
version of the same idea rather than the full treatment.

## In-class demo

We build a roughly sixty-line eval harness for a small RAG assistant in the spirit of L17's
system: a frozen four-question eval set, a retriever over a small constructed corpus, two
programmatic checks (faithfulness and reference match) that catch a deliberately injected
hallucinated citation and a real exact-match brittleness, and an LLM-as-judge stand-in
validated against eight hand-labeled cases, landing at a Cohen's kappa of about -0.11 with
every disagreement traced to a specific, nameable blind spot. In parallel, we evaluate a
regression model on real Intel Lab sensor data the way L3 first introduced it: an MAE of 2.49
on trustworthy, high-voltage readings that becomes 6.11, two and a half times worse, on the
low-voltage readings L3 already flagged as suspect, a bootstrap confidence interval around the
good-slice number, and a calibration check showing a stated 95% interval that actually covers
the truth only about 14% of the time. Both passes log their metrics and artifacts to a local
MLflow store.

The runnable notebook is [`l21-eval.ipynb`](l21-eval.ipynb). It downloads the same Intel Lab
data L3, L4, and L19 use and needs no API key or external service.

## Summary

An evaluation is only as trustworthy as the discipline behind it: a test set that is frozen and
versioned rather than quietly tuned on, metrics reported per slice rather than only in
aggregate because the failure that matters is usually hiding in one slice, and a judge that
earns your trust by agreeing with human labels rather than by sounding authoritative. Zillow's
algorithm did not fail because nobody had ever evaluated it; it failed because the evaluation
that mattered, whether the model's pricing was still matching a market that was actively
moving, was not being run continuously enough, at the right granularity, to catch the drift
before the losses were already booked. Reference-based checks, programmatic checks, and LLM-
as-judge are three different tools for three different situations, in roughly that order of
cost and reliability, and observability, capturing every request's inputs, outputs, tool calls,
latency, and cost, is what turns "the system seemed to get worse" into a traceable, debuggable
claim. None of this is process for its own sake; it is the difference between finding a problem
in a notebook and finding it in a quarterly earnings call. Next session takes a system that has
passed this evaluation and asks the remaining question: how do you actually ship it, behind a
service, in a container, on real infrastructure, without losing any of what this session just
taught you to check.

## Resources

- Chip Huyen, *Designing Machine Learning Systems* (O'Reilly, 2022), chapters on evaluation and
  monitoring. The deepest single treatment of this session's argument, written for exactly this
  course's audience.
- [Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"](https://arxiv.org/abs/2306.05685),
  NeurIPS 2023. The paper behind the position-bias, length-bias, and self-preference vocabulary
  this session names.
- [Guo et al., "A Survey on LLM-as-a-Judge"](https://arxiv.org/abs/2411.15594), 2024. A broader
  map of judge methods and their failure modes than one lecture can cover.
- [OpenTelemetry documentation](https://opentelemetry.io/docs/concepts/signals/traces/). The
  traces-and-spans vocabulary this session's observability section borrows, worth reading even
  if your own logs stay in plain JSON lines.
- [MLflow documentation: Tracking](https://mlflow.org/docs/latest/tracking.html), and MLflow's
  LLM evaluation utilities. Logging metrics and artifacts and comparing runs, the mechanism
  behind "results logged to MLflow so runs are comparable."
- Anthropic, ["Building Effective Agents"](https://www.anthropic.com/research/building-effective-agents),
  and Anthropic's developer documentation on evaluation. Referenced again here specifically for
  its treatment of evaluating agentic systems, not only single calls.
- ["Zillow says it will shut down Zillow Offers, cut 25% of staff"](https://www.cnbc.com/2021/11/02/zillow-shares-plunge-after-earnings-miss-zillow-offers-news.html),
  CNBC, 2 November 2021. Contemporaneous coverage of the earnings call behind this session's
  opening case study.

## Assignment

A11, "Eval harness + deployed API," is released this session. It asks you to build a versioned
evaluation harness, ML metrics or a validated LLM-as-judge, for one of your existing systems
(the Wk7 surrogate, the Wk10 RAG system, or the Wk11 agent), then, in the lighter second half
shared with L22, deploy that system behind a FastAPI and Docker service and run the same
harness against the live endpoint rather than only the local function. The full spec and
rubric are in `course/assignments/a11.md`; this paragraph is a pointer, not the rubric.
