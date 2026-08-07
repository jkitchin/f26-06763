---
marp: true
theme: course
paginate: true
header: "06-763 · L6"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L6 · Streaming and data validation

## Week 3 · Data Systems

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Two facts that break a batch pipeline
2. Batch, streaming, and the log
3. Windows, event time, watermarks
4. Validation: checks as a gate
5. Where this pushes back
6. Live demo: a gate that fails loudly

---

<!-- _class: section -->

# Why
## two facts break a batch pipeline

---

## L5 built a batch pipeline

A clean sequence of stages over a **fixed, finished** dataset.

The right picture most of the time.
Two facts about real sensor data sit just outside it.

---

## Fact 1: the data does not stop, or sort itself

A sensor network is an **unbounded** stream.
And the readings arrive jumbled in time.

In the Intel Lab feed, watched as it arrives:
**79.5%** of readings are out of event-time order.

Not corruption. Normal, over a lossy network.

---

## Fact 2: the data is not clean

The same feed carries physically impossible values.

- ~**18%** of temperatures outside 0–50 °C
- ~**26%** from motes below a trustworthy battery voltage

Hundreds of thousands of rows. Nothing announces them.

---

## Two disciplines

**Streaming**: compute over data that never stops
and arrives late, with windows, event time, watermarks.

**Validation**: stop bad data before it enters, with
executable checks that run as a gate and fail loudly.

---

<!-- _class: section -->

# Batch, streaming, and the log

---

## Batch vs streaming

| Batch | Streaming |
|---|---|
| bounded input, has an end | unbounded input, never ends |
| rerun, inspect, reason about | long-lived stateful service |
| start here | adopt when latency demands |

**Micro-batch**: a batch every few seconds. The honest middle.

---

## The log

An **append-only sequence of records**. Kafka's core abstraction.

- a topic is split into **partitions**
- producers append; consumers read forward at their own **offset**
- order is guaranteed **per partition**, not per topic

[Kafka: introduction](https://kafka.apache.org/intro)

---

## A queue is not a log

A classic **message queue** deletes a message once it is consumed.

A **log** keeps it, and lets many readers replay from any offset.

That retention is what makes reprocessing and new consumers cheap.

---

## Push, not pull

The batch instinct is to **poll**: ask the database "anything new?"

A stream **pushes**: each record is handed to the consumer as it lands.

Lower latency, and no query hammering a table that barely changed.

---

## Replay is the superpower

The log keeps records; each consumer keeps its position (**offset**).

Reset the offset and **reprocess history** through new code.

Fix a bug, rerun last week, no separate backfill job to write.

---

## Consumer groups scale the read

Partitions split a topic; a **consumer group** splits the partitions.

- more partitions → more consumers working in parallel
- each partition is read by exactly one member of the group

Throughput scales with partition count.

---

## On devices: MQTT

A "lightweight publish/subscribe messaging transport"
for the Internet of Things.

Small enough for a microcontroller,
built for lossy networks.

[MQTT](https://mqtt.org/)

---

## Delivery semantics

| Guarantee | Meaning |
|---|---|
| at most once | may be lost, never redelivered |
| at least once | never lost, may be redelivered |
| exactly once | processed once and only once |

Kafka is **at-least-once by default**. Exactly-once is opt-in.

[Kafka: semantics](https://kafka.apache.org/documentation/#semantics)

---

## Design for redelivery

Exactly-once is not a cluster switch.

It is an idempotent producer + transactions,
or Kafka Streams `exactly_once_v2`.

**Assume at-least-once. Make your processing tolerate a duplicate.**

---

## Backpressure

When a consumer can't keep up with the producer,
something has to give.

Signal upstream to slow down,
rather than dropping data or blowing up memory.

[Reactive Streams](https://www.reactive-streams.org/)

---

## State is the hard part

A running average, an open window, a dedup set:
a stream carries **state**.

That state must survive restarts and scale across machines.

This is the real reason a stream is heavier than a batch job.

---

<!-- _class: section -->

# Windows, event time, watermarks

---

## If the data never ends, what do you aggregate?

You cannot average an infinite sequence.

A **window** "slices up a dataset into finite chunks
for processing as a group."

[Akidau et al., The Dataflow Model (VLDB 2015)](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf)

---

## Four questions of a stream

Akidau's frame for any streaming computation:

- **What** result? (a sum, an average)
- **Where** in event time? (**windows**)
- **When** do you emit? (**watermarks**, triggers)
- **How** do refinements relate? (**accumulation**)

The rest of this section is those four questions.

---

## Three window shapes

- **Tumbling** (fixed): static size, no overlap
- **Sliding** (hopping): size + shorter step, overlaps
- **Session**: groups activity separated by gaps

Fixed is just the special case of sliding where size = step.

---

![w:1020](figures/windowing.png)

---

## A tumbling window, concretely

```python
(readings
 .set_index("ts")        # event time
 .resample("1h")         # tumbling: fixed, no overlap
 .agg(mean_temp=("temperature", "mean")))
```

One hour in, one row out. The figure's red steps, in four lines.

---

## Which time do you mean?

**Event time**: when the reading actually happened (sensor stamp).
**Processing time**: when your code observed it.

For a live stream they diverge constantly,
because events take a variable time to arrive.

---

## Use event time

A processing-time window mixes events
that happened at wildly different real times.

With **79.5%** of readings arriving out of order,
that window is meaningless.

**Group readings by when they were measured.**

---

## Watermarks

If a reading can arrive late, when is a window done?

A **watermark** is "a lower bound (often heuristically
established) on event times ... processed."

When it passes a window's end, the window closes.

---

## Triggers: when do you emit?

The watermark says a window *may* close.
A **trigger** decides when to actually emit a result.

- at the watermark, once (the "complete" answer)
- early, on a timer (a running estimate)
- late, on each straggler (a correction)

---

## Late data

The watermark is a **guess**. It can be wrong.

A reading that arrives after its window closed is **late**,
and you need a policy: drop it, hold windows open, or
re-emit a corrected result.

[Streaming 102](https://www.oreilly.com/radar/the-world-beyond-batch-streaming-102/)

---

## Accumulation: what a correction means

When a late reading arrives, the re-emitted result either

- **discards** the old value and replaces it, or
- **accumulates** the straggler onto it.

"The hourly mean is 24.1 °C. Correction: 24.3 °C."
Downstream must expect updates, not one final number.

---

<!-- _class: section -->

# Validation: checks as a gate

---

## Write down what you expect

**Validation**: executable checks the data must pass
before the pipeline acts on it. A **gate**.

Every pipeline, batch or streaming, has data entering it
that some upstream process swears is fine.

---

## Three kinds of check

- **Schema**: column exists, is a timestamp, is/ isn't nullable
- **Statistical**: null rate, uniqueness, distribution drift
- **Physical**: temperature in instrument range, time not backwards

The physical checks are where engineering validation earns its keep.

---

## The impossible temperatures, revisited

L3 found readings far outside any instrument range.

They are not random: they come from motes whose **batteries drained**.

A physical range check and a voltage check reject **the same rows**.

---

![w:820](figures/validation.png)

---

## pandera: schema as code

```python
import pandera.pandas as pa

schema = pa.DataFrameSchema({
    "moteid":      pa.Column(int, pa.Check.isin(range(1, 55))),
    "temperature": pa.Column(float, pa.Check.in_range(0, 50), nullable=True),
    "voltage":     pa.Column(float, pa.Check.ge(2.4)),
})
schema.validate(df, lazy=True)   # collect every failure
```

[pandera: checks](https://pandera.readthedocs.io/en/stable/checks.html)

---

## How it fails is the point

- `schema.validate(df)` → raises `SchemaError` on the **first** break
- `lazy=True` → `SchemaErrors` with **every** failing row

Fail fast to stop a pipeline; fail lazy to clean a dirty dump.

[pandera: lazy validation](https://pandera.readthedocs.io/en/stable/lazy_validation.html)

---

## What a failure report looks like

```text
column       check                          failure_case
temperature  in_range(0, 50)                122.15
voltage      greater_than_or_equal_to(2.4)  1.91
```

`lazy=True` hands you this: **which row, which check, which value.**

---

## Great Expectations

Heavier, framework-shaped, team-readable.

- **Expectation** → a verifiable assertion
- **Suite** → a collection of them
- **Checkpoint** → runs a suite in production
- **Data Docs** → human-readable reports

[GX overview](https://docs.greatexpectations.io/docs/core/introduction/gx_overview/)

---

## pandera or Great Expectations?

| pandera | Great Expectations |
|---|---|
| a schema in your code | a framework with a project |
| inline, unit-test feel | suites, checkpoints, Data Docs |
| one script, one dev | a pipeline, a team, an audit trail |

Reach for the lightest tool the job allows.

---

## Statistical checks: catching drift

Beyond "is this value possible", ask: has the **distribution** moved?

- a null rate creeping up
- a sensor's mean sliding month to month

The seam into **monitoring** (L20): the same checks, run forever.

---

## A schema is a contract

Written down, the schema is also **documentation**:
the shape the next person, or the next service, can rely on.

A check that fails loudly is a contract that **enforces itself**.

---

## What should a failure do?

| Policy | Use when |
|---|---|
| **block** | bad data must never reach a model/report |
| **warn** | you monitor it but won't act now |
| **quarantine** | route bad rows aside, let good ones flow |

A check that can only pass is untested decoration.

---

## Prove the gate works

Inject bad data on purpose.
Watch the pipeline halt.

A check that has never failed
has never been tested.

---

<!-- _class: section -->

# Where this pushes back

---

## Streaming is a cost to defer

A batch job is a function you rerun.
A stream is a long-lived stateful service.

Exactly-once is hard, watermarks are heuristics,
late data forces a policy.

**Start batch. Adopt streaming only when latency demands it.**

---

## Event-time windows trust your clocks

Everything rested on the event-time stamp.

A wrong or drifting sensor clock makes
event-time windows group by a **lie**.

The monotonic-timestamp check is what lets you trust them.

---

## Validation proves plausible, not correct

A value that passes every check can still be wrong.

24 °C is plausible whether or not it is what happened.
Validation catches the **impossible**, not the **miscalibrated**.

Same false comfort as a passing test or a reproducible result.

---

## A schema is a brittle burden

- too tight → cries wolf, until the team ignores it
- too loose → passes the data it should catch
- only tests the expectations you **thought to write**

Validation raises the floor; it does not cap the ceiling.

---

<!-- _class: demo -->

# Demo

## `l06-validation.ipynb`

A pandera gate on the sensor data: dtypes, a mote-id set,
temperature range, a voltage floor. Inject corrupt rows,
watch it fail loudly. Then a windowed replay of the stream.

---

## What to watch

With the gate: the pipeline **halts** with a precise complaint.

Without it: the pipeline runs to completion and
produces a **confident, wrong number**.

Loud failure vs silent corruption. That is the whole argument.

---

## Recap

- Real sensor data is **unbounded, out of order, and dirty**
- Streaming: windows in **event time**, closed by **watermarks**
- 79.5% out of order is *why* event time and watermarks exist
- Validation: schema + statistical + **physical** checks, as a **gate**
- pandera for code, Great Expectations for team-readable reports
- Block / warn / quarantine, and prove the gate halts

---

## Next

**Assignment** A3 (from L5): its validation half is now unblocked
**Reading** Akidau, "The Dataflow Model"; pandera docs
**L7** From guarding data to shaping it: features for time-series
and physical data, and the trap of **leakage**

Full notes, with all sources: `lectures/l06/notes.md`
