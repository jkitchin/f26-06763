---
marp: true
theme: course
paginate: true
header: "06-763 / L5"
footer: "Systems and Toolchains for AI Engineers"
---

<!-- _class: title -->

# Lecture 5: Dataframes and batch pipelines

## Week 3, Data Systems

**Systems and Toolchains for AI Engineers**

---

## Roadmap

1. Why dataframes and pipelines
2. What carries over from SQL
3. Polars: plan the work, then run it
4. Making it safe to rerun
5. Where this pushes back
6. Live demo: the same pipeline, two ways

---

<!-- _class: section -->

# Why dataframes and pipelines

---

## Why dataframes and pipelines

Lecture 3 gave you SQL: describe the result, the planner works out how. Lecture 4 gave you a faster layout for that same idea, still inside a database.

So why leave the database? Because this lecture's work is awkward to write as a query:

- decide what goes in the gaps where a sensor dropped out
- throw away channels that never moved
- rerun the whole thing tomorrow when the file changes

That is ordinary programming. Python is better at it.

---

## Why dataframes and pipelines, a plant's log

The Tennessee Eastman process: a simulated chemical plant.

- 52 measurements (reactor, separator, stripper, feeds, cooling water)
- sampled every 3 minutes, across hundreds of runs
- millions of rows before anyone asks a question

What we want out of it: **one row per fault**, showing what each sensor read on average while that fault was running. Put two faults side by side and you can see which sensors moved.

[Tennessee Eastman data, CC0](https://doi.org/10.7910/DVN/6C3JR1) · [Downs and Vogel, 1993](https://doi.org/10.1016/0098-1354(93)80018-I)

<!--
speaker: TEP is a Downs and Vogel 1993 benchmark, a real Eastman plant disguised. faultNumber 0 is normal, 1 to 20 are disturbances. Turning the raw log into per-fault means is a pipeline: load, clean, reshape, aggregate.
-->

---

![w:1050](figures/tep-screenshot.png)

<span class="source">Reactor, condenser, compressor, separator, stripper: the plant behind this session's 52 columns. Lyu, Botcha, Kulkarni, Pagaria, Alves, Sunshine, and Kitchin (2026). Run it yourself: <a href="https://kitchingroup.cheme.cmu.edu/tep-rust/studio/">TEP Studio</a></span>

---

## Why dataframes and pipelines, the two things you lose

Leaving the database costs you something. Write this as one long Python script and two things it was handling for you become your problem:

- **slow**: looping over the readings one at a time is **hundreds of times** slower than comparing the whole column at once
- **unsafe**: if the script stops halfway, nothing recorded which steps already finished, so you cannot tell whether rerunning it is safe

**Polars** gets the speed back. **Small, restartable stages** get the safety back.

---

<!-- _class: section -->

# What carries over from SQL

---

## What carries over from SQL

A **dataframe** is a table in memory: named columns, each with a fixed type. You have used one since Lecture 3.

You already wrote grouping and joining in SQL. Here they are methods, not clauses.

```python
readings.group_by("faultNumber").agg(pl.col("^xmeas_.*$").mean())  # every measured column
```

- `group_by` does the job `GROUP BY` did
- a join still matches two tables on a shared column, so a result reads "reactor cooling water" instead of `faultNumber = 4`

[pandas, group by](https://pandas.pydata.org/docs/user_guide/groupby.html)

---

## What carries over from SQL, vectorizing

This one does not carry over. SQL never let you handle rows one at a time: you asked for a result, and the database walked the rows however it wanted.

<div class="definition">

**Vectorization**: compute on a whole column at once instead of one value at a time.

</div>

On the reactor-pressure column, 480,000 readings:

- `readings["xmeas_7"] > threshold` compares the whole column: **0.2 ms**
- the same test as a plain `for` loop: **20 ms**
- with `iterrows()`, the usual first attempt: **3,900 ms**

Hundreds of times slower, and that is before anyone reaches for a bigger machine.

---

<!-- _class: section -->

# Polars: plan the work, then run it

---

## Polars: plan the work, then run it

pandas runs each line the moment you write it, on one core. That is **eager** execution.

<div class="definition">

**Polars**: a table library like pandas, but built to use every core at once. If you ask it to, it will also plan the whole computation before running any of it.

</div>

---

## Polars: plan the work, then run it, lazy evaluation

Lecture 3: you describe the result in SQL, the query planner decides the mechanism. Same idea, now in Python.

<div class="definition">

**Lazy evaluation**: writing an instruction does not run it. It adds a step to a plan. Nothing touches the data until `.collect()`, which runs the whole plan in one pass.

</div>

```python
pipeline = (pl.scan_parquet("data/tep.parquet")   # reads nothing yet
            .group_by("faultNumber")
            .agg(pl.col("^xmeas_.*$").mean()))
result = pipeline.collect()                        # optimize, then run
```

---

## Polars: plan the work, then run it, no server needed

You met these in Lecture 4, when DuckDB applied them to Parquet:

- **projection pushdown**: read only the columns you asked for
- **predicate pushdown**: a filter moves into the scan

Because pandas and Polars both lay columns out the same way in memory (**Arrow**), converting between them is cheap too: prototype in whichever you know, convert only if it turns out to matter.

[Polars, Lazy API](https://docs.pola.rs/user-guide/lazy/) · [Apache Arrow](https://arrow.apache.org/overview/)

---

<!-- _class: section -->

# Making it safe to rerun

---

## Making it safe to rerun

A pipeline written as one long function has no seam: no smaller piece you can test on its own, and none you can re-run on its own. Break it into stages.

<div class="definition">

**Pure stage**: output depends only on its input, and it changes nothing else. Same input, same output.

</div>

load, clean, aggregate: each stage a Parquet file in, a Parquet file out.

---

## Making it safe to rerun, idempotency

Your laptop goes to sleep while the clean stage is still writing `tep_clean.parquet`. You are left with half a file and no way to tell how much of it is good.

<div class="definition">

**Idempotency**: running a stage twice has the same effect as running it once, so you can safely retry a stage that failed.

</div>

If the clean stage is idempotent, the fix is to run it again. It reads the same input and overwrites the same output, so it makes no difference whether the first attempt stopped at row 100 or row 100,000.

In Lecture 3 the database's transactions did this for you.

---

<!-- _class: section -->

# Where this pushes back

---

## Where this pushes back

- **stricter has a cost**: more of your mistakes become real errors, and lazy evaluation reports them at `.collect()` rather than at the line that caused them
- **a fill value is a choice**: it shapes every number downstream, so decide it deliberately and report how much you filled
- **one machine goes further than you think**: exhaust a laptop with Polars or DuckDB before adding a cluster

---

## Where this pushes back, measure first

![w:840](figures/eager-vs-lazy.png)

One workload, one machine. Measure your own pipeline before you rewrite it.

---

<!-- _class: demo -->

# Demo

## `l05-pipelines.ipynb`

The Tennessee Eastman readings, one 4-stage pipeline built twice: pandas eager and Polars lazy, then timed.

The simulator's output has no gaps in it, so one clearly marked cell breaks the data on purpose: it deletes a chunk of readings and freezes one sensor at a constant. Now the cleaning stages have something real to fix.

---

## What to watch

1. pandas materializes a new table after **every** stage.

2. Polars builds a plan and runs it in **one** pass at `.collect()`.

3. Print that plan with `.explain()`: the column selection is folded into the read. Lecture 4's DuckDB trick, no server.

---

## Recap

- Lecture 3 and 4's ideas, now in Python: describe first, structure so failure is safe
- Vectorize first: **hundreds of times**, before reaching for a bigger machine
- Polars: every core, plans ahead, no server needed for the trick
- Small, pure, idempotent stages that cache to Parquet
- Measure your own workload before you rewrite it

---

## Next

- **Practice module** for this session (participation credit)
- No assignment is released this session
- **Reading**: Polars Lazy API guide; pandas group-by

Full notes, with all sources: `lectures/l05/notes.md`
