#!/usr/bin/env python3
"""Generate lectures/l08/l08-splits-versioning.ipynb.

The L8 demo is the payoff of the Data Systems arc: a leak that inflates a score,
then the versioning and tracking that make an honest result reproducible.

  1. Build per-engine features and a clipped RUL target on C-MAPSS FD001.
  2. Score one RandomForest two ways, a random row split and a per-unit
     GroupKFold. The random split leaks and looks about 37% better.
  3. Show the mechanism: count engines that land in both halves of a random split.
  4. Content-hash the feature file, the value a DVC .dvc metafile would store,
     and narrate the DVC workflow (add, dvc.yaml, local remote) without needing
     DVC installed.
  5. Log the leaky and honest runs to MLflow (sqlite) tagged with the data hash.
  6. Data-centric iteration: hold the model and the honest split fixed, improve
     the features, and measure the gain.

Design notes:
  - Same loader, features, model, and folds as figures/make_figures.py, so the
    demo reproduces the figure's numbers (about 12.2 random, 16.7 grouped).
  - DVC is narrated, not executed, per the course choice; the runnable core is
    the leak quantification and the MLflow tracking.
  - Runs top to bottom on "Restart and Run All"; relative paths only; the seed
    is fixed. C-MAPSS is fetched and cached under data/ (gitignored).

Kept in a generator for deterministic cell ids and no hand-edited JSON.
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).parent / "l08-splits-versioning.ipynb"

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
    md("# L8 demo: the split that inflates a score, then versioning\n",
       "\n",
       "We reuse the NASA C-MAPSS turbofan data from L7 and predict remaining useful life\n",
       "(RUL). The point of this notebook is not the model. It is that the same model and the\n",
       "same features can report two very different scores depending only on how the rows are\n",
       "split, and that only one of those scores is the one the model will earn on a new engine.\n",
       "\n",
       "Then we make the honest result reproducible: content-hash the data the way DVC does,\n",
       "and log the runs to MLflow tagged with that hash.\n",
       "\n",
       "> Data: [C-MAPSS FD001](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/),\n",
       "> 100 run-to-failure engines, carried over from L7."),

    md("## 1. Load C-MAPSS FD001\n",
       "\n",
       "One row per engine per cycle: 3 operational settings and 21 sensor channels, with the\n",
       "failure cycle known in the training data. Fetched once and cached under `data/`."),

    code("import io\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "import numpy as np\n",
         "import pandas as pd\n",
         "\n",
         "CACHE = Path('data/CMAPSS')\n",
         "URL = ('https://phm-datasets.s3.amazonaws.com/NASA/'\n",
         "       '6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip')\n",
         "NEEDED = ['train_FD001.txt', 'test_FD001.txt', 'RUL_FD001.txt', 'readme.txt']\n",
         "\n",
         "N_SETTINGS, N_SENSORS = 3, 21\n",
         "COLUMNS = (['unit', 'cycle']\n",
         "           + [f'setting{i + 1}' for i in range(N_SETTINGS)]\n",
         "           + [f'sensor{i + 1}' for i in range(N_SENSORS)])\n",
         "\n",
         "\n",
         "def fetch():\n",
         "    CACHE.mkdir(parents=True, exist_ok=True)\n",
         "    if all((CACHE / f).exists() for f in NEEDED):\n",
         "        return\n",
         "    print('downloading', URL)\n",
         "    with urllib.request.urlopen(URL) as r:\n",
         "        payload = r.read()\n",
         "    outer = zipfile.ZipFile(io.BytesIO(payload))\n",
         "    inner_name = next(n for n in outer.namelist() if n.lower().endswith('.zip'))\n",
         "    inner = zipfile.ZipFile(io.BytesIO(outer.read(inner_name)))\n",
         "    for name in NEEDED:\n",
         "        (CACHE / name).write_bytes(inner.read(name))\n",
         "\n",
         "\n",
         "fetch()\n",
         "train = pd.read_csv(CACHE / 'train_FD001.txt', sep=r'\\s+', header=None, names=COLUMNS)\n",
         "train[['unit', 'cycle']] = train[['unit', 'cycle']].astype(int)\n",
         "print(f\"{len(train):,} rows, {train['unit'].nunique()} engines\")\n",
         "train.head(3)"),

    md("## 2. Per-engine features and a clipped RUL target\n",
       "\n",
       "Every rolling feature is computed **within an engine** (`groupby('unit')`), never across\n",
       "the boundary between one engine and the next, exactly as L7 insisted. Six of the 21\n",
       "sensors are constant and drop out. The target is remaining cycles, clipped at 125, which\n",
       "is a modeling choice this dataset conventionally makes."),

    code("WINDOW, RUL_CAP, SEED = 5, 125, 0\n",
         "\n",
         "\n",
         "def build_features(df, rolling=True):\n",
         "    df = df.sort_values(['unit', 'cycle']).reset_index(drop=True)\n",
         "    sensors = [c for c in df.columns if c.startswith('sensor')]\n",
         "    live = [c for c in sensors if df[c].nunique() > 1]\n",
         "    g = df.groupby('unit', group_keys=False)\n",
         "    feats = {'cycle': df['cycle']}\n",
         "    for c in live:\n",
         "        feats[c] = df[c]\n",
         "        if rolling:\n",
         "            feats[f'{c}_rmean'] = g[c].transform(\n",
         "                lambda s: s.rolling(WINDOW, min_periods=1).mean())\n",
         "            feats[f'{c}_rstd'] = g[c].transform(\n",
         "                lambda s: s.rolling(WINDOW, min_periods=1).std()).fillna(0.0)\n",
         "    X = pd.DataFrame(feats)\n",
         "    life = g['cycle'].transform('max')\n",
         "    y = (life - df['cycle']).clip(upper=RUL_CAP).to_numpy()\n",
         "    groups = df['unit'].to_numpy()\n",
         "    return X, y, groups, live\n",
         "\n",
         "\n",
         "X, y, groups, live = build_features(train)\n",
         "print(f'{X.shape[1]} features from {len(live)} live sensors; target clipped at {RUL_CAP}')"),

    md("## 3. The same model, two splits\n",
       "\n",
       "We score one RandomForest with 5-fold cross-validation two ways. A **random** split\n",
       "shuffles the rows. A **grouped** split keeps each engine wholly in train or in test. The\n",
       "only difference between the two calls is the splitter."),

    code("from sklearn.ensemble import RandomForestRegressor\n",
         "from sklearn.model_selection import KFold, GroupKFold, cross_val_score\n",
         "\n",
         "model = RandomForestRegressor(n_estimators=100, n_jobs=-1, random_state=SEED)\n",
         "rmse = 'neg_root_mean_squared_error'\n",
         "\n",
         "random_rmse = -cross_val_score(\n",
         "    model, X, y, cv=KFold(5, shuffle=True, random_state=SEED), scoring=rmse).mean()\n",
         "group_rmse = -cross_val_score(\n",
         "    model, X, y, cv=GroupKFold(5), groups=groups, scoring=rmse).mean()\n",
         "\n",
         "print(f'random row split (leaks) : {random_rmse:5.2f} cycles RMSE')\n",
         "print(f'per-unit GroupKFold      : {group_rmse:5.2f} cycles RMSE')\n",
         "print(f'the leak makes the model look {group_rmse / random_rmse:.2f}x better than it is')"),

    md("The random split reports the lower error, so it is the one a careless review would\n",
       "ship. The grouped split reports what the model will actually earn on an engine it has\n",
       "never seen. Same rows, same model; only the split differs."),

    md("## 4. Why the random split leaks\n",
       "\n",
       "Consecutive cycles of one engine are near-duplicates, so a shuffled split puts almost\n",
       "every engine on both sides of the line. We can count it directly for one split."),

    code("from sklearn.model_selection import train_test_split\n",
         "\n",
         "idx = np.arange(len(X))\n",
         "tr, te = train_test_split(idx, test_size=0.2, random_state=SEED)\n",
         "both = set(groups[tr]) & set(groups[te])\n",
         "print(f'{len(both)} of {train[\"unit\"].nunique()} engines appear in BOTH train and test')\n",
         "print('so the model is graded on cycles almost identical to ones it trained on')"),

    md("The honest splitters keep an entity whole. `GroupKFold` and `GroupShuffleSplit` split\n",
       "by engine; `TimeSeriesSplit` trains on past cycles and tests on later ones. All three\n",
       "take the same one-line shape as the calls above."),

    code("from sklearn.model_selection import GroupShuffleSplit, TimeSeriesSplit\n",
         "\n",
         "gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)\n",
         "tr_g, te_g = next(gss.split(X, y, groups))\n",
         "print(f'GroupShuffleSplit holds out {len(set(groups[te_g]))} whole engines, '\n",
         "      f'{len(set(groups[tr_g]) & set(groups[te_g]))} shared')\n",
         "print(f'TimeSeriesSplit gives {TimeSeriesSplit(n_splits=5).get_n_splits()} past/future folds')"),

    md("## 5. Version the data by content\n",
       "\n",
       "Reproducing a result means pinning the data as precisely as the code. DVC does this by\n",
       "**content hashing**: it hashes the file's bytes and tracks that hash in git. We can\n",
       "compute the same hash ourselves to see what it stores."),

    code("import hashlib\n",
         "\n",
         "Path('artifacts').mkdir(exist_ok=True)\n",
         "feature_path = Path('artifacts/features.parquet')\n",
         "X.assign(rul=y, unit=groups).to_parquet(feature_path)\n",
         "\n",
         "digest = hashlib.md5(feature_path.read_bytes()).hexdigest()\n",
         "print(f'{feature_path}  ->  md5 {digest}')\n",
         "print('this hash is exactly what a .dvc metafile records for the file')"),

    md("### Narrated DVC workflow (commands shown, not run here)\n",
       "\n",
       "DVC is a command-line tool. In the assignment you run these; the point to see now is that\n",
       "the `.dvc` metafile git tracks is tiny, and the data itself goes to a cache and a\n",
       "**local remote that is just a directory**, so no cloud account is needed.\n",
       "\n",
       "```bash\n",
       "dvc init\n",
       "dvc remote add -d local ../dvc-store    # a plain directory\n",
       "dvc add artifacts/features.parquet      # hashes + caches the file\n",
       "git add artifacts/features.parquet.dvc .gitignore\n",
       "dvc push                                # copy bytes to the remote\n",
       "```\n",
       "\n",
       "The `features.parquet.dvc` file that git then tracks looks like this, and its `md5`\n",
       "matches the digest printed above:\n",
       "\n",
       "```yaml\n",
       "outs:\n",
       "  - md5: <the digest above>\n",
       "    path: features.parquet\n",
       "```\n",
       "\n",
       "A `dvc.yaml` records the pipeline that produced the file, so `dvc repro` rebuilds it from\n",
       "raw data and reruns only the stages whose inputs changed:\n",
       "\n",
       "```yaml\n",
       "stages:\n",
       "  featurize:\n",
       "    cmd: python featurize.py\n",
       "    deps: [data/CMAPSS/train_FD001.txt, featurize.py]\n",
       "    outs: [artifacts/features.parquet]\n",
       "```"),

    md("## 6. Track the runs, tagged with the data version\n",
       "\n",
       "Now the honest and leaky scores become reproducible facts. Each MLflow run records the\n",
       "split, the score, and the **data hash**, so a run can be tied back to the exact bytes it\n",
       "used. MLflow stores this in a local SQLite file, with no server to start."),

    code("import mlflow\n",
         "\n",
         "mlflow.set_tracking_uri('sqlite:///mlflow.db')\n",
         "mlflow.set_experiment('l08-rul-splits')\n",
         "\n",
         "for split_name, score in [('random_row', random_rmse), ('per_unit_group', group_rmse)]:\n",
         "    with mlflow.start_run(run_name=split_name):\n",
         "        mlflow.log_param('split', split_name)\n",
         "        mlflow.log_param('data_md5', digest)\n",
         "        mlflow.log_param('model', 'RandomForest(100)')\n",
         "        mlflow.log_metric('rmse_cycles', score)\n",
         "\n",
         "runs = mlflow.search_runs(experiment_names=['l08-rul-splits'])\n",
         "print(runs[['params.split', 'metrics.rmse_cycles', 'params.data_md5']].to_string(index=False))"),

    md("## 7. Data-centric iteration\n",
       "\n",
       "Improve the model by improving the data, with the model and the honest split held fixed,\n",
       "so any change in the score is attributable to the data. The change here is a **label**\n",
       "decision. C-MAPSS RUL is conventionally clipped at 125 cycles, which encodes that an\n",
       "engine's health is roughly flat until late in life. We train on the raw remaining-cycle\n",
       "count and on the clipped version, score both on the same clipped target (the quantity we\n",
       "actually care about) under the same `GroupKFold`, and log each as a run."),

    code("from sklearn.model_selection import cross_val_predict\n",
         "\n",
         "def rmse(a, b):\n",
         "    return float(np.sqrt(((a - b) ** 2).mean()))\n",
         "\n",
         "d = train.sort_values(['unit', 'cycle']).reset_index(drop=True)\n",
         "rul_raw = (d.groupby('unit')['cycle'].transform('max') - d['cycle']).to_numpy()\n",
         "y_true = np.clip(rul_raw, 0, RUL_CAP)          # scored on this, both ways\n",
         "gkf = GroupKFold(5)\n",
         "\n",
         "scores = {}\n",
         "for name, y_train in [('unclipped_rul', rul_raw), ('clipped_rul_125', y_true)]:\n",
         "    path = Path(f'artifacts/features_{name}.parquet')\n",
         "    X.assign(rul=y_train, unit=groups).to_parquet(path)\n",
         "    d_md5 = hashlib.md5(path.read_bytes()).hexdigest()\n",
         "    pred = np.clip(cross_val_predict(model, X, y_train, cv=gkf, groups=groups), 0, RUL_CAP)\n",
         "    scores[name] = rmse(y_true, pred)\n",
         "    with mlflow.start_run(run_name=name):\n",
         "        mlflow.log_param('label_scheme', name)\n",
         "        mlflow.log_param('data_md5', d_md5)\n",
         "        mlflow.log_metric('rmse_cycles', scores[name])\n",
         "\n",
         "gain = scores['unclipped_rul'] - scores['clipped_rul_125']\n",
         "print(f\"train on unclipped RUL : {scores['unclipped_rul']:5.2f} cycles (honest split, scored on clipped)\")\n",
         "print(f\"train on clipped RUL   : {scores['clipped_rul_125']:5.2f} cycles\")\n",
         "print(f'clipping the label improved the honest RMSE by {gain:.2f} cycles, same model and split')"),

    md("---\n",
       "\n",
       "## Takeaway\n",
       "\n",
       "The split decides whether your score means anything. A random split of grouped, ordered\n",
       "data leaks, and it flatters the model by about 37% here; a per-unit split reports what the\n",
       "model earns on a new engine. Version the data by content so a run pins its exact inputs,\n",
       "log the data hash beside the score, and then improve the data against a fixed model so the\n",
       "gain is attributable and reproducible. Assignment **A4** has you put the C-MAPSS features\n",
       "under DVC, implement a correct split, and quantify the leak, so its second half starts here."),
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
