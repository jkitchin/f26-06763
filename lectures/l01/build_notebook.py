#!/usr/bin/env python3
"""Generate lectures/l01/l01-reproducibility.ipynb.

The notebook is deliberately defective in three ways. Keeping it in a generator
means the defects are documented here, in one place, rather than being mistaken
for bugs by a future reader of the .ipynb JSON.

The three, in the order a student meets them:

1. Absolute path. The fetch cell writes to it and deliberately does NOT mkdir
   parents, so on any machine that is not the author's it raises FileNotFoundError
   rather than silently creating a directory tree. Fixing the path to a relative
   one also makes the download work, so the student is genuinely unblocked.
2. Unpinned split. Runs fine, different answer every time.
3. NumPy version. Two integration cells, one calling np.trapz (present in 1.x,
   removed in 2.0) and one calling np.trapezoid (added in 2.0, absent from 1.x).
   Exactly one of them fails for every student, whichever version they installed,
   so nobody sails through this section. Which cell fails identifies their
   version, which is the discussion.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "l01-reproducibility.ipynb"


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
    md("# L1 demo: an analysis that does not reproduce\n",
       "\n",
       "This notebook loads a year of roadside air-quality sensor data, plots a reference\n",
       "measurement against the corresponding sensor channel, fits a naive calibration, and\n",
       "integrates the concentration curve to get a cumulative exposure.\n",
       "\n",
       "All of that is ordinary work. The notebook is nonetheless broken in **three**\n",
       "independent ways, and you will meet them in order as you run it from the top.\n",
       "\n",
       "Your job is to name each one before I do, and to say not just what the fix is but\n",
       "what practice would have stopped it reaching a colleague. None of the three are\n",
       "exotic. That is the point: reproducibility fails for boring reasons, and boring\n",
       "reasons are the ones that survive review.\n",
       "\n",
       "> Data: [UCI Air Quality Data Set](https://archive.ics.uci.edu/dataset/360/air+quality),\n",
       "> De Vito et al. Hourly readings from a multisensor device deployed on an Italian\n",
       "> roadside, March 2004 onward."),

    md("## 1. Environment\n",
       "\n",
       "We import what we need. Nothing here records *which version* of anything this\n",
       "analysis was written against, and there is no lockfile beside the notebook.\n",
       "\n",
       "Print the versions and hold onto them. They matter in section 5."),

    code("import numpy as np\n",
         "import pandas as pd\n",
         "import matplotlib.pyplot as plt\n",
         "from sklearn.linear_model import LinearRegression\n",
         "from sklearn.model_selection import train_test_split\n",
         "from sklearn.metrics import r2_score\n",
         "\n",
         "print('numpy ', np.__version__)\n",
         "print('pandas', pd.__version__)"),

    md("## 2. Load the data\n",
       "\n",
       "The raw CSV is **not in this repository**. Datasets do not belong in git: they bloat\n",
       "the history, they are usually someone else's to license, and a repository is not a\n",
       "distribution channel. So the next cell fetches it from UCI on first run and reuses the\n",
       "local copy afterwards, which is what you should do in your own projects too.\n",
       "\n",
       "The export has the usual instrument-file quirks, none of them announced: semicolon\n",
       "separated, comma as the decimal mark, two trailing empty columns, and missing values\n",
       "coded as `-200` rather than left blank."),

    code("import io\n",
         "import urllib.request\n",
         "import zipfile\n",
         "from pathlib import Path\n",
         "\n",
         "DATA_PATH = Path('/Users/jkitchin/Dropbox/classes/f26-systems-toolchains/data/AirQualityUCI.csv')\n",
         "URL = 'https://archive.ics.uci.edu/static/public/360/air+quality.zip'\n",
         "\n",
         "if not DATA_PATH.exists():\n",
         "    print(f'fetching {URL}')\n",
         "    with urllib.request.urlopen(URL) as response:\n",
         "        payload = response.read()\n",
         "    with zipfile.ZipFile(io.BytesIO(payload)) as archive:\n",
         "        DATA_PATH.write_bytes(archive.read('AirQualityUCI.csv'))\n",
         "\n",
         "print(f'using {DATA_PATH}')"),

    md("### If that cell just failed\n",
       "\n",
       "Read the error. It has nothing to do with statistics, sensors, or modelling. It is a\n",
       "`FileNotFoundError`, and it happened while trying to *write* the downloaded file.\n",
       "\n",
       "The download worked. The place it was told to put the file does not exist on your\n",
       "machine, and never will.\n",
       "\n",
       "**Problem one.** Fix it, rerun, and the fetch will succeed. Then keep going."),

    code("df = (\n",
         "    pd.read_csv(DATA_PATH, sep=';', decimal=',')\n",
         "    .dropna(axis=1, how='all')\n",
         "    .dropna(how='all')\n",
         ")\n",
         "\n",
         "df['ts'] = pd.to_datetime(\n",
         "    df['Date'] + ' ' + df['Time'].str.replace('.', ':', regex=False),\n",
         "    format='%d/%m/%Y %H:%M:%S',\n",
         ")\n",
         "df = df.replace(-200, np.nan)\n",
         "\n",
         "print(f'{len(df)} rows, {df.ts.min().date()} to {df.ts.max().date()}')\n",
         "df.head(3)"),

    md("## 3. A first look\n",
       "\n",
       "`CO(GT)` is a reference-grade carbon monoxide measurement. `PT08.S1(CO)` is the cheap\n",
       "metal-oxide sensor that is supposed to track it. If the sensor is any good, these\n",
       "should be related."),

    code("d = df.dropna(subset=['CO(GT)', 'PT08.S1(CO)'])\n",
         "\n",
         "fig, ax = plt.subplots(figsize=(6, 4.2))\n",
         "ax.scatter(d['PT08.S1(CO)'], d['CO(GT)'], s=4, alpha=0.25)\n",
         "ax.set_xlabel('PT08.S1(CO) sensor response')\n",
         "ax.set_ylabel('CO(GT) reference, mg/m$^3$')\n",
         "ax.set_title('Sensor response vs reference measurement')\n",
         "plt.show()"),

    md("## 4. A naive calibration\n",
       "\n",
       "Fit a linear model from the sensor channel to the reference, hold out a quarter of\n",
       "the data, and score it."),

    code("X = d[['PT08.S1(CO)']]\n",
         "y = d['CO(GT)']\n",
         "\n",
         "X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25)\n",
         "\n",
         "model = LinearRegression().fit(X_train, y_train)\n",
         "score = r2_score(y_test, model.predict(X_test))\n",
         "\n",
         "print(f'R2 on held-out data: {score:.4f}')\n",
         "print(f'slope {model.coef_[0]:.5f}, intercept {model.intercept_:.5f}')"),

    md("### Run that cell again\n",
       "\n",
       "Do not change anything. Run it a second time, and a third. Write the numbers down.\n",
       "\n",
       "Then decide which of them you would be willing to put in a report, and how you would\n",
       "answer a reviewer who asked you to reproduce it six months from now.\n",
       "\n",
       "**Problem two.**"),

    md("## 5. Cumulative exposure\n",
       "\n",
       "A calibration is not the quantity a health question actually needs. What matters is\n",
       "cumulative dose: the area under the concentration curve over the deployment. That is\n",
       "a numerical integration over the hourly series.\n",
       "\n",
       "We do it for two pollutants. **Run both cells.**"),

    code("hourly_co = d.set_index('ts')['CO(GT)'].resample('h').mean().dropna()\n",
         "hours_co = (hourly_co.index - hourly_co.index[0]).total_seconds() / 3600.0\n",
         "\n",
         "exposure_co = np.trapz(hourly_co.values, hours_co)\n",
         "print(f'Integrated CO exposure:  {exposure_co:,.0f} mg-h/m3')"),

    code("nox = df.dropna(subset=['NOx(GT)'])\n",
         "hourly_nox = nox.set_index('ts')['NOx(GT)'].resample('h').mean().dropna()\n",
         "hours_nox = (hourly_nox.index - hourly_nox.index[0]).total_seconds() / 3600.0\n",
         "\n",
         "exposure_nox = np.trapezoid(hourly_nox.values, hours_nox)\n",
         "print(f'Integrated NOx exposure: {exposure_nox:,.0f} ppb-h')"),

    md("### Exactly one of those two cells failed\n",
       "\n",
       "Not both, and not neither. Which one depends on the NumPy version you printed in\n",
       "section 1.\n",
       "\n",
       "**Compare with the person next to you.** If you got different failures, neither of\n",
       "you did anything wrong, and that is the entire lesson. Both cells are ordinary\n",
       "numerical integration. Both were correct when someone wrote them.\n",
       "\n",
       "**Problem three.** Note that nothing in this repository told you which version this\n",
       "analysis expected, so nothing told you which cell was the broken one."),

    md("---\n",
       "\n",
       "## Your turn\n",
       "\n",
       "Fill this in. The last column is the one that matters.\n",
       "\n",
       "| # | Symptom | Root cause | Fix | Practice that prevents it |\n",
       "|---|---|---|---|---|\n",
       "| 1 | | | | |\n",
       "| 2 | | | | |\n",
       "| 3 | | | | |\n",
       "\n",
       "Two questions to take away:\n",
       "\n",
       "- Problem two does not raise an error. Nothing in the output marks it as wrong. How\n",
       "  many analyses have you run that had this property?\n",
       "- Problem three was introduced by a library doing something entirely reasonable, a\n",
       "  deprecated name being removed in a major release. Whose responsibility was it to\n",
       "  notice?\n",
       "\n",
       "We rebuild this properly in **L2**: a `uv`-managed project with a locked environment,\n",
       "a pinned interpreter, relative paths, seeded splits, and the analysis moved out of the\n",
       "notebook into a module you can test and rerun. That is also assignment **A1**."),
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
