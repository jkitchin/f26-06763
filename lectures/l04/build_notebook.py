#!/usr/bin/env python3
"""Generate lectures/l04/l04-storage.ipynb.

The L4 demo continues L3: the same Intel Lab readings, now stored columnar. It
writes the data to a Parquet file, asks the same analytical question three ways
(pandas, a SQLite row store, and DuckDB over Parquet) with warmed timings, then
shows DuckDB's zero-import reach: partition pruning and COPY TO.

Design notes so the numbers stay honest:
  - The head-to-head uses a SINGLE Parquet file and warms each query, so DuckDB
    is not charged cold file-open over many partitions; that isolates the layout.
  - Partitioning is shown separately, as a pruning feature, not as the timing basis.
  - Live numbers vary with hardware and warmup; the controlled figure in the notes
    (make_figures.py) is the cited measurement. The demo reproduces the direction.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The
committed .ipynb carries no outputs and must run top to bottom.
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l04-storage.ipynb"

_n = 0


def _next_id(kind):
    global _n
    _n += 1
    return f"{kind}-{_n:02d}"


def md(*lines):
    return {"cell_type": "markdown", "id": _next_id("md"),
            "metadata": {}, "source": list(lines)}


def code(*lines):
    return {"cell_type": "code", "id": _next_id("code"), "execution_count": None,
            "metadata": {}, "outputs": [], "source": list(lines)}


cells = [
    md("# L4 demo: the same data, stored columnar\n",
       "\n",
       "In L3 we put the Intel Berkeley Lab readings in a relational database and made a\n",
       "selective query fast with an index. This notebook keeps the exact same data and\n",
       "changes only where it lives: into columnar **Parquet**, queried by **DuckDB**. We ask\n",
       "one analytical question three ways and compare, then use DuckDB to query the Parquet\n",
       "with no import step.\n",
       "\n",
       "The data is fetched from a mirror on first run.\n",
       "\n",
       "> Data: [Intel Lab Data](https://db.csail.mit.edu/labdata/labdata.html), ~2.3M readings\n",
       "> from 54 motes, carried over from L3."),

    md("## 1. Load the readings\n",
       "\n",
       "Same loader as L3: a whitespace-separated export with no header, rows not in time\n",
       "order, and short or malformed rows we skip. We keep the six columns we care about."),

    code("import io\n",
         "import sqlite3\n",
         "import time\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "import duckdb\n",
         "import pandas as pd\n",
         "\n",
         "DATA = Path('data/data.txt')\n",
         "URL = 'https://raw.githubusercontent.com/linsea423/Intel_Lab_Data/master/data.zip'\n",
         "COLS = ['date', 'time', 'epoch', 'moteid',\n",
         "        'temperature', 'humidity', 'light', 'voltage']\n",
         "\n",
         "\n",
         "def load(path: Path = DATA) -> pd.DataFrame:\n",
         "    path.parent.mkdir(parents=True, exist_ok=True)\n",
         "    if not path.exists():\n",
         "        print(f'fetching {URL}')\n",
         "        with urllib.request.urlopen(URL) as r:\n",
         "            payload = r.read()\n",
         "        with zipfile.ZipFile(io.BytesIO(payload)) as z:\n",
         "            path.write_bytes(z.read('data.txt'))\n",
         "    # sep=' ' and not r'\\s+'. The delimiter is one space, and a dropped\n",
         "    # channel leaves its field empty; collapsing runs of whitespace shifts\n",
         "    # every following value one column left on the 93,879 rows that have\n",
         "    # one, silently. L3's notebook shows the damage side by side.\n",
         "    df = pd.read_csv(path, sep=' ', names=COLS, header=None, engine='c')\n",
         "    df['ts'] = pd.to_datetime(df['date'] + ' ' + df['time'],\n",
         "                              format='mixed', errors='coerce')\n",
         "    df = df.dropna(subset=['ts', 'moteid'])\n",
         "    df['moteid'] = df['moteid'].astype(int)\n",
         "    return df[['moteid', 'ts', 'temperature', 'humidity', 'light', 'voltage']]\n",
         "\n",
         "\n",
         "readings = load()\n",
         "print(f'{len(readings):,} readings, {readings.moteid.nunique()} motes, '\n",
         "      f'{readings.ts.min().date()} to {readings.ts.max().date()}')\n",
         "readings.head(3)"),

    md("## 2. Write it to Parquet, and compare size\n",
       "\n",
       "Parquet stores the table column by column, each column compressed on its own. Write\n",
       "the readings once as a single Parquet file and once as CSV, and compare the bytes on\n",
       "disk. One type of similar values per column is what compresses so well."),

    code("readings.to_parquet('data/readings.parquet', engine='pyarrow', compression='snappy')\n",
         "readings.to_csv('data/readings.csv', index=False)\n",
         "\n",
         "parq_mb = Path('data/readings.parquet').stat().st_size / 1e6\n",
         "csv_mb = Path('data/readings.csv').stat().st_size / 1e6\n",
         "print(f'CSV {csv_mb:.0f} MB   vs   Parquet {parq_mb:.0f} MB   "
         "({csv_mb / parq_mb:.1f}x smaller)')"),

    md("## 3. The same question, three ways\n",
       "\n",
       "Average temperature per mote over the whole table: a wide scan of one column across\n",
       "every row, exactly the query an index cannot help. We time each engine warmed (run\n",
       "once, then take the best of a few), so we are comparing steady-state work, not\n",
       "first-call overhead."),

    code("def bench(fn, n=5):\n",
         "    fn()  # warm up: parse, open files, fill caches\n",
         "    best = float('inf')\n",
         "    for _ in range(n):\n",
         "        s = time.perf_counter()\n",
         "        fn()\n",
         "        best = min(best, (time.perf_counter() - s) * 1000)\n",
         "    return best\n",
         "\n",
         "\n",
         "# pandas: the data is already in memory; compute in Python\n",
         "ms = bench(lambda: readings.groupby('moteid')['temperature'].mean())\n",
         "print(f'pandas (in memory)      {ms:6.0f} ms')"),

    code("# SQLite: a row store queried with SQL. It reads every column of every row.\n",
         "con = sqlite3.connect(':memory:')\n",
         "con.execute('CREATE TABLE readings (moteid INT, temperature REAL, '\n",
         "            'humidity REAL, light REAL, voltage REAL)')\n",
         "con.executemany(\n",
         "    'INSERT INTO readings VALUES (?,?,?,?,?)',\n",
         "    readings[['moteid', 'temperature', 'humidity', 'light', 'voltage']]\n",
         "    .itertuples(index=False, name=None))\n",
         "con.commit()\n",
         "Q = 'SELECT moteid, avg(temperature) FROM readings GROUP BY moteid'\n",
         "print(f'SQLite (row store)      {bench(lambda: con.execute(Q).fetchall()):6.0f} ms')"),

    code("# DuckDB over Parquet: a column store. It reads only moteid and temperature,\n",
         "# vectorized, straight from the file with no import step.\n",
         "duck_q = (\"SELECT moteid, avg(temperature) \"\n",
         "          \"FROM 'data/readings.parquet' GROUP BY moteid\")\n",
         "print(f'DuckDB + Parquet        {bench(lambda: duckdb.sql(duck_q).fetchall()):6.0f} ms')\n",
         "duckdb.sql(duck_q).df().head(3)"),

    md("All three return the same answer. pandas is fast because the data already sits in\n",
       "memory; the fair storage-to-storage comparison is the **row store** against the\n",
       "**column store**, and DuckDB over Parquet wins the analytical scan by a wide margin\n",
       "because it touches two columns of six and processes them in vectorized batches. The\n",
       "notes' figure isolates this under controlled warmup; your exact numbers will vary with\n",
       "hardware, but the direction is the lesson."),

    md("## 4. DuckDB's zero-import reach\n",
       "\n",
       "DuckDB queried the Parquet with no `CREATE TABLE` and no load. Two more moves it makes\n",
       "for free. **Partitioning**: write a directory tree keyed by date, and a filter on the\n",
       "date opens only the matching folders. **COPY TO**: stream a query result straight out\n",
       "to a new Parquet file."),

    code("# write a date-partitioned copy: readings_parquet/date=2004-03-01/...\n",
         "part = readings.assign(date=readings['ts'].dt.date.astype(str))\n",
         "part.to_parquet('readings_parquet', partition_cols=['date'],\n",
         "                engine='pyarrow', compression='snappy')\n",
         "\n",
         "# hive_partitioning exposes the folder's `date` as a column; the filter prunes folders\n",
         "duckdb.sql(\"\"\"\n",
         "    SELECT count(*) AS n, round(avg(temperature), 2) AS avg_temp\n",
         "    FROM read_parquet('readings_parquet/**/*.parquet', hive_partitioning = true)\n",
         "    WHERE date = '2004-03-01'\n",
         "\"\"\").show()"),

    code("# COPY a query result straight to a new Parquet file, no dataframe round-trip\n",
         "duckdb.sql(\"\"\"\n",
         "    COPY (SELECT moteid, avg(temperature) AS avg_temp\n",
         "          FROM 'data/readings.parquet' GROUP BY moteid)\n",
         "    TO 'data/mote_avg.parquet' (FORMAT parquet)\n",
         "\"\"\")\n",
         "print('wrote data/mote_avg.parquet')"),

    md("---\n",
       "\n",
       "## Takeaway\n",
       "\n",
       "The row store from L3 (OLTP) is built for writes and point lookups; the column store\n",
       "here (OLAP) is built for scanning a few columns over the whole history, and it is much\n",
       "faster and smaller for exactly that. Real platforms run both and move data across the\n",
       "seam on purpose. Assignment **A2** has you load the\n",
       "same dataset into PostgreSQL and into Parquet/DuckDB and compare, so the second half\n",
       "starts here."),
]

# The Colab bootstrap cell, injected from the notebook's own imports so this
# generator does not carry a second copy of the requirement list. See
# tools/colab_setup.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells = with_colab_cell(cells, OUT)

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT} ({len(cells)} cells)")
