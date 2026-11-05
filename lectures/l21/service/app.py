"""Lecture 14's concrete strength ensemble, served over HTTP. The L21 reference service.

    uv run --project . uvicorn app:app --port 8000        # from this directory
    curl -s localhost:8000/readyz

The model directory (MODEL_DIR, default ./model) holds two files written by
lectures/l21/figures/make_figures.py:

    ensemble.joblib   five scikit-learn pipelines (Lecture 9's network, seeds 0 to 4)
    manifest.json     versions, the training ranges, the recalibration factor, and the
                      SHA-256 of ensemble.joblib

Two endpoints are deliberately wrong and exist only so the lecture can measure what they do:
/predict_batch_async runs a CPU-bound prediction inside `async def`. Do not copy it.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import numpy as np
import sklearn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_DIR = Path(os.environ.get("MODEL_DIR", "model"))
Z90 = 1.6448536269514722          # two-sided 90% normal quantile
FEATURES = ["cement", "slag", "fly_ash", "water", "superplasticizer",
            "coarse_agg", "fine_agg", "age_days"]
STATE: dict = {}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the model once, before the server accepts a single request.

    Fail loudly rather than serve a model that is not the one that was tested: the artifact's
    hash and the scikit-learn version are both checked against the manifest.
    """
    t0 = time.perf_counter()
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text())
    artifact = MODEL_DIR / "ensemble.joblib"
    if sha256(artifact) != manifest["sha256"]:
        raise RuntimeError("ensemble.joblib does not match the hash in manifest.json")
    if sklearn.__version__ != manifest["sklearn"]:
        raise RuntimeError(f"model saved with scikit-learn {manifest['sklearn']}, "
                           f"this process has {sklearn.__version__}")
    STATE["nets"] = joblib.load(artifact)   # a pickle: load only artifacts you produced
    STATE["manifest"] = manifest
    STATE["lo"] = np.array([manifest["ranges"][f][0] for f in FEATURES])
    STATE["hi"] = np.array([manifest["ranges"][f][1] for f in FEATURES])
    STATE["load_s"] = time.perf_counter() - t0
    yield
    STATE.clear()


app = FastAPI(title="Concrete strength surrogate", version="1.0.0", lifespan=lifespan)


class Mix(BaseModel):
    """One concrete mix. kg per cubic metre of mixture, and age in days.

    The bounds reject inputs that are physically impossible (a negative mass, an age of zero).
    They do not reject inputs that are merely unusual: that is the in_domain flag's job.
    """
    cement: float = Field(gt=0, le=1000)
    slag: float = Field(ge=0, le=1000)
    fly_ash: float = Field(ge=0, le=1000)
    water: float = Field(gt=0, le=1000)
    superplasticizer: float = Field(ge=0, le=100)
    coarse_agg: float = Field(ge=0, le=2000)
    fine_agg: float = Field(ge=0, le=2000)
    age_days: float = Field(ge=1, le=3650)


class Prediction(BaseModel):
    strength_mpa: float
    interval_90: tuple[float, float]
    in_domain: bool
    outside: list[str]
    model_version: str


def predict_rows(X: np.ndarray) -> list[Prediction]:
    """Ensemble mean, and a 90% interval from the recalibrated ensemble spread (Lecture 14)."""
    P = np.array([net.predict(X) for net in STATE["nets"]])
    mu, sd = P.mean(0), STATE["manifest"]["scale"] * P.std(0, ddof=1)
    out = (X < STATE["lo"]) | (X > STATE["hi"])
    version = STATE["manifest"]["model_version"]
    return [Prediction(strength_mpa=round(float(m), 2),
                       interval_90=(round(float(m - Z90 * s), 2), round(float(m + Z90 * s), 2)),
                       in_domain=not o.any(),
                       outside=[f for f, flag in zip(FEATURES, o) if flag],
                       model_version=version)
            for m, s, o in zip(mu, sd, out)]


def as_matrix(mixes: list[Mix]) -> np.ndarray:
    return np.array([[getattr(m, f) for f in FEATURES] for m in mixes])


@app.get("/healthz")
def healthz() -> dict:
    """Liveness: the process is running and answering. Says nothing about the model."""
    return {"status": "alive"}


@app.get("/readyz")
def readyz() -> dict:
    """Readiness: the model is loaded and this process can serve predictions."""
    if "nets" not in STATE:
        raise HTTPException(status_code=503, detail="model not loaded")
    m = STATE["manifest"]
    return {"status": "ready", "model_version": m["model_version"], "sklearn": m["sklearn"],
            "load_seconds": round(STATE["load_s"], 4)}


@app.post("/predict")
def predict(mix: Mix) -> Prediction:
    return predict_rows(as_matrix([mix]))[0]


@app.post("/predict_batch")
def predict_batch(mixes: list[Mix]) -> list[Prediction]:
    if len(mixes) > 10_000:
        raise HTTPException(status_code=413, detail="at most 10000 mixes per request")
    return predict_rows(as_matrix(mixes))


@app.post("/predict_batch_async")
async def predict_batch_async(mixes: list[Mix]) -> list[Prediction]:
    """DELIBERATELY WRONG. The same CPU-bound work as /predict_batch, inside `async def`, so it
    runs on the event loop and every other request, /healthz included, waits until it ends."""
    return predict_rows(as_matrix(mixes))
