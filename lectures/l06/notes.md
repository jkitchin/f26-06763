# Lecture 6: Streaming concepts and data validation

:::{admonition} Overview
:class: tip

- **Session** Lecture 6, Week 3
- **Arc** Data Systems
- **Slides** <a href="../../slides/l06/">Deck for this session</a>
- **Demo** [`l06-validation.ipynb`](l06-validation.ipynb), a pandera gate that fails loudly, and a windowed replay of the sensor stream
- **Assignment 3**, released at Lecture 5; its validation half is this session's material
:::

## Why this matters

The pipeline we built in [Lecture 5](../l05/notes.md) was a batch pipeline: a clean sequence of stages over a fixed, finished dataset. That is the right picture most of the time, and it is where every team should start. But two facts about real sensor data sit just outside that picture, and a pipeline that ignores them fails quietly rather than loudly. This session is about both, because they are the two ways a data feed betrays the assumptions a batch job makes.

The first fact is that the data does not stop, and it does not arrive in order. A sensor network is an *unbounded* stream: there is no last row, only the row that has not arrived yet. Worse, the rows arrive jumbled in time. Take the Intel Berkeley Lab feed we have used since Lecture 3, and watch the readings in the order they actually land rather than after sorting. **79.5% of them arrive out of order**, meaning a reading whose timestamp is earlier than one already seen from the same mote. That is not a corrupt file; it is the normal behavior of many motes reporting over a lossy network with buffering and retries. A batch job that assumes rows come in time order, or that the dataset is complete when it runs, is simply wrong about this feed, and no amount of care downstream repairs an assumption broken at the source.

The second fact is that the data is not clean, and nothing announces the dirt. The same feed carries physically impossible values: about **18% of its temperature readings** fall outside a generous 0-to-50-degree indoor range, and about **26%** come from motes whose battery has drained below the level where the sensor can be trusted. Those are not rare outliers to shrug at; they are hundreds of thousands of rows that will quietly pull an average, train a model on nonsense, or trip an alarm, unless something stops them at the door.

Two disciplines answer these two facts. **Streaming** is how you compute over data that never stops and arrives late: windowing, event time, and watermarks. **Data validation** is how you stop bad data before it enters: executable checks that run as a gate and fail loudly. The through-line from earlier in the course is the same one Lecture 1 drew from a spreadsheet that silently dropped rows: the cheapest failure to prevent is the one you refuse to let in, and the way you refuse is a check that runs every time.

## Learning objectives

By the end of this session you should be able to:

- Distinguish batch from streaming, and identify when sensor systems require streaming.
- Explain windowing, event vs. processing time, watermarks, and late or out-of-order data.
- Author executable data-quality checks and integrate them as a pipeline gate.

## Batch, streaming, and the log

```{index} streaming, batch processing, log, Kafka, offset, delivery semantics, backpressure
```

A **batch** job runs on a schedule over a bounded chunk of data: yesterday's readings, this run's export, the file that just landed. It has a beginning and an end, it can be rerun, and it is by far the simplest thing to reason about, which is why Lecture 5 built one and why most engineering teams should start there. A **streaming** system, by contrast, processes an *unbounded* input as it arrives, record by record, and never runs out of input. The distinction that matters is not the tool but the shape of the data: bounded data invites batch, unbounded data eventually demands streaming, and the honest middle ground, **micro-batch**, runs a batch job every few seconds over whatever has accumulated, buying most of the latency of streaming with much of the simplicity of batch.

Underneath most streaming systems is one idea worth understanding even if you never operate one: the **log**. A log is an append-only sequence of records, and it is the abstraction Apache Kafka is built around. A Kafka topic is split into partitions, and, as the [Kafka introduction](https://kafka.apache.org/intro) puts it, "when a new event is published to a topic, it is actually appended to one of the topic's partitions." Producers append; consumers read forward at their own pace, each tracking an **offset**, the position of the next record it will read. The ordering guarantee is precise and worth stating precisely, because people routinely overstate it: Kafka guarantees order *within a partition*, not across a topic. If you need a mote's readings in order, they must land in the same partition. For the lightest-weight sensor case, the pub/sub protocol you will actually meet on devices is [MQTT](https://mqtt.org/), "an extremely lightweight publish/subscribe messaging transport" designed for microcontrollers and lossy networks.

Two properties of any such system decide how much you can trust it. The first is **delivery semantics**. A system is *at-most-once* if messages can be lost but never redelivered, *at-least-once* if they are never lost but can be redelivered, and *exactly-once* if each is processed once and only once. Exactly-once sounds like the obvious choice and is the expensive one, and here is the surprise that trips people: Kafka is [at-least-once by default](https://kafka.apache.org/documentation/#semantics). Exactly-once is not a switch you flip on the cluster; it is opt-in machinery, an idempotent producer plus transactions, or Kafka Streams' `exactly_once_v2` mode, and it constrains how you write your consumers. Assume at-least-once, and design your processing to tolerate a message arriving twice. The second property is **backpressure**: when a consumer cannot keep up with the rate a producer is pushing, something has to give, and a well-designed pipeline signals upstream to slow down rather than silently dropping data or exhausting memory. The [Reactive Streams](https://www.reactive-streams.org/) standard exists precisely so "a fast data source does not overwhelm the stream destination."

## Windows, event time, and watermarks

```{index} windowing, tumbling window, sliding window, session window, event time, processing time, watermark, late data
```

The question a stream forces on you is one a batch job never has to ask: if the data never ends, what exactly are you aggregating? You cannot take the average of an infinite sequence. The answer is a **window**, which, in the words of the canonical reference, Akidau and colleagues' [Dataflow Model](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf) (VLDB 2015), "slices up a dataset into finite chunks for processing as a group." Three window shapes cover almost everything. A **tumbling** window (the paper calls it fixed) has a static size and does not overlap: the average temperature in each clock hour, one number per hour. A **sliding** window (sometimes hopping) has a size and a shorter step, so windows overlap and the aggregate updates more often: a one-hour average recomputed every fifteen minutes. A **session** window has no fixed size at all; it groups activity separated by gaps of inactivity, which fits event bursts better than a clock. The paper's own summary is worth keeping: fixed windows are just the special case of sliding windows where the size equals the step.

```{figure} figures/windowing.png
:alt: One mote's temperature over eight hours, with tumbling one-hour means drawn as flat red steps and a sliding one-hour mean drawn as a smoother blue line
:width: 100%

The same unbounded stream, aggregated two ways. Tumbling one-hour windows (red) produce one non-overlapping mean per hour; a sliding one-hour window stepped every fifteen minutes (blue) overlaps and updates more often. One mote's temperature over its first eight hours in the Intel Lab feed.
```

Windows raise a subtler question, and it is the one that separates people who have run a stream from people who have only read about one: *which time do you mean?* The Dataflow paper draws the line cleanly. **Event time** is "the time at which the event itself actually occurred," stamped by the sensor. **Processing time** is "the time at which an event is observed at any given point during processing." For a batch over a static file the two barely differ; for a live stream they diverge constantly, because events take a variable, unpredictable time to travel from the sensor to your code. And this is where the 79.5% from the opening returns with teeth. When readings arrive that far out of order, a window defined by *processing* time, "everything I received between 3:00 and 4:00," mixes together events that happened at wildly different real times, and the answer is meaningless. You almost always want windows in *event* time, grouping readings by when they were measured, not when they showed up.

But event-time windows create a problem of their own: if a reading can arrive late, when is it safe to say a window is finished and emit its result? Waiting forever is not an option. The mechanism is a **watermark**, which the paper defines as "a lower bound (often heuristically established) on event times that have been processed by the pipeline." A watermark is the system's best guess that it has now seen all events up to some event time; when the watermark passes the end of a window, the window closes and its result is emitted. The word *heuristic* is load-bearing: the watermark can be wrong, and a reading can arrive after its window has already closed. That is **late data**, and a real streaming system needs an explicit policy for it, drop it, or hold windows open long enough to let stragglers in, or re-emit a corrected result when one arrives. The Streaming [101](https://www.oreilly.com/radar/the-world-beyond-batch-streaming-101/) and [102](https://www.oreilly.com/radar/the-world-beyond-batch-streaming-102/) articles are the readable long form here; 102 is where watermarks and triggers are actually developed, so send yourself there rather than 101 for that part.

## Data validation: checks as a gate

```{index} data validation, schema check, pandera, Great Expectations, quarantine
```

Streaming is about *when* data arrives; validation is about *whether it is any good*, and it is the more universally useful of the two, because every pipeline, batch or streaming, has data entering it that some upstream process swears is fine. **Data validation** is the practice of writing down what you expect of the data as executable checks, and running them as a **gate**: a stage that data must pass before the pipeline will act on it. The checks fall into three kinds, and a good suite has all three. **Schema checks** assert structure: this column exists, it is a timestamp with a zone, it is a float, it is or is not allowed to be null. **Statistical checks** assert distributions: the null rate is below some bound, an id is unique, a value's mean has not drifted off its historical range. **Physical-plausibility checks** assert what the engineering domain knows: a temperature is inside the instrument's range, a timestamp does not run backwards, a flow is non-negative. That last category is where engineering data validation earns its keep, because a value can be a perfectly good float and still be physically impossible, exactly the 386-degree readings from Lecture 3.

```{figure} figures/validation.png
:alt: A bar chart showing that about 18 percent of readings fail a temperature-range check and about 26 percent fail a battery-voltage check, with a note that 96 percent of the impossible temperatures come from low-voltage motes
:width: 80%
:align: center

Two plausibility checks applied to the full Intel Lab feed. A temperature-range check rejects about 18% of readings and a battery-voltage check about 26%, and the two overlap heavily: 96% of the impossible temperatures come from a mote already below 2.4 V. A schema encodes exactly these as executable rules.
```

The tool that makes this pleasant in Python is **pandera**, which lets you declare a schema as code. A `DataFrameSchema` is built from `Column` objects, each carrying a dtype, a nullability flag, and a list of `Check`s, where a [`Check`](https://pandera.readthedocs.io/en/stable/checks.html) wraps a function that returns a boolean or a boolean series and passes only if every element is true. Built-in checks cover the common cases (`Check.in_range`, `Check.ge`, `Check.isin`, `is_monotonic`, `no_duplicates`), and a custom check is just a function, so "temperature between 0 and 50" and "timestamps per mote never decrease" are a few lines each. How it *fails* is the important part: by default [`schema.validate(df)`](https://pandera.readthedocs.io/en/stable/lazy_validation.html) raises a `SchemaError` as soon as one assumption is falsified, and with `lazy=True` it instead collects every failure and raises a single `SchemaErrors` with a summary of the offending rows, which is what you want when you are cleaning a genuinely dirty dataset and would rather see all the problems at once than fix them one exception at a time. pandera validates both pandas and Polars frames.

```python
import pandera.pandas as pa

schema = pa.DataFrameSchema({
    "moteid":      pa.Column(int,   pa.Check.isin(range(1, 55))),
    "temperature": pa.Column(float, pa.Check.in_range(0, 50), nullable=True),
    "voltage":     pa.Column(float, pa.Check.ge(2.4),         nullable=True),
})
schema.validate(readings, lazy=True)   # collect every failure, not just the first
```

:::{admonition} Common pitfall
:class: warning

As of pandera v0.24 the recommended import for dataframe validation is `import pandera.pandas as pa` (with a parallel `pandera.polars`), and the old top-level `import pandera as pa` is on its way to deprecation for schemas. The schema code is otherwise identical, so a snippet copied from an older tutorial will still run but may print a deprecation warning. Pin the import to the namespace your version wants, and do not let the warning send students hunting for a bug that is not there.
:::

The heavier alternative is **Great Expectations**, which is less a library call and more a framework. Its vocabulary, from the [GX overview](https://docs.greatexpectations.io/docs/core/introduction/gx_overview/), is worth recognizing: an **Expectation** is "a verifiable assertion about data," an **Expectation Suite** is a collection of them, a **Checkpoint** runs a suite against data in production, and **Data Docs** are the human-readable reports it generates. That last piece is the real differentiator: Great Expectations is aimed at teams who want validation results as living documentation a non-engineer can read, at the cost of more setup than a pandera schema. One caution if you reach for it: the workflow changed substantially at the 0.18-to-1.0 boundary (Checkpoints now run "Validation Definitions"), so tie any example to a specific version and do not mix 1.x code with the older docs. For this course, pandera is the default for a pipeline gate and Great Expectations is the tool to know exists when the audience for the results is people rather than code.

Wherever the checks live, the decision that actually shapes a pipeline is what a failure *does*. There are three honest options. **Block**: the pipeline halts and nothing downstream runs, which is right when bad data must never reach a model or a report. **Warn**: the pipeline logs the problem and continues, which is right for a metric you are monitoring but will not act on immediately. **Quarantine**: the bad rows are routed aside for inspection while the good ones flow on, which is often the most practical for a large dirty feed where halting on every impossible temperature would stop everything. A check that can only ever pass is untested decoration; the discipline, as with the Lecture 1 demo, is to inject bad data on purpose and prove the gate catches it.

## Where streaming and validation push back

Both disciplines in this session are easy to over-apply, and the mature judgment is knowing their limits as well as their uses.

### Streaming is a large cost you should defer as long as you can

A batch pipeline is a function you can rerun, inspect, and reason about; a streaming system is a long-lived service with state, watermarks, delivery semantics, and failure modes that only appear under load. The exactly-once machinery is genuinely hard, watermarks are heuristics that will sometimes be wrong, and late data forces a policy decision with no free answer. Most engineering questions, a daily report, a model retrained weekly, an analysis of last month, are batch questions wearing a streaming costume, and the right move is to start with scheduled batch or micro-batch and adopt true streaming only when a real latency requirement forces it. Reaching for Kafka because the data "is a stream" when a nightly job would do is how teams acquire an operational burden they did not need.

### A window in event time is only as good as your timestamps

Everything in the windowing section rested on trusting the event-time stamp on each reading. If a sensor's clock is wrong, or drifts, or resets on a power cycle, then event-time windows group readings by a lie, and no watermark saves you. This is the point where streaming and validation meet: the monotonic-timestamp check from the validation section is not bookkeeping, it is what lets you trust the event times that windowing depends on. Garbage timestamps make sophisticated windowing produce confident nonsense.

### Validation confirms plausibility, not correctness

This is the limit worth carrying furthest, and it echoes Lecture 2 exactly: a value that passes every check can still be wrong. A temperature of 24 degrees is inside the plausible range whether or not it is the temperature that actually occurred; a check confirms the reading is *possible*, not that it is *true*. Validation catches the impossible and the malformed, which is a large and worthwhile class of error, and it is powerless against a sensor that is miscalibrated but reading plausibly, or a units error that lands inside the allowed range. Do not let a green validation dashboard become the same false comfort that a passing test suite or a reproducible result can be.

### A schema is a maintenance burden, and a brittle one fails both ways

Every expectation you encode is a rule someone must maintain as the data legitimately evolves. Set the checks too tight and they cry wolf on every normal fluctuation until the team learns to ignore them, which is worse than no check at all. Set them too loose and they pass the very data they were meant to catch. And a validation suite only ever tests the expectations you thought to write; the failure mode nobody anticipated sails straight through. Validation raises the floor on data quality; it does not cap the ceiling on data problems.

:::{admonition} What a practitioner should take from this
:class: tip

Put a validation gate at every boundary where data enters your control, and make failures do something you chose on purpose, block, warn, or quarantine, rather than defaulting to "log and hope." Write physical-plausibility checks, not just type checks, because engineering data fails in ways a type system cannot see. Treat streaming as a serious commitment to defer: reach for scheduled batch or micro-batch first, and adopt event-time windowing with watermarks only when latency genuinely demands it, remembering that a window is only as trustworthy as the timestamps under it. And hold onto the humbling half of validation: it proves data is plausible, never that it is correct.
:::

## In-class demo

We work the validation half concretely and sketch the streaming half. Starting from the sensor data, we declare a pandera schema, dtypes, the set of valid mote ids, an `in_range` check on temperature, and a voltage floor, and run it as a gate before the transform stage. The gate stops on the first problem it meets, a handful of readings tagged with impossible mote ids such as 65407, which is a plain set check earning its keep; running the same schema lazily then reveals the far larger population of out-of-range temperatures and low-voltage rows beneath. We show the cost of skipping the gate, the raw mean temperature is a confident wrong number because roughly a sixth of the readings are physically impossible, then inject two rows we know are bad and watch the `SchemaErrors` report name exactly those rows rather than letting them through to poison an aggregate. Finally we split the feed into a clean stream and a quarantine table, and see that the temperature and voltage rules reject nearly the same rows. For streaming, we measure how out of order the feed really is, about 79.5% of readings arrive before one already seen from the same mote, and replay one mote as tumbling and sliding windowed averages in event time.

The moment to watch is the gate. A pipeline with the check runs, hits bad data, and stops with a precise complaint; the same pipeline without the check runs to completion and produces a confident, wrong number. That contrast, loud failure versus silent corruption, is the whole argument for validation. The runnable notebook is [`l06-validation.ipynb`](l06-validation.ipynb).

## Summary

Real sensor data breaks two assumptions a batch pipeline quietly makes: that the data is finished, and that it is clean. Streaming answers the first. Unbounded, out-of-order data is aggregated with windows, tumbling, sliding, or session, computed in event time rather than processing time, and closed by watermarks that are explicit, heuristic guesses about when late data has stopped arriving. The Intel Lab feed, 79.5% out of order, is why event time and watermarks exist rather than being academic. Validation answers the second. Executable checks, schema, statistical, and physical-plausibility, run as a gate that fails loudly, encoded cleanly with pandera or, for team-readable reports, Great Expectations, and wired to block, warn, or quarantine on failure. On the same feed, a schema rejects about 18% of readings on temperature and 26% on voltage, and the two catch the same dying-battery failure. The honest limits matter as much as the uses: streaming is a cost to defer until latency demands it, and validation proves data plausible, never correct.

## Resources

- [pandera: DataFrame schemas](https://pandera.readthedocs.io/en/stable/dataframe_schemas.html). Columns, dtypes, and nullability; the shape of a schema-as-code.
- [pandera: Checks](https://pandera.readthedocs.io/en/stable/checks.html) and [lazy validation](https://pandera.readthedocs.io/en/stable/lazy_validation.html). Built-in and custom checks, and the difference between `SchemaError` (fail fast) and `SchemaErrors` (collect all).
- [Great Expectations overview](https://docs.greatexpectations.io/docs/core/introduction/gx_overview/). Expectations, suites, checkpoints, and Data Docs; the heavier, team-readable alternative.
- [Akidau et al., The Dataflow Model](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf) (VLDB 2015). The canonical treatment of event time, windowing, and watermarks; open access.
- [Streaming 101](https://www.oreilly.com/radar/the-world-beyond-batch-streaming-101/) and [Streaming 102](https://www.oreilly.com/radar/the-world-beyond-batch-streaming-102/). The readable long form; 102 is where watermarks and triggers are developed.
- [Apache Flink: Windows](https://nightlies.apache.org/flink/flink-docs-stable/docs/dev/datastream/operators/windows/). Crisp operational definitions of tumbling, sliding, and session windows, and of late data.
- [Apache Kafka: Introduction](https://kafka.apache.org/intro) and [delivery semantics](https://kafka.apache.org/documentation/#semantics). The log abstraction, per-partition ordering, offsets, and at-least-once vs exactly-once.
- [MQTT](https://mqtt.org/). The lightweight publish/subscribe protocol for internet of things (IoT) and sensor telemetry.
- [Reactive Streams](https://www.reactive-streams.org/). Backpressure as a standard: not overwhelming a slow consumer.
- [Intel Lab Data](https://db.csail.mit.edu/labdata/labdata.html). The streaming/validation feed, carried from Lecture 3, replayed by timestamp. Served over plain HTTP.
- [UCI SECOM](https://archive.ics.uci.edu/dataset/179/secom). The wide, dirty semiconductor feature matrix from Lecture 5: about 1,500 runs, roughly 590 process measurements, heavy missingness, a natural target for a validation suite.
- Kleppmann, *Designing Data-Intensive Applications*, Ch. 11 ("Stream Processing"). The clearest single treatment of logs, streams, and their relationship to batch.

## Assignment

Assignment 3, "Reproducible, validated data pipeline," was released at Lecture 5 and is due roughly one week later. Its first half is Lecture 5's batch-pipeline material; its second half is this session's, adding pandera or Great Expectations checks that fail the pipeline on bad data, including a physical-plausibility check and a proof that the gate actually halts on injected corruption. You can start the validation half now that this session is done. This is a pointer, not the rubric.
