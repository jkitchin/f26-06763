#!/usr/bin/env python3
"""Generate lectures/l02/l02-scaffold.ipynb.

Unlike the L1 notebook, this one is not deliberately broken; it is the "done
right" counterpart. It rebuilds the L1 analysis as a small, reproducible
project: the terminal scaffold steps (uv, git) are shown as commands to run in a
terminal, and the Python that would live in ``src/sensorlab/`` is defined and
run here so the notebook executes top to bottom on its own.

It fixes the exact three L1 defects: a relative data path whose parent is
created, a pinned seed, and a temporal (not random) split. Each run is logged to
MLflow with the seed, a data hash, and the git SHA, so one run equals one
reproducible fact.

Keeping the notebook in a generator gives deterministic cell ids, so
regenerating produces no spurious diff. The committed .ipynb carries no outputs;
verify execution separately (see the module notes).
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l02-scaffold.ipynb"

_n = 0


def _next_id(kind):
    """Stable, deterministic cell ids so regenerating produces no spurious diff."""
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
    md("# L2 demo: from an empty directory to a tracked run\n",
       "\n",
       "In L1 an analysis failed to reproduce three ways: an absolute path, an unpinned\n",
       "split, and an unrecorded library version. Here we rebuild the same analysis the way\n",
       "it should have been built the first time: a `uv`-managed project with a locked\n",
       "environment, a pinned interpreter, relative paths, a seeded model, and each run\n",
       "logged to MLflow.\n",
       "\n",
       "There are two kinds of cell below. The **scaffold steps** are terminal commands,\n",
       "shown in fenced blocks; run those in a terminal, not in the notebook. The **Python\n",
       "cells** define the functions that, in the real project, live in `src/sensorlab/`,\n",
       "and then run them, so this notebook still executes top to bottom on its own.\n",
       "\n",
       "> Data: [UCI Air Quality Data Set](https://archive.ics.uci.edu/dataset/360/air+quality),\n",
       "> the same roadside sensor series from L1, fetched from UCI on first run."),

    md("## 1. Scaffold the project (in a terminal)\n",
       "\n",
       "```bash\n",
       "uv init --package sensorlab && cd sensorlab\n",
       "uv add pandas scikit-learn mlflow\n",
       "```\n",
       "\n",
       "`uv init --package` writes `pyproject.toml`, `.python-version`, and an importable\n",
       "`src/sensorlab/` (the `--package` flag is what makes `python -m sensorlab.train` work);\n",
       "`uv add` resolves the whole dependency graph into `uv.lock`. On any other machine,\n",
       "`uv sync` rebuilds this exact\n",
       "environment. That lockfile, not a `requirements.txt`, is what makes the rebuild\n",
       "deterministic rather than merely probable.\n",
       "\n",
       "The layout the project grows into:\n",
       "\n",
       "```text\n",
       "sensorlab/\n",
       "├── pyproject.toml\n",
       "├── uv.lock\n",
       "├── .python-version\n",
       "├── .gitignore          # data/, .venv/, mlflow.db\n",
       "├── src/sensorlab/      # load, clean, featurize, train\n",
       "├── data/               # git-ignored: raw data does not go in git\n",
       "└── tests/\n",
       "```"),

    md("## 2. The functions (`src/sensorlab/`)\n",
       "\n",
       "In the project these live in importable modules; here we define them in the notebook\n",
       "so the whole thing runs top to bottom. Two of the L1 defects are fixed in the very\n",
       "first function: the data path is **relative** and its parent is **created** if\n",
       "missing, so the fetch works on any machine rather than only the author's."),

    code("import io\n",
         "import hashlib\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "import numpy as np\n",
         "import pandas as pd\n",
         "\n",
         "DATA = Path('data/AirQualityUCI.csv')\n",
         "URL = 'https://archive.ics.uci.edu/static/public/360/air+quality.zip'\n",
         "\n",
         "\n",
         "def load(path: Path = DATA) -> pd.DataFrame:\n",
         "    \"\"\"Fetch (once) and parse the UCI Air Quality CSV.\n",
         "\n",
         "    Relative path, parent created if missing: the L1 bug, fixed. The export is\n",
         "    semicolon separated with comma decimals, has two trailing empty columns, and\n",
         "    codes missing values as -200.\n",
         "    \"\"\"\n",
         "    path.parent.mkdir(parents=True, exist_ok=True)\n",
         "    if not path.exists():\n",
         "        print(f'fetching {URL}')\n",
         "        with urllib.request.urlopen(URL) as response:\n",
         "            payload = response.read()\n",
         "        with zipfile.ZipFile(io.BytesIO(payload)) as archive:\n",
         "            path.write_bytes(archive.read('AirQualityUCI.csv'))\n",
         "    df = (\n",
         "        pd.read_csv(path, sep=';', decimal=',')\n",
         "        .dropna(axis=1, how='all')\n",
         "        .dropna(how='all')\n",
         "    )\n",
         "    df['ts'] = pd.to_datetime(\n",
         "        df['Date'] + ' ' + df['Time'].str.replace('.', ':', regex=False),\n",
         "        format='%d/%m/%Y %H:%M:%S',\n",
         "    )\n",
         "    return df.replace(-200, np.nan)\n",
         "\n",
         "\n",
         "raw = load()\n",
         "print(f'{len(raw)} rows, {raw.ts.min().date()} to {raw.ts.max().date()}')"),

    md("`clean` and `featurize` take a frame and return values, with no hidden global\n",
       "state, so they can be imported and tested in isolation. We predict the reference CO\n",
       "measurement from the cheap sensor channels plus temperature and humidity."),

    code("FEATURES = [\n",
         "    'PT08.S1(CO)', 'PT08.S2(NMHC)', 'PT08.S3(NOx)',\n",
         "    'PT08.S4(NO2)', 'PT08.S5(O3)', 'T', 'RH', 'AH',\n",
         "]\n",
         "TARGET = 'CO(GT)'\n",
         "\n",
         "\n",
         "def clean(df: pd.DataFrame) -> pd.DataFrame:\n",
         "    \"\"\"Keep rows with all features and the reference present, in time order.\"\"\"\n",
         "    return (\n",
         "        df.dropna(subset=FEATURES + [TARGET])\n",
         "        .sort_values('ts')\n",
         "        .reset_index(drop=True)\n",
         "    )\n",
         "\n",
         "\n",
         "def featurize(df: pd.DataFrame):\n",
         "    \"\"\"Return the feature matrix and target as arrays.\"\"\"\n",
         "    return df[FEATURES].to_numpy(), df[TARGET].to_numpy()\n",
         "\n",
         "\n",
         "clean_df = clean(raw)\n",
         "X, y = featurize(clean_df)\n",
         "print(f'{len(clean_df)} usable rows, {X.shape[1]} features')"),

    md("`train` takes a seed. The split is **temporal** (fit on the earlier 75%, test on\n",
       "the later 25%), which is the honest protocol for a sensor series, and the model is\n",
       "seeded so the run is reproducible."),

    code("from sklearn.ensemble import RandomForestRegressor\n",
         "from sklearn.metrics import r2_score\n",
         "\n",
         "\n",
         "def train(X, y, seed: int) -> float:\n",
         "    \"\"\"Temporal split, seeded model, return R2 on the held-out later period.\"\"\"\n",
         "    cut = int(len(X) * 0.75)\n",
         "    model = RandomForestRegressor(n_estimators=200, random_state=seed)\n",
         "    model.fit(X[:cut], y[:cut])\n",
         "    return r2_score(y[cut:], model.predict(X[cut:]))\n",
         "\n",
         "\n",
         "print(f'R2 (seed 0): {train(X, y, seed=0):.4f}')"),

    md("## 3. Track each run (MLflow)\n",
       "\n",
       "Now make each run a fact you can point to. We log the seed, a hash of the data, and\n",
       "the git commit, alongside the metric, then run the trainer twice with two seeds.\n",
       "MLflow stores the runs locally in a small SQLite file, with no server to run."),

    code("import subprocess\n",
         "\n",
         "import mlflow\n",
         "\n",
         "# MLflow 3 recommends a local database backend over the bare file store.\n",
         "mlflow.set_tracking_uri('sqlite:///mlflow.db')\n",
         "mlflow.set_experiment('l02-scaffold')\n",
         "\n",
         "\n",
         "def data_hash(path: Path) -> str:\n",
         "    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]\n",
         "\n",
         "\n",
         "def git_sha() -> str:\n",
         "    try:\n",
         "        out = subprocess.check_output(\n",
         "            ['git', 'rev-parse', '--short', 'HEAD'], text=True, stderr=subprocess.DEVNULL)\n",
         "        return out.strip()\n",
         "    except Exception:\n",
         "        return 'unknown'\n",
         "\n",
         "\n",
         "for seed in (0, 1):\n",
         "    with mlflow.start_run(run_name=f'seed-{seed}'):\n",
         "        r2 = train(X, y, seed=seed)\n",
         "        mlflow.log_params({\n",
         "            'seed': seed,\n",
         "            'model': 'rf200',\n",
         "            'data_sha': data_hash(DATA),\n",
         "            'git_sha': git_sha(),\n",
         "        })\n",
         "        mlflow.log_metric('r2', r2)\n",
         "        print(f'seed {seed}: R2 = {r2:.4f}')"),

    # We do NOT re-list the functions here (those are the code cells above). Only
    # the entry point is shown, because it is the one piece the notebook cannot
    # run: argparse would try to parse Jupyter's own launch args. It lives in a
    # fenced block in a markdown cell, so "Restart & Run All" never executes it.
    md('''## 4. Move it into the project

You do not keep this in the notebook. You move the functions above, unchanged, into
`src/sensorlab/train.py`. One thing has to be **added** that the notebook never needed: a
**command-line entry point**, so the analysis runs as a command you type rather than cells
you click in the right order.

Two things get added at the bottom of `train.py`. First, wrap the run-and-log logic (the
`for`-loop from the MLflow cell above) into a `main(seed)` that does **one** seed. Second,
add the command-line entry point that reads `--seed` and calls it. Both use the functions
and `DATA` you already moved in (`load`, `clean`, `featurize`, `train`, `data_hash`,
`git_sha`):

```python
def main(seed: int) -> None:
    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("l02-scaffold")
    X, y = featurize(clean(load()))
    with mlflow.start_run(run_name=f"seed-{seed}"):
        r2 = train(X, y, seed=seed)
        mlflow.log_params({"seed": seed, "model": "rf200",
                           "data_sha": data_hash(DATA), "git_sha": git_sha()})
        mlflow.log_metric("r2", r2)
        print(f"seed {seed}: R2 = {r2:.4f}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    main(args.seed)
```

**Why it is needed, and what each part does:**

- `if __name__ == "__main__":` runs the block **only when the file is executed directly**
  (`python -m sensorlab.train`), and **not when it is imported** (`from sensorlab.train
  import train`). That is what lets one file be both an importable library and a runnable
  program. Without the guard, this code would fire every time anything imported the
  module, including your notebook and your tests.
- `argparse` is Python's standard command-line reader. `add_argument("--seed", ...)`
  declares a `--seed` option; `parse_args()` reads what you actually typed.
- `main(args.seed)` runs one seeded, logged run. The seed becomes a knob you set on the
  command line instead of a number buried in a cell, which is the whole point: the run is
  explicit and repeatable.

It is shown here, not run: `parse_args()` inside a notebook would try to parse Jupyter's
own launch arguments and fail. In the project you run it from a terminal, once per seed:

```bash
uv run python -m sensorlab.train --seed 0
uv run python -m sensorlab.train --seed 1
```
'''),

    md("## 5. Compare the two runs\n",
       "\n",
       "The two runs are now in `mlflow.db`, whether you logged them here (the MLflow cell\n",
       "above) or from the terminal (the two commands above). Open the UI to compare them.\n",
       "\n",
       "This is a **local** command: it serves to `http://127.0.0.1:5000` on your own machine,\n",
       "so run it from the project directory. On Colab there is nothing for it to open.\n",
       "\n",
       "```bash\n",
       "uv run mlflow ui --backend-store-uri sqlite:///mlflow.db   # then open http://127.0.0.1:5000\n",
       "```\n",
       "\n",
       "You will see two runs that differ only by their seed, with slightly different R2. That\n",
       "small difference is the whole reason to log the seed: without it, neither number is\n",
       "reconstructible. The data hash and git SHA make the rest of the run reconstructible\n",
       "too, which is the provenance the L2 notes argue for.\n",
       "\n",
       "That, plus the lockfile and the tracked runs, is assignment **A1**."),
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
