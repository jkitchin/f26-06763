# L23 · MLOps: CI/CD for ML, drift and regression monitoring, cost; safety and responsible AI

:::{admonition} At a glance
:class: tip

- **Session** L23, Week 13 · **Arc** Production & responsibility
- **Slides** <a href="../../slides/l23/">Deck for this session</a>
- **Demo** [`l23-mlops.ipynb`](l23-mlops.ipynb), an eval gate that fails CI, and drift measured before it costs you
- **Assignment** none new; effort goes to the final project
:::

## Why this matters

Between October 2018 and March 2019, two Boeing 737 MAX aircraft crashed within five months of
each other: Lion Air Flight 610 into the Java Sea, killing all 189 aboard, and Ethiopian
Airlines Flight 302 shortly after takeoff from Addis Ababa, killing all 157 aboard. Investigators
from Indonesia's KNKT, Ethiopia's Aircraft Accident Investigation Bureau, and later a United
States congressional investigation converged on the same automated system as the proximate
cause: the Maneuvering Characteristics Augmentation System, MCAS, software designed to push the
aircraft's nose down automatically under certain flight conditions to compensate for the
aerodynamic effects of the plane's redesigned, larger engines. MCAS made its decision to
intervene based on a reading from a single angle-of-attack sensor, with no cross-check against
the aircraft's second angle-of-attack sensor and no requirement that both agree before the
system acted. In both accidents, investigators found a faulty sensor fed MCAS an erroneous
reading, and the system repeatedly commanded a nose-down trim the pilots, who had not been
told the system existed and were not trained to counteract it, were unable to override in time.
Congressional and regulatory review afterward found the system's failure modes had not been
adequately analyzed during certification, and that the disclosure to airlines, pilots, and
regulators about what MCAS did and how it could fail had been insufficient. The entire 737 MAX
fleet was grounded worldwide for roughly twenty months while the system was redesigned to
compare both sensors and limit the size and repetition of its automatic input.

Every element of that finding maps onto a topic this session covers under a different name.
A single, unredundant input feeding an automated decision with no cross-check is exactly the
**guardrail failure** this session asks you to name and design against explicitly: input
validation and a domain check would have asked whether one sensor's reading was even
plausible given the other's. A system whose failure modes were not adequately analyzed before
it reached production is a **responsible-AI and documentation** failure: the people who needed
to know what the system could do wrong, pilots and regulators, were not told, which is precisely
what a model card or system card exists to prevent. And a system given authority to act
repeatedly on a physical control surface with no requirement that a human confirm each
intervention is the **human-in-the-loop for high-consequence decisions** guardrail, stated in
its most literal form. MCAS is not a machine-learned model, and this session's subject is
broader than aviation: what happens, in any engineering system that automates a consequential
decision, when nobody was required to ask "what if this one input is wrong" before the system
shipped. Every tool below, a CI gate, a drift alarm, a guardrail table, a documentation
requirement, is a concrete answer to that question.

## Learning objectives

By the end of this session you should be able to:

- Build a CI pipeline that runs tests and an eval gate (fail the build if a key metric drops
  below threshold) and produces a deployable container.
- Design drift and regression monitoring and choose alert thresholds you can justify.
- Identify system-specific failure modes and write concrete guardrails; apply a responsible-AI
  checklist to an engineering decision.

## CI/CD for ML and LLM systems

```{index} continuous integration, metric gate
```

Ordinary software CI answers one question: does the code still do what its tests say it should.
An ML or LLM system needs that question answered too, but it is not sufficient, because the
code can be entirely unchanged while the system's actual behavior degrades, a prompt edit that
seemed harmless, a retrieval index rebuilt from a slightly different corpus, a dependency
upgrade that changes a tokenizer's output by one character. **You are testing behavior on
data, not just code**, and that means the pipeline needs a stage ordinary software CI does not
have.

A pipeline built for this has a specific shape, and the order matters. **Lint and unit tests**
run first, cheaply, so a syntax error or a broken function is caught in seconds rather than
after minutes of eval harness execution. **Build the container** next, so the environment the
eval harness runs in is the same one that would actually ship. **Run the eval harness on the
frozen set** from L21, producing a metrics file. Then, the step that makes this an ML pipeline
rather than a software one: **gate on a metric threshold**, failing the build outright if a key
number has regressed, RAG faithfulness below 0.9, a surrogate's MAE regressed by more than some
tolerance, rather than merely reporting the number and letting a human notice. Only on a pass
does the pipeline **deploy**. This session's demo builds exactly this gate as a plain Python
function, unit-tested against L21's actual measured numbers as a passing case and two
constructed regressions, a dropped-citation prompt change and a quietly worse surrogate, as
failing cases, then wires it into a real, syntax-validated GitHub Actions workflow where the
container-build job's `needs: eval` line means the deployable artifact simply never gets built
if the gate step exited non-zero.

**Nondeterminism** is the wrinkle software CI never has to think about and ML CI cannot avoid.
An LLM call can return a different response to the identical prompt from one run to the next.
The fix is not to pretend this away; it is to design the gate around it. Pin every seed that
affects a result. Set `temperature=0` wherever the provider allows it, for tool selection and
for anything you intend to gate on. And where true determinism is not achievable at all, gate
on a **distribution or a tolerance band** rather than an exact match, a metric averaged over a
handful of repeated runs against a confidence interval, in the same spirit as L21's bootstrap
CI, rather than a single number compared with `==`.

## Detecting drift without waiting for labels

```{index} drift, Kolmogorov-Smirnov test, rolling baseline
```
```{index} single: drift; data drift
```
```{index} single: drift; concept drift
```
```{index} single: drift; prediction drift
```
```{index} pair: metric; population stability index
```

A model's accuracy can degrade in production long before you have any labels to measure it
against, because ground truth for an engineering prediction, whether a part actually failed,
whether the maintenance recommendation was correct, often arrives weeks or months later, if it
arrives in a form you can use at all. Monitoring input distributions rather than only output
correctness closes that gap. It comes in three flavors, worth distinguishing by name because
each points at a different root cause.

**Data drift** (also called covariate drift) is a change in the distribution of the inputs
themselves: a compressor gets retrofitted and now runs at pressures the training data never
saw, a new sensor with a different calibration curve gets installed. **Concept drift** is
subtler and arguably more dangerous, because the inputs can look completely familiar while the
relationship between input and correct output has quietly changed: a catalyst deactivates over
months, so the same feed conditions that used to yield a given output now yield a different
one, and a model trained before the deactivation is now wrong even on data it would have
handled correctly a year earlier. **Prediction drift** watches the model's own output
distribution shift over time, without needing any label at all, a useful proxy precisely
because it needs nothing you do not already have.

**PSI**, the Population Stability Index, and the **Kolmogorov-Smirnov test** are the two
standard tools for detecting data and prediction drift quantitatively. PSI bins a reference
distribution and measures how much probability mass has moved between those same bins in a new
sample, with a widely used rule of thumb reading a PSI under 0.1 as no meaningful shift, 0.1 to
0.25 as worth watching, and above 0.25 as a real shift demanding attention. The KS test compares
two samples' empirical cumulative distributions directly and returns a p-value for the
hypothesis that they came from the same distribution. This session's demo runs both against
real Intel Lab sensor data with three genuinely different comparisons rather than a single
illustration. A random split of one mote's own readings, which should show nothing, returns a
PSI near 0.001 on both temperature and voltage, confirming the metric is not simply noisy. The
mote's first week of deployment compared against its last week, no injection, just what the
sensor actually did over a month, returns a PSI of 1.26 on temperature and 9.03 on voltage,
both a clear alert, because a battery genuinely discharges over a deployment and a lab's
ambient temperature genuinely drifts over a season. A synthetic sudden shift, standing in for
the module's retrofitted-compressor scenario, alerts just as clearly. The instructive result is
that PSI cannot tell these last two apart on its own; both are real, both cross the same
threshold, and telling "the battery is aging on schedule" from "something changed overnight"
requires a human looking at the shape of the change over time, not a single number.

For LLM and agent systems, the equivalent signals to watch are less about a feature's numeric
distribution and more about behavioral proxies: **refusal rate** (is the model suddenly
declining to answer questions it used to answer, often a sign the underlying model was updated
by the provider), **tool-error rate**, **judge scores tracked over time** rather than measured
once, **latency and cost**, and **output-length creep**, a model's answers gradually getting
longer for the same class of question, which is frequently the first visible symptom of prompt
or context bloat before it becomes a cost problem.

Choosing a threshold is itself a decision with a real trade-off, specific to the system it
monitors rather than a default copied from a tutorial. A **static threshold** is simple and auditable but can be wrong for a system whose
normal operating range genuinely varies by season or by shift. A **rolling baseline**, comparing
this week against a trailing window rather than a fixed reference, adapts to genuine seasonal
change but can be slower to catch a sudden shift, since a rolling baseline that includes the
shift itself dilutes the comparison. Every choice here trades **false alarms**, which erode
trust in the monitor until people start ignoring it, against **missed drift**, which is
silent until it is expensive, and the right balance depends on which failure costs your system
more.

:::{admonition} Common pitfall
:class: warning

A drift alert tells you a distribution moved. It does not tell you whether that movement makes
the model wrong, and treating every alert as an incident invites exactly the alarm fatigue that
makes people stop responding to real ones. The first response to an alert should be to ask
which of the three drift types it is consistent with.
:::

## Cost in production, tracked over time

```{index} rate limit
```
```{index} pair: failure mode; retry storm
```
```{index} pair: failure mode; runaway agent loop
```

Cost per request moves after launch, usually upward, for reasons that are individually small
and cumulatively expensive. **Prompt and
context bloat**, a RAG system's retrieved context growing as the corpus grows, or a system
prompt accumulating one more instruction every time someone fixes an edge case, quietly raises
the token count on every single call. **Retry storms**, a downstream service degrading and a
client retrying aggressively, can multiply cost by the retry count exactly when the system is
already under stress. **Runaway agent loops**, the failure L19's bounded loop exists to prevent,
turn a single user request into dozens of billed model calls if nothing stops them. A one-time
cost estimate misses all three; only cost logged as a time series, the same way L21 logged eval
metrics, catches them. **Budgets and rate limits**,
a hard cap on spend per hour or per user, are the blunt but reliable backstop for the case where
monitoring catches the trend too late to matter.

## Failure modes and concrete guardrails

```{index} guardrail
```

A guardrail tied to no specific, named failure mode is a sentence that sounds like one.
The module's own teaching note is blunt about this: "we'll add
safety checks" is not an answer, and the discipline this session asks for is a table, one row
per failure mode, naming the mechanism that catches it.

| System | Failure mode | Concrete guardrail |
|---|---|---|
| LLM / RAG | Hallucinated fact or citation | Retrieval grounding with an explicit "answer only from context" instruction (L17); a faithfulness check verifying the cited chunk is in the retrieved set (L21) |
| LLM / RAG | Confident wrong number | Numeric-tolerance reference check against a known value where one exists; flag, don't silently accept, an unsourced quantity |
| LLM / agent | Prompt injection via retrieved or tool content | Treat all retrieved documents and tool outputs as untrusted input; never let instructions embedded in them change the system prompt's authority |
| Agent | Unsafe tool action (writes, actuation) | Tool allow-lists, read-only credentials by default (L19), a dry-run mode, human-in-the-loop approval before any consequential call executes |
| Agent | Infinite or repeating loop | Step budget, cost cap, and repeated-identical-call detection (L19) |
| LLM / agent | Silent schema drift | Output validation against a versioned schema; fail loudly, not by silently coercing a malformed response |
| Surrogate / ML | Extrapolation beyond the training domain | An explicit input-range check before every prediction, refuse or flag rather than silently extrapolate (L7, L13) |
| Surrogate / ML | Over-confident uncertainty | Calibration checked against held-out truth, not assumed from the model's own reported interval (L13, L21) |
| Surrogate / ML | Stale model | Drift monitoring on the input distribution, tied to a retraining or revalidation trigger, not a calendar guess |
| Surrogate / ML | Silent input-unit error | Named, typed feature columns; a units assertion at every system boundary (L7's Mars Climate Orbiter case) |

Notice that most of these guardrails are things this course has already built: a step budget
is L19's, a faithfulness check is L21's, an input-range check is L7's and L13's. This session's
contribution is the discipline of a table that forces you to name a mechanism for every failure
you can think of, rather than a paragraph of good intentions, and the module's suggested
exercise, filling this table for your own system and marking which rows require a human
sign-off before the guarded action proceeds, is worth doing on paper before your final project.

## Responsible AI for engineering decisions

```{index} model card, system card, datasheet, NIST AI Risk Management Framework
```
```{index} pair: failure mode; automation bias
```

Engineering AI's recommendations frequently feed decisions with physical, safety, environmental,
or economic consequences that a wrong chat response does not carry. A maintenance
agent that recommends deferring a repair, a surrogate that clears a design point as safe, a
classifier that flags a part as passing inspection, each of these outputs can become an action
in the physical world, and the responsible-AI themes below are the questions worth answering
before that happens rather than after.

**Accountability** asks who signs off on the AI's recommendation before it becomes an action,
and the honest answer is never "the model." A named person or role has to own the decision to
act on a recommendation, which means the system has to make clear, at the point of use, that a
recommendation is a recommendation and not a decision already made. **Transparency** asks
whether you can explain *why* the system recommended what it did, in terms a domain expert
without an ML background can evaluate. **Appropriate reliance**, often
discussed under the name **automation bias**, is the failure mode where a human notionally in
the loop stops meaningfully checking the system's output because it has been right often enough
that checking starts to feel like wasted effort, the exact posture pilots were put in by MCAS
when they were not even told the system existed to check.

**Documentation** turns these good intentions into an artifact someone can actually read before
relying on the system. A **model card**, following Mitchell and colleagues' 2019 proposal, states
a model's intended use, its known limitations, the population and range it was validated on, and
its performance broken down by the same kind of slice L21 argued for, alongside the aggregate
number. A **datasheet for a dataset**, per Gebru and colleagues, documents provenance, collection
method, and known biases in the data a model was trained on. For an agent, the equivalent is a
**system card**: what tools it can call, what it cannot do, and what guardrails are in place.
These documents exist so the next engineer who inherits the system, quite possibly not you, can
find out what it is safe to trust it with, without re-deriving that knowledge from scratch or,
worse, from an incident.

The **NIST AI Risk Management Framework** (AI RMF 1.0, 2023) organizes this into a repeatable
process rather than a one-time checklist: govern (who is accountable and how is that structured),
map (what is this system's context and who does it affect), measure (the evaluation and
monitoring this whole session builds), and manage (acting on what measurement finds). It is
worth knowing this framework exists and roughly what its four functions cover, both because it
is becoming a reference point regulators and customers ask about and because its structure is a
reasonable checklist for a system with no formal framework requirement at all.

The most often skipped responsible-AI question is **knowing when not to deploy AI at all**.
A recommendation system for a decision where the cost of a rare, hard-to-detect wrong answer
is severe, and where the validation data available cannot credibly rule out that failure mode,
is a case for a simpler, more auditable method, or for keeping a human fully in charge. That judgment is itself an
engineering decision, and making it explicitly, in writing, before deployment is a better
outcome than discovering the answer was "no" after the fact.

:::{admonition} What a practitioner should take from this
:class: tip

Write the model card or system card before the system goes into anyone else's hands. Name, in
a table, the specific failure modes your system can produce and the specific mechanism that
catches each one. And treat "should a human have to approve this" as a question with a real,
sometimes uncomfortable answer.
:::

## In-class demo

We build a CI eval gate as a small, unit-tested Python function, verify it passes on L21's real
measured metrics and fails, for a named reason, on two constructed regressions, then validate a
real GitHub Actions workflow file whose container-build job cannot start until the gate's job
succeeds. In parallel, we measure drift on real Intel Lab sensor data three ways: a random
split showing no drift at all, a mote's own first week against its last week showing real,
unforced drift from battery discharge and seasonal temperature change, and a synthetic sudden
shift standing in for a retrofitted compressor, all scored with PSI and the Kolmogorov-Smirnov
test against the same alert thresholds a production monitor would use.

The runnable notebook is [`l23-mlops.ipynb`](l23-mlops.ipynb). It downloads the same Intel Lab
data L3, L4, L19, and L21 use and needs no API key or live CI run to verify.

## Summary

MCAS acted on a single unverified input, its failure modes were not fully analyzed before it
shipped, and the people who needed to know what it could do wrong were not told. This session's
tools are concrete, checkable answers to each part of that failure. A CI pipeline that gates a
merge on a frozen eval metric turns "we tested it once" into "it is tested on every change,"
and refuses to build the very artifact that would have shipped a regression. Drift monitoring,
PSI and the KS test on input distributions, catches a model quietly leaving the world it was
trained on before a labeled failure ever surfaces; this session's own measurements show that
real, unforced sensor drift and an injected sudden shift can look identical to the alert, so a
human still has to interpret what an alert means. A named failure mode with a concrete guardrail
beats a paragraph of good intentions, and documentation, a model card, a system card, a
NIST AI RMF-style process, lets the next person who relies on your system know what it is safe
to trust it with. None of this replaces judgment about whether a system belongs in a
physical or safety-critical decision loop at all; it makes that judgment possible to make
honestly, on evidence, before an incident forces the question. The next session is a
studio, no new content, dedicated to wiring exactly this, an eval gate, a drift hook, a
guardrail table, onto your own final project before Week 14's presentations.

## Resources

- [NIST AI Risk Management Framework (AI RMF 1.0)](https://www.nist.gov/itl/ai-risk-management-framework),
  2023. The govern/map/measure/manage structure this session's responsible-AI section is built
  around.
- [Mitchell et al., "Model Cards for Model Reporting"](https://arxiv.org/abs/1810.03993),
  FAT* 2019. The paper defining the model-card format named in this session.
- [Gebru et al., "Datasheets for Datasets"](https://arxiv.org/abs/1803.09010), 2021. The dataset-
  side counterpart to a model card; already cited in L2's conventions, worth rereading here.
- Chip Huyen, *Designing Machine Learning Systems* (O'Reilly, 2022), the chapters on data
  distribution shifts, monitoring, and continual learning. The deepest single treatment of this
  session's drift material.
- [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/).
  Prompt injection and LLM-application risk, referenced again here specifically for the
  guardrail table's agent row.
- [GitHub Actions documentation: Workflow syntax](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions).
  The concrete syntax behind this session's example eval-gate workflow.
- [Sculley et al., "Hidden Technical Debt in Machine Learning Systems"](https://papers.nips.cc/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html),
  NeurIPS 2015. First cited in L1 for the "the model is a small fraction of the system" argument;
  worth rereading here for the monitoring and configuration-debt sections specifically.
- [Federal Aviation Administration, "Joint Authorities Technical Review: Boeing 737 MAX Flight
  Control System"](https://www.faa.gov/foia/electronic_reading_room/boeing_737_max_faa_review),
  October 2019. One of the primary investigative sources behind this session's opening case
  study; read alongside the National Transportation Safety Board's public docket for the fuller
  account.

## Assignment

No new assignment this week. Effort goes to the **final project**: wire a CI eval gate, a
drift or observability hook, and a system-specific failure-mode-to-guardrail table onto your
own system, ready for the L24 studio to help you close whichever gap remains before Week 14's
presentations. A11 from Week 12 may be folded directly into the project rather than treated as
separate work. Full spec: `course/final-project.md`.
