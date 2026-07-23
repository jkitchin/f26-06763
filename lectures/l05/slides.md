---
marp: true
theme: course
paginate: true
header: "06-763 · L5"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L5 · Dataframes & scalable processing

## Week 3 · Data Systems

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why this matters: the loop vs. the column
2. Dataframe fundamentals, vectorized
3. Polars and the lazy execution model
4. Designing a batch pipeline
5. Orchestration: when a plain DAG is enough
6. Scaling out: Dask, Spark, and when not to
7. Live demo: one pipeline, three ways

<!-- 110 min. Budget roughly 15 / 15 / 20 / 15 / 10 / 15 / 20 demo.
     SECOM: 1,567 runs x 590 sensors. If running long, cut the
     orchestration section, not the demo. -->

---

<!-- _class: section -->

# Why this matters

---

## The spreadsheet the engineer gets handed

1,567 manufacturing runs. 590 sensor columns.

Somewhere in there: the difference between a wafer
that ships and one that gets scrapped.

---

## The first working version

```python
for row in data:
    for sensor in row:
        clean(sensor)
```

It runs. It even finishes, on 1,567 rows.

---

## Then the data grows

Next month: 15,670 rows. A second fab line.

The "quick script" goes from 4 seconds to 7 minutes.

Nothing about this is a modeling problem.

---

## It's an architecture problem

A Python loop pays interpreter overhead
**590 times a row, every row.**

The honest description of the work is a handful
of whole-column operations.

---

## The other failure: reaching for a cluster you don't need

"Scalable processing" invites the assumption
that bigger tools are strictly better.

SECOM is a few **megabytes**. It fits on a phone.

---

## Judgment cuts both ways

- Loop instead of vectorizing → too slow, needlessly
- Spark instead of a laptop → too complex, needlessly

Both are the same mistake: not matching the tool to the data.

---

## Hear it from the source

2017: Wes McKinney (pandas' creator) publishes
**"10 Things I Hate About pandas."**

Single-core execution. No native out-of-core support.
An in-memory footprint several times the raw data.

[wesmckinney.com/blog/apache-arrow-pandas-internals](https://wesmckinney.com/blog/apache-arrow-pandas-internals/)

---

## That post is a design document

It's the motivation for **Apache Arrow**,
the columnar format Polars is built on.

The person who built the tool wrote down
exactly where it strains. Read that list first.

---

<!-- _class: section -->

# Dataframe fundamentals
## vectorized

---

## Vectorization

```python
df['temp_c'] = (df['temp_f'] - 32) * 5 / 9
```

Runs as a tight loop over contiguous memory, **in C**.
No per-element Python dispatch.

---

## The speedup is not a rounding error

Vectorized vs. row-wise Python loop, numeric columns:

**one to two orders of magnitude.**

590 columns each paying that tax independently, if you loop.

---

## `groupby`: the same idea, for aggregation

"Mean reading per run, per shift, per lot"

= one `groupby` + one aggregate.

The library decides how to bucket and reduce. You don't hand-roll it.

---

## Joins: the same idea, across tables

Attach calibration or recipe metadata by a shared key.

Same rule from L3: a column is a **kind** of measurement,
never a particular sensor or run.

---

## Reshaping: wide ↔ long

SECOM arrives **wide**: one column per sensor.

Right shape for a model. Wrong shape for
"which sensors are most often missing?"

---

## `melt` and `pivot`

```python
long = wide.melt(
    id_vars=['run_id', 'label'],
    var_name='sensor', value_name='reading'
)
```

Reshape explicitly. Don't maintain two copies that drift.

---

## The pitfall: `.apply` isn't vectorized

```python
df.apply(lambda row: row['a'] + row['b'], axis=1)
```

Looks like one line. Still calls your Python function
**once per row.** Nearly as slow as the loop it hides.

---

<!-- _class: section -->

# Polars and the
## lazy execution model

---

## Why a new dataframe library

pandas (2008): NumPy arrays, often boxed objects
for strings/nulls, mostly single-threaded.

Polars: Rust, built on Arrow, **typed columnar
storage, multithreaded by default.**

---

## The key distinction: eager vs. lazy

**Eager** (`pl.read_csv`): every step runs immediately.

**Lazy** (`pl.scan_csv`): you get a plan, a `LazyFrame`.
Nothing runs until `.collect()`.

---

## The optimizer only sees the lazy plan

```python
(
    pl.scan_parquet("sensors/*.parquet")
    .filter(pl.col("run_id") > 1000)
    .select(["run_id", "sensor_12", "sensor_87"])
    .collect()
)
```

Nothing executes until `.collect()`.

---

## What the optimizer does with it

**Predicate pushdown**: move `filter` as early as possible,
often into the file reader itself.

**Projection pushdown**: only read the columns
the final `.select()` actually needs.

---

## Why this matters more than "Polars is fast"

Not faster at the same computation.

Faster because it computes **less**,
having seen the whole query first.

---

## Expressions are what make this possible

```python
pl.col("sensor_12").mean()
```

Not a value. An **object describing a computation**,
one Polars can inspect, combine, and compile.

---

## 590 expressions, one pass

```python
df.select([pl.col(c).mean() for c in sensor_cols])
```

Runs together, in parallel, in one pass:
not 590 separate re-touches of the frame.

---

## Interop: Arrow underneath both

Polars ↔ pandas ↔ Arrow table:
usually zero-copy, not a serialization step.

Matters when one pipeline mixes all three.

---

<!-- _class: section -->

# Designing a
## batch pipeline

---

## Four stages

**ingest** → **clean** → **transform** → **persist**

Each one a pure function: typed input, typed output.

---

## Why pure functions

Testable and cacheable **one stage at a time**,
not as one large opaque script.

Debug stage 3 without rerunning stages 1–2.

---

## Idempotency

Running a stage twice on the same input
produces the **same output, byte for byte.**

Sounds minor. Matters the moment something crashes.

---

## Deterministic outputs

- Pin random seeds
- Sort before order-dependent operations

"Same input, same output" is a **correctness**
requirement, not a nicety.

---

## Case: one server out of eight

**Knight Capital, 1 August 2012.**
~$460M lost in 45 minutes.

New order-routing code deployed to 8 servers.
It reached **7**.

---

## The eighth server

Old test code ("Power Peg") was still present.
A repurposed flag reactivated it instead.

Nothing detected the fleet was no longer
running one consistent version.

[SEC Release No. 70694](https://www.sec.gov/litigation/admin/2013/34-70694.pdf)

---

## The generalization

A rollout across 8 machines **is** a batch job
whose "rows" are servers.

7-of-8 success looked identical to full success,
until the output made it obvious.

---

## What a practitioner should take from this

Build the reconciliation check **into the job**:
a count, a hash, a checksum of the output.

Don't trust "the job completed" to mean
"the job completed correctly everywhere."

---

## Caching to Parquet between stages

Rerunning `ingest` + `clean` every time you
iterate on `transform` wastes minutes,
thousands of times over a semester.

Persist each stage. Check the cache before recomputing.

---

<!-- _class: section -->

# Orchestration
## when a plain DAG is enough

---

## Every multi-stage pipeline is a DAG

A set of steps, dependencies between them,
no step depends on its own output.

---

## The oldest tool that takes this seriously

```makefile
clean.parquet: ingest.parquet clean.py
	python clean.py ingest.parquet clean.parquet

transform.parquet: clean.parquet transform.py
	python transform.py clean.parquet transform.parquet
```

`make` compares timestamps. Reruns only what changed.

---

## A Makefile is not "a step down"

For one author, one machine: often **enough.**

Correctly sized, not under-powered.

---

## What Prefect / Dagster add

- Automatic retries on transient failure
- A scheduler and a UI: which run failed, why
- Alerting
- Dagster: each output as a durable, lineage-tracked **asset**

---

## What they don't change

The graph itself.

They change **who can operate it**, and what
happens automatically when a stage fails at 3 a.m.

[Prefect docs](https://docs.prefect.io/) · [Dagster docs](https://docs.dagster.io/)

---

<!-- _class: section -->

# Scaling out
## without a cluster

---

## Where this all comes from

**MapReduce** (Dean & Ghemawat, OSDI 2004):
split into partitions, map each independently, reduce.

The framework handles parallelism and failures.

---

## MapReduce's weak spot

Wrote intermediate results to disk
between **every** map and reduce stage.

Awkward for anything iterative.

---

## Spark's fix

Zaharia et al., UC Berkeley AMPLab, 2012:
**Resilient Distributed Datasets.**

Keep intermediate data in memory across stages.

---

## Lineage-based fault tolerance

Record the transformations that produced a partition.

Lost a partition? **Recompute it from lineage**:
durability without copying the data upfront.

---

## Two mechanics that recur everywhere

**Partitioning**: split data into independent chunks.
Choose the key so related rows land together.

**Shuffle**: rows scattered across partitions
have to be gathered, expensive, over the network.

---

## Dask DataFrame

Partitions a big table into many ordinary
pandas frames. Lazy task graph, like Polars:
nothing runs until `.compute()`.

> Dask DataFrame is **pandas that spills**
> to disk or to a cluster.

---

## Spark DataFrame

Same role, larger scale: JVM runtime,
its own Catalyst optimizer, bigger operational footprint.

---

## The question that actually matters

Partitioning, shuffles, a scheduler:
all overhead paid **before** one useful byte is processed.

On data that fits in memory: pure cost.

---

## The honest answer for SECOM

A few megabytes. Nowhere near the crossover point.

> Just use DuckDB or Polars
> on one big machine.

---

<!-- _class: section -->

# Where this
## pushes back

---

## Polars vs. pandas

| pandas | Polars |
|---|---|
| forgiving types | stricter, less forgiving |
| huge ecosystem | younger, thinner ecosystem |
| eager only | eager **and** lazy, one more concept |
| everyone already knows it | migration cost if collaborators don't |

---

## When pandas is still the right call

Collaborators, codebase, or the next library
in the chain only speaks pandas.

Shared Arrow layout → converting later is cheap.
Prototype in what you know; convert if profiling says so.

---

## Distributed systems: what you're really paying for

- A scheduler to reason about
- A new failure mode: a worker dying mid-shuffle
- Real wall-clock overhead building the task graph

**Fixed cost, size-independent**: dominates on small data.

---

## Lazy evaluation moves the error

A bad expression in a lazy chain often doesn't
raise until `.collect()` / `.compute()`,
lines away from the mistake.

Eager pandas fails **at the line**. Genuinely easier to debug.

---

## Caching isn't free either

"Delete the cache when anything upstream changes"
is easy to state, easy to get wrong.

A stale cache that returns yesterday's answer
is worse than no cache: it fails **quietly**.

---

## What a practitioner should take from this

Reach for Polars when profiling shows a real,
columnar bottleneck.

Reach for Dask/Spark when data stops fitting
in memory, not in anticipation of it.

---

## Measure before you migrate

"It should be faster" is a hypothesis.

Today's demo lets you test it in five minutes.

---

<!-- _class: demo -->

# Demo

## `l05-pipelines.ipynb`

One 4-stage pipeline: pandas, Polars lazy, and Dask.

---

## What to watch

- pandas vs. Polars: same numbers, different time
- A **direct port** of `nunique` into Dask: painfully slow
- The `std`-based fix: correct **and** fast
- Final Dask vs. pandas: at this size, distributed loses

---

## Recap

- Vectorize; a Python loop over rows pays per-element tax
- Polars: typed, columnar, lazy, an optimizer that sees the whole query
- 4 pure pipeline stages: ingest → clean → transform → persist
- Idempotency isn't optional; Knight Capital lost $460M without it
- Dask/Spark: real tools, real overhead. Know your crossover point

---

## Next

**Assignment** A3 released today, due ~1 week
**Reading** Polars lazy API docs; Kleppmann Ch. 10
**L6** Same SECOM matrix, a different question: not how fast
you can clean it, but how you *prove* it's clean, automatically,
before a bad value reaches a model

Full notes, with all sources: `lectures/l05/notes.md`
