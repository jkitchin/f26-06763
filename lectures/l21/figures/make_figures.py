#!/usr/bin/env python3
"""Figures and every measured number for L21, deployment.

Runs inside the service's own locked environment, so the scikit-learn that trains the model is
the scikit-learn that serves it (the version check in service/app.py would refuse anything else):

    uv run --project lectures/l21/service --group dev python lectures/l21/figures/make_figures.py

Groups, in order (name some to run only those):

  train     Lecture 14's five-network ensemble on concrete, on Lecture 14's grouped split, with
            its one-factor recalibration. Writes service/model/ (ensemble.joblib, manifest.json).
  serve     Starts service/app.py with uvicorn on 127.0.0.1 and measures it: time to ready, a 422,
            an out-of-domain flag, latency against concurrency, one request against a batch, the
            async-def stall, and resident memory with one worker against four.
  docker    If Docker is installed: builds the image from service/Dockerfile, records its size,
            runs it and asks it a question; then shows a build argument in `docker history` and
            a deleted file surviving in an earlier layer.
  figures   fanout.png, saturation.png, latency.png, batching.png, stall.png, images.png,
            where.png.

Numbers go to results.json. The client and the server share one machine (recorded in
results.json), so the latencies are a floor: a real network adds to every one of them.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import warnings
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
L21 = HERE.parent
SERVICE = L21 / "service"
MODEL = SERVICE / "model"
REPO = L21.parent.parent
CACHE = HERE / ".cache"
RESULTS = HERE / "results.json"
UCI = "https://archive.ics.uci.edu/static/public/165/concrete+compressive+strength.zip"
COLUMNS = ["cement", "slag", "fly_ash", "water", "superplasticizer",
           "coarse_agg", "fine_agg", "age_days", "strength_mpa"]
FEATURES, MIX = COLUMNS[:8], COLUMNS[:7]
Z90 = 1.6448536269514722

CMU_RED, INK, MUTED, BLUE, ORANGE, GREEN, GRAY = (
    "#c41230", "#1a1a1a", "#5c5c5c", "#1f5c99", "#c2410c", "#2e7d32", "#8a8a8a")
STYLE = {
    "font.size": 14, "axes.labelsize": 14, "axes.titlesize": 15,
    "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 12,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": MUTED, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "savefig.dpi": 150, "savefig.bbox": "tight",
}


def load_results() -> dict:
    return json.loads(RESULTS.read_text()) if RESULTS.exists() else {}


def save_results(res: dict) -> None:
    RESULTS.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")


# ---------------------------------------------------------------- train

def load_concrete():
    import pandas as pd
    CACHE.mkdir(exist_ok=True)
    path = CACHE / "Concrete_Data.xls"
    for other in [REPO / "lectures" / "l14" / "figures" / ".cache",
                  REPO / "lectures" / "l09" / "figures" / ".cache"]:
        if not path.exists() and (other / "Concrete_Data.xls").exists():
            shutil.copy(other / "Concrete_Data.xls", path)
    if not path.exists():
        z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(UCI).read()))
        path.write_bytes(z.read("Concrete_Data.xls"))
    df = pd.read_excel(path)
    df.columns = COLUMNS
    return df


def train(res: dict) -> None:
    """The ensemble exactly as Lecture 14 builds it: same split seeds, same network, same seeds."""
    import joblib
    import sklearn
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    warnings.filterwarnings("ignore", category=ConvergenceWarning)

    df = load_concrete()
    X, y = df[FEATURES].to_numpy(), df["strength_mpa"].to_numpy()
    groups = df.groupby(MIX).ngroup().to_numpy()
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42).split(X, y, groups))
    fit_i, cal_i = next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=0)
                        .split(X[tr], y[tr], groups[tr]))
    fit_i, cal_i = tr[fit_i], tr[cal_i]
    nets = [make_pipeline(StandardScaler(), MLPRegressor(
        hidden_layer_sizes=(16,), activation="tanh", solver="lbfgs", max_iter=5000,
        random_state=s)).fit(X[fit_i], y[fit_i]) for s in range(5)]

    def ens(Xq):
        P = np.array([n.predict(Xq) for n in nets])
        return P.mean(0), P.std(0, ddof=1)
    mc, sc = ens(X[cal_i])
    s = float(np.sqrt(np.mean(((y[cal_i] - mc) / sc) ** 2)))
    mt, st = ens(X[te])
    cover = float(np.mean(np.abs(y[te] - mt) <= Z90 * s * st))
    rmse = float(np.sqrt(np.mean((y[te] - mt) ** 2)))

    MODEL.mkdir(parents=True, exist_ok=True)
    art = MODEL / "ensemble.joblib"
    joblib.dump(nets, art)
    data_hash = hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()
    ranges = {f: [float(X[tr][:, i].min()), float(X[tr][:, i].max())] for i, f in enumerate(FEATURES)}
    manifest = dict(model_version="concrete-ens5-v1", sklearn=sklearn.__version__,
                    numpy=np.__version__, python=platform.python_version(),
                    data="UCI concrete compressive strength (Yeh 1998), 1030 rows",
                    data_sha256=data_hash, split="Lecture 14 grouped split, seeds 42 and 0",
                    scale=s, ranges=ranges,
                    sha256=hashlib.sha256(art.read_bytes()).hexdigest(),
                    artifact_bytes=art.stat().st_size)
    (MODEL / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    # Lecture 14 reports s = 1.66 on this split; check we reproduced it.
    l14 = REPO / "lectures" / "l14" / "figures" / ".cache" / "scale.json"
    l14_s = None
    if l14.exists():
        l14_s = json.loads(l14.read_text())["splits"][0]["s"]
    res["train"] = dict(n_fit=len(fit_i), n_cal=len(cal_i), n_test=len(te), scale=round(s, 3),
                        l14_scale=None if l14_s is None else round(l14_s, 3),
                        test_rmse_mpa=round(rmse, 2), test_cover90=round(cover, 3),
                        artifact_bytes=art.stat().st_size, sklearn=sklearn.__version__,
                        ranges=ranges)
    # A pool of real mixes to send, from the test split, kept for the load tests.
    (CACHE / "test_mixes.json").write_text(json.dumps(
        [dict(zip(FEATURES, map(float, row))) for row in X[te]]))
    print("train", {k: v for k, v in res["train"].items() if k != "ranges"})


# ---------------------------------------------------------------- serve

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(workers: int = 1):
    port = free_port()
    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
                             "--port", str(port), "--workers", str(workers), "--log-level", "warning"],
                            cwd=SERVICE, env={**os.environ, "MODEL_DIR": str(MODEL)})
    import httpx
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


def stop(proc) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def pct(a, q):
    return float(np.percentile(a, q))


async def load(port: int, path: str, bodies: list, concurrency: int, n: int) -> dict:
    """n requests over `concurrency` closed-loop clients; each sends, waits, sends again."""
    import httpx
    lat: list[float] = []
    queue = list(range(n))
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", limits=limits,
                                 timeout=30) as c:
        async def client(k):
            while queue:
                i = queue.pop()
                t = time.perf_counter()
                r = await c.post(path, json=bodies[i % len(bodies)])
                r.raise_for_status()
                lat.append(time.perf_counter() - t)
        # warm the connections and the code paths first
        await asyncio.gather(*[c.post(path, json=bodies[0]) for _ in range(concurrency)])
        t0 = time.perf_counter()
        await asyncio.gather(*[client(k) for k in range(concurrency)])
        wall = time.perf_counter() - t0
    ms = np.array(lat) * 1e3
    return dict(concurrency=concurrency, n=n, p50_ms=round(pct(ms, 50), 3), p95_ms=round(pct(ms, 95), 3),
                p99_ms=round(pct(ms, 99), 3), mean_ms=round(float(ms.mean()), 3),
                throughput_rps=round(n / wall, 1),
                littles_L=round(float(n / wall * ms.mean() / 1e3), 2))


def _client(args):
    """One closed-loop client in its own process: send, wait for the answer, send again."""
    import httpx
    port, path, bodies, n, start_at = args
    lat = []
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) as c:
        c.post(path, json=bodies[0])                     # warm the connection
        while time.perf_counter() < start_at:
            time.sleep(0.001)
        t0 = time.perf_counter()
        for i in range(n):
            t = time.perf_counter()
            c.post(path, json=bodies[i % len(bodies)]).raise_for_status()
            lat.append(time.perf_counter() - t)
        return lat, t0, time.perf_counter()


def load_mp(port: int, path: str, bodies: list, concurrency: int, n_each: int) -> dict:
    """Closed-loop load with one process per client, so the load generator is not the bottleneck.

    The first version of this measurement drove every client from one asyncio process, and its
    throughput fell from about 1,300 to about 270 requests a second between 8 and 32 clients.
    Four server workers did not change that, which put the limit in the client.
    """
    from concurrent.futures import ProcessPoolExecutor
    start_at = time.perf_counter() + 1.5
    with ProcessPoolExecutor(concurrency) as ex:
        parts = list(ex.map(_client, [(port, path, bodies, n_each, start_at)] * concurrency))
    lat = np.concatenate([p[0] for p in parts]) * 1e3
    wall = max(p[2] for p in parts) - min(p[1] for p in parts)
    n = len(lat)
    return dict(concurrency=concurrency, n=n, p50_ms=round(pct(lat, 50), 3),
                p95_ms=round(pct(lat, 95), 3), p99_ms=round(pct(lat, 99), 3),
                mean_ms=round(float(lat.mean()), 3), throughput_rps=round(n / wall, 1),
                littles_L=round(float(n / wall * lat.mean() / 1e3), 2))


async def stall_probe(port: int, path: str, heavy: list, seconds: float = 4.0) -> dict:
    """Four clients hammer `path` with big batches; meanwhile one probe asks /healthz every 50 ms."""
    import httpx
    probe: list[float] = []
    stop_at = time.perf_counter() + seconds
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=60) as c:
        async def hammer():
            while time.perf_counter() < stop_at:
                (await c.post(path, json=heavy)).raise_for_status()

        async def ping():
            while time.perf_counter() < stop_at:
                t = time.perf_counter()
                (await c.get("/healthz")).raise_for_status()
                probe.append(time.perf_counter() - t)
                await asyncio.sleep(0.05)
        await asyncio.gather(*[hammer() for _ in range(4)], ping())
    ms = np.array(probe) * 1e3
    return dict(endpoint=path, probes=len(ms), p50_ms=round(pct(ms, 50), 2),
                p95_ms=round(pct(ms, 95), 2), max_ms=round(float(ms.max()), 1))


def rss_mb(proc) -> float:
    import psutil
    p = psutil.Process(proc.pid)
    procs = [p] + p.children(recursive=True)
    return sum(q.memory_info().rss for q in procs) / 2**20


def serve(res: dict) -> None:
    import httpx
    mixes = json.loads((CACHE / "test_mixes.json").read_text())
    out: dict = {"machine": f"{platform.machine()} {platform.system()} {platform.mac_ver()[0]}",
                 "cpu": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                       capture_output=True, text=True).stdout.strip()
                 if sys.platform == "darwin" else platform.processor(),
                 "python": platform.python_version()}
    proc, port, t_ready, ready = start(1)
    try:
        out["time_to_ready_s"] = round(t_ready, 2)
        out["model_load_s"] = ready["load_seconds"]
        base = f"http://127.0.0.1:{port}"
        good = mixes[0]
        r = httpx.post(base + "/predict", json=good)
        out["example_ok"] = dict(request=good, status=r.status_code, body=r.json())
        bad = {**good, "cement": -50.0}
        r = httpx.post(base + "/predict", json=bad)
        out["example_422"] = dict(status=r.status_code, body=r.json())
        odd = {**good, "slag": 400.0, "age_days": 730.0}
        r = httpx.post(base + "/predict", json=odd)
        out["example_ood"] = dict(request=odd, status=r.status_code, body=r.json())
        out["openapi_paths"] = sorted(httpx.get(base + "/openapi.json").json()["paths"])

        # Latency against concurrency, one mix per request.
        out["concurrency"] = [load_mp(port, "/predict", mixes, c, max(100, 1600 // c))
                              for c in (1, 2, 4, 8, 16, 32)]
        out["concurrency_single_process_client"] = [asyncio.run(load(port, "/predict", mixes, c, 1500))
                                                    for c in (8, 32)]
        # One request carrying B mixes, against B requests of one mix.
        batch = []
        for B in (1, 10, 100, 1000):
            body = (mixes * (B // len(mixes) + 1))[:B]
            reps = 200 if B <= 100 else 40
            with httpx.Client(base_url=base) as c:
                c.post("/predict_batch", json=body)
                t = time.perf_counter()
                for _ in range(reps):
                    c.post("/predict_batch", json=body).raise_for_status()
                per_req = (time.perf_counter() - t) / reps
            batch.append(dict(batch=B, ms_per_request=round(per_req * 1e3, 3),
                              us_per_prediction=round(per_req / B * 1e6, 1)))
        out["batching"] = batch
        heavy = (mixes * 40)[:5000]
        out["stall"] = [asyncio.run(stall_probe(port, p, heavy))
                        for p in ("/predict_batch", "/predict_batch_async")]
        out["rss_mb_1_worker"] = round(rss_mb(proc), 1)
    finally:
        stop(proc)
    proc, port, t4, _ = start(4)
    try:
        time.sleep(1.0)
        out["rss_mb_4_workers"] = round(rss_mb(proc), 1)
        out["concurrency_4_workers"] = [load_mp(port, "/predict", mixes, c, max(100, 1600 // c))
                                        for c in (8, 16, 32)]
        # The single-process client against four workers: if this is no faster than against one
        # worker, the limit is in the client.
        out["single_process_client_4_workers"] = asyncio.run(load(port, "/predict", mixes, 32, 1500))
        out["time_to_ready_4_workers_s"] = round(t4, 2)
    finally:
        stop(proc)
    res["serve"] = out
    print("serve", json.dumps({k: out[k] for k in ("time_to_ready_s", "model_load_s",
                                                    "rss_mb_1_worker", "rss_mb_4_workers")}))
    for row in out["concurrency"]:
        print("  ", row)
    for row in out["batching"]:
        print("  ", row)
    for row in out["stall"]:
        print("  ", row)


# ---------------------------------------------------------------- docker

def sh(*cmd, cwd=None, check=True) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def docker(res: dict) -> None:
    if not shutil.which("docker"):
        print("docker: not installed, skipped")
        return
    out: dict = {"docker_version": sh("docker", "version", "--format", "{{.Server.Version}}").strip(),
                 "platform": sh("docker", "version", "--format", "{{.Server.Arch}}").strip()}
    with tempfile.TemporaryDirectory() as d:
        ctx = Path(d) / "ctx"
        shutil.copytree(SERVICE, ctx, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
        # The committed Dockerfile uses BuildKit cache and bind mounts, as uv's guide recommends.
        # Without BuildKit (docker buildx), build an equivalent with plain COPY: the runtime stage
        # copies only .venv either way, so the final image is the same.
        has_buildkit = subprocess.run(["docker", "buildx", "version"], capture_output=True).returncode == 0
        out["builder"] = "BuildKit" if has_buildkit else "legacy builder: mounts replaced by COPY"
        if not has_buildkit:
            df_ = (ctx / "Dockerfile").read_text()
            i, j = df_.index("RUN --mount=type=cache"), df_.index("--no-install-project") + len("--no-install-project")
            df_ = df_[:i] + "COPY uv.lock pyproject.toml ./\nRUN uv sync --locked --no-dev --no-install-project" + df_[j:]
            (ctx / "Dockerfile").write_text(df_)
        t = time.perf_counter()
        sh("docker", "build", "-q", "-t", "l21-concrete:1.0.0", ".", cwd=ctx)
        out["build_s_cold_or_cached"] = round(time.perf_counter() - t, 1)
        # With Docker's containerd image store, `image inspect` Size is the compressed size: the
        # bytes a node downloads, comparable to Docker Hub's listed sizes. The unpacked size is the
        # sum of the layer sizes `docker history` reports.
        def unpacked(tag):
            units = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "GB": 1e9}
            total = 0.0
            for v in sh("docker", "history", "--format", "{{.Size}}", tag).split():
                num = v.rstrip("kKMGB")
                total += float(num) * units[v[len(num):]]
            return round(total / 1e6, 1)
        out["image_mb"] = round(int(sh("docker", "image", "inspect", "l21-concrete:1.0.0",
                                       "--format", "{{.Size}}")) / 1e6, 1)
        out["base_mb"] = round(int(sh("docker", "image", "inspect", "python:3.12-slim",
                                      "--format", "{{.Size}}")) / 1e6, 1)
        out["image_unpacked_mb"] = unpacked("l21-concrete:1.0.0")
        out["base_unpacked_mb"] = unpacked("python:3.12-slim")
        out["size_note"] = "image_mb and base_mb are compressed (containerd store); *_unpacked_mb sum docker history"
        # Edit app.py and rebuild: the dependency layer must come from cache.
        (ctx / "app.py").write_text((ctx / "app.py").read_text() + "\n# touched\n")
        t = time.perf_counter()
        sh("docker", "build", "-q", "-t", "l21-concrete:touched", ".", cwd=ctx)
        out["rebuild_after_code_edit_s"] = round(time.perf_counter() - t, 1)
        port = free_port()
        cid = sh("docker", "run", "-d", "--rm", "-p", f"127.0.0.1:{port}:8000",
                 "l21-concrete:1.0.0").strip()
        try:
            import httpx
            t = time.perf_counter()
            while True:
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/readyz", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
                if time.perf_counter() - t > 60:
                    raise RuntimeError("container never became ready")
            out["container_ready_s"] = round(time.perf_counter() - t, 2)
            out["container_user"] = sh("docker", "exec", cid, "whoami").strip()
            out["container_predict"] = httpx.post(f"http://127.0.0.1:{port}/predict",
                                                  json=json.loads((CACHE / "test_mixes.json").read_text())[0]).json()
            time.sleep(12)
            out["container_health"] = sh("docker", "inspect", "--format",
                                         "{{.State.Health.Status}}", cid).strip()
        finally:
            sh("docker", "stop", cid, check=False)

        # Secrets in layers. A fake key, passed the two wrong ways.
        leak = Path(d) / "leak"
        leak.mkdir()
        fake = "demo-not-a-real-key-7f3a"
        (leak / "key.txt").write_text(fake + "\n")
        (leak / "Dockerfile").write_text(
            "FROM python:3.12-slim\n"
            "ARG API_KEY\n"
            "RUN echo \"configured\" > /tmp/marker\n"
            "COPY key.txt /app/key.txt\n"
            "RUN rm /app/key.txt\n")
        sh("docker", "build", "-q", "--build-arg", f"API_KEY={fake}", "-t", "l21-leak", ".", cwd=leak)
        hist = sh("docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", "l21-leak")
        out["history_shows_arg"] = fake in hist
        out["history_line"] = next((h for h in hist.splitlines() if fake in h), "")[:160]
        live = subprocess.run(["docker", "run", "--rm", "l21-leak", "ls", "/app"],
                              capture_output=True, text=True)
        out["file_visible_in_container"] = "key.txt" in live.stdout
        tar = Path(d) / "leak.tar"
        sh("docker", "save", "-o", str(tar), "l21-leak")
        found = False
        with tarfile.open(tar) as outer:
            for m in outer.getmembers():
                if not m.isfile():
                    continue
                blob = outer.extractfile(m).read()
                try:
                    with tarfile.open(fileobj=io.BytesIO(blob)) as layer:
                        for lm in layer.getmembers():
                            if lm.name.endswith("app/key.txt") and lm.isfile():
                                found = fake in layer.extractfile(lm).read().decode()
                except tarfile.ReadError:
                    continue
        out["deleted_file_in_saved_layers"] = found
        sh("docker", "rmi", "-f", "l21-leak", "l21-concrete:touched", check=False)
    res["docker"] = out
    print("docker", json.dumps(out, indent=1)[:1500])


# ---------------------------------------------------------------- figures

# Cited sizes, read 2026-11-04 (Docker Hub compressed sizes, amd64; PyPI and download.pytorch.org
# file sizes). They change with every release.
CITED = [("python:3.12-slim, Docker Hub", 43.3, "Docker Hub"),
         ("torch 2.15.0 CPU wheel", 209.5, "download.pytorch.org"),
         ("torch 2.15.0 Linux wheel (CUDA libraries extra)", 539.2, "PyPI"),
         ("nvidia/cuda 12.8.1 runtime", 2160, "Docker Hub"),
         ("pytorch/pytorch 2.15.0 runtime", 3290, "Docker Hub"),
         ("pytorch/pytorch 2.15.0 devel", 13850, "Docker Hub")]


def figures(res: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update(STYLE)

    # 1. Fan-out: the chance a request that waits for n servers meets at least one slow one.
    n = np.logspace(0, np.log10(2000), 200)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for p, c, lab in [(0.01, CMU_RED, "each server slow 1 time in 100"),
                      (1e-4, BLUE, "each server slow 1 time in 10,000")]:
        ax.plot(n, 1 - (1 - p) ** n, color=c, lw=2.5, label=lab)
    ax.plot([100], [1 - 0.99 ** 100], "o", color=CMU_RED)
    ax.annotate("100 servers: 63%", (100, 1 - 0.99 ** 100), (160, 0.48), color=CMU_RED,
                arrowprops=dict(arrowstyle="-", color=CMU_RED))
    ax.plot([2000], [1 - 0.9999 ** 2000], "o", color=BLUE)
    ax.annotate("2,000 servers: 18%", (2000, 1 - 0.9999 ** 2000), (300, 0.27), color=BLUE,
                arrowprops=dict(arrowstyle="-", color=BLUE))
    ax.set_xscale("log")
    ax.set_xlabel("servers one request waits for (fan-out)")
    ax.set_ylabel("share of requests that are slow")
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    fig.savefig(HERE / "fanout.png")
    plt.close(fig)

    # 2. Saturation: M/M/1 time in system, in units of the service time, against utilization.
    rho = np.linspace(0, 0.97, 300)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.plot(rho, 1 / (1 - rho), color=CMU_RED, lw=2.5)
    for r_ in (0.5, 0.8, 0.9, 0.95):
        ax.plot([r_], [1 / (1 - r_)], "o", color=INK)
        ax.annotate(f"{r_:.0%}: {1 / (1 - r_):.0f}x", (r_, 1 / (1 - r_)), (r_ - 0.2, 1 / (1 - r_) + 3),
                    arrowprops=dict(arrowstyle="-", color=MUTED))
    ax.set_xlabel("utilization  ρ = arrival rate / service rate")
    ax.set_ylabel("time in system / service time")
    ax.set_ylim(0, 35)
    fig.savefig(HERE / "saturation.png")
    plt.close(fig)

    sv = res.get("serve")
    if sv:
        # 3. Latency and throughput against concurrency, measured, one worker and four.
        one, four = sv["concurrency"], sv["concurrency_4_workers"]
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
        for rows, c_, lab in [(one, CMU_RED, "1 worker"), (four, BLUE, "4 workers")]:
            cc = [r["concurrency"] for r in rows]
            a1.plot(cc, [r["p50_ms"] for r in rows], "o-", color=c_, lw=2, label=f"{lab}, p50")
            a1.plot(cc, [r["p95_ms"] for r in rows], "o--", color=c_, lw=1.5, label=f"{lab}, p95")
            a2.plot(cc, [r["throughput_rps"] for r in rows], "o-", color=c_, lw=2, label=lab)
        for a in (a1, a2):
            a.set_xscale("log", base=2)
            a.set_xlabel("concurrent clients")
        a1.set_ylabel("latency (ms)")
        a2.set_ylabel("throughput (requests / s)")
        a2.set_ylim(0, None)
        a1.legend(fontsize=10)
        a2.legend()
        fig.tight_layout()
        fig.savefig(HERE / "latency.png")
        plt.close(fig)

        # 4. One request carrying B mixes.
        b = sv["batching"]
        fig, ax = plt.subplots(figsize=(8, 4.2))
        ax.plot([r["batch"] for r in b], [r["us_per_prediction"] for r in b], "o-", color=CMU_RED, lw=2.5)
        for r in b:
            ax.annotate(f"{r['us_per_prediction']:.0f} µs", (r["batch"], r["us_per_prediction"]),
                        (6, 6), textcoords="offset points", color=MUTED)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel("mixes per request")
        ax.set_ylabel("time per prediction (µs)")
        fig.savefig(HERE / "batching.png")
        plt.close(fig)

        # 5. The async-def stall: how long /healthz waits while big batches run.
        st = sv["stall"]
        fig, ax = plt.subplots(figsize=(8, 3.6))
        labels = ["def predict_batch", "async def predict_batch_async"]
        y = np.arange(2)
        ax.barh(y + 0.2, [s["p50_ms"] for s in st], 0.38, color=BLUE, label="p50")
        ax.barh(y - 0.2, [s["p95_ms"] for s in st], 0.38, color=CMU_RED, label="p95")
        ax.set_yticks(y, labels)
        for k, s_ in enumerate(st):
            ax.text(s_["p50_ms"] + 2, k + 0.2, f"{s_['p50_ms']:.0f} ms", va="center", color=MUTED, fontsize=11)
            ax.text(s_["p95_ms"] + 2, k - 0.2, f"{s_['p95_ms']:.0f} ms", va="center", color=MUTED, fontsize=11)
        ax.set_xlabel("/healthz latency while four clients send 5,000-mix batches (ms)")
        ax.legend(loc="lower right")
        fig.savefig(HERE / "stall.png")
        plt.close(fig)

    # 6. Image and wheel sizes: ours measured, the rest cited and dated.
    rows = list(CITED)
    dk = res.get("docker")
    if dk:
        rows.insert(1, ("this service, uv + scikit-learn (measured)", dk["image_mb"], "measured"))
        rows.insert(1, ("python:3.12-slim (measured, arm64)", dk["base_mb"], "measured"))
    rows.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(9, 4.4))
    cols = [CMU_RED if r[2] == "measured" else GRAY for r in rows]
    ax.barh(range(len(rows)), [r[1] for r in rows], color=cols)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xscale("log")
    for i, r in enumerate(rows):
        ax.text(r[1] * 1.08, i, f"{r[1]:,.0f} MB", va="center", color=MUTED, fontsize=11)
    ax.set_xlabel("compressed image or file size (MB, log scale); red measured, grey cited 2026-11-04")
    fig.savefig(HERE / "images.png")
    plt.close(fig)

    # 7. Where a model runs, and where this course already ran something.
    fig, ax = plt.subplots(figsize=(12.5, 4.6))
    ax.axis("off")
    boxes = [("In the caller's\nprocess", "import the model\nlike a library", "DuckDB (L4)\nFAISS index (L18)"),
             ("Long-running\nservice", "a process that\nanswers requests", "PostgreSQL (L3)\nMQTT broker (L6)"),
             ("Serverless", "started per request,\nscales to zero", "the clicker\n(a Cloudflare Worker)"),
             ("Batch job", "runs on a schedule,\nwrites results", "pipeline stages (L5)"),
             ("The user's\nbrowser", "the model ships\nto the client", "notes chat (L18)\npractice game")]
    for i, (t, d, e) in enumerate(boxes):
        x = i * 2.2
        ax.add_patch(plt.Rectangle((x, 1.6), 2.0, 1.5, fc="#eef3f9", ec=BLUE, lw=1.5))
        ax.text(x + 1.0, 2.7, t, ha="center", va="center", fontsize=12, weight="bold", color=INK)
        ax.text(x + 1.0, 2.0, d, ha="center", va="center", fontsize=10.5, color=MUTED)
        ax.add_patch(plt.Rectangle((x, 0.1), 2.0, 1.2, fc="#fbeef0", ec=CMU_RED, lw=1.2))
        ax.text(x + 1.0, 0.7, e, ha="center", va="center", fontsize=11, color=INK)
    ax.text(-0.15, 2.35, "where", rotation=90, ha="center", va="center", color=MUTED)
    ax.text(-0.15, 0.7, "in this course", rotation=90, ha="center", va="center", color=MUTED)
    ax.set_xlim(-0.4, 11)
    ax.set_ylim(0, 3.2)
    fig.savefig(HERE / "where.png")
    plt.close(fig)
    print("figures written")


if __name__ == "__main__":
    groups = sys.argv[1:] or ["train", "serve", "docker", "figures"]
    res = load_results()
    for g in groups:
        {"train": train, "serve": serve, "docker": docker, "figures": figures}[g](res)
        save_results(res)
