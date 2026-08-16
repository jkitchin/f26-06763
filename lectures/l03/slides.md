---
marp: true
theme: course
paginate: true
header: "06-763 · L3"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L3 · Relational data & SQL

## Week 2 · Data Systems

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. Why a database, not a spreadsheet
2. The relational model: long beats wide
3. Types that carry physical meaning
4. SQL that answers engineering questions
5. Loading, indexes, and `EXPLAIN ANALYZE`
6. Live demo: a month of sensor data

<!-- 110 min. Budget: 15 / 20 / 20 / 20 / 15 / 20 demo, ~ leave slack.
     Dataset is the Intel Berkeley Lab motes, ~2.3M readings. The demo is
     the payoff; if running long, cut the numeric-vs-double slide, not the demo. -->

---

<!-- _class: section -->

# Why a database
## and not a spreadsheet

---

## The questions are one-liners

- Which sensor ran hottest last Tuesday?
- How many readings did node 12 drop overnight?
- What was the hourly average across the floor?

The arithmetic is trivial.
The **shape of the data** is the hard part.

---

## The tempting shape: one column per sensor

| ts | m1 | m2 | m3 | … | m54 |
|---|---|---|---|---|---|
| 08:00 | 19.9 | 20.1 | NULL | … | 18.7 |

Looks tidy with four sensors.
Falls apart on a real deployment.

---

## Why wide falls apart

- New node → **add a column** → every query breaks
- Node offline → column of blanks (offline? or zero?)
- *"Which sensors exceeded 30°C?"* → **no answer**

You cannot put a `WHERE` clause on a **column name**.

---

## The quieter failure

A CSV has no opinion about what belongs in a cell.

This week's data: **2.3M** readings, 54 motes,
Intel Berkeley Lab, February to April 2004.

Hiding in it: temperatures of **122°C** and **386°C**,
in the same column as the honest 19°C ones.

Nothing marks them impossible.

[Intel Lab Data](https://db.csail.mit.edu/labdata/labdata.html)

---

## A schema is a contract

A database lets you state, once and **enforceably**:

- this column is a timestamp **with a time zone**
- this one is a number
- this `sensor_id` **must** refer to a sensor that exists

A contract you can query turns a pile of numbers
into something you can **answer questions from and defend**.

---

<!-- _class: section -->

# The relational model
## long beats wide

---

## Two ideas on top of tables

**Keys**

- *Primary key*: uniquely identifies a row `(sensor_id, ts, …)`
- *Foreign key*: must match a key elsewhere

A reading for sensor 5 **cannot exist** unless sensor 5 does.
Enforced on every insert.

---

## Integrity, enforced for you

```sql
INSERT INTO readings VALUES (999, now(), 'temperature', 21.0);
-- ERROR: violates foreign key constraint "readings_sensor_id_fkey"
```

A mote that isn't in `sensors` is rejected, not silently stored.
And `(sensor_id, ts, variable)` as the primary key means
the **same reading twice** is a duplicate the database refuses.

---

## Normalization

> Store each fact once, in the place it belongs,
> and refer to it by key everywhere else.

- Location & unit don't change per reading → `sensors` table
- Readings carry only a `sensor_id` pointer

Fix a calibration in **one row**, not two million.

---

![w:1080](figures/schema-long-vs-wide.png)

---

## The long form, in SQL

```sql
CREATE TABLE sensors (             -- static per-mote metadata
    sensor_id int PRIMARY KEY,
    x_m double precision, y_m double precision
);
CREATE TABLE readings (            -- one row per (mote, time, quantity)
    sensor_id int NOT NULL REFERENCES sensors (sensor_id),
    ts        timestamptz NOT NULL,
    variable  text NOT NULL,       -- 'temperature', 'voltage', …
    value     double precision,
    PRIMARY KEY (sensor_id, ts, variable)
);
```

Units and plausible ranges live in a small `variables` table.

---

## Tidy vs typed

| Fully tidy | Typed columns |
|---|---|
| `variable, value` | `temperature`, `humidity`, … |
| new channel = new **rows** | new channel = **ALTER TABLE** |
| one type for all | a type per channel |

Both beat wide. Pick deliberately; justify it in A2.

---

## The pitfall to resist

Column names should never be **entities**
(sensor ids, machine ids, run numbers).

> A column is a **kind** of thing you measure,
> never a **particular** thing you measured it from.

Entities go in **rows**.

<!-- This is THE recurring mistake. Worth 90 seconds and a show of hands. -->

---

<!-- _class: section -->

# Types that carry
## physical meaning

---

## Time: `timestamptz`, in UTC

`timestamp` = wall clock, no zone → **ambiguous**
`timestamptz` = an instant, stored UTC → **well defined**

`2004-03-14 02:30:00` on a clock-change night
happened twice, or never.

**Store instants in UTC. Always.**

[PostgreSQL: date/time types](https://www.postgresql.org/docs/current/datatype-datetime.html)

---

## Time punishes the overconfident

Case: the leap second of **30 June 2012**

- Last minute of the day ran to `23:59:60`
- A Linux kernel bug → servers spun at **100% CPU**

---

## Who fell over

Reddit · LinkedIn · Mozilla · Yelp · Foursquare · StumbleUpon

**Amadeus Altea** reservation system offline ~1 hour
→ Qantas & Virgin Australia checked in passengers **by hand**

[The Register, 2 Jul 2012](https://www.theregister.com/2012/07/02/leap_second_crashes_airlines/)

---

## Who didn't

Google saw it coming: spread the extra second across
many tiny clock adjustments. A **"leap smear."**

Lesson at every scale:

> Calendar arithmetic is full of edge cases.
> Don't be the one reimplementing it.

Store UTC · use `timestamptz` · let tested code do the math.

---

## `numeric` vs `double precision`

| `double precision` | `numeric` |
|---|---|
| 64-bit float, inexact | exact decimal |
| fast, compact | slow, large |
| **sensor values** | money, exact calibration |

Measurement uncertainty ≫ float error.
`double precision` is the right **default** for physical data.

[PostgreSQL: numeric types](https://www.postgresql.org/docs/current/datatype-numeric.html)

---

## `interval`: a real duration

`ts - lag(ts)` yields an **`interval`**, not a bare number.

Compare it straight to `'1 hour'` or `'31 seconds'`.
No juggling epoch seconds by hand.

---

## A typed column is not a validated one

`double precision` accepts **386°C** as happily as 19.

386 is a perfectly good float.

You need a `CHECK` constraint or a range filter,
and a threshold that knows the instrument.

---

## Push the check into the schema

```sql
ALTER TABLE readings ADD CONSTRAINT plausible_value
  CHECK (value BETWEEN -50 AND 500);
```

A `CHECK` makes the database **refuse** the bad row on write.
Set the bound from the instrument, not from hope.

---

![w:1080](figures/voltage-quality.png)

---

## Voltage is a data-quality signal

- Batteries drain past **~2.4 V** over the month
- Below that, the temperature channel **lies**
- ~18% of temps are impossible (outside 0 to 50°C)
- **Essentially all** of them: motes already below 2.4 V

The cleaning rule isn't a guess. It's in the data.

---

## So store the context

Units and calibration live in the `sensors` table,
**beside** the values they explain.

> A number without its provenance
> cannot be validated, only believed.

---

<!-- _class: section -->

# SQL that answers
## engineering questions

---

## SQL is declarative

You describe the **result** you want.
The database decides **how** to compute it.

Same query, different plan as the data grows,
with no rewrite from you. (That's what an index changes.)

---

## The vocabulary

- `SELECT` the columns
- `FROM` the table, `JOIN` another by key
- `WHERE` keeps rows
- `GROUP BY` combines rows, `HAVING` keeps groups

Almost every sensor question is a short combination of these.

---

## Time bucketing with `date_trunc`

Hourly average temperature per sensor:

```sql
SELECT sensor_id,
       date_trunc('hour', ts) AS hour,
       avg(value)             AS avg_temp
FROM   readings
WHERE  variable = 'temperature'
GROUP  BY sensor_id, hour;
```

`date_trunc` collapses irregular readings into regular buckets.

[PostgreSQL: date/time functions](https://www.postgresql.org/docs/current/functions-datetime.html)

---

## `HAVING`: filter the groups

Dropped motes = motes with too few readings.

```sql
SELECT sensor_id, count(*) AS n
FROM   readings
WHERE  variable = 'temperature'
GROUP  BY sensor_id
HAVING count(*) < 30000
ORDER  BY n;
```

`WHERE` filters rows; `HAVING` filters aggregates.

---

## Window functions

Compute across neighbouring rows **without collapsing them**.

Each reading keeps its identity **and** sees its neighbours.

`lag`, `avg(...) OVER (...)`, `rank`, …

The part of SQL that makes time-series tractable.

[PostgreSQL: window functions](https://www.postgresql.org/docs/current/tutorial-window.html)

---

## `lag`: turn gaps into a column

```sql
SELECT sensor_id, ts,
       ts - lag(ts) OVER (
         PARTITION BY sensor_id ORDER BY ts
       ) AS gap
FROM   readings
WHERE  variable = 'temperature';
```

Motes report ~every 31 s.
Any `gap` ≫ 31 s is a dropout, located in time.

---

## Rolling average, by time not rows

```sql
avg(value) OVER (
    PARTITION BY sensor_id ORDER BY ts
    RANGE BETWEEN INTERVAL '1 hour' PRECEDING
              AND CURRENT ROW
)
```

Sampling is irregular → a **time** frame is the honest one.
PostgreSQL writes it almost as you'd say it.

---

## `WHERE` + `CASE`: flag, don't just drop

```sql
WHERE r.value < 0 OR r.value > 50   -- impossible indoors
```

```sql
CASE WHEN value BETWEEN 0 AND 50
     THEN 'ok' ELSE 'suspect' END
```

Label rather than discard, when that's what you want.

---

## `JOIN`: attach the context

```sql
SELECT r.sensor_id, s.x_m, s.y_m, avg(r.value)
FROM   readings r
JOIN   sensors  s USING (sensor_id)
WHERE  r.variable = 'temperature'
GROUP  BY r.sensor_id, s.x_m, s.y_m;
```

The reading's value, placed where it was measured.

---

## Aggregates summarize a sensor

```sql
SELECT sensor_id,
       count(*), min(value), max(value),
       avg(value), stddev(value)
FROM   readings
WHERE  variable = 'temperature'
GROUP  BY sensor_id;
```

`DISTINCT` when you want the set, not the count:
`SELECT DISTINCT sensor_id FROM readings;`

---

<!-- _class: section -->

# Loading, indexes,
## and query cost

---

## Getting data in: not a loop of INSERTs

2M single-row `INSERT`s = 2M round trips = an afternoon.

**`COPY`** streams a whole file in one operation:

```sql
COPY readings (sensor_id, ts, variable, value)
FROM '/data/readings.csv'
WITH (FORMAT csv, HEADER true);
```

Orders of magnitude faster.

[PostgreSQL: COPY](https://www.postgresql.org/docs/current/sql-copy.html)

---

## The paths from Python

- **`psql`**: interactive client, `\copy` from the client side
- **[`psycopg`](https://www.psycopg.org/psycopg3/docs/)**: direct driver, `cursor.copy()`
- **[SQLAlchemy](https://www.sqlalchemy.org/)**: portable layer, pairs with pandas

---

## Real data resists the loader

This file has:

- truncated rows (a few fields only)
- sub-second timestamps
- mote ids **outside** 1 to 54 (corrupt id field)

**Staging table** pattern: `COPY` raw → clean with SQL → insert.
Cleaning rules become **queries**, and the FK catches the rest.

---

## The dominant query: a range scan

One sensor, one window of time.

Naively: read **every row**, discard misses.
A **sequential scan** costs the whole table
even for a 100-row answer.

---

## The B-tree index

Keeps keys **sorted**, so a range lookup is
a descent + a walk. Cost tracks the **result**, not the table.

For per-sensor time ranges:

```sql
CREATE INDEX ON readings (sensor_id, ts);
```

Composite, **in that order**: cluster by sensor, sort by time.

---

![w:820](figures/index-scan.png)

<span class="source">One sensor, one-hour window, as the table grows to 2.3M rows. ~67× at full size. Measured in SQLite (B-trees, like Postgres).</span>

---

## `EXPLAIN ANALYZE`: read two things

Run the query; print the real plan and timings.

1. The **scan at the base**, the strategy
   (`Seq Scan` vs `Index Only Scan`)
2. The **total execution time** at the bottom

```sql
EXPLAIN ANALYZE
SELECT count(*) FROM readings
WHERE sensor_id = 5
  AND ts BETWEEN '2004-03-15' AND '2004-03-16';
```

[PostgreSQL: using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html)

---

## Reading the plan

Before the index (9.1M rows):

```text
Aggregate
  -> Gather  (Workers Planned: 2)
       -> Parallel Seq Scan on readings
            Filter: (sensor_id = 5 AND ts BETWEEN ...)
Execution Time: ~190 ms
```

After `CREATE INDEX ... (sensor_id, ts)`:

```text
Aggregate
  -> Index Only Scan using readings_sensor_ts
Execution Time: ~0.04 ms
```

---

## Indexes are not free

- Each one costs **space**
- Each one slows every **write** (maintained on insert)
- An index the planner never uses is pure overhead

Index the access patterns you **have**;
confirm with `EXPLAIN ANALYZE`.

[PostgreSQL: indexes](https://www.postgresql.org/docs/current/indexes.html)

---

## When time-access dominates: hypertables

**[TimescaleDB](https://docs.timescale.com/use-timescale/latest/hypertables/)** auto-partitions a table into
time **chunks**.

- Query last week → touch only last week's chunks
- Compress or drop old data a chunk at a time

Same SQL, same relational model, tuned for time-series.

---

## Today's database is OLTP

Optimized for **many correct writes** and **point/range reads**:
transactions, joins, constraints, one row at a time.

Scanning three columns across ten years is a **different** job.

That's **OLAP**, and it's L4: Parquet & DuckDB.

---

<!-- _class: demo -->

# Demo

## `l03-sql-timeseries.ipynb`

PostgreSQL in Docker → schema → `COPY` 2.3M rows
→ answer engineering questions live

---

## What to watch

- `date_trunc` hourly averages
- windowed `lag` for dropouts, rolling voltage
- the impossible temps low voltage predicts
- **`EXPLAIN ANALYZE` before vs after the index**

Watch the top node flip: `Seq Scan` → `Index Only Scan`.

---

## Recap

- Long form: new sensor = `INSERT`, every question = `WHERE`
- Types with meaning: `timestamptz` UTC, `double precision`
- A type is **not** a validation (386°C)
- `date_trunc` + window functions answer time-series
- B-tree on `(sensor_id, ts)`; confirm with `EXPLAIN ANALYZE`

---

## Next

**Assignment** A2 released today, due ~1 week
**Reading** PostgreSQL window functions; Kleppmann Ch. 3
**L4** Same data, new home: Parquet & DuckDB, and when a
column store beats today's row store

Full notes, with all sources: `lectures/l03/notes.md`
