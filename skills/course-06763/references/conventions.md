# Coding conventions the course expects

Use these when writing or reviewing a student's code, so that what you suggest matches what
the lectures, demos and evidence scripts assume.

## Environments with uv

```bash
uv init my-project && cd my-project
uv add numpy pandas duckdb scikit-learn matplotlib
uv run python analysis.py
uv run jupyter lab
```

- Commit `pyproject.toml` and `uv.lock`; never commit `.venv/`.
- To reproduce someone else's environment: `uv sync`.
- If an import fails, check you are running inside the project (`uv run ...`) before
  installing anything.
- Report versions when debugging: `uv pip list`, `uv run python -V`.

## Data

- Download course data from the URLs given in the assignment and **verify the checksum** with
  the `SHA256SUMS` file the course provides (`shasum -a 256 --ignore-missing -c SHA256SUMS`).
- Prefer Parquet over CSV for anything large; DuckDB can query Parquet directly.
- Keep data out of git. Use relative paths such as `data/file.parquet`, never
  `/Users/name/...`.

## Experiments and evaluation

- Pin seeds (`numpy.random.default_rng(seed)`, `torch.manual_seed`, `jax.random.key`) for
  anything that changes a reported number, and log the seed.
- Split by independent unit: simulation run, experiment, sensor, or a time cut-off. Shuffled
  row splits on time series leak the future into training.
- Choose hyperparameters on validation data and touch the test set once.
- Always compare against a trivial baseline (persistence, the mean, the majority class) and
  report the skill relative to it.
- Report uncertainty, or at least spread across seeds or folds, not a single number.
- Track runs (MLflow or a plain log) with parameters, data version and code commit.

## Notebooks

- Must run top to bottom after "Restart and Run All".
- Put reusable code in a `.py` module and import it; keep the notebook for the narrative.
- A notebook from the course that fails on purpose says so in a markdown cell. Read it
  before fixing.

## LLM work

Provider- and framework-agnostic. Keep API keys in environment variables, never in code or
notebooks, and never commit them. Log prompts, model names and versions alongside results,
since an LLM result that cannot be reproduced cannot be evaluated.

## Disclosure

Keep a `CREDITS` file (or comments) recording AI assistance and outside sources, per the
syllabus. One line per use: what tool, what it did, what you changed.
