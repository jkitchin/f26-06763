---
marp: true
theme: course
paginate: true
header: "06-763 / L6"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# Lecture 6: Streaming and data validation

## Week 3, Data Systems

**Systems and Toolchains for AI Engineers**

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

# Two facts that break a batch pipeline

---

## Two facts that break a batch pipeline

Lecture 5 built a batch pipeline: a clean sequence of stages over a **fixed, finished** dataset.

The right picture most of the time.

Two facts about real sensor data sit just outside it.

---

## Two facts that break a batch pipeline, unbounded and out of order

<div class="definition">

**Unbounded stream**: a feed with no last row, only the row that has not arrived yet.

</div>

Readings also arrive jumbled in time. In the Intel Lab feed, watched as it lands:

- **79.5%** of readings are out of event-time order
- normal behavior over a lossy network, not corruption

[Intel Lab Data](https://db.csail.mit.edu/labdata/labdata.html), 2.3 M readings, 54 motes

---

## Two facts that break a batch pipeline, dirty data

The same feed carries physically impossible values.

- ~**18%** of temperatures outside 0 to 50 °C
- ~**26%** from motes below a trustworthy battery voltage
- **96%** of the impossible temperatures come from a mote already under 2.4 V

Hundreds of thousands of rows. Nothing announces them, and the two checks are
mostly finding one failure.

---

## Two facts that break a batch pipeline, two disciplines

<div class="definition">

**Streaming**: compute over data that never stops and arrives late, with windows, event time, and watermarks.

</div>

- **Data validation**: stop bad data before it enters, with executable checks that run as a gate and fail loudly.

---

<!-- _class: section -->

# Batch, streaming, and the log

---

## Batch, streaming, and the log

| Batch | Streaming |
|---|---|
| bounded input, has an end | unbounded input, never ends |
| rerun, inspect, reason about | long-lived stateful service |
| start here | adopt when latency demands |

- **Micro-batch**: run a batch job every few seconds over whatever has accumulated.

---

## Batch, streaming, and the log, the log

<div class="definition">

**Log**: an append-only sequence of records, the abstraction Kafka is built around.

</div>

- a topic is split into **partitions**
- producers append; consumers read forward at their own **offset**
- order is guaranteed **per partition**, not per topic

[Kafka: introduction](https://kafka.apache.org/intro)

---

## Batch, streaming, and the log, why a log

- a queue deletes a message once consumed; a log keeps it and lets many readers replay from any **offset**
- push, not poll: each record is handed to the consumer as it lands
- reset the offset to reprocess history through new code, no separate backfill
- a **consumer group** splits the partitions; throughput scales with partition count

---

## Batch, streaming, and the log, delivery semantics

| Guarantee | Meaning |
|---|---|
| at most once | may be lost, never redelivered |
| at least once | never lost, may be redelivered |
| exactly once | processed once and only once |

Kafka is **at-least-once by default**. Exactly-once is opt-in: an idempotent producer plus transactions, or Kafka Streams `exactly_once_v2`. Assume at-least-once and tolerate a duplicate.

[Kafka: semantics](https://kafka.apache.org/documentation/#semantics)

---

## Batch, streaming, and the log, a question

<div class="clicker" data-tag="l06-at-least-once" data-seconds="45" data-answer="B" data-hint="At-least-once is a promise the broker makes about delivery, not a promise about your code. Work out what it does when the offset was never committed." data-why="B. The offset was never committed, so on restart the broker replays from the last one it has and that reading is added a second time. Nothing in Kafka knows about your total, so nothing corrects it. A is at-most-once, the opposite trade: commit the offset first and a crash loses the reading instead. This is the reason the fix is an idempotent consumer, keyed so a repeat is a no-op, rather than reaching for exactly-once." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**Your consumer reads a Kafka topic and adds each reading to a running total. It crashes after adding one and before committing its offset. What does the total look like after it restarts?**

<ol class="clicker-opts">
<li>Short by that reading, which is lost</li>
<li>Too high, because that reading is added twice</li>
<li>Correct, because Kafka will not redeliver a processed record</li>
<li>Correct, because the broker rolls the total back</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
Tests whether at-least-once is understood as a redelivery guarantee rather than
a vague promise of reliability.

A is the productive wrong answer: it is what you get from committing the offset
first, which is a real design and the wrong one here. Ask a defender of A which
line they would move, and at-most-once falls out of it.

Land on the word idempotent, because A3 asks them to make a pipeline idempotent
under exactly this delivery model.
-->

---

## Batch, streaming, and the log, on devices and under load

MQTT is a "lightweight publish/subscribe messaging transport" for microcontrollers and lossy networks. [MQTT](https://mqtt.org/)

- **Backpressure**: when a consumer cannot keep up, signal upstream to slow down rather than dropping data or exhausting memory.

State is the hard part: a running average, an open window, or a dedup set must survive restarts, the real reason a stream is heavier than a batch job. [Reactive Streams](https://www.reactive-streams.org/)

---

<!-- _class: section -->

# Windows, event time, watermarks

---

## Windows, event time, watermarks

You cannot average an infinite sequence.

<div class="definition">

**Window**: "slices up a dataset into finite chunks for processing as a group."

</div>

Akidau's frame for any streaming computation:

- **What** result (a sum, an average)
- **Where** in event time (windows)
- **When** to emit (watermarks, triggers)
- **How** refinements relate (accumulation)

[Akidau et al., The Dataflow Model (VLDB 2015)](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf)

---

## Windows, event time, watermarks, three shapes

- **Tumbling** (fixed): static size, no overlap, one mean per clock hour.
- **Sliding** (hopping): a size and a shorter step, so windows overlap.
- **Session**: groups activity separated by gaps of inactivity.

Fixed is the special case of sliding where size = step.

---

![w:1020](figures/windowing.png)

---

## Windows, event time, watermarks, tumbling in code

```python
(readings
 .set_index("ts")        # event time
 .resample("1h")         # tumbling: fixed, no overlap
 .agg(mean_temp=("temperature", "mean")))
```

One hour in, one row out. This produces the red steps in the figure.

---

## Windows, event time, watermarks, event and processing time

- **Event time**: "the time at which the event itself actually occurred," stamped by the sensor.
- **Processing time**: "the time at which an event is observed at any given point during processing."

For a live stream they diverge constantly. A processing-time window mixes events from wildly different real times, and with **79.5%** out of order it is meaningless. Group readings by when they were measured.

---

## Windows, event time, watermarks, a question

<div class="clicker" data-tag="l06-processing-time" data-seconds="45" data-answer="B" data-hint="Processing time is stamped when a reading is observed, not when it was measured. Ask when all of these were observed." data-why="B. Processing time is stamped on arrival, so every buffered reading takes the timestamp of the reconnect and lands in one window: two hours that look like an outage, then one hour that looks like a spike, and neither of those happened. C is the productive wrong answer, because a processing-time window has no late data by definition, and nothing can arrive before it is observed. Event time puts each reading back where it was measured, which is the whole reason the distinction has a name." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**A mote loses its link for two hours, buffers its readings, and uploads all of them the moment it reconnects. You window by processing time, one hour per window. What do those two hours look like?**

<ol class="clicker-opts">
<li>Two hours of readings, spread across two windows as measured</li>
<li>Two empty windows, then a single window holding all of them</li>
<li>The readings are dropped, since their windows closed while the mote was offline</li>
<li>The same as event time, since each reading carries its own timestamp</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
The one question in this deck that decides whether the rest of the section lands.
A student who cannot answer it is not ready for watermarks.

D is the tempting one: the timestamp does travel with the reading, and that is
exactly why it is available to window on. Ask which timestamp the window used.

If the room lands in the middle band, draw the two hours on the board as a gap
followed by a spike, then ask what the plant actually did.
-->

---

## Windows, event time, watermarks, watermarks and triggers

<div class="definition">

**Watermark**: "a lower bound (often heuristically established) on event times that have been processed by the pipeline."

</div>

When it passes a window's end, the window closes.

A **trigger** decides when to emit: at the watermark once, early on a timer, or late on each straggler.

---

## Windows, event time, watermarks, late data

- **Late data**: a reading that arrives after its window has already closed.

The watermark is a guess and can be wrong. You need a policy: drop it, hold windows open, or re-emit a corrected result.

Accumulation decides what a correction means: discard the old value and replace it, or accumulate the straggler onto it. "The hourly mean is 24.1 °C. Correction: 24.3 °C." Downstream must expect updates.

[Streaming 102](https://www.oreilly.com/radar/the-world-beyond-batch-streaming-102/)

---

## Windows, event time, watermarks, a question

<div class="clicker" data-tag="l06-watermark-tradeoff" data-seconds="45" data-answer="A" data-hint="The watermark decides when a window is allowed to close. Ask what the window is doing in the meantime." data-why="A. The watermark is how long you are willing to wait before calling a window complete, so a wider one catches more stragglers and delays every result by the same amount. Completeness and latency are two ends of one dial, and no setting avoids the trade, so the number is one you state and defend rather than a default you accept. D is the common misreading, that a watermark labels records late rather than triggering a window to close." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**You widen your watermark from 10 minutes to 2 hours. What have you bought, and what have you paid?**

<ol class="clicker-opts">
<li>Fewer late records, and every window emits two hours later</li>
<li>Fewer late records, at no cost</li>
<li>More late records, and every window emits sooner</li>
<li>Nothing: a watermark labels records late, it does not change when a window closes</li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
This is A3 task 4 in one slide: the sweep asks them to price several allowances
and defend one, and this is the shape of the answer.

B is the answer a student gives who has only heard watermarks described as a way
to catch late data. Ask what the window is doing for those two hours.

Worth saying out loud that there is no correct number, only a stated reason.
-->

---

<!-- _class: section -->

# Validation: checks as a gate

---

## Validation: checks as a gate

<div class="definition">

**Data validation**: write down what you expect of the data as executable checks.

</div>

- **Gate**: a stage the data must pass before the pipeline will act on it.

Every pipeline, batch or streaming, has data entering it that some upstream process swears is fine.

---

## Validation: checks as a gate, three kinds of check

- **Schema check**: asserts structure (column exists, is a timestamp, is or is not nullable).
- **Statistical check**: asserts distributions (null rate, uniqueness, drift).
- **Physical-plausibility check**: asserts what the domain knows (temperature in range, time not backwards).

The physical checks earn their keep: the impossible temperatures from Lecture 3 come from motes whose batteries drained, and a range check and a voltage check reject the same rows.

---

![w:820](figures/validation.png)

---

## Validation: checks as a gate, pandera

<div class="definition">

**pandera**: declare a `DataFrameSchema` as code, from `Column` objects carrying a dtype, a nullability flag, and `Check`s.

</div>

```python
import pandera.pandas as pa

schema = pa.DataFrameSchema({
    "moteid":      pa.Column(int, pa.Check.isin(range(1, 55))),
    "temperature": pa.Column(float, pa.Check.in_range(0, 50), nullable=True),
    "voltage":     pa.Column(float, pa.Check.ge(2.4), nullable=True),
})
schema.validate(df, lazy=True)   # collect every failure
```

[pandera: checks](https://pandera.readthedocs.io/en/stable/checks.html)

---

## Validation: checks as a gate, how it fails

- `schema.validate(df)` raises `SchemaError` on the **first** break
- `lazy=True` raises `SchemaErrors` with **every** failing row

Fail fast to stop a pipeline; fail lazy to clean a dirty dump.

[pandera: lazy validation](https://pandera.readthedocs.io/en/stable/lazy_validation.html)

---

## Validation: checks as a gate, a failure report

```text
column       check                          failure_case
temperature  in_range(0, 50)                122.15
voltage      greater_than_or_equal_to(2.4)  1.91
```

`lazy=True` hands you which row, which check, which value.

---

## Validation: checks as a gate, a question

<div class="clicker" data-tag="l06-range-check-drift" data-seconds="45" data-answer="B" data-hint="The check runs on one row and knows nothing about the rows before it. Sketch the climb and mark where 50 sits on it." data-why="B. A range check is a per-row predicate: it rejects 122 and it accepts 48, and it has no memory of the same mote reading 24 last week. Everything from the start of the drift up to the crossing of 50 passes the gate. That is why the schema two slides back also checks voltage: the drained battery is the upstream cause and it crosses its floor earlier, so the voltage check catches the same mote sooner. Catching the trend itself is a statistical check, not a schema check. D is worth naming: lazy changes how many failures you are told about, never which rows fail." data-read="https://clicker.f26-06763.workers.dev">
<div class="clicker-main">

**A mote's battery drains. Its temperature readings drift slowly upward over a week and end at 122&deg;C. Your schema checks `temperature` in range 0 to 50. How much of that drift does the gate catch?**

<ol class="clicker-opts">
<li>All of it, since the mote is rejected once any reading fails</li>
<li>Only the readings above 50, so the whole climb up to it passes</li>
<li>None, since a range check cannot see a trend</li>
<li>All of it, once you pass <code>lazy=True</code></li>
</ol>

</div>
<aside class="clicker-panel">
<img src="figures/clicker-qr.png" alt="QR code linking to the vote page">
<div class="clicker-url">clicker.f26-06763.workers.dev</div>
<button class="clicker-start">Start voting</button>
<div class="clicker-timer">45</div>
<div class="clicker-count">no votes yet</div>
</aside>
</div>

<!--
Ties the failure report on the previous slide to the pandera schema two before it,
and sets up the pushback section on validation confirming plausibility.

A is the productive wrong answer and it is a good one: students read the gate as
rejecting the mote rather than the row. Ask what pandera was handed.

C is worth a sentence too, because it is nearly right for the wrong reason: the
range check does catch the tail, it just cannot catch the climb.
-->

---

## Validation: checks as a gate, Great Expectations

<div class="definition">

**Great Expectations**: a heavier validation framework aimed at teams who want results as living documentation.

</div>

- **Expectation**: a verifiable assertion about data
- **Suite**: a collection of them
- **Checkpoint**: runs a suite in production
- **Data Docs**: human-readable reports

[GX overview](https://docs.greatexpectations.io/docs/core/introduction/gx_overview/)

---

## Validation: checks as a gate, pandera or Great Expectations

| pandera | Great Expectations |
|---|---|
| a schema in your code | a framework with a project |
| inline, unit-test feel | suites, checkpoints, Data Docs |
| one script, one dev | a pipeline, a team, an audit trail |

Prefer pandera for a single script; use Great Expectations when a team needs an audit trail.

---

## Validation: checks as a gate, drift and contract

Statistical checks ask whether the **distribution** moved:

- a null rate creeping up
- a sensor's mean sliding month to month

The seam into **monitoring**: the same checks, run forever.

A written schema is a **data contract**, the shape a consumer is entitled to assume, and documentation that fails the build when it goes stale.

---

## Validation: checks as a gate, what a failure does

| Policy | Use when |
|---|---|
| **block** | bad data must never reach a model/report |
| **warn** | you monitor it but won't act now |
| **quarantine** | route bad rows aside, let good ones flow |

Inject bad data on purpose and prove the gate halts, because an untested check gives false confidence.

---

<!-- _class: section -->

# Where this pushes back

---

## Where this pushes back, streaming is a cost to defer

A batch job is a function you rerun. A stream is a long-lived stateful service.

Exactly-once is hard, watermarks are heuristics, late data forces a policy.

Start batch or micro-batch. Adopt streaming only when latency demands it.

---

## Where this pushes back, event-time windows trust your clocks

Everything rested on the event-time stamp.

A wrong or drifting sensor clock makes event-time windows group by a **lie**.

The monotonic-timestamp check lets you trust them.

---

## Where this pushes back, validation confirms plausibility

A value that passes every check can still be wrong.

24 °C is plausible whether or not it is what happened.

Validation catches impossible and malformed values. It misses a sensor that is miscalibrated but reading plausibly. It gives the same false comfort as a passing test or a reproducible result.

---

## Where this pushes back, a schema is a brittle burden

- too tight: cries wolf, until the team ignores it
- too loose: passes the data it should catch
- only tests the expectations you **thought to write**

Validation improves the baseline of data quality, and problems it did not anticipate still pass through.

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

Without it: the pipeline runs to completion and produces a **confident, wrong number**.

The gate turns silent corruption into a loud failure.

---

## Recap

- Real sensor data is **unbounded, out of order, and dirty**
- Streaming: windows in **event time**, closed by **watermarks**
- 79.5% out of order is *why* event time and watermarks exist
- Validation: schema, statistical, and **physical** checks, as a **gate**
- pandera for code, Great Expectations for team-readable reports
- Block, warn, or quarantine, and prove the gate halts

---

## Standings

Nicknames only. Everyone who skipped one still counted in every bar you saw.

<div class="clicker-leaderboard"
     data-read="https://clicker.f26-06763.workers.dev"
     data-top="8"
     data-hours="6"
     data-title="Standings"></div>

---

## Next

**Assignment 3** is released today: collect ten minutes of a live plant stream, then make it trustworthy
**Reading** Akidau, "The Dataflow Model"; pandera docs

Full notes, with all sources: `lectures/l06/notes.md`

<script src="clicker-slide.js"></script>
