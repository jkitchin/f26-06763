#!/usr/bin/env python3
"""Generate lectures/l10/l10-tracking-search.ipynb.

The L10 demo takes the Week-5 power-plant model from an ad-hoc search to a
tracked, reproducible, registered artifact:

  1. Load CCPP and lock a test split (touched once, at the very end).
  2. Run an Optuna study over gradient-boosting hyperparameters, logging every
     trial to MLflow as a nested run under one parent study run.
  3. Read the runs back, sorted by validation RMSE, and see which
     hyperparameters mattered (Optuna importances).
  4. Refit the winner, register it, and load it back by its models:/ URI.
  5. Compute the single held-out test RMSE, and see the gap between it and the
     best validation score the search optimized.

Design notes:
  - Tracking backend is sqlite:///mlflow.db, the local default now that the bare
    file store is deprecated.
  - Same model family and search space as figures/make_figures.py.
  - Runs top to bottom on "Restart and Run All"; the seed is fixed; CCPP is
    cached under data/ and mlflow.db/mlruns are gitignored.

Kept in a generator for deterministic cell ids and no hand-edited JSON.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "l10-tracking-search.ipynb"

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
    md("# L10 demo: a hyperparameter search, tracked and registered\n",
       "\n",
       "We predict the Combined Cycle Power Plant's net output (MW) from four ambient\n",
       "measurements, the same set as L9. The model is not the point. The point is that the\n",
       "search that finds a good model is a machine for generating hundreds of runs, and\n",
       "without a record of them you cannot say which run produced your number or reproduce it.\n",
       "\n",
       "So we log every trial to **MLflow**, search with **Optuna**, register the winner, and\n",
       "report a single honest test score at the end.\n",
       "\n",
       "> Data: [UCI Combined Cycle Power Plant](https://archive.ics.uci.edu/dataset/294/combined+cycle+power+plant),\n",
       "> 9,568 hourly records, carried over from L9."),

    md("## 1. Load CCPP and lock a test split\n",
       "\n",
       "The test split is set aside now and scored exactly once, at the very end, on the single\n",
       "model we select. Everything in between uses only the training portion."),

    code("import io\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "import numpy as np\n",
         "import pandas as pd\n",
         "from sklearn.model_selection import train_test_split\n",
         "\n",
         "CACHE = Path('data')\n",
         "CACHE.mkdir(exist_ok=True)\n",
         "URL = 'https://archive.ics.uci.edu/static/public/294/combined+cycle+power+plant.zip'\n",
         "xlsx = CACHE / 'Folds5x2_pp.xlsx'\n",
         "if not xlsx.exists():\n",
         "    print('downloading', URL)\n",
         "    with urllib.request.urlopen(URL) as r:\n",
         "        archive = zipfile.ZipFile(io.BytesIO(r.read()))\n",
         "    xlsx.write_bytes(archive.read('CCPP/Folds5x2_pp.xlsx'))\n",
         "\n",
         "FEATURES, TARGET, SEED = ['AT', 'V', 'AP', 'RH'], 'PE', 0\n",
         "df = pd.read_excel(xlsx, 'Sheet1')\n",
         "X, y = df[FEATURES].to_numpy(), df[TARGET].to_numpy()\n",
         "X_tr, X_test, y_tr, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED)\n",
         "print(f'{len(X):,} rows; train {len(X_tr):,}, locked test {len(X_test):,}')"),

    md("## 2. Search, with every trial tracked\n",
       "\n",
       "The Optuna **study** proposes a configuration, we score it by 3-fold cross-validation on\n",
       "the training data, and we log that trial to MLflow as a **nested run** under one parent\n",
       "run for the whole study. Optuna's default sampler is TPE, which models the good regions\n",
       "of the space and samples toward them.\n",
       "\n",
       "The tracking backend is a local SQLite file, the default now that MLflow's bare file\n",
       "store is deprecated."),

    code("import mlflow\n",
         "import optuna\n",
         "from sklearn.ensemble import HistGradientBoostingRegressor\n",
         "from sklearn.model_selection import KFold, cross_val_score\n",
         "\n",
         "optuna.logging.set_verbosity(optuna.logging.WARNING)\n",
         "mlflow.set_tracking_uri('sqlite:///mlflow.db')\n",
         "mlflow.set_experiment('ccpp-search')\n",
         "cv = KFold(n_splits=3, shuffle=True, random_state=SEED)\n",
         "\n",
         "\n",
         "def objective(trial):\n",
         "    params = dict(\n",
         "        learning_rate=trial.suggest_float('learning_rate', 0.01, 0.5, log=True),\n",
         "        max_leaf_nodes=trial.suggest_int('max_leaf_nodes', 8, 128, log=True),\n",
         "        max_iter=trial.suggest_int('max_iter', 50, 250),\n",
         "        l2_regularization=trial.suggest_float('l2_regularization', 1e-6, 10.0, log=True),\n",
         "        min_samples_leaf=trial.suggest_int('min_samples_leaf', 5, 60),\n",
         "    )\n",
         "    model = HistGradientBoostingRegressor(random_state=SEED, **params)\n",
         "    rmse = -cross_val_score(model, X_tr, y_tr, cv=cv, n_jobs=-1,\n",
         "                            scoring='neg_root_mean_squared_error').mean()\n",
         "    with mlflow.start_run(nested=True):\n",
         "        mlflow.log_params(params)\n",
         "        mlflow.log_metric('val_rmse', rmse)\n",
         "    return rmse\n",
         "\n",
         "\n",
         "with mlflow.start_run(run_name='optuna-study') as parent:\n",
         "    study = optuna.create_study(direction='minimize',\n",
         "                                sampler=optuna.samplers.TPESampler(seed=SEED))\n",
         "    study.optimize(objective, n_trials=25)\n",
         "    mlflow.log_metric('best_val_rmse', study.best_value)\n",
         "print(f'best validation RMSE {study.best_value:.3f} MW after {len(study.trials)} trials')"),

    md("## 3. Read the runs back\n",
       "\n",
       "Every trial is now a row in the tracking store. In practice you open the UI with\n",
       "`mlflow ui` (or `mlflow server`) and sort; here we pull the same table with\n",
       "`search_runs` and show the best few. Nothing about the search is hidden."),

    code("runs = mlflow.search_runs(experiment_names=['ccpp-search'],\n",
         "                          order_by=['metrics.val_rmse ASC'])\n",
         "cols = ['metrics.val_rmse', 'params.learning_rate', 'params.max_leaf_nodes',\n",
         "        'params.max_iter']\n",
         "print(runs[runs['metrics.val_rmse'].notna()][cols].head(5).to_string(index=False))"),

    md("Optuna can also say which hyperparameters actually moved the score. On this easy,\n",
       "low-dimensional problem the answer is usually a single dominant knob, which is exactly\n",
       "the Bergstra and Bengio point: most hyperparameters do not matter, and which one does\n",
       "depends on the dataset."),

    code("from optuna.importance import get_param_importances\n",
         "\n",
         "importances = get_param_importances(study)\n",
         "for name, imp in importances.items():\n",
         "    print(f'{name:20s} {imp:.3f}')"),

    md("## 4. Register the winner, with its lineage\n",
       "\n",
       "Refit the best configuration on the full training set and register it under a name, so\n",
       "it can be found again by URI rather than by remembering a run id. We log its data hash\n",
       "and seed alongside, so the registered model carries its lineage."),

    code("import hashlib\n",
         "\n",
         "data_md5 = hashlib.md5(xlsx.read_bytes()).hexdigest()\n",
         "winner = HistGradientBoostingRegressor(random_state=SEED, **study.best_params).fit(X_tr, y_tr)\n",
         "\n",
         "with mlflow.start_run(run_name='winner'):\n",
         "    mlflow.log_params(study.best_params)\n",
         "    mlflow.log_param('data_md5', data_md5)\n",
         "    mlflow.log_param('seed', SEED)\n",
         "    mlflow.log_metric('val_rmse', study.best_value)\n",
         "    mlflow.sklearn.log_model(winner, name='model', registered_model_name='ccpp-hgb')\n",
         "print('registered ccpp-hgb with data_md5', data_md5[:12], '...')"),

    md("## 5. Load it back by URI, and score the test set once\n",
       "\n",
       "A registered model is loaded by a `models:/` URI, not by a file path. We fetch the\n",
       "latest version, load it on a clean handle, and only now touch the locked test set. You\n",
       "report this test number, not the best validation score, because the search optimized the\n",
       "validation score. On this large, easy dataset the two land close together, and any small\n",
       "difference here is mostly the winner training on more data than the cross-validation\n",
       "folds rather than selection bias, which the module measured as negligible at full size.\n",
       "On small data the validation score would instead be optimistically low, which is the\n",
       "reason to report the test at all."),

    code("from mlflow import MlflowClient\n",
         "from sklearn.metrics import root_mean_squared_error\n",
         "\n",
         "client = MlflowClient()\n",
         "latest = max(int(v.version) for v in client.search_model_versions(\"name='ccpp-hgb'\"))\n",
         "uri = f'models:/ccpp-hgb/{latest}'\n",
         "loaded = mlflow.sklearn.load_model(uri)\n",
         "\n",
         "test_rmse = root_mean_squared_error(y_test, loaded.predict(X_test))\n",
         "print(f'loaded {uri}')\n",
         "print(f'best VALIDATION RMSE (search optimized) : {study.best_value:.3f} MW')\n",
         "print(f'held-out TEST RMSE (reported once)      : {test_rmse:.3f} MW')"),

    md("---\n",
       "\n",
       "## Takeaway\n",
       "\n",
       "The search optimized the validation score; the number you report is the test score,\n",
       "computed once on the model you selected. Every trial is in the tracking store with its\n",
       "parameters and metric, the winner is registered with its data hash and seed, and it\n",
       "loads back by a `models:/` URI on any machine. That record of what you tried and why is\n",
       "the deliverable. Assignment **A5** has you take one dataset from data to a defended model\n",
       "choice with every run tracked, so it starts here."),
]

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
