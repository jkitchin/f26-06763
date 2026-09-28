#!/usr/bin/env python3
"""Generate lectures/l10/l10-tracking-search.ipynb.

The L10 demo takes Lecture 9's decision tree on the concrete strength dataset from an ad-hoc
search (a few depths, tried by eye) to a tracked, reproducible, registered artifact:

  1. Load the concrete strength dataset and lock the same grouped test split Lecture 9 used.
  2. Define one Optuna trial: a configuration, a GroupKFold CV score, and a nested MLflow
     run that records both.
  3. Run the study. The parent run stays open for all twenty trials, then receives the
     best parameters and best score directly.
  4. Refit the winner on every training row, register it, and close the parent run.
  5. Load the registered model back by its models:/ URI, and score the held-out test mixes
     exactly once.

Design notes:
  - Tracking backend is sqlite:///mlflow.db, the same local store L1, L2 and A1 already use.
  - Same model, split and search space as figures/make_figures.py: Lecture 9's
    DecisionTreeRegressor(random_state=0), GroupShuffleSplit(n_splits=1, test_size=0.2,
    random_state=42) on the mix groups, GroupKFold(5) inside the objective, max_depth (int)
    2 to 20, min_samples_leaf (int) 1 to 50.
  - Runs top to bottom on "Restart and Run All"; every seed is fixed; the concrete workbook is
    cached under data/, and mlflow.db/mlruns are gitignored.

Kept in a generator for deterministic cell ids and no hand-edited JSON. Unlike most of this
course's demo notebooks, the committed copy carries real output: a student reading the page
should see an actual search and a registered model, not blank cells. After regenerating,
execute it with nbclient and then run tools/colab_setup.py --write on it, which re-templates
only the Colab bootstrap pair back to its unexecuted form and leaves every other cell's
output alone:

    python3 lectures/l10/build_notebook.py
    rm -rf mlflow.db mlruns mlartifacts   # a stale local store, not the committed notebook
    MLFLOW_DISABLE_AGENT_HINT=1 uv run --no-project \
        --with numpy --with pandas --with xlrd --with pyarrow \
        --with scikit-learn --with matplotlib --with scipy --with optuna --with mlflow \
        --with nbclient --with nbformat --with ipykernel --with ipywidgets \
        python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l10-tracking-search.ipynb', as_version=4)
NotebookClient(nb, timeout=300, resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l10-tracking-search.ipynb')
"
    python3 tools/colab_setup.py --write lectures/l10/l10-tracking-search.ipynb
"""
import json
import sys
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
       "**Optuna** is a Python library that runs a hyperparameter search for you:\n",
       "https://optuna.org. You give it a range for each hyperparameter and a way to score one\n",
       "choice, and it tries a sequence of configurations and keeps the best one.\n",
       "\n",
       "**MLflow** records every trial Optuna tries as its own run, so the settings and their\n",
       "scores survive after the search ends.\n",
       "\n",
       "Lecture 9 fit its decision tree to the concrete strength dataset by trying a few depths by\n",
       "eye. This notebook lets Optuna search over the tree's depth and leaf size instead. We then\n",
       "register the best tree, load it back by name, and touch the held-out test mixes exactly\n",
       "once.\n",
       "\n",
       "> Companion notes: [`notes.md`](notes.md)."),

    md("## 1. Load the concrete strength dataset, and lock the split\n",
       "\n",
       "One row per specimen, 20% of the *mixes* held out exactly as in Lecture 9:\n",
       "`GroupShuffleSplit` keeps every row of a mix on the same side, so the model is never\n",
       "tested on a recipe it trained on."),

    code("import io\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "import mlflow\n",
         "import optuna\n",
         "import pandas as pd\n",
         "from sklearn.tree import DecisionTreeRegressor\n",
         "from sklearn.metrics import root_mean_squared_error\n",
         "from sklearn.model_selection import GroupKFold, GroupShuffleSplit, cross_val_score\n",
         "\n",
         "DATA = Path('data')\n",
         "DATA.mkdir(exist_ok=True)\n",
         "XLS = DATA / 'Concrete_Data.xls'\n",
         "if not XLS.exists():\n",
         "    url = 'https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip'\n",
         "    XLS.write_bytes(\n",
         "        zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read())).read('Concrete_Data.xls')\n",
         "    )\n",
         "\n",
         "COLUMNS = ['cement', 'slag', 'fly_ash', 'water', 'superplasticizer',\n",
         "           'coarse_agg', 'fine_agg', 'age_days', 'strength_mpa']\n",
         "FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]\n",
         "\n",
         "concrete = pd.read_excel(XLS)\n",
         "concrete.columns = COLUMNS\n",
         "X = concrete[FEATURES].to_numpy()\n",
         "y = concrete['strength_mpa'].to_numpy()\n",
         "groups = concrete.groupby(MIX).ngroup().to_numpy()\n",
         "\n",
         "splitter = GroupShuffleSplit(\n",
         "    n_splits=1,\n",
         "    test_size=0.2,\n",
         "    random_state=42,\n",
         ")\n",
         "train, test = next(splitter.split(X, y, groups))\n",
         "X_tr, y_tr, groups_tr = X[train], y[train], groups[train]\n",
         "X_te, y_te = X[test], y[test]\n",
         "print(f'{len(X_tr)} training rows ({len(set(groups_tr))} mixes), {len(X_te)} held-out test rows')"),

    md("## 2. Point MLflow at a local store\n",
       "\n",
       "The same pattern as Lecture 1 and Lecture 2: a local SQLite file, no server to run. Every\n",
       "trial the search tries becomes one MLflow run, and Optuna's study becomes the parent run\n",
       "those trials nest under."),

    code("SEED = 0\n",
         "mlflow.set_tracking_uri('sqlite:///mlflow.db')\n",
         "mlflow.set_experiment('concrete-search')\n",
         "optuna.logging.set_verbosity(optuna.logging.WARNING)"),

    md("## 3. One trial, one nested run\n",
       "\n",
       "`objective` is what Optuna calls once per trial. It draws a tree depth and a leaf size\n",
       "from a range, scores that one tree by five-fold `GroupKFold` on the training mixes, and\n",
       "logs the trial as a run nested under whichever run is currently open.\n",
       "\n",
       "`max_depth` caps how many splits deep the tree can go. `min_samples_leaf` sets the\n",
       "fewest training rows a leaf is allowed to end with, so the tree cannot keep splitting\n",
       "down to one row."),

    code("def objective(trial):\n",
         "    params = dict(\n",
         "        max_depth=trial.suggest_int('max_depth', 2, 20),\n",
         "        min_samples_leaf=trial.suggest_int('min_samples_leaf', 1, 50),\n",
         "    )\n",
         "    model = DecisionTreeRegressor(\n",
         "        random_state=SEED,\n",
         "        **params,\n",
         "    )\n",
         "    rmse = -cross_val_score(\n",
         "        model,\n",
         "        X_tr,\n",
         "        y_tr,\n",
         "        groups=groups_tr,\n",
         "        cv=GroupKFold(5),\n",
         "        scoring='neg_root_mean_squared_error',\n",
         "    ).mean()\n",
         "    with mlflow.start_run(nested=True):\n",
         "        mlflow.log_params(params)\n",
         "        mlflow.log_metric('val_rmse', rmse)\n",
         "    return rmse"),

    md("## 4. Run the study\n",
       "\n",
       "`mlflow.start_run` opens the parent and leaves it open, so every nested run that\n",
       "`objective` starts over the next twenty trials lands underneath it.\n",
       "\n",
       "The sampler is TPE, the Tree-structured Parzen Estimator: Optuna's default way to choose\n",
       "the next trial. It looks at the trials so far and tries next where the good ones cluster.\n",
       "`seed=SEED` fixes its random draws, so the search gives the same trials every run.\n",
       "\n",
       "Once the study is done, its best parameters and best score are logged straight to that\n",
       "same parent run."),

    code("parent = mlflow.start_run(run_name='concrete-tree-search')\n",
         "study = optuna.create_study(\n",
         "    direction='minimize',\n",
         "    sampler=optuna.samplers.TPESampler(seed=SEED),\n",
         ")\n",
         "study.optimize(\n",
         "    objective,\n",
         "    n_trials=20,\n",
         ")\n",
         "mlflow.log_params(study.best_params)\n",
         "mlflow.log_metric('best_val_rmse', study.best_value)\n",
         "print(f'best validation RMSE {study.best_value:.2f} MPa after {len(study.trials)} trials')\n",
         "print('best params:', study.best_params)"),

    md("## 5. Register the winner\n",
       "\n",
       "Refit the best settings on all 835 training rows and register the tree under a name,\n",
       "`concrete-tree`. MLflow needs one extra argument to save a decision tree, explained in the\n",
       "code comment. The parent run then closes, holding twenty child runs, the best settings\n",
       "and the registered model."),

    code("winner = DecisionTreeRegressor(\n",
         "    random_state=SEED,\n",
         "    **study.best_params,\n",
         ").fit(X_tr, y_tr)\n",
         "\n",
         "mlflow.sklearn.log_model(\n",
         "    winner,\n",
         "    name='model',\n",
         "    registered_model_name='concrete-tree',\n",
         "    # A DecisionTreeRegressor stores its splits in a type MLflow's default\n",
         "    # serializer does not trust automatically. We just trained this model\n",
         "    # ourselves, so trusting it back is safe.\n",
         "    skops_trusted_types=['sklearn.tree._tree.Tree'],\n",
         ")\n",
         "mlflow.end_run()\n",
         "print('registered concrete-tree; parent run closed')"),

    md("## 6. Load it back, and test once\n",
       "\n",
       "A registered model is loaded fresh by its `models:/` URI, the way a teammate on a\n",
       "different machine would load it. This cell is the only one that touches the held-out\n",
       "test mixes, and it touches them once."),

    code("from mlflow import MlflowClient\n",
         "\n",
         "client = MlflowClient()\n",
         "latest = max(int(v.version) for v in client.search_model_versions(\"name='concrete-tree'\"))\n",
         "loaded = mlflow.sklearn.load_model(f'models:/concrete-tree/{latest}')\n",
         "\n",
         "test_rmse = root_mean_squared_error(y_te, loaded.predict(X_te))\n",
         "print(f'loaded models:/concrete-tree/{latest}')\n",
         "print(f'best VALIDATION RMSE (search optimized) : {study.best_value:.2f} MPa')\n",
         "print(f'held-out TEST RMSE (reported once)      : {test_rmse:.2f} MPa')"),

    md("## Try it\n",
       "\n",
       "Open the tracking UI from this folder and look for the `concrete-search` experiment:\n",
       "\n",
       "```\n",
       "mlflow ui --backend-store-uri sqlite:///mlflow.db\n",
       "```\n",
       "\n",
       "Sort its child runs by `val_rmse` and see which of the two hyperparameters moves the\n",
       "score. Then raise `n_trials` in section 4 from 20 to 50, Restart and Run All, and see the\n",
       "parent run gain more child runs."),
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

OUT.parent.mkdir(
    parents=True,
    exist_ok=True,
)
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT} ({len(cells)} cells)")
