# L5 teaching notes: answers to have open during class

**Instructor-only. Never published.** This file lives in `course/modules/`,
which `_config.yml` excludes from the build and CI checks for on every run. Do
not move it into `lectures/`, where only one setting stands between it and the
public site.

A crib sheet for the questions students are most likely to ask in L5, with the
smallest concrete example for each.

---

## 1. Slide 9: "a join matches two tables on a shared column"

**The problem it solves.** The readings table stores the fault as a number.
Every row says `faultNumber = 4`. Nowhere in that table does it say what fault 4
actually is.

So your final summary table looks like this, and nobody can read it:

| faultNumber | xmeas_7 | xmeas_9 |
|---|---|---|
| 4 | 2705.1 | 120.4 |
| 11 | 2698.3 | 121.9 |

**The fix.** Keep a second, tiny table that spells out the numbers. Someone
types this once, from the Downs and Vogel paper:

| faultNumber | description |
|---|---|
| 4 | reactor cooling water inlet temperature |
| 11 | reactor cooling water valve, random |

Both tables have a `faultNumber` column. That shared column is what lets you
glue them together:

```python
summary.join(fault_names, on="faultNumber")
```

**What you get back.** Every row of the summary, with the matching description
attached:

| faultNumber | description | xmeas_7 | xmeas_9 |
|---|---|---|---|
| 4 | reactor cooling water inlet temperature | 2705.1 | 120.4 |
| 11 | reactor cooling water valve, random | 2698.3 | 121.9 |

**In one sentence:** a join is a lookup. "For each row, go find the matching row
in that other table and staple its columns on."

**If a student asks why not just store the text in the readings table:** because
you would repeat that same sentence on all 480,000 rows. Store it once, look it
up when you need it. That is Lecture 3's argument for splitting tables.

---

## 2 and 4. Slide 14: projection pushdown and predicate pushdown

Both are the same idea: **do the filtering while reading the file, not after.**

Our file has 55 columns and 480,000 rows.

### Projection pushdown = throw away *columns* early

Say you only want reactor pressure per fault. You need 2 columns of the 55.

```python
pl.scan_parquet("tep.parquet").select(["faultNumber", "xmeas_7"])
```

- **Without pushdown:** read all 55 columns off the disk into memory, then keep
  2 and discard 53. You paid to load 53 columns you never wanted.
- **With pushdown:** Polars looks at the whole plan first, sees that only 2
  columns are ever used, and reads only those 2 off the disk. The other 53 are
  never touched.

Parquet is what makes this possible: it stores each column in its own block, so
you can grab column 7 without reading columns 1 to 6. (That was Lecture 4.)

### Predicate pushdown = throw away *rows* early

Say you only care about fault 4.

```python
pl.scan_parquet("tep.parquet").filter(pl.col("faultNumber") == 4)
```

- **Without pushdown:** read all 480,000 rows, then delete the ~456,000 that are
  not fault 4.
- **With pushdown:** the filter moves down into the read. Parquet stores the min
  and max of each block, so Polars skips whole blocks whose range cannot contain
  a 4, without decompressing them.

### The line to say out loud

> "Both tricks mean: decide what you need *before* reading, so you never pay to
> load data you were going to throw away. You saw DuckDB do this in Lecture 4.
> Polars does the same thing with no database involved."

### Why it needs lazy mode

This only works because `scan_parquet` does not read anything immediately. It
builds a plan, so by the time anything runs, Polars already knows every column
and filter you asked for. `read_parquet` reads first, so it is too late.

**Show it live:** `plan.explain()`, and look at the scan line. The column list
appears on the scan itself.

---

## 3. Slide 16: "has no seam" and "pure stage"

### "No seam"

Seam = a place you can cut the thing open and look inside.

Compare these two:

```python
# one function: no seam
def run_everything(path):
    df = pd.read_parquet(path)
    ...200 lines...
    return summary
```

```python
# four stages: three seams
load(path)      -> raw.parquet
clean()         -> clean.parquet
aggregate()     -> summary.parquet
```

Now the summary comes out wrong. In version two you open `raw.parquet`: fine.
You open `clean.parquet`: the pressure column is all zeros. **Found it, the bug
is in clean**, and you never re-ran the load.

In version one there is nothing to open. Your only move is to add print
statements and run all 200 lines again, and again, until you corner it.

**One sentence:** a seam is a saved file between two steps. It is where you put
your finger to find out which step lied.

### "Pure stage"

Two promises:

1. **The output depends only on the input.** Give it the same file, get the same
   answer. Every time, on any machine, on any day.
2. **It changes nothing else.** It does not append to a log another stage reads,
   does not depend on today's date, does not need a variable someone set in a
   cell above.

**Impure, and why it hurts:**

```python
def clean(df):
    df["cleaned_at"] = datetime.now()      # different output every run
    return df
```

Run it twice, get two different tables. Now you cannot tell whether a changed
result means you fixed something or just that time passed.

```python
CUTOFF = 0.5                # someone edits this cell
def clean(df):
    return df.dropna(thresh=CUTOFF)        # depends on hidden state
```

Reruns of the *same* function now disagree, depending on what was executed
before it. That is what makes notebooks hard to trust.

**Why we care:** pure is what makes "just run it again" a safe answer. If the
output depends only on the input, a half-finished run has left nothing behind
that could poison the next one.

---

## 5. Slide 20: dumb simple example of each bullet

### "stricter has a cost"

A column of sensor readings, with one gap in it.

- **pandas:** quietly turns your integer column into floats to fit the `NaN`, and
  carries on. You find out later when a row ID prints as `4.0`.
- **Polars:** more of that becomes an actual error you have to deal with now.

Better in the long run, slower on the afternoon you are learning it.

**The lazy half.** Misspell a column name:

```python
plan = pl.scan_parquet(f).select("xmeas_77")   # no such column. No error yet.
...30 lines of pipeline...
result = plan.collect()                         # error appears HERE
```

The traceback points at `.collect()`, not at the line with the typo. In eager
pandas it would have blown up on the typo itself.

### "a fill value is a choice"

Reactor pressure has 100 missing readings. You fill them with the column average,
2,700 kPa.

You have now *invented* 100 readings of 2,700 kPa. They are in the file. They
look exactly like real measurements. Every average, plot, and model downstream
treats them as real.

Nobody reading your summary table can tell. So write it down: "xmeas_7: 100
values (0.02%) filled with the column mean."

**The sharper version:** if a sensor is 40% missing and you fill it with the
mean, then average per fault, every fault drifts toward that same mean. The
differences between faults, the exact thing you set out to measure, get flattened
by numbers you made up.

### "one machine goes further than you think"

Students hear "480,000 rows" and think Spark cluster.

This session's whole pipeline runs on a laptop in under a second. Polars and
DuckDB will happily work through files bigger than RAM by streaming them.

A cluster adds: a scheduler, a network, machines that die mid-job, and a config
file. Do that when one good machine has actually run out, not before.

**Rule of thumb to say:** "If it fits on your laptop's disk, try your laptop
first."

---

## Two things students reliably ask that are not on a slide

**"Why does the Polars version need a `.collect()` in the middle?"**
Because deciding which columns to drop needs real numbers: how many nulls, how
many distinct values. You cannot plan that, you have to look. So we run one
small pass, get the counts, then build the rest as a plan.

**"Is Polars just faster pandas?"**
No. It has a planner, so it can rearrange your work before running it, and it
uses every core. pandas runs each line as written, on one core. The measured
speedup here is about 6x on the pipeline, but the bigger number in this lecture,
hundreds of times, is about looping versus whole columns, which applies to
pandas too.
