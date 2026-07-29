---
marp: true
theme: course
paginate: true
header: "06-763 · L4"
footer: "Systems & Toolchains for AI in Engineering"
---

<!-- _class: title -->

# L4 · Columnar storage, Parquet, DuckDB

## Week 2 · Data Systems

**Systems & Toolchains for AI in Engineering**

---

## Roadmap

1. The query the index could not help
2. Row stores vs column stores
3. Parquet: the columnar file
4. DuckDB: SQL analytics in your process
5. The wider landscape
6. Where columns stop helping
7. Live demo: the same data, columnar

---

<!-- _class: section -->

# Why columns
## the query the index could not help

---

## L3 left us here

The Intel Lab readings in PostgreSQL,
indexed on `(sensor_id, ts)`.

One sensor, one hour → a few hundredths of a ms.

That is the **dashboard** query.

---

## The analyst asks a different question

- average temperature of **every** mote, **all** month
- daily energy across the floor, **all** year
- the distribution of one channel over **all** history

Nothing to narrow. The index has nothing to prune.

---

## So the database reads the whole table

And in a **row store**, reading every row
means reading every **column**.

Six columns in `readings`. To average one,
it drags all six off disk, for all **2.3M** rows.

---

## Cost that depends on nothing you asked for

The work grows with the **width** of the table
and the **height** of the table.

The answer, an average of one column,
depends on **neither**.

---

## The fix is the layout, not the data

Store each **column** together instead of each **row**.

Then `avg(temperature)` reads only the temperature values,
in one run, already compressed.

Same data. Different bytes. Today, measured: **~80× faster, ~5× smaller.**

---

<!-- _class: section -->

# Row stores
## and column stores

---

## Two ways to place a table on disk

**Row store:** row 1's columns, then row 2's, then row 3's.

**Column store:** all timestamps, then all motes, then all temps.

Same logical table. Different things sit **next to each other**.

---

![w:1050](figures/row-vs-column.png)

---

## OLTP vs OLAP

| OLTP (row store) | OLAP (column store) |
|---|---|
| small reads/writes of whole rows | scan few columns over many rows |
| insert, update, fetch by key | aggregate, trend, report |
| PostgreSQL (L3) | Parquet + DuckDB (today) |

Not "which is better." **Which workload is this?**

---

## The query in question

```sql
SELECT mote_id, avg(temperature)
FROM readings
GROUP BY mote_id;
```

One column, aggregated over every row.
The whole session is about making this cheap.

---

## Win 1: projection

A query that names two columns reads **two columns**.

Cost scales with the columns you **ask for**,
not the width of the table.

---

## Win 2: compression

One column holds **one type** of similar values.

A temperature near the last temperature,
a mote id repeated thousands of times.

That compresses far harder than a row's mixed bytes.

---

## Win 3: predicate pushdown

Each block carries its **min and max**.

A block whose range can't match your `WHERE`
is **skipped without being read**.

The three wins compound. Smaller data is also less to read.

---

## When columns win

Wide analytical scans:

- aggregate one channel across all of history
- scan a few columns of a very wide table
- compress cold data you rarely rewrite

---

## When columns lose

The mirror runs both ways.

- one whole row = gather from **every** column block
- one update = touch **every** column block

**Point writes and updates** are the row store's job.

---

## The trade, in one line

> Column stores win the wide analytical scan.
> Row stores win the point write and lookup.

So the column store **complements** L3's database,
it does not replace it.

[Kleppmann, DDIA ch. 3](https://www.oreilly.com/library/view/designing-data-intensive-applications/9781491903063/)

---

<!-- _class: section -->

# Parquet
## the columnar file

---

## Parquet is columnar, on disk

The standard on-disk form of a column store.
A file, not a server, that any tool can read.

---

## Inside a Parquet file

- **row groups**: horizontal slices of rows
- **column chunks**: each column stored together, compressed on its own
- a **footer** written last, with the schema and per-column stats

---

## The footer earns its keep

The **schema travels in the file**, so a reader needs
no external definition to make sense of it.

The per-column **min/max** are what let a reader
skip row groups that cannot match a filter.

---

## Compression is the free win

Measured on the Intel Lab readings:

**101 MB CSV → 18 MB Parquet.**

About 5× smaller, and every byte saved is a byte not read.

[Apache Parquet, file format](https://parquet.apache.org/docs/file-format/)

---

## Encoding, not just compression

Parquet does not merely zip bytes. Per column it applies
**dictionary** encoding for repeated values and
**run-length** encoding for runs, then compresses on top.

A mote id repeated thousands of times nearly vanishes.

---

## Partitioning prunes whole files

```text
readings/date=2004-03-01/part.parquet
readings/date=2004-03-02/part.parquet
```

A query filtered to one date opens **one folder**.
Partition on what you filter by; keep partitions from getting tiny.

---

## Writing it is one line

```python
df.to_parquet("readings.parquet", compression="snappy")
```

From pandas or PyArrow. Read it back the same way.

---

## Parquet is a file, not a database

- no indexes you build
- no transactions
- no in-place update: rewrite the file, or write new files

Great for batch analytics.
Need point updates? That data belongs in the **row store**.

---

<!-- _class: section -->

# DuckDB
## SQL analytics in your process

---

## In-process OLAP

DuckDB runs **inside your process**.

- no server to start, no connection to manage
- an analytical (OLAP) SQL engine
- roughly: **SQLite, but for analytics**

`import duckdb` and you are querying.

[Why DuckDB](https://duckdb.org/why_duckdb)

---

## It queries Parquet directly

```sql
SELECT mote_id, avg(temperature)
FROM 'readings/*.parquet'
GROUP BY mote_id;
```

No `CREATE TABLE`. No load. It reads the files where they sit,
with projection and row-group skipping.

[DuckDB: reading Parquet](https://duckdb.org/docs/stable/data/parquet/overview)

---

## And prunes partitions for free

```sql
FROM read_parquet('readings/**/*.parquet', hive_partitioning = true)
WHERE date = '2004-03-01'
```

The folder name becomes a column; the filter opens **one folder**.

---

## It reaches into PostgreSQL too

```sql
ATTACH 'dbname=labdata host=localhost' AS pg (TYPE postgres);
SELECT * FROM pg.readings LIMIT 5;
```

Query the **live** L3 database with no export.

[DuckDB: postgres extension](https://duckdb.org/docs/stable/core_extensions/postgres)

---

## Which bridges OLTP and OLAP

One query can join a small table living in **PostgreSQL**
against a large history living in **Parquet**.

The transactional store and the analytical engine,
on speaking terms, with nothing exported.

---

## Write results back out

```sql
COPY (SELECT mote_id, avg(temperature) AS avg_temp
      FROM 'readings/*.parquet' GROUP BY mote_id)
TO 'mote_avg.parquet' (FORMAT parquet);
```

Query in, Parquet out, no dataframe round-trip.

---

## It reads a dataframe, too

DuckDB can query a pandas dataframe in place
and hand results back as one.

So it is not "leave pandas." It is another tool
that meets your data where it already is.

---

## The payoff, measured

![w:1000](figures/columnar-scan.png)

---

## Read that figure

- row store: cost **climbs with the table** (reads everything)
- columnar: **nearly flat** (reads 2 columns of 6, vectorized)
- and the file is several times **smaller**

`≈80×` on the whole-table aggregate at 2.3M rows.

---

## pandas, DuckDB, or PostgreSQL?

| Tool | Reach for it when |
|---|---|
| pandas | it fits in memory, you want Python |
| DuckDB | bigger than memory, SQL, query files/DBs in place |
| PostgreSQL | live writes, transactions, many clients |

They interoperate. The choice is rarely exclusive.

---

<!-- _class: section -->

# The wider landscape
## not everything is a table

---

## Document stores

**MongoDB**: data as documents, schema varies per document.

- wrong for uniform sensor readings (you *want* the schema)
- right for **heterogeneous experiment metadata**:
  run A logged 3 params, run B logged 11

[MongoDB: document databases](https://www.mongodb.com/resources/basics/databases/document-databases)

---

## Key-value stores

**Redis**: a dictionary, often entirely in memory.

No rich queries, no joins, that is not the job.
The job is a **cache**, a config store, a hot lookup
that has to be instant.

[Redis](https://redis.io/about/)

---

## Time-series databases

**InfluxDB**: bucketing, retention, and high-rate ingest
built in, for workloads that are millions of points a second
and almost nothing else.

[InfluxDB](https://docs.influxdata.com/influxdb/v2/get-started/)

---

## Vector stores (a preview)

Not "find the row with this key" but
"find the items most **similar** to this one."

Store embeddings, search by nearest-neighbor.
The machinery under **RAG**, later in the course.

Name it now; do not build one yet. [FAISS](https://github.com/facebookresearch/faiss/wiki)

---

## The common thread

Each of these drops a relational guarantee,
usually the **schema**, the **joins**, or the **transactions**,
in exchange for a fit to one access pattern.

Choose one when your pattern demands it.

---

<!-- _class: section -->

# Where columns stop helping

---

## Wrong home for writes and updates

Parquet is effectively **immutable**.

- add data = write new files
- change a row = rewrite its file

Constantly-corrected data belongs in the row store.

---

## The layout must match the query

Columns are fast for "average this one column."

They are **slow** for "give me this whole row,"
which has to gather from every column block.

That point lookup is the row store's home turf.

---

## DuckDB is an engine, not a server

One process. Superb for one analyst, one pipeline.

**Not** a shared backend that many clients write to
concurrently with transactions.

That is still PostgreSQL's job. DuckDB **complements** it.

---

## Small data needs none of this

The 80× shows at millions of rows.

At data that fits in memory, a pandas `groupby`
is simpler and fast enough.

Match the tool to the **size**, not just the pattern.

---

## OLTP and OLAP compose

"Just use DuckDB for everything" is a trap.

Real platforms run **both**: Postgres takes the live writes,
Parquet + DuckDB scan the history, and you move data
across the seam. The `postgres` attachment is that bridge.

---

## NoSQL trades away your guarantees

Reach for a document, key-value, or time-series store
because your **access pattern** demands it.

Never just to dodge designing a schema.

---

<!-- _class: demo -->

# Demo

## `l04-storage.ipynb`

Intel Lab data → Parquet → the same query in
pandas, a SQLite row store, and DuckDB.
Then zero-import over Parquet and PostgreSQL.

---

## What to watch

1. The analytical scan: the row store **climbs**,
   DuckDB over Parquet stays **flat**.

2. DuckDB answering a query over Parquet and over
   the live Postgres it **never loaded**.

---

## Recap

- Layout should match the access pattern
- Row store / OLTP for writes and point reads (L3)
- Column store / OLAP for wide scans: Parquet + DuckDB
- Measured: `≈80×` faster, `≈5×` smaller on the scan
- DuckDB queries files and databases with **zero import**
- Document, key-value, time-series, vector: each fits one pattern

---

## Next

**Assignment** A2 (from L3): its Parquet + DuckDB half is now unblocked
**Reading** DuckDB Parquet docs; Kleppmann ch. 3
**L5** Up a layer: dataframes and scalable processing
with pandas and Polars, and batch pipelines

Full notes, with all sources: `lectures/l04/notes.md`
