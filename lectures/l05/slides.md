---
marp: true
theme: course
paginate: true
header: "06-763 / L5"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# Lecture 5: Dataframes & scalable processing

## Week 3, Data Systems

**Systems and Toolchains for AI Engineers**

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

## Why this matters

1,567 manufacturing runs. 590 sensor columns.

Somewhere in there: the difference between a wafer
that ships and one that gets scrapped.

```python
for row in data:            # the first working version
    for sensor in row:
        clean(sensor)
```

It runs. It even finishes, on 1,567 rows.

---

## Why this matters, then the data grows

Next month: 15,670 rows. A second fab line.

The "quick script" goes from 4 seconds to 7 minutes.

Nothing about this is a modeling problem.

**It's an architecture problem.**

A Python loop pays interpreter overhead
**590 times a row, every row.**

The honest description of the work is a handful
of whole-column operations.

**Judgment cuts both ways.**

- Loop instead of vectorizing → too slow, needlessly
- Spark instead of a laptop → too complex, needlessly

SECOM is a few **megabytes**. It fits on a phone.

Same mistake twice: not matching the tool to the data.

---

## Why this matters, hear it from the source

2013 talk, revisited in a 2017 post by
Wes McKinney, who started pandas in 2008:

**"10 Things I Hate About Pandas"** (there are 11)

[wesmckinney.com/blog/apache-arrow-pandas-internals](https://wesmckinney.com/blog/apache-arrow-pandas-internals/)

<!-- The list is from a Nov 2013 talk; the 2017 post walks it item by item and
     explains what he built instead. Don't say "he published a list in 2017". -->

**Three of the eleven, verbatim.**

- "No support for memory-mapped datasets"
- "'Slow', limited multicore algorithms for large datasets"
- **"Eager evaluation model, no query planning"**

Hold that last one. It's what "lazy" answers.

---

## Why this matters, and the memory number

> you should have **5 to 10 times as much RAM**
> as the size of your dataset

"a dataset that is 5GB on disk take up 20GB
or more in memory."

That post is the design document for **Apache Arrow**.

<!-- The author of the dominant tool wrote down where it strains, then built the
     replacement for its internals. That's why the list is worth reading.
     Blame the BlockManager (2011) and the tight NumPy coupling. -->

---

<!-- _class: section -->

# Dataframe fundamentals

---

## Dataframe fundamentals


<div class="definition">

**Vectorization**: running one operation over a whole array in compiled code, instead of looping in Python.

</div>
```python
df['temp_c'] = (df['temp_f'] - 32) * 5 / 9
```

Runs as a tight loop over contiguous memory, **in C**.
No per-element Python dispatch.

---

## Dataframe fundamentals, so we measured it

![w:920](figures/vectorization-scaling.png)

<!-- 400k rows, one column, one rescale. Walk the four lines bottom to top.
     Ask them to predict where .apply lands BEFORE showing the top line. -->

---

## Dataframe fundamentals, the numbers, at 400,000 rows

| | vs vectorized |
|---|---|
| vectorized pandas / Polars | 1× |
| Python row loop | **~100× slower** |
| `.apply(axis=1)` | **~3,000× slower** |

590 columns each paying that tax independently, if you loop.

<!-- Exact ratios move ~20% run to run; the plot carries the measured values
     from the last regeneration. Don't defend a specific digit.
     Also point at the bottom two lines: vectorized pandas and a Polars
     expression are nearly identical here. Polars' win is not per-operation
     speed, it's the optimizer, and it needs a bigger query to show. -->

---

## Dataframe fundamentals, the same idea, twice more

**`groupby`**: "mean reading per run, per shift, per lot"
= one groupby + one aggregate. Don't hand-roll the buckets.

**Joins**: attach calibration or recipe metadata by key.
Same rule as [Lecture 3](https://pandas.pydata.org/docs/user_guide/merging.html): a column is a *kind* of measurement,
never a particular sensor or run.

---

## Dataframe fundamentals, reshaping: wide ↔ long

SECOM arrives **wide**: one column per sensor.
Right shape for a model. Wrong shape for
"which sensors are most often missing?"

```python
long = wide.melt(id_vars=['run_id', 'label'],
                 var_name='sensor', value_name='reading')
```

Reshape explicitly. Don't keep two copies that drift.
[pandas reshaping docs](https://pandas.pydata.org/docs/user_guide/reshaping.html)

**The pitfall: `.apply` isn't vectorized.**

```python
df.apply(lambda row: row['a'] + row['b'], axis=1)
```

Looks like one line. It is **~30× slower than
writing the loop by hand.**

---

## Dataframe fundamentals, why it's worse than the loop

`axis=1` builds a **whole `Series` per row**
just to pass into your function.

Allocate, populate, call, discard. 400,000 times.

Legitimate uses: an external library per row, or
irregular logic with no column expression. Not arithmetic.

<!-- This surprises people every year: the one-line idiom that LOOKS like the
     vectorized style is the slowest thing on the plot. Reach for .apply when
     you've run out of alternatives, not first. -->

---

<!-- _class: section -->

# Polars and lazy execution

---

## Polars and lazy execution

pandas (2008): NumPy arrays, often boxed objects
for strings/nulls, mostly single-threaded.

Polars: Rust, built on Arrow, **typed columnar
storage, multithreaded by default.**

---

## Polars and lazy execution, the key distinction: eager vs. lazy

<div class="definition">

**Lazy evaluation**: building a plan of the whole query first, so an optimizer can rewrite it before any data moves.

</div>

**Eager** (`pl.read_csv`): every step runs immediately.

**Lazy** (`pl.scan_csv`): you get a plan, a `LazyFrame`.

```python
(pl.scan_parquet("sensors/*.parquet")
   .filter(pl.col("run_id") > 1000)
   .select(["run_id", "sensor_12", "sensor_87"])
   .collect())          # nothing ran until here
```

[docs.pola.rs/user-guide/lazy/using](https://docs.pola.rs/user-guide/lazy/using/)

---

## Polars and lazy execution, what the optimizer does with it

<div class="definition">

**Predicate pushdown**: moving a filter as close to the data source as possible, so rows are never read rather than read and discarded.

</div>

**Predicate pushdown**: move `filter` as early as possible,
often into the file reader itself.

**Projection pushdown**: only read the columns
the final `.select()` actually needs.

Not faster at the same computation. Faster because
it computes **less**, having seen the whole query first.

---

## Polars and lazy execution, expressions are what make this possible

```python
pl.col("sensor_12").mean()          # not a value

df.select([pl.col(c).mean() for c in sensor_cols])
```

An **object describing a computation**, which Polars can
inspect, combine, and compile.

590 of them run together, in parallel, **in one pass.**
[Polars expressions](https://docs.pola.rs/user-guide/expressions/)

**So how much does lazy actually buy you?.**

| rows | Polars vs pandas | Dask vs pandas |
|---|---|---|
| 1,567 | ~2× faster | **34× slower** |
| 200,000 | ~7× faster | 2× slower |

Every performance claim here has a **regime**.
"Which is faster" is incomplete until someone says how big.

---

## Polars and lazy execution, where the 2× comes from

- The read: ~40 ms vs pandas' ~75 ms
- The stats: **3 passes → 1 pass**, ≈4× on that portion

pandas asks each column for distinct count, then
missing count, then mean. Three walks over the frame.

**The trap: schema inference.**

```
ComputeError: could not parse `4.1955`
as dtype `i64` at column 'column_75'
```

Polars samples **100 rows**, picks `i64`.
The decimal shows up on row **1,458** of 1,567.

---

## Polars and lazy execution, two fixes, not equally good

| approach | read | outcome |
|---|---|---|
| default (100 rows) | n/a | **raises** |
| `infer_schema_length=None` | ~110 ms | scans everything |
| `schema_overrides=...` | **~38 ms** | decides nothing |
| pandas, for reference | ~75 ms | silently upcasts |

Declaring beats inferring: 3× faster **and** unsurprisable.

<!-- Then say it out loud, it's the setup for Monday: a declared schema is a
     belief written down, and a belief written down is one you can check.
     That's pandera. -->

---

## Polars and lazy execution, interop: Arrow ≠ Parquet

<div class="definition">

**Apache Arrow**: an in-memory columnar format. Parquet is the on-disk one; they are not the same thing.

</div>

**Arrow** = in-memory, uncompressed, CPU reads it directly.
**Parquet** = on-disk, compressed, must be decoded.

> "Arrow and Parquet complement each other" ([Arrow FAQ](https://arrow.apache.org/faq/))

So: **Parquet between stages, Arrow within one.**
Polars ↔ pandas ↔ DuckDB share the layout, so crossing
a library boundary is cheap. Pick each stage's tool on merit.

[parquet.apache.org](https://parquet.apache.org/docs/file-format/), [duckdb.org](https://duckdb.org/)

---

<!-- _class: section -->

# Designing a batch pipeline

---

## Designing a batch pipeline

**ingest** → **clean** → **transform** → **persist**

Each one a pure function: typed input, typed output.

Testable and cacheable **one stage at a time**.
Debug stage 3 without rerunning stages 1 and 2.

---

## Designing a batch pipeline, what `clean` actually removes

![w:880](figures/secom-column-triage.png)

<!-- Ask: how many of the 590 columns do you think survive? Nobody guesses low
     enough. 440. A quarter of the matrix is gone before any modelling. -->

---

## Designing a batch pipeline, two independent failure modes

| reason | columns |
|---|---|
| constant, one distinct value | **122** |
| more than 40% missing | **28** |
| overlap | 0 |
| **survive** | **440 of 590** |

A sensor wired up but never varying, and a sensor
that reports intermittently. Different bugs.

---

## Designing a batch pipeline, idempotency

<div class="definition">

**Idempotency**: running a stage twice produces the same result as running it once.

</div>

Running a stage twice on the same input
produces the **same output, byte for byte.**

- Pin random seeds
- Sort before order-dependent operations

"Same input, same output" is a **correctness**
requirement, not a nicety.

<!-- Sounds minor until you're recovering from a partial failure. If clean is
     idempotent, rerunning after a crash is free. The demo hashes its Parquet
     output twice and compares: cheapest reconciliation check there is. -->

---

## Designing a batch pipeline, case: one server out of eight

**Knight Capital Americas, 1 August 2012.**
\$460M lost in ~45 minutes.

~10% of all trading in listed US equities, at the time.

[SEC Release No. 70694](https://www.sec.gov/litigation/admin/2013/34-70694.pdf)

**The deployment.**

New code for **SMARS**, its order router, to support
NYSE's Retail Liquidity Program launching that day.

Staged across **8 servers** from 27 July.
One technician did not copy it to the eighth.

> "Knight did not have a second technician review
> this deployment... Knight had no written
> procedures that required such a review."

---

## Designing a batch pipeline, mistake 1: the repurposed flag

The new code reused a flag that used to activate
an old feature, **Power Peg**.

Unused since 2003. Never deleted.
Still "present and callable."

**Mistake 2: dead code nobody retested.**

2005: Knight moved the function counting
already-filled shares to an earlier point.

> "did not retest the Power Peg code after moving
> the cumulative quantity function"

Dead **and** broken, for seven years.

---

## Designing a batch pipeline, the result

**212** parent orders into the eighth server.

**4 million** executions, **154** stocks,
**397 million** shares, ~45 minutes.

\$3.5B unintended long, \$3.15B short.

**The signal that existed.**

**8:01 a.m.**, 90 minutes before the open:
97 automated emails, "Power Peg disabled."

> "Knight did not design these types of messages
> to be system alerts, and Knight personnel
> generally did not review them."

---

## Designing a batch pipeline, three habits, all of them Assignment 3

A rollout across 8 machines **is** a batch job whose
"rows" are servers. 7-of-8 looked exactly like 8-of-8.

1. **Reconcile**: count, hash, version read back
2. **Delete dead code**; distrust dormant code
3. **A signal is something or nothing**:
   97 unread emails are worse than zero

<!-- The demo hashes its Parquet twice and compares: habit 1, small version.
     On habit 2: Power Peg was harmless until a flag made it reachable, and code
     nobody calls is code nobody tests. A pipeline stage switched off by config
     is in exactly that category. -->

---

## Designing a batch pipeline, caching to Parquet between stages

Rerunning `ingest` + `clean` every time you
iterate on `transform` wastes minutes,
thousands of times over a semester.

Persist each stage. Check the cache before recomputing.

---

<!-- _class: section -->

# Orchestration

---

## Orchestration

Steps, dependencies, no step depends on its own output.
The oldest tool that takes this seriously:

```makefile
clean.parquet: ingest.parquet clean.py
	python clean.py ingest.parquet clean.parquet
```

`make` compares timestamps. Reruns only what changed.

<!-- Ten lines per stage buys you incremental caching for free. -->


---

## Orchestration, what Prefect / Dagster add

For one author on one machine, that Makefile is often
**enough.** Correctly sized, not under-powered.

- Automatic retries on transient failure
- A scheduler and a UI: which run failed, why
- Alerting
- Dagster: each output as a lineage-tracked **asset**

Not the graph. **Who can operate it**, and what
happens when a stage fails at 3 a.m.

[Prefect](https://docs.prefect.io/), [Dagster](https://docs.dagster.io/)

---

<!-- _class: section -->

# Scaling out

---

## Scaling out

**[MapReduce](https://research.google.com/archive/mapreduce-osdi04.pdf)** (Dean & Ghemawat, OSDI 2004):
split into partitions, map each independently, reduce.

The framework handles parallelism and failures.

Its weak spot: wrote intermediate results to disk
between **every** stage. Awkward for anything iterative.

---

## Scaling out, spark's fix

Zaharia et al., UC Berkeley AMPLab, 2012:
**[Resilient Distributed Datasets](https://www.usenix.org/system/files/conference/nsdi12/nsdi12-final138.pdf).**

Keep intermediate data in memory across stages.

**Lineage-based fault tolerance.**

<div class="definition">

**Lineage**: the recorded chain of operations that produced a partition, so a lost one can be recomputed rather than replicated.

</div>

Record the transformations that produced a partition.

Lost a partition? **Recompute it from lineage**:
durability without copying the data upfront.

---

## Scaling out, two mechanics that recur everywhere

**Partitioning**: split data into independent chunks.
Choose the key so related rows land together.

**Shuffle**: rows scattered across partitions
have to be gathered, expensive, over the network.

**Ask this of every operation: `mean` or `nunique`?.**

`mean` → **reduction.** Each partition reports a sum
and a count. Cheap, parallel, no talking.

exact `nunique` → **shuffle.** No partition knows if
its `7.2` appears elsewhere. Dask builds one per column.

590 columns = 590 shuffles.

---

## Scaling out, measured, on 1,253 rows

| 590 columns | time | tasks (100 cols) |
|---|---|---|
| Dask `nunique` | **tens of s** | **9,908** |
| Dask `std` | **< 0.1 s** | **18** |

Same 122 constant columns. `std == 0` ⟺ constant.
You wait on the scheduler, not the arithmetic.

---

## Scaling out, how you know it's overhead, not work

![w:1000](figures/dask-overhead.png)

<!-- Right panel: MORE partitions is SLOWER. That's the tell. And in the demo,
     4× the rows takes the same time. A cost that ignores data size is not the
     cost of processing data. -->

---

## Scaling out, dask DataFrame, and Spark

Dask partitions a big table into many ordinary
pandas frames. Lazy graph; nothing runs until `.compute()`.

> Dask DataFrame is **pandas that spills**
> to disk or to a cluster.

Spark: same role, larger scale. JVM runtime, its own
Catalyst optimizer, much bigger operational footprint.

**Overhead paid before the work starts.**

Partitioning, shuffles, a scheduler:
all overhead paid **before** one useful byte is processed.

On data that fits in memory: pure cost.

SECOM is a few megabytes.

> Just use [DuckDB](https://duckdb.org/) or Polars
> on one big machine.

---

## Scaling out, don't take it from me

Dask's own best-practices page.
First section title, in full:

# "Use Pandas"

[docs.dask.org/en/stable/dataframe-best-practices](https://docs.dask.org/en/stable/dataframe-best-practices.html)

---

## Scaling out, their words

> For data that fits into RAM, pandas can often be
> faster and easier to use than Dask DataFrame.
> While "Big Data" tools can be exciting, they are
> almost always worse than normal data tools
> while those remain appropriate.

**A pipeline moves in and out of distributed execution as data size changes.**

<!-- Their second section is "Reduce, and then use pandas": even on genuinely
     large data there's a step where a filter or aggregate cuts it down to one
     machine. Call .compute() there and go back to normal tools. -->

---

<!-- _class: section -->

# Where this pushes back

---

## Where this pushes back

| pandas | Polars |
|---|---|
| forgiving types | stricter, less forgiving |
| huge ecosystem | younger, thinner ecosystem |
| eager only | eager **and** lazy, one more concept |
| everyone already knows it | migration cost if collaborators don't |

---

## Where this pushes back, when pandas is still the right call

Collaborators, codebase, or the next library
in the chain only speaks pandas.

Shared Arrow layout → converting later is cheap.
**Prototype in what you know; convert if profiling says so.**

<!-- The ecosystem argument is the real one. Nobody migrates for 2x. -->

**Distributed systems: the costs.**

- A scheduler to reason about
- A new failure mode: a worker dying mid-shuffle
- Real wall-clock overhead building the task graph

**Fixed cost, size-independent**: dominates on small data.

---

## Where this pushes back, lazy evaluation moves the error

A bad expression in a lazy chain often doesn't
raise until `.collect()` / `.compute()`,
lines away from the mistake.

Eager pandas fails **at the line**. Genuinely easier to debug.

**Caching isn't free either.**

"Delete the cache when anything upstream changes"
is easy to state, easy to get wrong.

A stale cache that returns yesterday's answer
is worse than no cache: it fails **quietly**.

**What a practitioner should take from this.**

Reach for Polars when profiling shows a real,
columnar bottleneck.

Reach for Dask/Spark when data stops fitting
in memory, not in anticipation of it.

**"It should be faster" is a hypothesis.**
Today's demo lets you test it in five minutes.

---

## Where this pushes back, and check when the benchmark last ran

The much-linked `h2oai.github.io/db-benchmark` says
it "runs regularly... and automatically updates."

Its repo's last commit: **June 2023.**

Maintained fork: [duckdblabs.github.io/db-benchmark](https://duckdblabs.github.io/db-benchmark/)

<!-- Small thing, but it's the whole course in miniature: a page claiming to be
     live is not evidence that it is live. Check the code, not the copy. -->

---

<!-- _class: demo -->

# Demo

## `l05-pipelines.ipynb`

One 4-stage pipeline: pandas, Polars lazy, and Dask.

---

## What to watch

- pandas vs. Polars: same numbers to 1e-12, ~2× the speed
- A **direct port** of `nunique` into Dask: painfully slow
- The `std`-based fix: correct **and** fast
- Final Dask vs. pandas: at this size, distributed loses

---

## Three bugs that never raised

1. Quoted timestamp → **whole column `NaT`**,
   "daily" mean over one meaningless group
2. Schema inference → breaks on row 1,458
3. `nunique` port → 800× slower than pandas

All three caught by **a number that didn't match
an expectation.** That's Monday's whole lecture.

---

## Recap

- Vectorize; `.apply(axis=1)` is worse than the loop it hides
- Polars: typed, columnar, lazy, an optimizer that sees the whole query
- Declare schemas; don't let the library guess
- 4 pure pipeline stages: ingest → clean → transform → persist
- Knight Capital: partial success that looked like success
- Dask/Spark: real tools, real overhead. Know your crossover point

---

## The one transferable habit

Every number in this session came from measuring,
and two of them **contradicted** the first draft.

`.apply` is worse than the loop, not equal to it.
Scanning to be "safe" cost more than declaring.

**Measure. Then write it down.**

---

## Next

**Assignment 3**, out today, due at Lecture 7, Wed 16 Sep
**Reading** [Polars lazy API](https://docs.pola.rs/user-guide/lazy/using/), [Dask best practices](https://docs.dask.org/en/stable/dataframe-best-practices.html), Kleppmann Ch. 10
**Lecture 6** Same SECOM matrix, a different question: not how fast
you can clean it, but how you *prove* it's clean, automatically,
before a bad value reaches a model

Full notes, with all sources: `lectures/l05/notes.md`
