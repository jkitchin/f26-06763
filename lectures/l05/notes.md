# Lecture 5: Dataframes, batch pipelines, and scalable processing

:::{admonition} Overview
:class: tip

- **Session** Lecture 5, Week 3
- **Arc** Data Systems
- **Slides** <a href="../../slides/l05/">Deck for this session</a>
- **Demo** [`l05-pipelines.ipynb`](l05-pipelines.ipynb), one pipeline in pandas, Polars, and Dask
- **Assignment 3** released this session
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
memory on a phone. Standing up Spark to process it adds scheduling overhead, latency, and new
ways for the job to fail, purchased for a benefit that does not exist at this size. Judgment
about when a laptop is still the right machine is as much a part of "scalable processing" as
knowing how to reach for more machines when the data actually demands it, and this session
tries to leave you able to make that call instead of defaulting to whichever tool is loudest
this year.

Wes McKinney, who started pandas in April 2008, gave a talk in November 2013 subtitled
"10 Things I Hate About Pandas," and in September 2017 he published
[a post revisiting that list](https://wesmckinney.com/blog/apache-arrow-pandas-internals/)
item by item to explain what he was building instead. The list runs to eleven entries despite
the title, and three of them are the reason this session exists: "No support for
memory-mapped datasets," "'Slow', limited multicore algorithms for large datasets," and
"Eager evaluation model, no query planning." Hold that last one in mind, because the lazy API
that the next section spends most of its length on is a direct answer to it.

The memory numbers in that post are worth quoting because they are more specific than the
usual hand-waving about pandas being memory-hungry. McKinney's stated rule of thumb is that
you should have **five to ten times as much RAM as the size of your dataset**, and he notes
that because pandas stores many internal details as Python objects, "it's not unusual to see
a dataset that is 5GB on disk take up 20GB or more in memory." The root cause he names is a
2011 design decision, the `BlockManager` and its tight coupling to NumPy, which was entirely
reasonable when nobody was analyzing a terabyte in Python and became technical debt when they
were.

That post is the design document for
[Apache Arrow](https://arrow.apache.org/overview/), the columnar memory format Polars is
built on, written by McKinney himself, the person best positioned to know exactly where
pandas was going to strain. The author of the dominant tool in a field wrote down its failure
modes in public, then built the replacement for its internals; that list is worth reading
before you hit the same walls yourself.

## Learning objectives

By the end of this session you should be able to:

- Write idiomatic transformations in pandas and Polars and read/benchmark both.
- Structure a batch pipeline into reproducible, parameterized stages.
- Explain the distributed-processing model (partitioning, lazy graphs) without needing a
  cluster.

## Vectorization, and the shape sensor data actually take

```{index} vectorization
```

Start from the operation every engineering dataset needs constantly: apply the same
arithmetic to every value in a column. In pandas or Polars this is one line,
`df['temp_c'] = (df['temp_f'] - 32) * 5 / 9`, and under the hood it runs as a tight loop over a
contiguous block of memory, in C, with no per-element Python overhead. Write the equivalent as
a Python `for` loop over rows and you are asking the interpreter to create a new Python object,
check its type, and dispatch an arithmetic operator, 590 times a row, for every row in the
table. **Vectorization** is the discipline of expressing a computation as whole-array
operations so the loop happens once, in fast code, instead of once per element in slow code.
The speedup compounds: a wide sensor matrix has hundreds of columns, each paying that tax
independently if you loop.

How large is it really? Rather than repeat a rule of thumb, the figure below measures one
rescale of one column, four ways, on this session's data replicated up to 400,000 rows. At that
size a Python loop lands within a factor of two of **100 times** slower than the vectorized
expression, so "one to two orders of magnitude" is about right. That is a charitable
measurement, incidentally: the loop being timed pulls the column out to a plain Python list
first and then iterates, which is the *fast* way to write a slow loop. Index into the dataframe
on every iteration instead and it gets considerably worse.

```{figure} figures/vectorization-scaling.png
:alt: Log-log plot of wall time against row count for four implementations of the same arithmetic, with .apply the slowest by a wide margin, then the Python row loop, then vectorized pandas and Polars nearly overlapping at the bottom.
:width: 100%

The same arithmetic on one column, four ways, as the row count grows. Vectorized pandas and a
Polars expression are nearly indistinguishable and both scale gently; the Python loop is about
two orders of magnitude slower at 400,000 rows, and `.apply(axis=1)` roughly three. Exact
ratios move by a fifth or so between runs on the same machine, so regenerate it on yours and
read the spacing rather than the digits.
```

The top line inverts a common assumption. `.apply(axis=1)` is **more than thirty times
slower than the loop it replaces**, and three orders of magnitude slower than the vectorized
form. The reason is that `.apply(axis=1)` calls your Python function once per row, and
constructs a whole pandas `Series` object for each row to pass in, so every iteration
allocates and populates a small dataframe-shaped object before your arithmetic runs. The
one-line idiom that looks like the vectorized style is the slowest thing in the plot.

`groupby` is the same idea applied to aggregation. "Mean sensor reading per run, per shift, per
lot" is a `groupby` plus an aggregate, and the library decides internally how to bucket and
reduce the rows, which is again something you do not want to hand-roll with a dictionary and a
loop. Joins extend the same reasoning across tables: attaching a sensor's calibration record
or a lot's recipe metadata to each reading is a join on a shared key, exactly as it was for the
`sensors` and `readings` tables in [Lecture 3](../l03/notes.md), and the same warning applies here that
applied there, that column names should describe a *kind* of measurement, not a particular
sensor or run.

**Reshaping** is the move you will make constantly with instrument exports, because
instruments rarely hand you tidy data. A wide sensor matrix, one column per signal, is
exactly the shape SECOM comes in, and it is often the right shape for a model that wants one
row per training example. But the moment you need to ask "which sensors were most often
missing this month" or "plot every signal on one axis," you want the long form instead, one
row per (run, sensor, value), which is the same wide-versus-long argument from Lecture 3's relational
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

`df.apply(lambda row: ..., axis=1)` looks vectorized because it is one line and touches a whole
dataframe. It is the slowest option measured above, worse than writing the loop out by hand,
because pandas calls your Python function once per row *and* builds a `Series` for each row to
pass into it. If you find yourself writing `.apply` with a lambda that only touches arithmetic
on one or two columns, a plain vectorized expression was available and you reached for the wrong
hammer. The legitimate uses are the ones where no vectorized equivalent exists: calling an
external library per row, or applying genuinely irregular logic that cannot be expressed as
column operations. Reach for `.apply` when you have run out of alternatives, not first.
:::

## Polars and the lazy execution model

```{index} Polars, lazy evaluation, query optimizer, predicate pushdown, projection pushdown
```

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
distinction determines whether that optimizer ever gets a chance to run. `pl.read_csv(...)`
followed immediately by `.filter(...)` and `.select(...)` in **eager**
mode runs each step the moment you call it, exactly like pandas: read every column, then
throw most of it away in the filter. Build the same chain with `pl.scan_csv(...)` instead and
nothing runs at all. You are handed a `LazyFrame`, a description of the computation, and Polars
only executes it when you call `.collect()`. In between, the query optimizer inspects the
whole plan and rewrites it: **predicate pushdown** moves your `filter` as early as possible,
often into the file reader itself, and **projection pushdown** notices which columns the final
`.select()` actually needs and skips reading the rest from disk entirely. The practical
consequence is that `scan_csv(...).filter(...).select(...).collect()` can be dramatically
cheaper than the eager equivalent: the per-operation speed is unchanged, but it computes
*less*, having seen the whole query before running any of it.

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

**Expressions** are the second concept to define, because the query optimizer operates
directly on them. `pl.col("sensor_12").mean()` is an object describing a computation,
which Polars can inspect, combine with other expressions, and
compile into a single multithreaded pass over the data. This is why Polars expressions compose
so differently from pandas method chains: `df.select([pl.col(c).mean() for c in sensor_cols])`
describes 590 reductions as 590 expressions and runs them together, in parallel, in one pass
over the table, rather than as 590 separate calls each re-touching the frame.

### How much does this actually buy you

Enough that the answer depends on the size of your data, which is why you should distrust any
single number, including the ones in this course. On the demo's full four-stage pipeline over
all 1,567 SECOM runs, Polars finishes about **twice** as fast as pandas. On the same 590-column
cleaning computation applied to 200,000 rows, the gap widens to roughly sevenfold. The advantage
is real and it grows with the work, but a benchmark headline quoting 10× or 30× was measured on
grouped aggregations over tens of millions of rows, which is a different question than the one
you are asking.

The factor of two comes from two different sources, and they teach different
lessons. Part of it is the read: parsing this file with the dtypes declared takes Polars around
40 ms against pandas' 75 ms. The rest is the pass structure. The pandas `clean`
and `transform` stages ask three separate questions of every column, distinct count, missing
count, and mean, and each one walks the frame again; the Polars version expresses all three as
expressions in a single `select`, and the optimizer computes them together in one pass, which on
this data is roughly four times faster for that portion of the work.

There is a trap hiding in the read, and it is instructive because the obvious safe choice is the
slow one. Polars infers column dtypes from the first 100 rows by default, which on SECOM
produces an outright failure: it decides sensor 74 is an integer column and then meets a decimal
value 1,458 rows into a 1,567-row file, about 93% of the way through. The reflexive fix,
`infer_schema_length=None`, works but costs around 110 ms, half again as much as pandas' entire
read, because it scans the whole file to determine what you already knew. Declaring the schema
instead, `schema_overrides={...: pl.Float64}`, is the fastest option at around 40 ms and the only
one that cannot be surprised by a value near the end of the file. Stating your assumptions in
code is both cheaper and safer than having the library guess at them: a schema is the
cheapest executable check you will ever write.

This is the first appearance of a pattern the rest of the session leans on. Every performance
claim here has a data-size regime attached to it, and moving between regimes reverses
conclusions. Polars over pandas is negligible at a thousand rows and substantial at a million.
Dask over pandas is catastrophic at a thousand rows and eventually necessary. The skill being
taught is not memorizing which tool wins, it is knowing that the question is incomplete until
someone says how much data.

### Arrow and Parquet are not the same thing

```{index} Apache Arrow, Parquet
```

Interop keeps this practical rather than academic. Two names
get used interchangeably here and should not be.
[**Arrow**](https://arrow.apache.org/docs/format/Columnar.html) is an *in-memory* format. Its
whole design goal is that a CPU can operate on the bytes directly, so the data is laid out
uncompressed, in the natural layout for the machine.
[**Parquet**](https://parquet.apache.org/docs/file-format/) is an *on-disk* format, designed
for space efficiency with heavy compression and encoding, which means it cannot be computed on
until it has been decoded. The Arrow project's own
[FAQ](https://arrow.apache.org/faq/) states the division plainly: "Arrow and Parquet complement
each other and are commonly used together in applications. Storing your data on disk using
Parquet and reading it into memory in the Arrow format will allow you to make the most of your
computing hardware."

That is exactly the pipeline shape this session recommends: Parquet between stages, Arrow
within one. And because Polars, pyarrow, DuckDB and modern pandas all speak the same in-memory
layout, moving a table between them is often a matter of sharing a pointer to the same buffers
rather than serializing and reparsing. Do not over-read "zero copy," though; it holds for
numeric columns that already match Arrow's representation, and a conversion that has to
materialize a validity bitmap or unbox Python strings still costs real time. The weaker and
more useful claim is this: crossing a library boundary inside one pipeline is cheap enough
that you should pick each stage's tool on its merits rather than picking one
library for the whole pipeline to avoid conversions.

## Designing a batch pipeline: stages, idempotency, and caching

```{index} batch pipeline, idempotency, deterministic output
```

A **batch pipeline** is nothing more exotic than a sequence of transform stages, each one a
pure function that reads an input and produces an output, run on a schedule or on demand over
a bounded chunk of data. Assignment 3 asks for exactly four: **ingest** (read the raw file into a typed
frame), **clean** (drop constant and high-missingness columns), **transform** (impute, using
statistics computed only on the training split), and **persist** (cache the result, typically
to Parquet). Keeping each stage a pure function with a typed input and output matters more
than the specifics of any individual stage: it makes the pipeline testable, cacheable, and
debuggable one stage at a time instead of as one large opaque script.

What the `clean` stage actually removes looks like housekeeping ("drop constant and
high-missingness columns") but is closer to triage. On the SECOM
training split, 122 of the 590 sensor columns are **constant**: one distinct value across every
run, which is to say a signal that was logged but never varied and can carry no information
about anything. A further 28 columns are missing more than 40% of their readings, the worst of
them absent for 90% of runs. The two sets do not overlap at all, which is itself informative:
these are two independent failure modes of an instrumentation system, a sensor wired up but
never varying, and a sensor that reports only intermittently.

```{figure} figures/secom-column-triage.png
:alt: Bar chart of all 590 SECOM sensor columns sorted by the fraction of readings missing, with constant columns colored separately and a dashed line at the 40 percent missingness threshold.
:width: 100%

Every sensor column in the SECOM training split, sorted by missingness. The dashed line is the
40% cutoff used in the demo; the columns marked in red are constant, carrying one distinct
value across all 1,253 training runs. 122 constant plus 28 too-sparse leaves 440 of the
original 590 columns, and the two rules select disjoint sets.
```

Note what that means for the shape of the work: a quarter of this feature matrix is discarded
before any modeling happens, on the strength of two one-line rules. That is typical of
industrial sensor exports rather than exceptional, and it is why the `clean` stage deserves to
be a named, tested, individually inspectable function rather than three lines buried in a
script. The thresholds in it are decisions, and Assignment 3 asks you to put them in a config file for
exactly that reason.

**Idempotency** is the property that running a stage twice on the same input produces the same
output, byte for byte, and it sounds like a minor implementation detail until you have to
recover from a partial failure. If `clean` is idempotent, rerunning it after a crash is free:
you get back exactly what you had, and you can move on. If it is not, because it depended on
the current time, an unseeded random draw, or the order files happened to arrive in, rerunning
it silently produces a different pipeline than the one that ran in production, and a
"reproduction" of last week's numbers quietly stops being one. **Deterministic outputs** are
idempotency's twin requirement: pin your random seeds, sort before any operation whose result
depends on row order, and treat "the same input always yields the same output" as a
correctness requirement.

### Case study: one server out of eight

```{index} pair: case study; Knight Capital
```

On 1 August 2012, Knight Capital Americas LLC lost more than \$460 million in roughly
forty-five minutes. Knight was not a marginal firm: the SEC's order records that its trading
"generally represented approximately ten percent of all trading in listed U.S. equity
securities." The cause was a deployment, and every step of it is documented in the
[SEC's administrative order](https://www.sec.gov/litigation/admin/2013/34-70694.pdf), a
detailed post-mortem of a batch job that partially succeeded.

The New York Stock Exchange was launching a Retail Liquidity Program (RLP) on 1 August, and to
let its customers participate, Knight wrote new code for SMARS, its automated order router.
Beginning on 27 July, that code was deployed in stages across the eight servers SMARS ran on,
over successive days. One technician did not copy it to the eighth server. That, on its own,
was survivable. Three earlier decisions turned it into a catastrophe.

First, the new code **repurposed a flag** that had previously activated an old feature called
Power Peg. Knight had stopped using Power Peg in 2003, but had never deleted it; it remained
"present and callable." So on the one server that never received the new code, setting the
flag to "yes" did not enable RLP, it woke Power Peg.

Second, Power Peg had itself been silently broken for seven years. In 2005 Knight moved the
function that counted how many shares of an order had already been filled to an earlier point
in the code sequence, and, in the SEC's words, "did not retest the Power Peg code after moving
the cumulative quantity function to determine whether Power Peg would still function correctly
if called." The dead code was untested, and it was missing the exact
check that would have told it to stop.

Third, nobody verified the deployment. The order is blunt about it: "Knight did not have a
second technician review this deployment and no one at Knight realized that the Power Peg code
had not been removed from the eighth server, nor the new RLP code added. Knight had no written
procedures that required such a review."

At the open on 1 August, seven servers processed orders correctly. The eighth received 212
parent orders and, because the code that would have counted completed fills had been moved
away in 2005, sent child orders continuously without regard to whether the parent orders were
already filled. In about forty-five minutes it produced **four million executions in 154
stocks, for more than 397 million shares**, leaving Knight with an unintended \$3.5 billion
net long position in 80 stocks and a \$3.15 billion net short position in 74 others.

There is one more detail that belongs in a course about pipelines. Starting at about 8:01 a.m.,
ninety minutes before the market opened, Knight's own systems sent 97 automated emails
referencing SMARS and reporting an error described as "Power Peg disabled." The signal existed,
in writing, before any money was lost. As the SEC put it, "Knight did not design these types of
messages to be system alerts, and Knight personnel generally did not review them when they were
received."

:::{admonition} What a practitioner should take from this
:class: tip

A deployment, a migration, and a nightly pipeline run are all batch jobs, and all three fail
the same way when partial success looks identical to full success. Three habits follow, and
each maps onto something you will build in Assignment 3.

Build the reconciliation check into the job. After any batch operation meant to leave every
unit in the same state, compare actual output against expected: a row count, a content hash, a
version string read back from each machine. The job must raise seven-of-eight as an error itself,
before anyone downstream discovers it. The demo notebook does the small version of this by
hashing its Parquet output twice and comparing.

Delete dead code, and distrust dormant code you cannot delete. Power Peg was harmless right up
to the moment a repurposed flag made it reachable, and by then it had been quietly broken for
seven years, because code nobody calls is code nobody tests. A pipeline stage that is
switched off by config is in exactly this category.

Make a signal something, or make it nothing. Ninety-seven emails nobody reads are worse than
no emails at all, because they create the appearance of monitoring. If a condition matters,
it should fail a check or page a human; if it does not, stop emitting it.
:::

Caching intermediate outputs to **Parquet** between stages makes iteration practical day to
day, beyond correctness. A pipeline that reruns `ingest` and `clean` from the raw file every
time you want to iterate on the `transform` stage wastes minutes you will lose thousands of
times over a semester. Persist each stage's output, and make each stage check for its cached
output before recomputing, and iteration on stage four stops requiring you to redo stages one
through three.

## Orchestration, or when a plain DAG is enough

```{index} orchestration, directed acyclic graph, Makefile
```

Every pipeline with more than one stage is, whether or not anyone calls it one, a **directed
acyclic graph** (DAG): a set of steps with dependencies between them, and no step depends on its own
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

For a single author running a pipeline on one machine, a Makefile is frequently enough, a
correctly sized tool for a small DAG. [Prefect](https://docs.prefect.io/) and
[Dagster](https://docs.dagster.io/) add automatic retries on transient failure, a scheduler,
a UI showing which run failed and why, alerting, and, in Dagster's case, an explicit model
of each pipeline output as a durable "software-defined asset" with its own lineage rather
than an anonymous intermediate file, once a pipeline has to run unattended, on a schedule,
and be trusted by people who are not the author. None of that changes what the graph *is*;
it changes who can operate it and what happens automatically when a stage fails at 3 a.m.

## Scaling out without a cluster: partitioning, Dask, and Spark concepts

```{index} partitioning, shuffle, lineage, Dask, Apache Spark
```

The mental model behind every distributed dataframe system traces back to a single 2004 paper,
Dean and Ghemawat's
[MapReduce: Simplified Data Processing on Large Clusters](https://research.google.com/archive/mapreduce-osdi04.pdf),
which described
splitting data into **partitions**, applying a function to each partition independently (map),
and combining the partial results (reduce), with the framework handling the parallelism,
retries, and machine failures so the author of the job never touches them directly. The
constraint that made MapReduce awkward for anything iterative was that it wrote intermediate
results to disk between every map and reduce stage. Matei Zaharia and colleagues at UC
Berkeley's AMPLab built Spark specifically to remove that constraint, publishing the design in
2012 as
[Resilient Distributed Datasets](https://www.usenix.org/system/files/conference/nsdi12/nsdi12-final138.pdf),
keeping intermediate data in memory across stages
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
the single most common source of a distributed job being slower than anyone expected. Dask's
own documentation makes the same point with a sensor-shaped example: "if your data is arranged
by customer ID but now you want to arrange it by time, all of your partitions will have to talk
to each other to exchange shards of data."

### The operation that tells you which kind you have

In practice, an operation either can be answered partition-locally and then combined, or it
needs a shuffle. A **mean** is the first
kind: each partition reports a sum and a count, and the coordinator adds them up. An **exact
distinct count** is the second: no partition can know whether the value `7.2` it holds also
appears in some other partition, so the partitions have to compare notes.

That difference is not academic, and this session's demo is built around measuring it. Asking
Dask for `nunique` on all 590 SECOM columns takes **tens of seconds** on 1,253 rows, a table
small enough to print. Asking for `std` on the same 590 columns takes **well under a tenth of a
second**, and identifies exactly the same 122 constant columns, because a numeric column is
constant precisely when its standard deviation is zero. That is a factor of several hundred, for
the same answer. Three measurements in the notebook show why the gap is so large:
the cost scales with the number of *columns*, it gets **worse** as you add partitions, and it
does not move when you quadruple the number of *rows*. A cost that ignores the size of the data
is not the cost of processing the data. Inspecting the task graph makes it concrete: 100
columns of `nunique` compile to roughly ten thousand tasks, the same 100 columns of `std` to
eighteen.

```{figure} figures/dask-overhead.png
:alt: Two panels. Left, wall time versus row count for pandas, Polars and Dask on the same 590-column cleaning stage, with Dask far above the others at small sizes and converging slowly. Right, wall time versus partition count for nunique and std, with nunique rising steeply as partitions are added while std stays flat.
:width: 100%

Left: the same 590-column cleaning stage in three libraries, as SECOM is replicated up to
200,000 rows (about a gigabyte in memory). Dask starts more than 30× slower than pandas and is
still over 2× slower at the right-hand edge: there is no crossover inside this range, because the
data still fits in RAM throughout it. Note also that Polars' margin over
pandas *grows* with size, from negligible to roughly sevenfold. Right: two ways to find the
constant columns.
`nunique` needs a shuffle per column and gets steadily slower as partitions are added; `std` is
a combinable reduction and does not care. Both select the same 122 columns.
```

The general rule this yields is more useful than the specific bug. Before porting an operation
to a distributed engine, ask whether it is a reduction or a shuffle. If it is a shuffle and you
are doing it per column across a wide matrix, you are asking for hundreds of shuffles, and
there is very often a combinable reduction that answers the same question.

:::{admonition} One caveat on "constant iff the standard deviation is zero"
:class: warning

That equivalence is exact in arithmetic and only nearly exact in floating point. A column holding the single
value `14.62` in every row has a true variance of zero, but the variance is *computed* from
sums of squared deviations, and the rounding can leave you with `5.3e-15` instead of `0.0`. A
literal `std == 0` test then declares that constant column non-constant and keeps it.

On SECOM the substitution happens to be clean, and the 122 columns match exactly. Do not
generalize from that. Write the test with a tolerance, `std < 1e-12`, or use a distinct-value
count when you can afford it, and be aware that you are choosing between an exact test that is
expensive to distribute and a cheap test that needs an epsilon.
:::

[Dask](https://docs.dask.org/en/stable/dataframe-best-practices.html)'s dataframe is the
version of this idea built to feel like pandas: it partitions a large table into many
ordinary pandas dataframes, one per chunk, and most `dask.dataframe` calls describe a lazy
task graph over those chunks that only runs at `.compute()`, in the same spirit as Polars'
`.collect()`. The module spec's one-line description holds up: **Dask
dataframe is pandas that spills to disk or to a cluster**, useful precisely when a table
stops fitting in one machine's memory and you would otherwise have to hand-roll chunking
yourself. Spark's dataframe API plays the same role at larger scale, with a JVM runtime, its
own Catalyst query optimizer, and a much larger operational footprint.

The question this section is really building toward is when *not* to reach for either.
Partitioning, shuffles, and a scheduler are all overhead paid before a single useful byte is
processed, and on data that fits comfortably in memory, that overhead has nothing to amortize
against. The honest answer for a great deal of engineering data, including SECOM, a table
measured in megabytes, is: **just use [DuckDB](https://duckdb.org/) or Polars on one big
machine.**

You do not have to take that from a lecturer with an axe to grind, because it is the first
thing Dask's own maintainers say. Their
[DataFrame best-practices page](https://docs.dask.org/en/stable/dataframe-best-practices.html)
opens with a section titled, in full, **"Use Pandas"**:

> For data that fits into RAM, pandas can often be faster and easier to use than Dask
> DataFrame. While "Big Data" tools can be exciting, they are almost always worse than normal
> data tools while those remain appropriate.

The second section is titled "Reduce, and then use pandas," and makes the follow-on point: even
on genuinely large data, there is usually a step where a filter or an aggregate has cut the
table down to something one machine can hold, and the right move at that step is to call
`.compute()` and go back to ordinary tools. A pipeline moves in and out of distributed
execution as the data shrinks or grows at each stage.

The rest of that page is the best short list anywhere of how to make Dask fast once you do need
it: set an index if you will slice on it, do it rarely because it is a shuffle, and expect
`set_index`, `merge` and `join` to be the expensive operations. The demo for this session
measures the overhead directly instead, by running identical logic through Dask on data far
below the scale where Dask earns its keep.

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
is after is knowing how to tell, before you start, which side of
that crossover point your job is on.

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
three times: once in pandas, once in Polars' lazy API, and once spread across Dask partitions.
The pandas and Polars versions are checked against each other twice, once on which of the 590
columns survive cleaning and once on the imputed values themselves, and then benchmarked end to
end. Expect Polars to win by roughly 2×, not by the order of magnitude the marketing suggests,
because at 1,567 rows a large share of both runtimes is CSV parsing.

The Dask version exists to make the partitioned execution model concrete on hardware you can
see. A direct port of the pandas `nunique` constant-column check takes about 23 seconds; the
equivalent written with `std` takes about 80 milliseconds and selects exactly the same 122
columns. We measure three things to establish
that the difference is scheduling overhead and not computation: cost per column, cost versus
partition count, and cost versus row count. The last one is the clincher, because quadrupling
the rows does not change the runtime.

Two other bugs in the notebook are worth arriving prepared for, because both are the kind that
does not raise an exception where the mistake is. SECOM's label file stores its timestamp as a
single *quoted* field, so splitting on whitespace into three columns yields an all-`NaT`
timestamp and a "daily" aggregate over one meaningless group. And Polars' default schema
inference commits to an integer type for sensor 74 on the strength of 100 rows, then fails on a
decimal value 1,458 rows in. Both are caught the same way: by checking a number against an
expectation rather than assuming the parse worked.

The runnable notebook is [`l05-pipelines.ipynb`](l05-pipelines.ipynb). Run it before class if
you would like to see the numbers on your own machine; the download is cached after the first
run. Budget about a minute for the Dask cells, which are slow on purpose.

## Summary

A vectorized column operation and a Python loop over the same data differ by roughly two orders
of magnitude, and `.apply(axis=1)`, the idiom that looks like the fast one, is worse than the
loop by another factor of thirty. That gap in wall-clock time, with no change in what is
mathematically computed, is most of what "scalable processing" means at the scale most
engineering teams actually operate at. Polars widens it further by combining a typed,
Arrow-based columnar layout with a query optimizer that only its lazy API exposes, answering
the specific complaint, "eager evaluation model, no query planning," that pandas' own
creator put on his list of the things he would change.

A batch pipeline built from small, pure, idempotent stages turns "a script that worked once"
into something you can rerun, cache, and trust. Knight Capital is the reminder that the
expensive failures in this space are batch jobs that partially succeeded while reporting
success, with dead code nobody had tested and alerts nobody had designed to be read.

Dask and Spark extend the same dataframe idioms across partitions and, when the data outgrows
one machine's memory, across machines, using a lineage-based model descended directly from
MapReduce. What this session asks you to carry forward is that their crossover point is a real,
measurable threshold rather than a matter of taste, that most of the data in this course sits
well below it, and that the way you tell is to time both. Along the way, three of the bugs in
the demo notebook, a quoted timestamp, an over-eager schema inference, and a per-column
shuffle, were all found the same way: a number came back that did not match what somebody
expected.

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
  Read at least the first two sections, "Use Pandas" and "Reduce, and then use pandas." The
  maintainers of the distributed tool telling you when not to use it is the most credible source
  available for the judgment this session is about.
- [Apache Arrow overview](https://arrow.apache.org/overview/) and the project's
  [FAQ on Arrow versus Parquet](https://arrow.apache.org/faq/). The second one settles the
  in-memory-versus-on-disk confusion that costs people hours.
- [Apache Parquet file format](https://parquet.apache.org/docs/file-format/). The on-disk format
  every stage of your Assignment 3 pipeline will cache to; skim the structure so you know why it reads
  columns cheaply and rows expensively.
- [Wes McKinney, "Apache Arrow and the '10 Things I Hate About pandas'" (2017)](https://wesmckinney.com/blog/apache-arrow-pandas-internals/).
  pandas' creator on where the library he built strains at scale, revisiting his own 2013 list
  item by item. The source of the 5-to-10× RAM rule of thumb quoted above, and the design
  motivation for Arrow and, transitively, for Polars.
- [Tom Augspurger, "Modern Pandas"](https://tomaugspurger.net/posts/modern-1-intro/). A series on
  writing idiomatic, fast pandas, recommended by the Dask documentation itself. The chapters on
  indexing and performance are the ones that change how you write code.
- [DuckDB](https://duckdb.org/). The other correct answer to "my data got big but not
  cluster-big": an in-process analytical database that reads Parquet directly and, like Polars,
  has a real query optimizer. Pairs naturally with the SQL from [Lecture 3](../l03/notes.md).
- [db-benchmark](https://duckdblabs.github.io/db-benchmark/), a reproducible benchmark of groupby
  and join performance across pandas, Polars, DuckDB, Dask, Spark and others at 0.5, 5 and 50 GB.
  Note the provenance carefully: the widely linked original at
  `h2oai.github.io/db-benchmark` still says on its front page that it "runs regularly against
  very latest versions of these packages and automatically updates," but its repository has had
  no commits since June 2023, so those numbers are frozen years in the past. This DuckDB Labs
  fork is the maintained continuation. A benchmark page that claims to be live is not
  necessarily live; check when the code last ran before you cite a number from it.
- M. Zaharia et al.,
  ["Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing"](https://www.usenix.org/system/files/conference/nsdi12/nsdi12-final138.pdf),
  *NSDI* 2012. The paper behind Spark's execution model and its lineage-based fault tolerance.
- J. Dean and S. Ghemawat,
  ["MapReduce: Simplified Data Processing on Large Clusters"](https://research.google.com/archive/mapreduce-osdi04.pdf),
  *OSDI* 2004. The paper the entire distributed-dataframe lineage descends from. Short, readable,
  and worth it for section 3.1 alone, on how the framework hides failure from the job author.
- M. Kleppmann, *Designing Data-Intensive Applications*, Chapter 10 ("Batch Processing").
  Recommended for the deeper argument behind MapReduce-style batch systems and their trade-offs
  against streaming.
- [In the Matter of Knight Capital Americas LLC](https://www.sec.gov/litigation/admin/2013/34-70694.pdf),
  SEC Release No. 70694, 16 October 2013. The primary source for the deployment failure
  discussed above.
- [U.S. Securities and Exchange Commission, "SEC Charges Knight Capital"](https://www.sec.gov/news/press-release/2013-222).
  The accompanying press release, a shorter read than the full order, for the headline figures.

## Assignment

Assignment 3, "Reproducible, validated data pipeline," is released this session (Wednesday 9 September
2026) and is due Wednesday 16 September 2026. It asks you to build the
four-stage pipeline this session covers on SECOM (or a documented fallback), in pandas and/or
Polars, with pandera or Great Expectations checks that fail the pipeline on injected bad data,
logged to MLflow. Start on the pipeline stages now and add the validation checks as you go. This
is a pointer, not the rubric.
