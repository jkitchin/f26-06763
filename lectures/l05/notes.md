# Lecture 5: Dataframes and batch pipelines

:::{admonition} Overview
:class: tip

- **Session** Lecture 5, Week 3
- **Arc** Data Systems
- **Slides** <a href="../../slides/l05/">Deck for this session</a>
- **Practice** <a href="../../game/#/l05">Practice module for this session</a>
- **Demo** [`l05-pipelines.ipynb`](l05-pipelines.ipynb), the same cleaning pipeline in pandas and in Polars
- No assignment is released this session; your participation credit comes from the practice module
:::

## Why this matters

Imagine a chemical plant. Four gas feeds enter a reactor, where they react over a catalyst to make two liquid products. The reactor's output passes through a condenser, then into a tank that separates the leftover vapor from the liquid, and the liquid moves on to a stripper that removes the last unreacted gas before the rest counts as finished product. Watching all of this are dozens of instruments: pressure gauges on the reactor, level sensors on every tank, temperature probes on every cooling loop, and slow chemical analyzers that report what is actually inside each stream. This is the **Tennessee Eastman process**, a simulated chemical plant published as a benchmark in 1993 that the process-control field has used ever since to test the kind of software this course teaches you to write.

```{figure} figures/tep-screenshot.png
:alt: Piping and instrumentation diagram of the Tennessee Eastman process, showing four feed streams entering a reactor, a condenser, a compressor, a vapor-liquid separator, and a product stripper, with two sets of analyzers measuring stream composition
:width: 100%

The Tennessee Eastman process, the plant this session's data comes from. Reactor, condenser, compressor, separator, and stripper, wired up with the pressure, level, temperature, and composition instruments that produce this session's 52 columns. Figure from [Lyu, Botcha, Kulkarni, Pagaria, Alves, Sunshine, and Kitchin (2026)](https://chemrxiv.org/doi/abs/10.26434/chemrxiv.10001628/v1).
```

Every three minutes, all 52 of those instruments report a number. Run the simulation for a few hundred batches, twenty different kinds of fault plus normal operation, and you have millions of readings before anyone has asked a single question.

:::{admonition} Try the plant yourself
:class: tip

[**TEP Studio**](https://kitchingroup.cheme.cmu.edu/tep-rust/studio/) runs this exact simulator live in your browser: start it, watch the 52 channels trend in real time, inject one of the 20 faults, and download the resulting CSV.
:::

Turning those readings into one row per fault, the average of each sensor during that fault, is what this course calls a **data pipeline**.

:::{admonition} Definition: data pipeline
:class: tip

A **data pipeline** is the sequence of steps that turns raw readings into an answer: load the data, clean it up, reshape it if you need to, and aggregate it into the result you actually wanted.
:::

[Lecture 3](../l03/notes.md) gave you SQL: describe the result you want, and the database's planner works out how to get it. [Lecture 4](../l04/notes.md) gave you a faster physical layout for that same idea, DuckDB reading Parquet, still inside a database engine. This session is where the work leaves the database and becomes your own Python code, because turning millions of readings into one row per fault needs logic a `SELECT` statement does not comfortably express: filling gaps, reshaping tables, running the same steps twice without breaking anything.

Write that logic as one long script, and you lose the two things a database gave you for free:

- **It is slow.** A Python loop that checks one reading at a time is commonly about **100 times** slower than checking the whole column at once.
- **It is unsafe.** If the script dies halfway through, there is no record of what it already finished, so you cannot tell whether running it again is safe.

This session rebuilds both, one Python-native tool at a time: **Polars** gets you the speed and the describe-first-run-later trick back, with no server anywhere. **Small, restartable pipeline stages** get you back the safety a database's transactions gave you for free.

## Learning objectives

By the end of this session you should be able to:

- Write pandas and Polars code that operates on whole columns at once instead of row by row, including grouping, joining, and reshaping a table between long and wide form.
- Break a data pipeline into small steps that each read one file and write one file, so a run that fails partway through can be started again without corrupting anything.
- Explain the difference between pandas running code immediately and Polars planning a computation before running it, and use that difference to choose between the two for a given task.

## Your SQL habits, typed differently

```{index} dataframe, vectorization, long format, wide format
```

You have been handling a **dataframe**, a table held in memory with named, typed columns, since [Lecture 3](../l03/notes.md)'s `read_sql` and [Lecture 4](../l04/notes.md)'s `.df()`. Three moves you already know from SQL work the same way here. Only the syntax changes.

:::{admonition} Definition: vectorization
:class: tip

**Vectorization** means doing a computation on a whole column at once instead of one value at a time. `readings["xmeas_7"] > threshold` does that comparison once, in compiled code; a loop over the column does it once per row, in the Python interpreter.
:::

**Vectorize.** A `for` loop over a sensor column pays a fixed cost on every row; the vectorized version pays it once. That is the hundredfold slowdown from the opening example.

**Group and join.** `readings.group_by("faultNumber")` is `GROUP BY faultNumber`, a method call instead of a clause. A join still lines up two tables on a shared key, so a result can say "reactor cooling water" instead of `faultNumber = 4`.

**Long and wide.** [Lecture 3](../l03/notes.md)'s long-versus-wide argument, one level down: there it was a permanent schema decision, here it is an operation you run when you need it. `pivot` spreads one column per sensor; `melt` (`unpivot` in Polars) puts the readings back one per row.

## Getting DuckDB's trick without DuckDB

```{index} Polars, eager execution, lazy evaluation, Apache Arrow
```

pandas runs each instruction the moment you write it, on one core. That is **eager execution**, the model you already know from ordinary Python. On this session's 52-sensor, hundreds-of-thousands-of-row table, that means checking every column one at a time while the rest of your machine's cores sit idle.

:::{admonition} Definition: Polars
:class: tip

**Polars** is a table library for Python, like pandas, but built to use every core on your machine at once and, if you ask it to, to plan a whole computation before running any of it.
:::

:::{admonition} Definition: lazy evaluation
:class: tip

Under **lazy evaluation**, writing an instruction does not run it. It adds a step to a plan. Nothing touches the data until you call `.collect()`, which runs the whole plan in one optimized pass.
:::

This is [Lecture 3](../l03/notes.md)'s query planner again, and [Lecture 4](../l04/notes.md)'s DuckDB trick again, now with no server anywhere. `pl.scan_parquet(...)` hands back a description of the read, not the data, and folds your later steps back into that description before anything runs, exactly the projection pushdown and predicate pushdown DuckDB applied to Parquet in Lecture 4.

```python
import polars as pl

pipeline = (
    pl.scan_parquet("data/tep.parquet")
    .group_by("faultNumber")
    .agg(pl.col("^xmeas_.*$").mean())   # every measured column
)
result = pipeline.collect()   # only now does anything run
```

The demo shows the rest live: the query plan, printed and compared before and after optimization, and pandas-to-Polars conversion, cheap because both libraries lay columns out the same way in memory (the Arrow format, Parquet's in-memory cousin from Lecture 4).

## Making it safe to rerun

```{index} batch pipeline, idempotency, pure function, caching
```

A pipeline written as one long function has no seam: nothing to test on its own, nothing to re-run on its own. The fix is stages: load, clean, aggregate, each a small function with one input and one output, usually a Parquet file the next stage reads.

:::{admonition} Definition: pure stage
:class: tip

A **pure** stage's output depends only on its input, and it changes nothing else. Same input, same output, every time.
:::

Saving each stage's output is **caching**: the expensive early work runs once, and you can open any stage's file and see exactly what it produced.

Say the clean stage is halfway through writing `tep_clean.parquet` when your laptop sleeps. If clean is a pure stage, the fix is one word: rerun it. Same raw file in, same output out, whether the interrupted attempt got through row one hundred or row one hundred thousand.

:::{admonition} Definition: idempotency
:class: tip

A stage is **idempotent** when running it twice has the same effect as running it once. You do not need to know whether the last attempt finished. You just run it again.
:::

This is what a database's transactions gave you for free in Lecture 3, and what you rebuild by hand once the logic is your own Python: a partial failure that leaves nothing to clean up.

One trap: cache a stage's output under a name that mentions only the stage, `clean.parquet`, then change a setting the stage depends on, and the stale file gets reused silently, because nothing tells it to invalidate. Name the cache after the inputs and settings that actually determine its contents, not just the stage.

## Where this pushes back

```{index} pair: failure mode; undocumented fill value
```

- **Polars is stricter, and stricter costs you while you are learning it.** More of your mistakes become real errors instead of quiet workarounds, and lazy evaluation moves errors away from the line that caused them, sometimes several stages away. Stay with pandas when your codebase or collaborators only speak it; reach for Polars once the table outgrows comfort.
- **A fill value is a choice, not a fact.** It becomes part of every result computed downstream of it, as the opening example showed. Choose it deliberately, and report how much of a column you filled.
- **One machine goes further than you think.** Vectorized pandas, and especially Polars with DuckDB over Parquet, comfortably handle hundreds of thousands of rows on a laptop. Exhaust one good machine before adding a cluster.
- **A benchmark measures one workload on one machine.** The pandas-versus-Polars ratio you see in the demo will not transfer to a different pipeline. The number worth carrying out of this session is the hundredfold vectorization gap, not that ratio, because it is about the shape of the computation, not which library won on one afternoon.

## In-class demo

We take the Tennessee Eastman readings and build the same four-stage pipeline twice, once in pandas and once in Polars, and time both. The stages are load, drop the columns that are constant or mostly missing, fill in what remains, and aggregate to the mean of each sensor per fault. The data arrives clean, so a clearly labeled cell injects the defects on purpose, dropped readings and one stuck sensor, so the cleaning stages have real work to do.

Watch the difference between eager and lazy. The pandas version builds a new table after every stage. The Polars version builds a plan and runs it in one pass at `.collect()`, and printing that plan with `.explain()` shows the column selection folded down into the very first read, exactly the projection pushdown from Lecture 4's DuckDB, now with no server. The runnable notebook is [`l05-pipelines.ipynb`](l05-pipelines.ipynb).

## Summary

A data pipeline turns a raw sensor log into an answer, and Lecture 3 and Lecture 4 already taught you most of how to do it well: describe what you want and let a planner work out how, and structure the work so a partial failure cannot corrupt anything. This session moves both ideas out of the database and into your own Python code. Vectorization and Polars get the speed back, about a hundredfold from vectorizing alone. Small, pure, idempotent stages that cache to Parquet get the safety back. pandas or Polars, the durable habit is the one from the last two lectures: describe the work, structure it honestly, and measure before you optimize.

## Resources

- [TEP Studio](https://kitchingroup.cheme.cmu.edu/tep-rust/studio/). The Tennessee Eastman simulator itself, running live in your browser. Start a run, watch the 52 channels move in real time, inject a fault, and download the CSV.
- [Lyu, Botcha, Kulkarni, Pagaria, Alves, Sunshine, and Kitchin, Benchmarking machine learning fault detection methods on the Tennessee Eastman process dataset (2026)](https://chemrxiv.org/doi/abs/10.26434/chemrxiv.10001628/v1). The plant diagram in this session comes from this paper, which benchmarks a range of machine learning fault detectors on the same dataset.
- [Polars user guide, Lazy API](https://docs.pola.rs/user-guide/lazy/). What a `LazyFrame` is, why `scan_parquet` beats `read_parquet` for a pipeline, and how `.collect()` triggers optimization. Start here.
- [Polars user guide, Expressions](https://docs.pola.rs/user-guide/expressions/). The expression API the whole library is built on, with the group-by and selection patterns the demo uses.
- [pandas user guide, Group by](https://pandas.pydata.org/docs/user_guide/groupby.html). The split-apply-combine model, the same idea as SQL's `GROUP BY`, in pandas.
- [pandas user guide, Reshaping and pivot tables](https://pandas.pydata.org/docs/user_guide/reshaping.html). `pivot`, `melt`, and moving between long and wide form.
- [Apache Arrow overview](https://arrow.apache.org/overview/). The in-memory columnar layout that makes pandas-to-Polars conversion cheap, and how it differs from Parquet on disk.
- [Tennessee Eastman process simulation data (Rieth et al. 2017)](https://doi.org/10.7910/DVN/6C3JR1). The dataset for this session. Faults 1 to 20 plus fault-free operation, 52 process variables.
- [Downs and Vogel, A plant-wide industrial process control problem (1993)](https://doi.org/10.1016/0098-1354(93)80018-I). The original paper that defines the process, its units, and its twenty disturbances. The source for what each fault means.

## Assignment

No assignment is released this session, so this week's deliverable is the practice module below, which is where your participation credit for the session comes from.

## Practice module

<a href="../../game/#/l05"><strong>Practice module for this session</strong></a>, about ten
minutes of questions drawn from this session's notes, slides and demo. It runs entirely in
your browser, the questions are selected from your Andrew ID, and it ends by producing a PDF
you upload for participation credit.
