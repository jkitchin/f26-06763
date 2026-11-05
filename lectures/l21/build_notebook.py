#!/usr/bin/env python3
"""Generate lectures/l21/l21-deployment.ipynb, the L21 worked example.

Serves Lecture 14's concrete strength ensemble with FastAPI on the machine running the notebook,
in Colab or locally, with no cloud account and no Docker: fit and save the model with a manifest;
exercise the service in process; start uvicorn in the background; load it at several
concurrencies and check Little's law; one request against a batch; the async-def stall, on
purpose; an optimizer as the client; cost per request. The Docker cells run only where Docker is
installed and the repository's service/ directory is beside the notebook.

The service code is not copied by hand: the %%writefile cell is generated from service/app.py,
so the notebook and the committed service cannot drift. The splits and seeds follow
figures/make_figures.py, which produced the numbers in the notes.

Kept in a generator for deterministic cell ids and no hand-edited JSON. The committed copy
carries real output. After regenerating, execute it in the service's own environment:

    python3 lectures/l21/build_notebook.py
    export JUPYTER_DATA_DIR=$(mktemp -d)
    cd lectures/l21 && uv run --project service --group dev --with nbclient --with nbformat \
        --with ipykernel python -c "
import nbformat
from nbclient import NotebookClient
nb = nbformat.read('l21-deployment.ipynb', as_version=4)
NotebookClient(nb, timeout=900, kernel_name='python3', resources={'metadata': {'path': '.'}}).execute()
nbformat.write(nb, 'l21-deployment.ipynb')
"
    cd ../.. && python3 tools/colab_setup.py --write "$PWD/lectures/l21/l21-deployment.ipynb"

Run it on an idle machine: the latency cells measure this computer, and a busy one gives numbers
three or four times slower than the notes report.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "l21-deployment.ipynb"
APP = (HERE / "service" / "app.py").read_text()
sys.path.insert(0, str(HERE.parent.parent / "tools"))
from colab_setup import with_colab_cell  # noqa: E402

cells, n = [], 0


def md(text):
    global n
    n += 1
    cells.append({"cell_type": "markdown", "id": f"md-{n:02d}", "metadata": {},
                  "source": text.strip("\n").splitlines(keepends=True)})


def code(text):
    global n
    n += 1
    cells.append({"cell_type": "code", "id": f"code-{n:02d}", "execution_count": None,
                  "metadata": {}, "outputs": [], "source": text.strip("\n").splitlines(keepends=True)})


md(r"""
# L21 worked example: serving a model, and measuring what it costs

The model is Lecture 14's five-network ensemble for concrete compressive strength, with its
one-factor recalibration. This notebook turns it into an HTTP service and measures it:

1. **Fit and save** the ensemble, with a manifest recording versions, the data hash and the
   artifact's own hash.
2. **The service**, `app.py`: typed, range-checked requests; a response with an interval, an
   out-of-domain flag and the model version; the model loaded once; liveness and readiness.
3. **In process**, with FastAPI's test client: a good request, a 422, an out-of-domain mix.
4. **On a port**, with uvicorn in the background: latency and throughput against concurrency,
   checked with Little's law.
5. **Batching**: one mix per request against a thousand.
6. **A deliberate mistake**: the same prediction inside `async def`, and what it does to a health
   check.
7. **An optimizer as the client**, counting its calls.
8. **Cost** per prediction and per LLM answer.
9. **Docker**, only if it is installed: the image, its size, and a secret recovered from a layer.

Everything runs on this machine. The client and the server share it, so every latency here is a
floor: a real network adds to each one.
""")

code(r"""
import hashlib, io, json, os, platform, shutil, socket, subprocess, sys, tempfile, time
import urllib.request, warnings, zipfile
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
import sklearn
import fastapi
import uvicorn  # started below as a separate process; imported so the version is on record

WORK = Path("l21_work")
(WORK / "model").mkdir(parents=True, exist_ok=True)
print("python", platform.python_version(), "| scikit-learn", sklearn.__version__,
      "| fastapi", fastapi.__version__, "| uvicorn", uvicorn.__version__)
print("machine", platform.machine(), platform.system(), "| cores", os.cpu_count())
""")

md(r"""
## 1. Fit and save the model

Lecture 14's grouped split (mixes, not rows, are kept apart), its network (Lecture 9's one hidden
layer of 16 tanh units), seeds 0 to 4, and one scale factor fitted on calibration mixes. The
manifest is what lets the service prove that the file it loads is the file that was tested.

The networks stop at their 5,000-iteration cap without converging, and the warning is silenced
as in Lecture 14. That is why your scale factor may differ from the notes' 2.09 and from Lecture
14's 1.66: an unconverged fit depends on floating-point details that library builds change. The
saved artifact is the model; rerunning the recipe gives a slightly different one.
""")

code(r"""
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import GroupShuffleSplit
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings("ignore", category=ConvergenceWarning)

UCI = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]
xls = WORK / "Concrete_Data.xls"
if not xls.exists():
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI).read()))
    xls.write_bytes(z.read("Concrete_Data.xls"))
df = pd.read_excel(xls)
df.columns = COLUMNS
X, y = df[FEATURES].to_numpy(), df["strength_mpa"].to_numpy()
groups = df.groupby(MIX).ngroup().to_numpy()

tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0)
                    .split(X[tr], y[tr], groups[tr]))
fit_i, cal_i = tr[fit_i], tr[cal_i]
nets = [make_pipeline(StandardScaler(), MLPRegressor(hidden_layer_sizes=(16,), activation="tanh",
        solver="lbfgs", max_iter=5000, random_state=s)).fit(X[fit_i], y[fit_i]) for s in range(5)]

def ensemble(Xq):
    P = np.array([net.predict(Xq) for net in nets])
    return P.mean(0), P.std(0, ddof=1)

mc, sc = ensemble(X[cal_i])
scale = float(np.sqrt(np.mean(((y[cal_i] - mc) / sc) ** 2)))
mt, st = ensemble(X[te])
Z90 = 1.6448536269514722
print(f"fit {len(fit_i)}, calibration {len(cal_i)}, test {len(te)} rows")
print(f"iterations used: {[n[-1].n_iter_ for n in nets]} (cap 5000)")
print(f"scale factor s = {scale:.2f}; test RMSE {np.sqrt(np.mean((y[te] - mt) ** 2)):.2f} MPa; "
      f"90% interval coverage on test mixes {np.mean(np.abs(y[te] - mt) <= Z90 * scale * st):.1%}")

artifact = WORK / "model" / "ensemble.joblib"
joblib.dump(nets, artifact)
manifest = dict(model_version="concrete-ens5-v1", sklearn=sklearn.__version__, numpy=np.__version__,
                python=platform.python_version(),
                data_sha256=hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),
                split="Lecture 14 grouped split, seeds 42 and 0", scale=scale,
                ranges={f: [float(X[tr][:, i].min()), float(X[tr][:, i].max())]
                        for i, f in enumerate(FEATURES)},
                sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
(WORK / "model" / "manifest.json").write_text(json.dumps(manifest, indent=1))
print(f"wrote {artifact} ({artifact.stat().st_size:,} bytes) and manifest.json")
test_mixes = [dict(zip(FEATURES, map(float, row))) for row in X[te]]
""")

md(r"""
## 2. The service

This is `lectures/l21/service/app.py` from the course repository, written to disk unchanged. Read
the `lifespan` function (the model is loaded once, and refused if its hash or scikit-learn
version does not match the manifest), the `Mix` bounds (impossible inputs are rejected), and the
`Prediction` fields (the interval, the domain flag and the version travel with every answer).
""")

code("%%writefile l21_work/app.py\n" + APP)

md(r"""
## 3. In process, with the test client

`TestClient` runs the app inside this Python process, including its lifespan, with no server and
no port. It is how you test the contract before anything is deployed.
""")

code(r"""
from fastapi.testclient import TestClient

os.environ["MODEL_DIR"] = str(WORK / "model")
sys.path.insert(0, str(WORK))
import app as service

with TestClient(service.app) as c:
    print("readyz      ", c.get("/readyz").json())
    good = test_mixes[0]
    print("predict     ", c.post("/predict", json=good).json())
    r = c.post("/predict", json={**good, "cement": -50})
    print("cement = -50", r.status_code, r.json()["detail"][0]["msg"])
    odd = {**good, "slag": 400.0, "age_days": 730.0}
    print("outside     ", c.post("/predict", json=odd).json())
    print("paths in the OpenAPI schema:", sorted(c.get("/openapi.json").json()["paths"]))
""")

md(r"""
The impossible mix gets a 422 that names the field and the rule. The unusual one gets an answer,
flagged: look at its interval. It is no wider than the in-domain mix's, which is Lecture 14's point
about ensembles off their data, and the reason the flag exists.
""")

md(r"""
## 4. On a port, under load

Now the real thing: uvicorn in a separate process, listening on `127.0.0.1`. The notebook waits
for `/readyz`, which answers only once the model is loaded.
""")

code(r"""
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

def start_server(workers=1):
    port = free_port()
    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                             "--port", str(port), "--workers", str(workers), "--log-level", "warning"],
                            cwd=WORK, env={**os.environ, "MODEL_DIR": "model"})
    while True:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=1)
            if r.status_code == 200:
                return proc, port, time.perf_counter() - t0, r.json()
        except httpx.HTTPError:
            pass
        if proc.poll() is not None:
            raise RuntimeError("uvicorn exited before it was ready")
        time.sleep(0.02)

server, PORT, t_ready, ready = start_server()
BASE = f"http://127.0.0.1:{PORT}"
print(f"ready after {t_ready:.2f} s, of which loading the model took {ready['load_seconds']:.3f} s")
""")

md(r"""
The load test uses **closed-loop** clients: each sends a request, waits for the answer, and sends
the next. Each client is its own process. A first version that ran every client from one Python
process measured the client's limit rather than the server's, so the clients are a small script
started as separate processes.
""")

code(r"""
(WORK / "load_client.py").write_text('''
import json, sys, time, httpx
port, path, n, start_at, bodies = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), json.load(open(sys.argv[5]))
lat = []
with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as c:
    c.post(path, json=bodies[0])
    while time.time() < start_at:
        time.sleep(0.001)
    t0 = time.time()
    for i in range(n):
        t = time.perf_counter()
        c.post(path, json=bodies[i % len(bodies)]).raise_for_status()
        lat.append(time.perf_counter() - t)
print(json.dumps({"lat": lat, "t0": t0, "t1": time.time()}))
''')
(WORK / "mixes.json").write_text(json.dumps(test_mixes))

def load(port, concurrency, n_each, path="/predict"):
    start_at = time.time() + 1.0 + 0.05 * concurrency
    procs = [subprocess.Popen([sys.executable, str(WORK / "load_client.py"), str(port), path,
                               str(n_each), str(start_at), str(WORK / "mixes.json")],
                              stdout=subprocess.PIPE, text=True) for _ in range(concurrency)]
    parts = [json.loads(p.communicate()[0]) for p in procs]
    lat = np.concatenate([p["lat"] for p in parts]) * 1e3
    wall = max(p["t1"] for p in parts) - min(p["t0"] for p in parts)
    rate = len(lat) / wall
    return dict(clients=concurrency, p50_ms=np.percentile(lat, 50), p95_ms=np.percentile(lat, 95),
                mean_ms=lat.mean(), throughput_rps=rate, littles_L=rate * lat.mean() / 1e3)

rows = [load(PORT, c, max(100, 800 // c)) for c in (1, 2, 4, 8, 16)]
print(pd.DataFrame(rows).round(2).to_string(index=False))
""")

md(r"""
Two things to read in that table. First, **Little's law**, $L = \lambda W$: the last column,
throughput times mean latency, should come back as the number of clients, because each client
always has exactly one request in the system. Second, **saturation**: once throughput stops
rising, every extra client only waits, and the mean latency grows as clients divided by
throughput. Where that happens depends on your machine.
""")

md(r"""
## 5. One request at a time, against a batch
""")

code(r"""
with httpx.Client(base_url=BASE) as c:
    for B in (1, 10, 100, 1000):
        body = (test_mixes * (B // len(test_mixes) + 1))[:B]
        reps = 100 if B <= 100 else 20
        c.post("/predict_batch", json=body)
        t = time.perf_counter()
        for _ in range(reps):
            c.post("/predict_batch", json=body).raise_for_status()
        per = (time.perf_counter() - t) / reps
        print(f"{B:5d} mixes per request: {per * 1e3:7.2f} ms per request, "
              f"{per / B * 1e6:7.1f} us per prediction")
""")

md(r"""
## 6. A deliberate mistake: CPU work inside `async def`

**This cell is meant to show a failure.** `/predict_batch` is a plain `def`, so FastAPI runs it in
a thread pool. `/predict_batch_async` does exactly the same work inside `async def`, so it runs on
the event loop and nothing else can be answered until it finishes. Four threads send 5,000-mix
batches to one endpoint while a probe asks `/healthz` every 50 ms.
""")

code(r"""
import threading

def stall(path, seconds=3.0):
    heavy = (test_mixes * 40)[:5000]
    stop = time.perf_counter() + seconds
    probe = []
    def hammer():
        with httpx.Client(base_url=BASE, timeout=60) as c:
            while time.perf_counter() < stop:
                c.post(path, json=heavy).raise_for_status()
    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    with httpx.Client(base_url=BASE, timeout=60) as c:
        while time.perf_counter() < stop:
            t0 = time.perf_counter()
            c.get("/healthz").raise_for_status()
            probe.append((time.perf_counter() - t0) * 1e3)
            time.sleep(0.05)
    for t in threads:
        t.join()
    return len(probe), np.percentile(probe, 50), np.percentile(probe, 95)

for path in ("/predict_batch", "/predict_batch_async"):
    k, p50, p95 = stall(path)
    print(f"{path:22s} health checks answered: {k:3d}   p50 {p50:6.1f} ms   p95 {p95:6.1f} ms")
""")

md(r"""
## 7. An optimizer as the client

A design loop is the surrogate's real caller. Here Nelder-Mead searches cement and water for the
strongest mix at 28 days, holding the other inputs at a typical mix, and treats an out-of-domain
answer as unusable. Every evaluation is one HTTP request. Then the same question is answered with
2,000 random candidates sent in two batches. Count the calls.
""")

code(r"""
from scipy.optimize import minimize

base_mix = dict(cement=300.0, slag=100.0, fly_ash=0.0, water=180.0, superplasticizer=6.0,
                coarse_agg=970.0, fine_agg=775.0, age_days=28.0)
calls = 0
with httpx.Client(base_url=BASE) as c:
    def objective(v):
        global calls
        calls += 1
        mix = {**base_mix, "cement": float(np.clip(v[0], 1, 1000)), "water": float(np.clip(v[1], 1, 1000))}
        p = c.post("/predict", json=mix).json()
        return -p["strength_mpa"] if p["in_domain"] else 1e3
    t = time.perf_counter()
    res = minimize(objective, x0=[300.0, 180.0], method="Nelder-Mead",
                   options=dict(xatol=1.0, fatol=0.05, maxfev=400))
    t_nm = time.perf_counter() - t
    print(f"Nelder-Mead: {calls} requests, {t_nm * 1e3:.0f} ms, best {-res.fun:.1f} MPa "
          f"at cement {res.x[0]:.0f}, water {res.x[1]:.0f} kg/m3")

    rng = np.random.default_rng(0)
    lo, hi = manifest["ranges"]["cement"], manifest["ranges"]["water"]
    cand = [{**base_mix, "cement": float(a), "water": float(b)}
            for a, b in zip(rng.uniform(*lo, 2000), rng.uniform(*hi, 2000))]
    t = time.perf_counter()
    preds = c.post("/predict_batch", json=cand[:1000]).json() + c.post("/predict_batch", json=cand[1000:]).json()
    t_b = time.perf_counter() - t
    best = max((p for p in preds if p["in_domain"]), key=lambda p: p["strength_mpa"])
    i = preds.index(best)
    print(f"Random search, batched: 2 requests for 2,000 candidates, {t_b * 1e3:.0f} ms, best "
          f"{best['strength_mpa']:.1f} MPa at cement {cand[i]['cement']:.0f}, water {cand[i]['water']:.0f} kg/m3")
""")

md(r"""
The optimizer's answer and the batch's answer should be close. The difference is the number of
round trips, and therefore how much of the time went to overhead rather than to the model.
""")

md(r"""
## 8. Cost

Two estimates. For the CPU service, throughput is the denominator: predictions per core-hour from
what you measured above. For a hosted LLM, input and output tokens are priced separately. The
prices below were read from Anthropic's pricing page on 2026-11-04; read the page again before you
rely on them, and record the date with your estimate.
""")

code(r"""
peak = max(r["throughput_rps"] for r in rows[:1])  # one client, one worker
print(f"one worker, one mix per request, one client: {peak:,.0f} requests/s "
      f"= {peak * 3600 / 1e6:.1f} million predictions per hour")

PRICES_2026_11_04 = {"Claude Sonnet 5.5": (2.00, 10.00)}  # USD per million tokens, (input, output)

def llm_cost(tokens_in, tokens_out, model="Claude Sonnet 5.5"):
    p_in, p_out = PRICES_2026_11_04[model]
    return tokens_in * p_in / 1e6 + tokens_out * p_out / 1e6

per = llm_cost(3000, 300)
print(f"an answer with 3,000 tokens of retrieved context and a 300-token reply: ${per:.4f}, "
      f"${per * 1000:.2f} per thousand answers")
""")

md(r"""
## 9. Docker, if it is installed

These cells build the repository's own `service/Dockerfile`, so they need a checkout of the course
repository (the notebook beside `service/`) and Docker. In Colab, or without Docker, they say so
and do nothing. Without BuildKit, the build swaps the Dockerfile's cache and bind mounts for plain
`COPY`, which produces the same final image.
""")

code(r"""
SERVICE = Path("service")
have_docker = shutil.which("docker") is not None and SERVICE.joinpath("Dockerfile").exists()
if not have_docker:
    print("Docker or the repository's service/ directory is not available here; skipping.")
else:
    ctx = Path(tempfile.mkdtemp()) / "ctx"
    shutil.copytree(SERVICE, ctx, ignore=shutil.ignore_patterns(".venv", "__pycache__", "model"))
    shutil.copytree(WORK / "model", ctx / "model")
    if subprocess.run(["docker", "buildx", "version"], capture_output=True).returncode != 0:
        df_ = (ctx / "Dockerfile").read_text()
        i, j = df_.index("RUN --mount=type=cache"), df_.index("--no-install-project") + len("--no-install-project")
        (ctx / "Dockerfile").write_text(df_[:i] + "COPY uv.lock pyproject.toml ./\nRUN uv sync --locked --no-dev --no-install-project" + df_[j:])
    t = time.perf_counter()
    subprocess.run(["docker", "build", "-q", "-t", "l21-concrete:nb", "."], cwd=ctx, check=True, capture_output=True)
    size = int(subprocess.run(["docker", "image", "inspect", "l21-concrete:nb", "--format", "{{.Size}}"],
                              capture_output=True, text=True).stdout)
    # With Docker's containerd image store this Size is the compressed size, the bytes a machine
    # downloads; the layer sizes printed by docker history below are unpacked.
    print(f"built in {time.perf_counter() - t:.1f} s; image {size / 1e6:.0f} MB compressed")
    print(subprocess.run(["docker", "history", "l21-concrete:nb", "--format", "{{.Size}}\t{{.CreatedBy}}"],
                         capture_output=True, text=True).stdout[:1500])
""")

md(r"""
**This cell is meant to show a failure.** A fake key passed as a build argument appears in
`docker history`; a key file copied in and deleted in the next step is gone from the running
container and still present in the saved image's earlier layer.
""")

code(r"""
import tarfile
if not have_docker:
    print("skipping")
else:
    d = Path(tempfile.mkdtemp())
    fake = "demo-not-a-real-key-7f3a"
    (d / "key.txt").write_text(fake + "\n")
    (d / "Dockerfile").write_text("FROM python:3.12-slim\nARG API_KEY\nRUN echo configured > /tmp/marker\n"
                                  "COPY key.txt /app/key.txt\nRUN rm /app/key.txt\n")
    subprocess.run(["docker", "build", "-q", "--build-arg", f"API_KEY={fake}", "-t", "l21-leak", "."],
                   cwd=d, check=True, capture_output=True)
    hist = subprocess.run(["docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", "l21-leak"],
                          capture_output=True, text=True).stdout
    print("build argument in docker history:", fake in hist)
    print("key.txt in the running container:", "key.txt" in subprocess.run(
        ["docker", "run", "--rm", "l21-leak", "ls", "/app"], capture_output=True, text=True).stdout)
    subprocess.run(["docker", "save", "-o", str(d / "img.tar"), "l21-leak"], check=True)
    found = False
    with tarfile.open(d / "img.tar") as outer:
        for m in outer.getmembers():
            if m.isfile():
                try:
                    with tarfile.open(fileobj=io.BytesIO(outer.extractfile(m).read())) as layer:
                        for lm in layer.getmembers():
                            if lm.name.endswith("app/key.txt") and lm.isfile():
                                found = fake in layer.extractfile(lm).read().decode()
                except tarfile.ReadError:
                    pass
    print("key.txt recoverable from a saved layer:", found)
    subprocess.run(["docker", "rmi", "-f", "l21-leak", "l21-concrete:nb"], capture_output=True)
""")

code(r"""
server.terminate()
server.wait(timeout=10)
print("server stopped")
""")

md(r"""
## Try it

- Start the server with `start_server(workers=4)` and rerun the load table. Where does throughput
  stop rising now, and what does `ps` say about memory?
- Change `/predict` from `def` to `async def` in `l21_work/app.py`, restart, and rerun section 4.
  What happens to p95 at 8 clients?
- Edit one value in `l21_work/model/manifest.json` and restart the server. What happens, and why
  is that the behaviour you want?
- Send the optimizer of section 7 a mix with `age_days` 730. What does the service say, and what
  should the optimizer do with it?
- Raise the 2,000 candidates to 20,000 in one request. Which limit stops you, and why does the
  service have it?
""")

cells = with_colab_cell(cells, OUT)
nb = {"cells": cells, "metadata": {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, indent=1) + "\n")
print(f"wrote {OUT.name} ({len(cells)} cells)")
