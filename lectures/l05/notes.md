# L5 · Dataframes, batch pipelines, and scalable processing

:::{admonition} At a glance
:class: tip

- **Session** L5, Week 3 · **Arc** Data Systems
- **Slides** <a href="../../slides/l05/">Deck for this session</a>
- **Demo** [`l05-pipelines.ipynb`](l05-pipelines.ipynb), one pipeline in pandas, Polars, and Dask
- **Assignment** A3 released this session
:::

## Why this matters

Picture a process engineer at a semiconductor fab who has just been handed a spreadsheet
export: 1,567 manufacturing runs down the rows, 590 sensor and process measurements across
the columns. Somewhere in that matrix is the difference between a wafer that ships and one
that gets scrapped, and the job is to find it. The first working version of that analysis is
almost always a `for` loop: iterate over the rows, pull each sensor's reading, apply some
cleaning rule, append the result to a list. It runs. It even finishes, on 1,567 rows. Then
next month's export has 15,670 rows, because the fab added a second line, and the "quick
script" that took four seconds now takes forty, and the one after that takes seven minutes,
and nobody budgeted for a batch job to be the thing standing between a shift ending and the
report going out.

Nothing about that slowdown is a modeling problem, and nothing about it is really even a
Moore's-law problem. It is an architecture problem: a Python-level loop pays the interpreter's
per-element overhead 590 times a row, every row, when the honest description of the work is a
handful of whole-column operations that could be handed to compiled code in one shot. The
first half of this session is about that gap, between the loop you write first and the
vectorized, columnar operation you should write instead, and about a library, Polars, built
from scratch to close it further than pandas can.

The second half is about a different and easily confused failure: reaching for a cluster you
did not need. "Scalable processing" in a course title invites the assumption that bigger
tools are strictly better, and the semester's running dataset is about to make the opposite
case with numbers. SECOM, the dirty industrial matrix above, is a few megabytes. It fits in
memory on a phone. Standing up Spark to process it is not a neutral choice you might as well
make "to be safe"; it is added complexity, added latency, and added ways for the job to fail,
purchased for a benefit that does not exist at this size. Judgment about when a laptop is
still the right machine is as much a part of "scalable processing" as knowing how to reach
for more machines when the data actually demands it, and this session tries to leave you able
to make that call instead of defaulting to whichever tool is loudest this year.

It is worth hearing this critique from the source. In 2017, Wes McKinney, who created pandas,
published a post enumerating what he called "10 Things I Hate About pandas": no native
support for memory-mapped or out-of-core data, most operations running on a single core
regardless of how many are available, and an in-memory representation that, because it stores
missing data and strings as boxed Python objects rather than compact typed arrays, can occupy
several times the footprint of the raw data on disk. That post is not a takedown by a
competitor; it is the design document for [Apache Arrow](https://arrow.apache.org/overview/),
the columnar memory format Polars is built on, written by the person best positioned to know
exactly where pandas was going to strain. When the author of the dominant tool in a field
writes down its failure modes in public, that list is worth reading before you hit the same
walls yourself.

## Learning objectives

By the end of this session you should be able to:

- Write idiomatic transformations in pandas and Polars and read/benchmark both.
- Structure a batch pipeline into reproducible, parameterized stages.
- Explain the distributed-processing model (partitioning, lazy graphs) without needing a
  cluster.

## Vectorization, and the shape sensor data actually take

Start from the operation every engineering dataset needs constantly: apply the same
arithmetic to every value in a column. In pandas or Polars this is one line,
`df['temp_c'] = (df['temp_f'] - 32) * 5 / 9`, and under the hood it runs as a tight loop over a
contiguous block of memory, in C, with no per-element Python overhead. Write the equivalent as
a Python `for` loop over rows and you are asking the interpreter to create a new Python object,
check its type, and dispatch an arithmetic operator, 590 times a row, for every row in the
table. **Vectorization** is the discipline of expressing a computation as whole-array
operations so the loop happens once, in fast code, instead of once per element in slow code.
The speedup is not a rounding error; on numeric columns it is routinely one to two orders of
magnitude, and it compounds because a wide sensor matrix has hundreds of columns each paying
that tax independently if you loop.

`groupby` is the same idea applied to aggregation. "Mean sensor reading per run, per shift, per
lot" is a `groupby` plus an aggregate, and the library decides internally how to bucket and
reduce the rows, which is again something you do not want to hand-roll with a dictionary and a
loop. Joins extend the same reasoning across tables: attaching a sensor's calibration record
or a lot's recipe metadata to each reading is a join on a shared key, exactly as it was for the
`sensors` and `readings` tables in [L3](../l03/notes.md), and the same warning applies here that
applied there, that column names should describe a *kind* of measurement, not a particular
sensor or run.

**Reshaping** is the move you will make constantly with instrument exports, because
instruments rarely hand you tidy data. A wide sensor matrix, one column per signal, is
exactly the shape SECOM comes in, and it is often the right shape for a model that wants one
row per training example. But the moment you need to ask "which sensors were most often
missing this month" or "plot every signal on one axis," you want the long form instead, one
row per (run, sensor, value), which is the same wide-versus-long argument from L3's relational
schemas, now happening inside a single dataframe rather than across database tables. `melt`
(wide to long) and `pivot` (long to wide) are how you move between them, and a pipeline that
needs both shapes at different stages should reshape explicitly rather than maintain two
copies that can drift apart.

```python
# Wide to long: one row per (run, sensor), not one column per sensor.
long = wide.melt(id_vars=['run_id', 'label'], var_name='sensor', value_name='reading')
```

:::{admonition} Common pitfall
:class: warning

`df.apply(lambda row: ...)` looks vectorized because it is one line and touches a whole
dataframe, and it is nearly as slow as the explicit loop it is hiding, because pandas still
calls your Python function once per row (or once per column with `axis=0`). If you find
yourself writing `.apply` with a lambda that only touches arithmetic on one or two columns,
that is almost always a sign a plain vectorized expression was available and you reached for
the wrong hammer.
:::

## Polars and the lazy execution model

Pandas made a specific set of design choices in 2008 that were entirely reasonable for the
data of that era and that Arrow-based tools now revisit. Its default numeric layout is
NumPy arrays, which are contiguous and fast, but strings, categoricals, and missing values are
frequently stored as boxed Python objects, and most of its operations run single-threaded even
on a machine with sixteen idle cores. Polars, a dataframe library written in Rust and built
directly on Apache Arrow's columnar memory format, was designed after that gap was visible,
and it makes the opposite choice on nearly every axis: typed columnar storage throughout,
multithreaded execution by default, and, most consequentially, a genuine **query optimizer**
sitting between the code you write and the computation that actually runs.

That optimizer is only reachable through Polars' **lazy API**, and the eager-versus-lazy
distinction is the single most important thing to internalize before writing a line of Polars
code. `pl.read_csv(...)` followed immediately by `.filter(...)` and `.select(...)` in **eager**
mode runs each step the moment you call it, exactly like pandas: read every column, then
throw most of it away in the filter. Build the same chain with `pl.scan_csv(...)` instead and
nothing runs at all. You are handed a `LazyFrame`, a description of the computation, and Polars
only executes it when you call `.collect()`. In between, the query optimizer inspects the
whole plan and rewrites it: **predicate pushdown** moves your `filter` as early as possible,
often into the file reader itself, and **projection pushdown** notices which columns the final
`.select()` actually needs and skips reading the rest from disk entirely. The practical
consequence is that `scan_csv(...).filter(...).select(...).collect()` can be dramatically
cheaper than the eager equivalent, not because Polars computes faster in some generic sense,
but because it computes *less*, having seen the whole query before running any of it.

```python
# Nothing executes until .collect(). The optimizer sees filter and select
# together and can skip unread columns and unmatched rows during the scan itself.
result = (
    pl.scan_parquet("sensors/*.parquet")
    .filter(pl.col("run_id") > 1000)
    .select(["run_id", "sensor_12", "sensor_87"])
    .collect()
)
```

**Expressions** are the second idea worth naming, because they are what makes the optimizer
possible in the first place. `pl.col("sensor_12").mean()` is not a computed value; it is an
object describing a computation, which Polars can inspect, combine with other expressions, and
compile into a single multithreaded pass over the data. This is why Polars expressions compose
so differently from pandas method chains: `df.select([pl.col(c).mean() for c in sensor_cols])`
describes 590 reductions as 590 expressions and runs them together, in parallel, in one pass
over the table, rather than as 590 separate calls each re-touching the frame.

Interop is what keeps this practical rather than academic. Polars reads and writes
[Parquet](https://arrow.apache.org/docs/format/Columnar.html) natively and shares Arrow's
in-memory layout, so converting between a Polars frame, a pandas frame, and an Arrow table is
typically a zero-copy or near-zero-copy operation rather than a serialization step, which
matters the moment your pipeline has one stage written in each.

## Designing a batch pipeline: stages, idempotency, and caching

A **batch pipeline** is nothing more exotic than a sequence of transform stages, each one a
pure function that reads an input and produces an output, run on a schedule or on demand over
a bounded chunk of data. A3 asks for exactly four: **ingest** (read the raw file into a typed
frame), **clean** (drop constant and high-missingness columns), **transform** (impute, using
statistics computed only on the training split), and **persist** (cache the result, typically
to Parquet). The discipline that matters more than any individual stage is keeping each one a
pure function with a typed input and output, because that is what makes the pipeline testable,
cacheable, and debuggable one stage at a time instead of as one large opaque script.

**Idempotency** is the property that running a stage twice on the same input produces the same
output, byte for byte, and it sounds like a minor implementation detail until you have to
recover from a partial failure. If `clean` is idempotent, rerunning it after a crash is free:
you get back exactly what you had, and you can move on. If it is not, because it depended on
the current time, an unseeded random draw, or the order files happened to arrive in, rerunning
it silently produces a different pipeline than the one that ran in production, and a
"reproduction" of last week's numbers quietly stops being one. **Deterministic outputs** are
idempotency's twin requirement: pin your random seeds, sort before any operation whose result
depends on row order, and treat "the same input always yields the same output" as a
correctness requirement, not a nicety.

### Case study: one server out of eight

On 1 August 2012, Knight Capital Group, then one of the largest market-makers in US equities,
lost roughly \$460 million in the first forty-five minutes of trading. The proximate cause,
laid out in the SEC's subsequent order, was a software deployment: engineers pushed new
order-routing code, called RLP, to eight production servers, repurposing an old flag that used
to activate a decommissioned test function called Power Peg. The deployment reached seven of
the eight servers. On the eighth, the old Power Peg code was still present, and the repurposed
flag activated it instead of the intended new logic. For forty-five minutes, that one server
sent a stream of erroneous orders into the market, and nothing in the deployment process
detected that the fleet was no longer running one consistent version of the code.

The mechanism generalizes directly to a batch pipeline that is not idempotent and not
verified. A rollout across eight machines is, in effect, a batch job whose "rows" are servers,
and it succeeded on seven out of eight without anyone knowing the eighth had a different
result until the output, millions of dollars of erroneous trades, made it obvious. The
practitioner-level lesson is not "test more before deploying," which is true but unhelpful. It
is narrower and more actionable: after any batch operation that is supposed to leave every
unit in the same state, verify that it did, with an automated check comparing actual output
against expected output, rather than trusting that "the job completed" means "the job
completed correctly everywhere."

:::{admonition} What a practitioner should take from this
:class: tip

A deployment, a migration, and a nightly pipeline run are all batch jobs, and all three fail
the same way when partial success looks identical to full success. Build the reconciliation
check, a count, a hash, a checksum of the output, into the job itself, so an inconsistent
result is caught by the pipeline rather than discovered downstream by whatever it was
protecting.
:::

Caching intermediate outputs to **Parquet** between stages is what makes this practical day to
day, beyond correctness. A pipeline that reruns `ingest` and `clean` from the raw file every
time you want to iterate on the `transform` stage wastes minutes you will lose thousands of
times over a semester. Persist each stage's output, and make each stage check for its cached
output before recomputing, and iteration on stage four stops requiring you to redo stages one
through three.

## Orchestration, or when a plain DAG is enough

Every pipeline with more than one stage is, whether or not anyone calls it one, a **directed
acyclic graph**: a set of steps with dependencies between them, and no step depends on its own
output, directly or through a cycle. A **Makefile** is the oldest tool that takes this
seriously: each target names its dependencies, `make` compares file modification times, and it
reruns only the targets whose inputs changed since the last build, which is incremental
caching for free, expressed in about ten lines per stage.

```makefile
clean.parquet: ingest.parquet clean.py
	python clean.py ingest.parquet clean.parquet

transform.parquet: clean.parquet transform.py
	python transform.py clean.parquet transform.parquet
```

For a single author running a pipeline on one machine, that is frequently enough, and it is
worth normalizing that a Makefile is not a step down from a "real" orchestrator, it is a
correctly sized tool for a small DAG. What tools like [Prefect](https://docs.prefect.io/) and
[Dagster](https://docs.dagster.io/) add is everything that matters once a pipeline has to run
unattended, on a schedule, and be trusted by people who are not the author: automatic retries
on transient failure, a scheduler, a UI showing which run failed and why, alerting, and, in
Dagster's case, an explicit model of each pipeline output as a durable "software-defined
asset" with its own lineage rather than an anonymous intermediate file. None of that changes
what the graph *is*; it changes who can operate it and what happens automatically when a stage
fails at 3 a.m.

## Scaling out without a cluster: partitioning, Dask, and Spark concepts

The mental model behind every distributed dataframe system traces back to a single 2004 paper,
Dean and Ghemawat's "MapReduce: Simplified Data Processing on Large Clusters," which described
splitting data into **partitions**, applying a function to each partition independently (map),
and combining the partial results (reduce), with the framework handling the parallelism,
retries, and machine failures so the author of the job never touches them directly. The
constraint that made MapReduce awkward for anything iterative was that it wrote intermediate
results to disk between every map and reduce stage. Matei Zaharia and colleagues at UC
Berkeley's AMPLab built Spark specifically to remove that constraint, publishing the design in
2012 as "Resilient Distributed Datasets," keeping intermediate data in memory across stages
and recording enough **lineage**, the sequence of transformations that produced a partition,
that a lost partition can be recomputed from its inputs rather than needing to be replicated
in advance. That lineage-based fault tolerance is Spark's central idea: durability without
copying the data, bought by remembering how to rebuild it.

Two mechanics recur across every one of these systems and are worth knowing by name.
**Partitioning** is how the data is split into independent chunks, and choosing a partition
key well means related rows, everything for one sensor, one run, one customer, end up on the
same partition, which avoids the second mechanic. A **shuffle** is what happens when an
operation needs rows that are scattered across partitions to end up together, a `groupby` on a
column that is not the partition key being the canonical example, and it is expensive because
it means moving data across the network (Spark) or across worker processes (Dask), which is
the single most common source of a distributed job being slower than anyone expected.

[Dask](https://docs.dask.org/en/stable/dataframe-best-practices.html)'s dataframe is the
version of this idea built to feel like pandas: it partitions a large table into many
ordinary pandas dataframes, one per chunk, and most `dask.dataframe` calls describe a lazy
task graph over those chunks that only runs at `.compute()`, in the same spirit as Polars'
`.collect()`. The honest one-line description from the module spec is worth keeping: **Dask
dataframe is pandas that spills to disk or to a cluster**, useful precisely when a table
stops fitting in one machine's memory and you would otherwise have to hand-roll chunking
yourself. Spark's dataframe API plays the same role at larger scale, with a JVM runtime, its
own Catalyst query optimizer, and a much larger operational footprint.

The question this section is really building toward is when *not* to reach for either.
Partitioning, shuffles, and a scheduler are all overhead paid before a single useful byte is
processed, and on data that fits comfortably in memory, that overhead has nothing to amortize
against. The honest answer for a great deal of engineering data, including SECOM, a table
measured in megabytes, is: **just use DuckDB or Polars on one big machine.** The demo for this
session measures exactly that overhead directly, by running the identical logic through Dask
on data far below the scale where Dask earns its keep, and the gap it finds is the entire
argument in one number.

## Where this pushes back

Every tool introduced above buys something at a price, and the prices are worth stating as
plainly as the benefits.

**Polars is faster and stricter, and stricter has a cost.** Its type system is less forgiving
of the casual type-mixing pandas tolerates, its ecosystem of third-party integrations (plotting
libraries, statistical packages, scikit-learn adapters) is younger and thinner than pandas',
and the eager-versus-lazy split is a genuine extra concept a newcomer has to learn before Polars
stops feeling foreign. If your collaborators, your existing codebase, or the library you need
next only speaks pandas, that is frequently the correct reason to stay with pandas rather than
migrate for a speed benefit you may not need. Converting between the two costs little because
of the shared Arrow layout, so "prototype in whichever you know, convert if profiling says so"
is a defensible default.

**Distributed systems trade latency and simplicity for scale, and most engineering data never
needs the scale.** Spinning up Dask or Spark adds a scheduler to reason about, a new class of
failure (a worker dying mid-shuffle) that single-machine pandas never has, and genuine
wall-clock overhead building and dispatching a task graph before any computation starts. That
overhead is fixed cost, largely independent of data size, which is exactly why it dominates on
small data and fades into irrelevance on data too large for one machine. The skill this session
is after is not "know how Dask works," it is "know how to tell, before you start, which side of
that crossover point your job is on."

**Lazy evaluation moves errors away from the line that causes them.** A malformed expression in
a Polars lazy chain, or a Dask task graph, frequently does not raise until `.collect()` or
`.compute()`, several lines and possibly several stages removed from the mistake. Pandas' eager
default fails immediately at the offending line, which is genuinely easier to debug, and it is
a real reason some people keep eager pandas in an exploratory notebook and only reach for
Polars' lazy API once the pipeline shape has stabilized.

**Idempotency and caching are not free either.** A pipeline stage that caches to Parquet has to
be told when the cache is stale, and "delete the cache when anything upstream changes" is a
correctness rule that is trivial to state and easy to get wrong in practice, particularly once
a config parameter changes and nothing invalidates the file that was keyed only on its stage
name. The Makefile's timestamp comparison solves this for file-level dependencies for free;
homegrown caching in a Python script usually has to solve it by hand, and a stale cache that
silently returns yesterday's answer is a more dangerous failure than no cache at all, because
it fails quietly.

:::{admonition} What a practitioner should take from this
:class: tip

Reach for Polars over pandas when profiling shows the bottleneck is real and columnar,
multithreaded execution addresses it. Reach for Dask or Spark only once a table stops fitting
in memory on the machine you actually have, not in anticipation of a scale you might reach
someday. In both cases, measure before you migrate; "it should be faster" is a hypothesis, and
this session's demo is built to let you test it in five minutes rather than assume it.
:::

## In-class demo

We build the same four-stage pipeline, ingest, clean, impute, aggregate, on the SECOM dataset
three times: once in pandas, once in Polars' lazy API, and once spread across Dask
partitions. The pandas and Polars versions should agree on every number, including which of
the 590 sensor columns get dropped, and we benchmark them against each other end to end. The
Dask version exists to make the partitioned, out-of-core execution model concrete on hardware
you can see, and it comes with a genuine trap: a direct port of pandas' `nunique`-based
constant-column check is dramatically slower under Dask than the equivalent check written with
`std`, for reasons specific to how Dask builds its task graph column by column. Watch for the
moment that trap gets fixed, and watch the final Dask-versus-pandas timing, because on data
this size, the distributed version does not win.

The runnable notebook is [`l05-pipelines.ipynb`](l05-pipelines.ipynb). Run it before class if
you would like to see the numbers on your own machine; the download is cached after the first
run.

## Summary

A dataframe operation and a Python `for` loop over the same data can differ in wall-clock time
by two orders of magnitude, and that gap, not a change in what is mathematically being
computed, is most of what "scalable processing" means at the scale most engineering teams
actually operate at. Polars closes that gap further than pandas by combining a typed, Arrow-
based columnar layout with a query optimizer that only a lazy API exposes, and it does so
having learned, in public, from a list of pandas' own limitations that pandas' creator wrote
himself. A batch pipeline built from small, pure, idempotent stages is what turns "a script
that worked once" into something you can rerun, cache, and trust, and Knight Capital is a
reminder that idempotency failures are not a pandas problem, they are a distributed-systems
problem that shows up the moment more than one machine is supposed to agree. Dask and Spark
extend the same dataframe idioms across partitions and, when the data outgrows one machine's
memory, across machines, using a lineage-based model descended directly from MapReduce; the
discipline this session asks you to carry forward is knowing that the crossover point where
that extension pays for itself is a real threshold, measurable rather than assumed, and that
most of the data in this course sits well below it. Next session keeps the same SECOM matrix
and asks a different question: not how fast you can clean it, but how you prove, automatically
and before a bad value reaches a model, that it is clean at all.

## Resources

- [Polars User Guide: Lazy API](https://docs.pola.rs/user-guide/lazy/using/). The eager-versus-lazy
  distinction from the source; read this before writing a `LazyFrame`.
- [Polars User Guide: Expressions](https://docs.pola.rs/user-guide/expressions/). What an
  expression actually is, and why it is what the query optimizer operates on.
- [pandas documentation: Group by](https://pandas.pydata.org/docs/user_guide/groupby.html). The
  canonical reference for split-apply-combine in pandas.
- [pandas documentation: Reshaping](https://pandas.pydata.org/docs/user_guide/reshaping.html).
  `melt` and `pivot`, the wide/long conversions this session leans on.
- [Dask DataFrame: Best Practices](https://docs.dask.org/en/stable/dataframe-best-practices.html).
  Written by the Dask maintainers specifically to head off the "why is my Dask job slower than
  pandas" question this session's demo answers directly.
- [Apache Arrow overview](https://arrow.apache.org/overview/). The columnar memory format both
  Polars and modern pandas interoperate with.
- [Wes McKinney, "Apache Arrow and the '10 Things I Hate About pandas'"](https://wesmckinney.com/blog/apache-arrow-pandas-internals/).
  pandas' creator, in his own words, on where the library he built strains at scale; the design
  motivation for Arrow and, transitively, for Polars.
- [H2O.ai db-benchmark](https://h2oai.github.io/db-benchmark/). A public, reproducible benchmark
  of groupby and join performance across pandas, Polars, Dask, Spark, and others at several
  data sizes; worth checking against your own intuition, and checking again next time you read
  it, since the numbers move as each project improves.
- M. Zaharia et al., "Resilient Distributed Datasets: A Fault-Tolerant Abstraction for
  In-Memory Cluster Computing," *NSDI* 2012. The paper behind Spark's execution model and its
  lineage-based fault tolerance.
- J. Dean and S. Ghemawat, "MapReduce: Simplified Data Processing on Large Clusters," *OSDI*
  2004. The paper the entire distributed-dataframe lineage descends from.
- M. Kleppmann, *Designing Data-Intensive Applications*, Chapter 10 ("Batch Processing").
  Recommended for the deeper argument behind MapReduce-style batch systems and their trade-offs
  against streaming, which is where L6 picks up.
- [In the Matter of Knight Capital Americas LLC](https://www.sec.gov/litigation/admin/2013/34-70694.pdf),
  SEC Release No. 70694, 16 October 2013. The primary source for the deployment failure
  discussed above.
- [U.S. Securities and Exchange Commission, "SEC Charges Knight Capital"](https://www.sec.gov/news/press-release/2013-222).
  The accompanying press release, a shorter read than the full order, for the headline figures.

## Assignment

A3, "Reproducible, validated data pipeline," is released this session and due roughly one week
later. It asks you to build the four-stage pipeline this session covers on SECOM (or a
documented fallback), in pandas and/or Polars, with pandera or Great Expectations checks that
fail the pipeline on injected bad data, logged to MLflow. The full spec and rubric are in
`course/assignments/a03.md`; this paragraph is a pointer, not the rubric.
