#!/usr/bin/env python3
"""Generate lectures/l03/l03-sql-timeseries.ipynb.

The notebook is the artifact driven live in L3. Keeping it in a generator means
the SQL and the cell structure live in one readable place rather than in the
.ipynb JSON. Unlike the L1 demo, this notebook is NOT deliberately broken; it is
meant to run top to bottom against a PostgreSQL brought up from the sibling
docker-compose.yml.

Regenerate with:  python build_notebook.py
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l03-sql-timeseries.ipynb"

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


# The Colab bootstrap, kept as one readable block. subprocess is called with an
# argv list rather than a shell string, so the SQL below needs no shell quoting:
# `$$` inside double quotes would otherwise expand to the shell's process id.
COLAB_PG = """# Only if you have no PostgreSQL of your own. Does nothing outside Colab.
import os
import subprocess
import sys

if 'google.colab' in sys.modules:
    def run(*cmd, **kw):
        print('$', ' '.join(cmd))
        return subprocess.run(cmd, **kw)

    run('apt-get', '-y', '-qq', 'update', check=True)
    run('apt-get', '-y', '-qq', 'install', 'postgresql', check=True)
    run('service', 'postgresql', 'start', check=True)

    # CREATE ROLE has no IF NOT EXISTS, hence the DO block, so re-running this
    # cell is harmless. createdb has no equivalent at all, so a second run is
    # simply allowed to fail.
    run('sudo', '-u', 'postgres', 'psql', '-c',
        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='demo') "
        "THEN CREATE ROLE demo LOGIN PASSWORD 'demo' SUPERUSER; END IF; END $$;",
        check=True)
    run('sudo', '-u', 'postgres', 'createdb', '-O', 'demo', 'sensors')

    # The next cell reads this, so nothing downstream changes.
    os.environ['L3_DSN'] = 'postgresql+psycopg://demo:demo@localhost:5432/sensors'
    print('\\nPostgreSQL is up, and L3_DSN points at it.')
else:
    print('Not on Colab, so nothing to do here. Use docker compose up -d.')"""


cells = [
    md("# L3 demo: a month of sensor data in PostgreSQL\n",
       "\n",
       "This notebook loads the Intel Berkeley Lab sensor data (54 motes, about 2.3\n",
       "million readings over roughly a month) into PostgreSQL, then answers the\n",
       "engineering questions from the notes with SQL: hourly averages, dropout\n",
       "detection, rolling windows, range checks, and a before/after look at an index\n",
       "with `EXPLAIN ANALYZE`.\n",
       "\n",
       "**Prerequisites.** A running PostgreSQL. The simplest way is the sibling\n",
       "`docker-compose.yml`:\n",
       "\n",
       "```bash\n",
       "docker compose up -d          # starts postgres on localhost:5432\n",
       "```\n",
       "\n",
       "The database, user, and password below match that compose file. If you cannot\n",
       "install Docker, the next section starts PostgreSQL inside Colab instead.\n",
       "Install the Python dependencies with `uv`:\n",
       "\n",
       "```bash\n",
       "uv run --with pandas,psycopg[binary],sqlalchemy jupyter lab\n",
       "```\n"),

    md("## No Docker? Start PostgreSQL here instead\n",
       "\n",
       "Colab cannot run Docker. It is itself a sandboxed container with no daemon\n",
       "and no privileged access, so `docker compose up` has nothing to talk to.\n",
       "Docker is not the requirement though: PostgreSQL is, and Colab runs as root\n",
       "with `apt`, so the server can simply be installed here.\n",
       "\n",
       "Run the cell below **only if you have no PostgreSQL of your own**. On a\n",
       "machine where `docker compose up -d` already worked, skip it; it does nothing\n",
       "outside Colab anyway.\n",
       "\n",
       "Two things to know before relying on this. A Colab runtime is temporary, so\n",
       "the download and the load happen again every session and disappear when it\n",
       "disconnects. And the index comparison later in this notebook is timed on\n",
       "shared, throttled hardware, so expect the numbers to be mushier than the ones\n",
       "in the notes. Nothing here needs PostgreSQL 16 specifically: the newest\n",
       "feature used is a generated column, which arrived in 12."),
    code(* COLAB_PG.splitlines(keepends=True)),

    md("## Connect\n",
       "\n",
       "One SQLAlchemy engine for reading query results into pandas, and one plain\n",
       "`psycopg` connection for the fast `COPY` load. The DSN is overridable by\n",
       "environment variable so the same notebook works against a hosted instance."),
    code("import os\n",
         "import sqlalchemy as sa\n",
         "\n",
         "DSN = os.environ.get(\n",
         "    'L3_DSN', 'postgresql+psycopg://demo:demo@localhost:5432/sensors')\n",
         "engine = sa.create_engine(DSN)\n",
         "\n",
         "with engine.connect() as c:\n",
         "    print(c.execute(sa.text('select version()')).scalar())"),

    md("## Fetch and parse the raw data\n",
       "\n",
       "The raw `data.txt` has eight columns and no header:\n",
       "`date time epoch moteid temperature humidity light voltage`. It is cached\n",
       "locally on first run. The rows are not in time order, and some `moteid`\n",
       "values fall outside the documented 1-54, both of which are normal for a\n",
       "sensor-network export and neither of which is announced.\n",
       "\n",
       "**The delimiter is a single space, and getting that wrong is the trap in this\n",
       "file.** A transmission that dropped a channel leaves that field *empty*, so\n",
       "the row reads `... 42.5178  2.65143` with two spaces in it, and 93,879 of the\n",
       "2,313,682 rows are like that. `sep=' '` sees eight fields on every one of\n",
       "them and turns the empty one into `NaN`, which is what an absent measurement\n",
       "is. The reflex, `sep=r'\\s+'`, collapses the two spaces into one, sees seven\n",
       "fields, and shifts every following value one column to the left, so the\n",
       "voltage lands in `light` and `voltage` becomes null.\n",
       "\n",
       "Nothing raises. `on_bad_lines` does not fire, because pandas pads a short row\n",
       "with `NaN` rather than calling it bad; the row count is identical either way.\n",
       "The cell after this one shows the difference the only way you can see it,\n",
       "which is by looking at where the nulls ended up. This is the \"real data\n",
       "resists the loader\" section of the notes, in the one place it costs you\n",
       "something."),
    code("import io, urllib.request, zipfile\n",
         "from pathlib import Path\n",
         "import pandas as pd\n",
         "\n",
         "CACHE = Path('.cache'); CACHE.mkdir(exist_ok=True)\n",
         "txt = CACHE / 'data.txt'\n",
         "URL = ('https://raw.githubusercontent.com/'\n",
         "       'linsea423/Intel_Lab_Data/master/data.zip')\n",
         "if not txt.exists():\n",
         "    print('downloading', URL)\n",
         "    with urllib.request.urlopen(URL) as r:\n",
         "        buf = r.read()\n",
         "    with zipfile.ZipFile(io.BytesIO(buf)) as z:\n",
         "        txt.write_bytes(z.read('data.txt'))\n",
         "\n",
         "cols = ['date', 'time', 'epoch', 'moteid',\n",
         "        'temperature', 'humidity', 'light', 'voltage']\n",
         "# sep=' ' and not r'\\s+': an empty field is an absent measurement, and a\n",
         "# parser that collapses whitespace shifts it away. See the text above.\n",
         "raw = pd.read_csv(txt, sep=' ', names=cols, header=None, engine='c')\n",
         "print(f'{len(raw):,} rows, {int(raw.isna().any(axis=1).sum()):,} with a missing field')\n",
         "raw.head()"),

    md("### The same file, parsed the wrong way\n",
       "\n",
       "Run this once, look at the two rows of null counts, and then forget the\n",
       "second parser exists. Both read every row and neither complains."),
    code("wrong = pd.read_csv(txt, sep=r'\\s+', names=cols, header=None,\n",
         "                    engine='c', on_bad_lines='skip')\n",
         "print(f'sep=\\' \\'    {len(raw):,} rows')\n",
         "print(raw[cols[4:]].isna().sum().to_string())\n",
         "print(f'\\nsep=r\\'\\\\s+\\'  {len(wrong):,} rows')\n",
         "print(wrong[cols[4:]].isna().sum().to_string())\n",
         "\n",
         "# Where did the 93,878 missing light readings go? Into `light` as voltages.\n",
         "shifted = wrong[wrong.light.between(2.0, 3.0) & wrong.voltage.isna()]\n",
         "print(f'\\n{len(shifted):,} rows where \\'light\\' holds a number in the 2-3 V band'\n",
         "      f' and voltage is null: {wrong.voltage.max():.3g} V is the highest voltage'\n",
         "      f' it can now see, against {raw.voltage.max():.4g} V in the correct parse.')\n",
         "del wrong, shifted"),

    md("## Clean, then reshape to the long/tidy form\n",
       "\n",
       "We keep only motes in the documented 1-54 range, build a real `timestamptz`\n",
       "from the date and time, and melt the four measured channels into the tidy\n",
       "`(sensor_id, ts, variable, value)` shape the schema uses. This is the wide to\n",
       "long move from the notes, done once in pandas before the data ever reaches\n",
       "the database."),
    code("df = raw.dropna(subset=['moteid']).copy()\n",
         "df['moteid'] = df['moteid'].astype(int)\n",
         "df = df[df.moteid.between(1, 54)]\n",
         "df['ts'] = pd.to_datetime(df['date'] + ' ' + df['time'],\n",
         "                          format='mixed', errors='coerce')\n",
         "df = df.dropna(subset=['ts'])\n",
         "\n",
         "long = df.melt(\n",
         "    id_vars=['moteid', 'ts'],\n",
         "    value_vars=['temperature', 'humidity', 'light', 'voltage'],\n",
         "    var_name='variable', value_name='value',\n",
         ").dropna(subset=['value']).rename(columns={'moteid': 'sensor_id'})\n",
         "# one row per (sensor, ts, variable): drop the occasional duplicate\n",
         "long = long.drop_duplicates(['sensor_id', 'ts', 'variable'])\n",
         "print(f'{len(long):,} tidy readings, '\n",
         "      f'{long.sensor_id.nunique()} sensors, '\n",
         "      f\"{long.variable.nunique()} variables\")\n",
         "long.head()"),

    md("## Create the schema\n",
       "\n",
       "Three tables. `sensors` holds static per-mote metadata, `variables` holds the\n",
       "unit and plausible range of each measured quantity, and `readings` holds the\n",
       "facts, tied to the two dimensions by foreign keys. The foreign key on\n",
       "`sensor_id` is what makes a reading from a non-existent mote impossible rather\n",
       "than merely unlikely.\n",
       "\n",
       "One deliberate choice for the index section later: `readings` uses a surrogate\n",
       "`id` key and is **not** indexed on `(sensor_id, ts)` yet, so we can watch an\n",
       "index change the query plan. In production you would make\n",
       "`(sensor_id, ts, variable)` the primary key, which enforces one row per\n",
       "reading *and* gives you the `(sensor_id, ts)` index below for free."),
    code("SCHEMA = '''\n",
         "DROP TABLE IF EXISTS readings;\n",
         "DROP TABLE IF EXISTS variables;\n",
         "DROP TABLE IF EXISTS sensors;\n",
         "\n",
         "CREATE TABLE sensors (\n",
         "    sensor_id int PRIMARY KEY,\n",
         "    x_m double precision,\n",
         "    y_m double precision\n",
         ");\n",
         "\n",
         "CREATE TABLE variables (\n",
         "    variable text PRIMARY KEY,\n",
         "    unit text NOT NULL,\n",
         "    lo double precision,\n",
         "    hi double precision\n",
         ");\n",
         "\n",
         "CREATE TABLE readings (\n",
         "    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,\n",
         "    sensor_id int NOT NULL REFERENCES sensors (sensor_id),\n",
         "    ts        timestamptz NOT NULL,\n",
         "    variable  text NOT NULL REFERENCES variables (variable),\n",
         "    value     double precision\n",
         ");\n",
         "'''\n",
         "with engine.begin() as c:\n",
         "    c.execute(sa.text(SCHEMA))\n",
         "print('schema created')"),

    md("## Populate the dimensions\n",
       "\n",
       "The motes that actually appear in the data, and one row per measured quantity\n",
       "with its unit and a plausible physical range. Real mote coordinates live in\n",
       "the dataset's `mote_locs.txt`; we leave `x_m`/`y_m` null here and let the\n",
       "foreign key do its job."),
    code("import pandas as pd\n",
         "# insert only sensor_id; x_m/y_m stay NULL (they live in mote_locs.txt)\n",
         "sensors = pd.DataFrame({'sensor_id': sorted(long.sensor_id.unique())})\n",
         "sensors.to_sql('sensors', engine, if_exists='append', index=False)\n",
         "\n",
         "# The same bands the notes use, so the 0-to-50 C figure there and the\n",
         "# range query below are talking about one rule rather than two.\n",
         "variables = pd.DataFrame([\n",
         "    ('temperature', 'degC', 0.0, 50.0),\n",
         "    ('humidity', '%RH', 0.0, 100.0),\n",
         "    ('light', 'lux', 0.0, 2000.0),\n",
         "    ('voltage', 'V', 2.0, 3.5),\n",
         "], columns=['variable', 'unit', 'lo', 'hi'])\n",
         "variables.to_sql('variables', engine, if_exists='append', index=False)\n",
         "print(sensors.shape[0], 'sensors,', variables.shape[0], 'variables')"),

    md("## Load the readings with COPY\n",
       "\n",
       "`COPY` streams the whole table in one operation, which is the difference\n",
       "between a few seconds and an afternoon of row-by-row `INSERT`s. We hand it a\n",
       "CSV in memory through `psycopg`'s copy interface."),
    code("import psycopg\n",
         "\n",
         "raw_dsn = engine.url.render_as_string(hide_password=False).replace(\n",
         "    'postgresql+psycopg://', 'postgresql://')\n",
         "\n",
         "buf = io.StringIO()\n",
         "long[['sensor_id', 'ts', 'variable', 'value']].to_csv(\n",
         "    buf, index=False, header=False)\n",
         "buf.seek(0)\n",
         "\n",
         "copy_sql = ('COPY readings (sensor_id, ts, variable, value) '\n",
         "            'FROM STDIN WITH (FORMAT csv)')\n",
         "with psycopg.connect(raw_dsn) as conn:\n",
         "    with conn.cursor() as cur:\n",
         "        with cur.copy(copy_sql) as cp:\n",
         "            for chunk in iter(lambda: buf.read(1 << 20), ''):\n",
         "                cp.write(chunk)\n",
         "    conn.commit()\n",
         "\n",
         "def q(sql):\n",
         "    '''Run SQL and return the result as a DataFrame.'''\n",
         "    with engine.connect() as c:\n",
         "        return pd.read_sql_query(sa.text(sql), c)\n",
         "\n",
         "print(q('SELECT count(*) AS n FROM readings').n[0], 'readings loaded')"),

    md("## The foreign key is not decorative\n",
       "\n",
       "A reading for a mote that is not in `sensors` is rejected on the spot. This is\n",
       "the integrity guarantee a CSV cannot make."),
    code("from sqlalchemy.exc import IntegrityError\n",
         "try:\n",
         "    with engine.begin() as c:\n",
         "        c.execute(sa.text(\n",
         "            \"INSERT INTO readings (sensor_id, ts, variable, value) \"\n",
         "            \"VALUES (999, now(), 'temperature', 21.0)\"))\n",
         "    print('inserted (unexpected)')\n",
         "except IntegrityError as e:\n",
         "    print('rejected, as it should be:')\n",
         "    print(' ', str(e.orig).splitlines()[0])"),

    md("## Question 1: hourly average temperature per sensor\n",
       "\n",
       "`date_trunc` buckets the irregular readings into clean hours; `GROUP BY` does\n",
       "the rest. This is the query the whole session is built around."),
    code("q('''\n",
         "SELECT sensor_id,\n",
         "       date_trunc('hour', ts) AS hour,\n",
         "       round(avg(value)::numeric, 2) AS avg_temp\n",
         "FROM   readings\n",
         "WHERE  variable = 'temperature'\n",
         "GROUP  BY sensor_id, hour\n",
         "ORDER  BY sensor_id, hour\n",
         "LIMIT  8\n",
         "''')"),

    md("## Question 2: which motes dropped out?\n",
       "\n",
       "A mote that went quiet reported far fewer times than a healthy one. `HAVING`\n",
       "filters on the aggregate, so this is a one-statement dropout report."),
    code("q('''\n",
         "SELECT sensor_id, count(*) AS n_temp_readings\n",
         "FROM   readings\n",
         "WHERE  variable = 'temperature'\n",
         "GROUP  BY sensor_id\n",
         "HAVING count(*) < 30000\n",
         "ORDER  BY n_temp_readings\n",
         "LIMIT  8\n",
         "''')"),

    md("## Question 3: gaps in reporting, with a window function\n",
       "\n",
       "`lag` reaches back to a sensor's previous reading, so `ts - lag(ts)` is the\n",
       "gap since it last reported. Motes aim for one reading about every 31 seconds,\n",
       "so the large gaps are the dropouts, located exactly in time."),
    code("q('''\n",
         "WITH gaps AS (\n",
         "  SELECT sensor_id, ts,\n",
         "         ts - lag(ts) OVER (PARTITION BY sensor_id ORDER BY ts) AS gap\n",
         "  FROM   readings\n",
         "  WHERE  variable = 'temperature'\n",
         ")\n",
         "SELECT sensor_id, ts, gap\n",
         "FROM   gaps\n",
         "WHERE  gap > interval '1 hour'\n",
         "ORDER  BY gap DESC\n",
         "LIMIT  8\n",
         "''')"),

    md("## Question 4: a rolling 1-hour average voltage\n",
       "\n",
       "The same window machinery with an aggregate and a time-based frame. Because\n",
       "the sampling is irregular, a `RANGE` frame measured in time is the honest\n",
       "choice, not a fixed number of rows."),
    code("q('''\n",
         "SELECT sensor_id, ts,\n",
         "       round(value::numeric, 3) AS voltage,\n",
         "       round(avg(value) OVER (\n",
         "         PARTITION BY sensor_id ORDER BY ts\n",
         "         RANGE BETWEEN interval '1 hour' PRECEDING AND CURRENT ROW\n",
         "       )::numeric, 3) AS voltage_1h_avg\n",
         "FROM   readings\n",
         "WHERE  variable = 'voltage' AND sensor_id = 1\n",
         "ORDER  BY ts\n",
         "LIMIT  8\n",
         "''')"),

    md("## Question 5: the impossible readings, and what predicts them\n",
       "\n",
       "Roughly a fifth of the temperature readings are physically impossible for an\n",
       "indoor lab. Joining each temperature reading to the same mote's voltage at the\n",
       "same instant shows why: nearly every impossible temperature comes from a mote\n",
       "whose battery had already fallen below about 2.4 V. Voltage is a data-quality\n",
       "signal, not just housekeeping."),
    code("q('''\n",
         "WITH t AS (\n",
         "  SELECT sensor_id, ts, value AS temp FROM readings\n",
         "  WHERE variable = 'temperature'\n",
         "), v AS (\n",
         "  SELECT sensor_id, ts, value AS volt FROM readings\n",
         "  WHERE variable = 'voltage'\n",
         ")\n",
         "SELECT\n",
         "  count(*) FILTER (WHERE temp < 0 OR temp > 50) AS impossible,\n",
         "  round(100.0 * avg((temp < 0 OR temp > 50)::int), 1) AS pct_impossible,\n",
         "  round(100.0 * (count(*) FILTER (WHERE (temp < 0 OR temp > 50)\n",
         "                                    AND volt < 2.4))\n",
         "        / nullif(count(*) FILTER (WHERE temp < 0 OR temp > 50), 0), 1)\n",
         "        AS pct_of_impossible_below_2v4\n",
         "FROM t JOIN v USING (sensor_id, ts)\n",
         "''')"),

    md("## Indexing: the same range query, before and after\n",
       "\n",
       "The query that dominates time-series work is a single sensor over a window of\n",
       "time. Read the plan from the scan at the base (`Seq Scan` vs `Index Only\n",
       "Scan`) and the total execution time at the bottom. With no index on\n",
       "`(sensor_id, ts)`, it is a sequential scan of the whole table, parallelized\n",
       "across workers but still touching every row."),
    code("def explain(sql):\n",
         "    for row in q('EXPLAIN ANALYZE ' + sql)['QUERY PLAN']:\n",
         "        print(row)\n",
         "\n",
         "RANGE_Q = '''\n",
         "SELECT count(*) FROM readings\n",
         "WHERE  sensor_id = 1\n",
         "  AND  ts BETWEEN '2004-03-15' AND '2004-03-16'\n",
         "'''\n",
         "explain(RANGE_Q)"),

    md("Now add the composite B-tree on `(sensor_id, ts)` and run the identical\n",
       "query. The top node changes to an index scan and the execution time collapses."),
    code("with engine.begin() as c:\n",
         "    c.execute(sa.text(\n",
         "        'CREATE INDEX IF NOT EXISTS readings_sensor_ts '\n",
         "        'ON readings (sensor_id, ts)'))\n",
         "    c.execute(sa.text('ANALYZE readings'))\n",
         "explain(RANGE_Q)"),

    md("## Where this goes next\n",
       "\n",
       "Everything here is OLTP: correct writes, foreign keys, and fast point and\n",
       "range reads over a row store. L4 keeps this exact dataset and changes only\n",
       "where it lives, into columnar Parquet and the embedded engine DuckDB, and\n",
       "asks when an analytical column store beats the database we just built.\n"),
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
        "kernelspec": {"display_name": "Python 3", "language": "python",
                       "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT} ({len(cells)} cells)")
