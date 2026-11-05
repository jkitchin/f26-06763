# Lecture 21: Deployment: serving models, containers, latency and cost

:::{admonition} At a glance
:class: tip

- **Session** Lecture 21, Week 12 (optional)
- **Arc** Production and responsibility
- **Slides** <a href="../../slides/l21/">Deck for this session</a>
- **Practice** <a href="../../game/#/l21">Practice module for this session</a>
- **Demo** [`l21-deployment.ipynb`](l21-deployment.ipynb), which serves Lecture 14's concrete strength ensemble with
  FastAPI on your own machine, loads it, and measures it; the service itself is in
  [`service/`](service/app.py) and every number below comes from
  [`figures/make_figures.py`](figures/make_figures.py)
- **Tools** FastAPI, Pydantic and uvicorn; `uv` and Docker; httpx for load
- **Assignment** None. This session is optional and no assignment depends on it
:::

## Why this matters

On 1 August 2012 the trading firm Knight Capital deployed new code to the eight servers of its
automated order router. The Securities and Exchange Commission's order
describes what happened next. "One of Knight's technicians did not copy the new code to one of
the eight SMARS computer servers. Knight did not have a second technician review this
deployment." The new code also "repurposed a flag that was formerly used to activate the Power
Peg code", a function retired years before but still present on every server. On the eighth
server, the flag woke it up. Before the market opened, Knight's system sent 97 automated emails naming the
error, but "Knight did not design these types of messages to be system alerts, and Knight personnel
generally did not review them when they were received." In about 45 minutes the router made more than 4
million executions in 154 stocks, and when engineers tried to fix it by uninstalling
the new code from the seven good servers, "this action worsened the problem." Knight lost more
than $460 million and paid a $12 million penalty
([SEC order, Release 34-70694](https://www.sec.gov/files/litigation/admin/2013/34-70694.pdf);
[press release](https://www.sec.gov/newsroom/press-releases/2013-222)).

Nothing in that story is a modelling error. The code that was meant to run was correct. The
failure was in getting it onto every machine, checking that it had arrived, and knowing what the
fallback would do. This course's own website has had the same failure on a smaller scale. On 6
August 2026 the build job succeeded, the deployment step "sat in deployment_queued for ten
minutes and timed out, and the published site silently stayed on the previous commit while the
run's build job still showed green" (the comment in `.github/workflows/book.yml`). Students saw
yesterday's lectures for hours, and the only thing that caught it was a person loading a page by
hand.

[Lecture 1](../l01/notes.md) put the problem in one sentence: "Your model runs on your laptop.
That is not a deliverable." Deployment is the work of turning a trained model into something
other people and other programs can depend on. It asks five questions: where the model runs,
what contract it offers its callers, how it is packaged, how fast and at what cost it answers,
and how it is changed without hurting the people who depend on it. None of the five is new to
you. This course has already answered each of them at least once, for a database server, an
embedded query engine, a message broker, a model registry, and a language model that runs in your
browser. This session collects those answers, applies them to a model, and measures what they
cost.

## Learning objectives

By the end of this session you should be able to:

- Choose where a model runs (an in-process library, a long-running HTTP service, a
  serverless container, a batch job, or the user's browser) from its call pattern, latency
  budget and cost, and name the system already deployed in this course that made the same choice.
- Serve a trained model behind a FastAPI endpoint with typed, range-checked request and
  response schemas that carry the prediction's uncertainty and the model version, with the
  model loaded once at startup and separate liveness and readiness checks.
- Package the service in a reproducible container built from the `uv` lockfile, CPU-only where
  the model allows, with no secrets in any image layer.
- Measure p50 and p95 latency and throughput under load, use Little's law and batching to
  reason about capacity, and estimate the cost per request of a model service and of an LLM call.
- Release a change with a staged rollout, a rollback plan and a check against the deployed
  endpoint, and explain from documented incidents what each of those prevents.

## Where a model runs

```{index} serverless, cold start
```

You have already made this decision for a database. [Lecture 3](../l03/notes.md) ran PostgreSQL,
which is "a server you must run, secure, back up, monitor, and connect to within its connection
limits." [Lecture 4](../l04/notes.md) ran DuckDB, which has "no server to start, no connection to
manage", because it is a library that runs inside your own process. Both answer SQL. They differ
in where the work happens, who has to keep it running, and what the caller must install. A
trained model faces the same choice, with three more options that databases rarely use. Figure 1
lays out all five, with the system in this course that used each.

```{figure} figures/where.png
:alt: Five boxes across the top naming where a model can run: in the caller's process, a long-running service, serverless, a batch job, and the user's browser. Below each, the system in this course that runs that way: DuckDB and the FAISS index; PostgreSQL and the MQTT broker; the clicker; pipeline stages; the notes chat and the practice game.
:width: 100%

Figure 1. Five places a model can run, and where this course already ran something in each.
Drawn in `figures/make_figures.py`.
```

**In the caller's process.** The caller imports the model and calls it like a function, the way
your notebooks have called every model so far. There is no network hop and nothing to keep
running, so it is the fastest and simplest option. The price is that every caller must install
the same libraries at the same versions. scikit-learn says so plainly: none of its persistence
methods support "loading a model trained with a different version of scikit-learn, and possibly
different versions of other dependencies such as numpy and scipy"
([scikit-learn, Model persistence](https://scikit-learn.org/stable/model_persistence.html)). That
is acceptable when the caller is your own pipeline and a problem when the caller is a colleague's
MATLAB script.

**A long-running service.** A process that loads the model once and answers requests over the
network, usually HTTP. The caller needs only an HTTP client and the contract, and the model's
environment is the service's problem. This is how PostgreSQL works, and how the MQTT broker that
fed the Tennessee Eastman stream in [Lecture 6](../l06/notes.md) works. It is the default for a
model that several programs call, and most of this session is about doing it well.

**Serverless.** A platform starts copies of your container or function when requests arrive and
stops them when traffic stops. Google Cloud Run will "scale to zero when idle to reduce costs"
([Cloud Run autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling)). The
cost of scaling to zero is the **cold start**, the extra time a request waits while a stopped
instance starts and loads its model. On AWS Lambda, "Cold starts typically occur in under 1% of
invocations. The duration of a cold start varies from under 100 ms to over 1 second," and "the
largest contributor of latency before function execution comes from initialization code"
([AWS Lambda execution environment](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html)).
For a model, initialization code means loading weights. Cloud Run lets you keep a minimum number
of instances warm "to avoid slow container start times", and those instances "do incur billing
costs" ([Cloud Run minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)).
The course clicker runs this way, as a Cloudflare Worker with a small database behind it.

:::{admonition} Definition: cold start
:class: tip
A **cold start** is the delay a request sees when no instance of a service is running and one has
to be started, its code imported and its model loaded, before the request can be answered.
:::

**A batch job.** If nobody is waiting for the answer, do not run a server. Score the whole table
on a schedule and write the predictions where the consumers already read, the same idempotent
stages you built in [Lecture 5](../l05/notes.md). AWS describes its batch service as the tool for
when you "don't need a persistent endpoint"
([SageMaker batch transform](https://docs.aws.amazon.com/sagemaker/latest/dg/batch-transform.html)).
Most engineering surrogates that feed a nightly report or a weekly design review belong here.

**The user's browser.** The model is shipped to the client and runs there, with no server at
all. The course-notes chat in [Lecture 18](../l18/notes.md) does this with WebGPU, and the
practice game does it with no "runtime network call of any kind" (CLAUDE.md). Serving costs
nothing and the user's data never leaves their machine. The limits are the user's hardware and
the first load: L18's chat needs about 1.6 GB of GPU memory, WebGPU "is available only on secure
(HTTPS) pages", and `chat/README.md` puts the first download of the weights "on the order of 15 to
20 minutes" at the speeds it measured. That is a cold start measured in minutes, paid once per
browser. Operator support also narrows: ONNX Runtime Web supports every operator on WebAssembly
"but only a subset are currently supported by WebGL, WebGPU and WebNN"
([ONNX Runtime Web](https://onnxruntime.ai/docs/tutorials/web/)).

| Where | Who waits for the answer | Who pays when idle | What the caller needs | In this course |
|---|---|---|---|---|
| In process | the calling code, microseconds | nobody | the same libraries and versions | DuckDB (L4) |
| Long-running service | a client over the network | you, always | an HTTP client and the contract | PostgreSQL (L3), the broker (L6) |
| Serverless | a client, plus a cold start sometimes | nobody, unless you keep instances warm | an HTTP client | the clicker |
| Batch | nobody; results are read later | nobody | the output table | pipeline stages (L5) |
| Browser | the user, after a first load | nobody | a capable browser | the notes chat (L18), the practice game |

The rest of these notes builds the second option, because it is the one with the most decisions
in it, and because a long-running service can be turned into the others: run it once over a
table and it is a batch job, put it on Cloud Run and it is serverless.

## The service contract

```{index} Pydantic, OpenAPI
```

A service is a promise to its callers about what they may send and what they will get back.
[Lecture 1](../l01/notes.md) introduced FastAPI as the tool that exposes "your model as an HTTP
endpoint with typed request and response schemas, which is also a data contract with your
callers." [Lecture 6](../l06/notes.md) defined a **data contract** as "the written-down shape of
the data." Here the contract is code. FastAPI reads the type annotations of each endpoint,
validates every request against them with Pydantic, and publishes the result as an
[OpenAPI](https://fastapi.tiangolo.com/tutorial/first-steps/) schema, so the same types serve as
the validation, the documentation and the client's specification.

The worked example is the five-network ensemble from [Lecture 14](../l14/notes.md), fitted to
the concrete strength dataset of [Lecture 9](../l09/notes.md): seven mix proportions and an age in
days in, a compressive strength in MPa out, with the ensemble's spread rescaled by one
calibration factor to give a 90% interval. The service is `service/app.py`, about 140 lines.

### Requests that cannot be wrong in the obvious ways

[Lecture 3](../l03/notes.md) made the point for database columns: "A typed column is still not
a validated column," because a type constrains the kind of value and says nothing about whether
it is possible. The same holds for a request. A float field accepts a cement content of −50
kg/m³. So the request model carries bounds:

```python
class Mix(BaseModel):
    cement: float = Field(gt=0, le=1000)     # kg per m3 of mixture
    slag: float = Field(ge=0, le=1000)
    water: float = Field(gt=0, le=1000)
    age_days: float = Field(ge=1, le=3650)
    # ... four more fields
```

When a request breaks a bound, FastAPI raises a `RequestValidationError` and answers with status
422 before your code runs
([FastAPI, Handling errors](https://fastapi.tiangolo.com/tutorial/handling-errors/)). Measured
against the running service, a mix with `cement = -50` returned:

```json
{"detail": [{"type": "greater_than", "loc": ["body", "cement"],
             "msg": "Input should be greater than 0", "input": -50.0, "ctx": {"gt": 0.0}}]}
```

The body names the field, the rule and the value, which is what a caller needs to fix the
request. Returning that, instead of a stack trace and a 500, is most of what "returning useful
errors" means.

These bounds reject the impossible. They should not reject the unusual. A mix with more slag
than any mix the model was trained on is a legitimate question with an unreliable answer, and
[Lecture 9](../l09/notes.md) showed what an unreliable answer looks like: outside its data, a tree
"stays flat at its last leaf." [Lecture 14](../l14/notes.md) added the harder lesson: when a
conformal interval failed on the strongest mixes, "The guarantee did not fail. Its condition was
not met." So the service answers such a request, and says it is out of domain. The manifest
stores the minimum and maximum of each feature over the training mixes, and the response flags
every feature outside that box.

### Responses that carry what the caller needs

```python
class Prediction(BaseModel):
    strength_mpa: float
    interval_90: tuple[float, float]
    in_domain: bool
    outside: list[str]
    model_version: str
```

Every field has a job. The interval is Lecture 14's whole argument: a design loop that sees only a
point estimate will trust it equally everywhere. The domain flag exists because the interval
alone does not warn you, and the service shows why. For a mix inside the training ranges the
ensemble predicted 48.3 MPa with a 90% interval of 30.0 to 66.6 MPa. Raising the slag to 400
kg/m³ and the age to 730 days, both outside the training data, gave 58.9 MPa with an interval of
41.8 to 76.0 MPa: a narrower interval, 34 MPa wide against 37, for the question the model knows
less about. The ensemble's members agree with each other off the data as readily as on it, so
only the explicit check catches it. The model version lets a caller who logs it find out later
which model produced a number.

FastAPI also validates the response. If your code returns data that does not fit the declared
type, "it means that your app code is broken, not returning what it should, and it will return a
server error instead of returning incorrect data"
([FastAPI, Response model](https://fastapi.tiangolo.com/tutorial/response-model/)). The same
filtering stops a field you did not mean to return, such as an internal path, from leaking out.

### Loading the model once

A common and expensive mistake is to load the model inside the request handler. FastAPI's
documentation uses this very case as its example of a **lifespan** handler: "Let's imagine that
loading the model can take quite some time, because it has to read a lot of data from disk. So
you don't want to do it for every request." Code before the `yield` "will be executed once,
before the application starts receiving requests"
([FastAPI, Lifespan events](https://fastapi.tiangolo.com/advanced/events/)). The older
`@app.on_event("startup")` decorator still appears in tutorials; the docs list it under
"Alternative Events (deprecated)".

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text())
    if sha256(MODEL_DIR / "ensemble.joblib") != manifest["sha256"]:
        raise RuntimeError("artifact does not match its manifest")
    if sklearn.__version__ != manifest["sklearn"]:
        raise RuntimeError("model saved with a different scikit-learn")
    STATE["nets"] = joblib.load(MODEL_DIR / "ensemble.joblib")
    yield
```

The two checks make the service refuse to start rather than serve a model nobody tested. On the
laptop that produced these notes, the process took 0.81 s from launch to its first ready
answer, and loading the model took 0.058 s of that. The other 93% was starting Python and
importing FastAPI, NumPy and scikit-learn. For a small model the cold start is mostly imports. For
a large one the load dominates, which is why the lifespan handler matters more as models grow.

Each worker process loads its own copy. FastAPI's deployment guide is direct about it: "if your
code loads a Machine Learning model with 1 GB in size, when you run one process with your API,
it will consume at least 1 GB of RAM. And if you start 4 processes (4 workers), each will consume
1 GB of RAM" ([FastAPI, Deployments concepts](https://fastapi.tiangolo.com/deployment/concepts/)).
Uvicorn's process manager "does not use pre-fork, but uses spawn"
([Uvicorn, Deployment](https://uvicorn.dev/deployment/)), so the workers do not share weights
loaded before they started. Measured here, one worker held 200 MB of resident memory and four
workers held 665 MB, though the model file is 46 kB: the interpreter and the libraries are
duplicated with the weights.

### def, async def, and a model that blocks

FastAPI accepts two kinds of endpoint function, and the choice matters for a model. "When you
declare a path operation function with normal `def` instead of `async def`, it is run in an
external threadpool that is then awaited, instead of being called directly (as it would block
the server)." An `async def` endpoint runs on the event loop itself, which is right for code that
spends its time waiting on the network and wrong for code that computes. The docs' advice for the
undecided is "If you just don't know, use normal `def`"
([FastAPI, Concurrency and async / await](https://fastapi.tiangolo.com/async/)).

The docs frame blocking as an I/O problem, and a CPU-bound `predict` blocks the loop in exactly
the same way, so the service measures it. It has the same 5,000-mix batch prediction behind two
endpoints, one written with `def` and one, deliberately, with `async def`. While four clients
sent those batches, a fifth asked `/healthz` every 50 ms. Against the `def` endpoint the health
check answered in 48 ms at the median and 80 ms at p95; against the `async def` endpoint, in 161
ms and 167 ms, and it got 19 answers in four seconds instead of 42 (Figure 2). With `async def`
every request, health checks included, waits for whole batches to finish. The `def` version is
not free, because the prediction threads still share Python's global interpreter lock, but the
server keeps answering.

```{figure} figures/stall.png
:alt: Horizontal bars of health-check latency. The def endpoint gives 48 ms at p50 and 80 ms at p95; the async def endpoint gives 161 ms and 167 ms.
:width: 80%

Figure 2. How long a health check waited while four clients sent 5,000-mix batches to the same
prediction code written as `def` and as `async def`. One uvicorn worker, measured on an Apple M4
Pro laptop by `figures/make_figures.py`.
```

### What to save, and how to load it

```{index} pair: failure mode; unsafe model deserialization
```

The service loads a scikit-learn ensemble saved with `joblib`, which is a pickle, and that
choice has two consequences you should make on purpose. First, scikit-learn's persistence page
lists pickle, joblib and cloudpickle with the same warning, "Loading can execute arbitrary code,"
and recommends `skops.io` as "More secure than pickle based formats" and ONNX as the "Most secure
option," with the caveat that "not all models are supported by ONNX"
([scikit-learn, Model persistence](https://scikit-learn.org/stable/model_persistence.html)). Load a
pickle only if you produced it, which is why the service checks the file's SHA-256 against the
manifest before it calls `joblib.load`. Second, the version lock quoted above means the artifact
and the environment travel together, which is why the manifest records the scikit-learn version
and the service refuses a mismatch.

PyTorch models have the same choice with more history. Saving the whole model object pickles a
reference to your class, and "the serialized data is bound to the specific classes and the exact
directory structure used when the model is saved"
([PyTorch, Saving and loading models](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html)),
so the standard practice is to save the `state_dict` and rebuild the module in code, as
[Lecture 12](../l12/notes.md)'s checkpoints do. `torch.load` warns "Never load data from an
untrusted source," and "Starting in version 2.6, torch.load will use weights_only=True if the
pickle_module argument is not passed"
([PyTorch, Serialization semantics](https://docs.pytorch.org/docs/2.15/notes/serialization.html)).
Older code that saved and loaded whole models now fails until someone opts into the unsafe path,
which is the intended effect. To ship a network without shipping Python at all, TorchScript was
the old answer and the PyTorch 2.10 documentation says "TorchScript is deprecated, please use
torch.export instead" ([PyTorch 2.10, TorchScript](https://docs.pytorch.org/docs/2.10/jit.html));
from 2.11 its reference page redirects elsewhere. The current route is
[`torch.export`](https://docs.pytorch.org/docs/2.15/user_guide/torch_compiler/export.html), or
ONNX, whose exporter with `dynamo=True` is "the recommended and default way to export models to
ONNX" ([PyTorch, ONNX](https://docs.pytorch.org/docs/2.15/onnx.html)).
[Lecture 13](../l13/notes.md) already listed ONNX as "a file format to export the trained
network", and [ONNX Runtime](https://onnxruntime.ai/docs/) runs such a file in Python, in other
languages, and in the browser.

Whatever the format, write a manifest next to it. [Lecture 2](../l02/notes.md) argued that "The
thing worth saving is the recipe that produced the model, more than the weights themselves," and
for a deterministic training run that is right. Building this service found the exception. The
script reproduced Lecture 14's ensemble with the same split, network and seeds, and its
calibration factor came out at 2.09 where Lecture 14 reports 1.66. Rerunning Lecture 14's own
script gives 2.09 as well. All five networks stop at the 5,000-iteration cap without converging,
so their final weights depend on floating-point details that a change of library build can move,
and the per-mix spreads differ from the earlier run by as much as half. With 2.09 the service's
intervals covered 95.9% of the test mixes, against the 90% they are meant to cover. The recipe
was saved and it did not reproduce the model. What does reproduce it is the artifact, with a
manifest that records the library versions, the data hash and the file's own hash, so that the
thing you tested and the thing you serve can be shown to be the same file.

### Training-serving skew

```{index} training-serving skew
```

```{index} pair: failure mode; training-serving skew
```

A model can be loaded correctly and still be fed the wrong thing. Google's
[Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml)
define **training-serving skew** as "a difference between performance during training and
performance during serving," caused by a difference in how data is handled in the two pipelines,
a change in the data between training and serving, or a feedback loop, and report "production
machine learning systems at Google with training-serving skew that negatively impacts
performance." Their remedies are the ones this course has met separately. Rule 29: "save the set
of features used at serving time, and then pipe those features to a log to use them at training
time." Rule 32: "Re-use code between your training pipeline and your serving pipeline whenever
possible."

:::{admonition} Definition: training-serving skew
:class: tip
**Training-serving skew** is a difference between a model's performance in training and in
serving, caused by the inputs being computed or distributed differently in the two.
:::

[Lecture 1](../l01/notes.md) named the commonest form, "a feature computed one way in training and
another way in serving." [Lecture 8](../l08/notes.md)'s `Pipeline` is the cure for one case of it:
the service saves the scaler with each network, so a request is standardized with the training
means and spreads and cannot be standardized any other way. [Lecture 7](../l07/notes.md)'s leakage
is another case: a feature that will not exist at request time, such as "the 2:03 PM reading" that
"has not happened yet," cannot be computed by the service at all. [Lecture 18](../l18/notes.md)
found the retrieval version, where "a query embedded with a different model from the index
silently ruins retrieval." The course's own chat avoids that one by embedding the index and the
query with the same runtime, because, as `chat/README.md` records, a Python embedding of the index
and a JavaScript embedding of the query "would disagree by enough to reorder close results."

## Packaging the service

```{index} Docker, image layer
```

A lockfile freezes your Python packages. [Lecture 2](../l02/notes.md) named the next step: "When
you need to freeze the entire stack down to the system libraries, the tool is a container, which
packages the operating-system (OS) layer as well." A **container image** is that frozen stack, a
stack of read-only filesystem layers with your code and environment on top of a base operating
system, and a Dockerfile is the script that builds it. You have run one already: L3's
`docker-compose.yml` started PostgreSQL from the `postgres:16` image. Here you build your own.

### A Dockerfile from the lockfile

The service's `Dockerfile` follows Astral's
[Using uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/) guide, and each line
exists to prevent a specific failure.

```dockerfile
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.3 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app.py ./
COPY model/ ./model/
ENV PATH="/app/.venv/bin:$PATH" MODEL_DIR=/app/model
USER app
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

The uv binary comes from Astral's own image at a pinned version; the guide recommends pinning
because tags can be moved. `uv sync --locked` installs exactly what `uv.lock` records and fails
the build if the lockfile has fallen out of step with `pyproject.toml`, which carries L2's
lockfile discipline into the image. The dependencies are installed before the code is copied, in
their own layer, because Docker's cache is strictly ordered: "Once a layer changes, then all
downstream layers need to be rebuilt as well"
([Docker, Build cache](https://docs.docker.com/build/cache/)). Measured here, a full build took
11.7 s with the base images already downloaded, and after an edit to `app.py` the rebuild took
2.9 s, because the
layer holding scikit-learn and NumPy came from the cache. `UV_COMPILE_BYTECODE` "tends to improve
startup time (at the cost of increased installation time and image size)."

The file has two stages. The first has uv and builds the virtual environment; the second starts
from a clean base and copies only that environment, the code and the model. Docker's own advice
is that "multi-stage builds let you reduce the size of your final image, by creating a cleaner
separation between the building of your image and the final output"
([Docker, Building best practices](https://docs.docker.com/build/building/best-practices/)). The
same page says "If a service can run without privileges, use USER to change to a non-root user,"
and the running container reported its user as `app`. The `CMD` is in exec form, a JSON list,
which FastAPI's container guide asks for "to ensure that FastAPI can shutdown gracefully and
lifespan events are triggered" ([FastAPI in containers](https://fastapi.tiangolo.com/deployment/docker/)).
In shell form the server runs under `/bin/sh`, which does not pass on the stop signal. A
`.dockerignore` keeps the local `.venv` out of the build context.

Two documented sources disagree about the install step. FastAPI's container page exports a
`requirements.txt` with uv and installs it with pip; uv's own guide runs `uv sync` inside the
image. These notes use the second, because it keeps one lockfile as the only description of the
environment, and a second exported file is a second thing that can drift from it. Both work.
FastAPI's page also settles a question older tutorials answer differently: its official
Gunicorn-based image "is now deprecated," Uvicorn's `--workers` replaces it, and under an
orchestrator such as Kubernetes you "would want to have a single (Uvicorn) process per container"
and let the orchestrator run more containers.

:::{admonition} A note on this build
:class: note
The machine that measured these numbers runs Docker without BuildKit, which the `--mount` lines
need, so `make_figures.py` built an equivalent image with plain `COPY` of the two files in place
of the mounts. The final stage copies only `.venv`, so the image is the same. With Docker
Desktop, or with the `buildx` plugin, the committed Dockerfile builds as written.
:::

### Image size, and the GPU you do not need

The finished image is 126 MB compressed, which is what a machine downloads to start it, on a 44 MB
`python:3.12-slim` base; unpacked on disk it is 461 MB, on a 160 MB base (arm64, as Docker's
containerd image store reports them). It holds FastAPI, uvicorn, NumPy, scikit-learn and a 46 kB model. Figure 3 puts that next
to what a deep-learning image weighs.

```{figure} figures/images.png
:alt: Horizontal bars on a log scale. Measured: python 3.12 slim 44 MB and this service 126 MB. Cited: torch CPU wheel 210 MB, torch Linux wheel 539 MB before its CUDA libraries, nvidia cuda runtime 2,160 MB, pytorch runtime 3,290 MB, pytorch devel 13,850 MB.
:width: 95%

Figure 3. Image and package sizes, compressed. Red bars were measured for this service (arm64);
grey bars are cited from Docker Hub (compressed size, amd64) and from the PyPI and download.pytorch.org file
listings, all read on 2026-11-04. These numbers change with every release.
```

The large numbers are mostly CUDA. The Linux `torch` 2.15.0 wheel on PyPI is 539 MB, and it
depends on NVIDIA's libraries, of which cuDNN alone is another 519 MB. The CPU-only wheel from
download.pytorch.org is about 210 MB. uv's
[PyTorch guide](https://docs.astral.sh/uv/guides/integration/pytorch/) explains why the default
surprises people: PyPI hosts "CPU-only wheels for Windows and macOS, and GPU-accelerated wheels on
Linux," so a plain `uv add torch` that is small on your Mac is large in a Linux container. The
guide shows how to point `torch` at the CPU index in `pyproject.toml`. The base images follow the
same pattern: `nvidia/cuda`'s runtime image is 2.2 GB and `pytorch/pytorch`'s development image is
13.9 GB, against 43 MB for `python:3.12-slim`, as Docker Hub listed them on the day these notes
were written.

Size is a deployment cost three times over. Every node that starts the service downloads the
image, which is a cold start; registries and nodes store it; and AWS Lambda refuses any image
over "10 GB (maximum uncompressed image size, including all layers)"
([Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)), which
rules out the largest images above. [Lecture 11](../l11/notes.md) already gave the deciding
question, whether the model needs a GPU at all: "A GPU is a throughput device with a large fixed
cost per kernel launch," and "For a model the size of this session's, the CPU is the correct
choice." Many engineering surrogates, this one included, are that size.

### Configuration and secrets

```{index} secret, twelve-factor app
```

```{index} pair: failure mode; secret in an image layer
```

A **secret** is any value that grants access: an API key, a database password, a signing key.
Earlier lectures used them without saying how to handle them, so this section is the course's
first treatment. The rule comes from the [Twelve-Factor App](https://12factor.net/config):
configuration that varies between deployments, secrets included, lives in the environment, and
"A litmus test for whether an app has all config correctly factored out of the code is whether
the codebase could be made open source at any moment, without compromising any credentials."

Containers add a trap. Docker's documentation says "Build arguments and environment variables are
inappropriate for passing secrets to your build, because they persist in the final image"
([Docker, Build secrets](https://docs.docker.com/build/building/secrets/)), and that build
arguments "are visible in the docker history command"
([Dockerfile reference](https://docs.docker.com/reference/dockerfile/)). The figure script tested
both claims with a fake key. A build that passed `API_KEY` as a build argument showed it in
`docker history --no-trunc`, on the line `|1 API_KEY=demo-not-a-real-key-7f3a /bin/sh -c rm
/app/key.txt`. The same build copied a key file into the image and deleted it in the next step.
The file was gone from the running container, and it was still present, readable, in the earlier
layer of the saved image. Layers are immutable, and "Each layer in an image contains a set of
filesystem changes" ([Docker, Image layers](https://docs.docker.com/get-started/docker-concepts/building-images/understanding-image-layers/)),
so deleting a file adds a layer that hides it and removes nothing.

The fixes are simple. Pass build-time secrets with `RUN --mount=type=secret`, which exposes them
to one step and writes them to no layer. Pass runtime secrets as environment variables or files
supplied when the container starts, never baked in. And if a secret does reach a repository or an
image, GitHub's advice is to "rotate the affected credential immediately," because removing it
from history "is time-intensive and often unnecessary if you've already revoked the credential"
([GitHub, Secret scanning](https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning)).

The course has all three patterns in its own files. L3's `docker-compose.yml` puts the password
`demo` in plain text, with the comment "These credentials are for a local teaching database only;
do not reuse them," which is acceptable for a database on your laptop and nowhere else. The plant
stream's publisher password "is generated on the Pi into `/etc/tep-stream/publisher.secret`, mode
640, root:tepstream, and never goes near the repository" (`stream/README.md`). And the practice
game's signing key reaches the build as a GitHub Actions secret, with a check that refuses to
publish a build that fell back to the development key.

### Health checks

```{index} health check, liveness probe, readiness probe
```

A process that is running is not necessarily a process that can answer. L3's compose file already
asks PostgreSQL the real question, with `pg_isready` every five seconds, rather than checking that
the container exists. Docker's `HEALTHCHECK` instruction exists because a server can be "stuck in
an infinite loop and unable to handle new connections, even though the server process is still
running" ([Dockerfile reference](https://docs.docker.com/reference/dockerfile/)). The service's
image declares one, and within 12 s of starting Docker reported the container `healthy`.

Kubernetes splits the question in two, and the split is the useful idea even if you never run
Kubernetes ([Kubernetes, Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)).
"Liveness probes determine when to restart a container," for example to catch "a deadlock, where
an application is running, but unable to make progress." "Readiness probes determine when a
container is ready to accept traffic," which "is useful when waiting for an application to perform
time-consuming initial tasks, such as establishing network connections, loading files, and warming
caches." A container that fails readiness is taken out of the load balancer and left running; one
that fails liveness is restarted. A third, the startup probe, holds off both until a slow start
has finished. The service mirrors the split with `/healthz`, which answers if the process is
alive, and `/readyz`, which answers only when the model is loaded and returns its version. With
FastAPI's lifespan handler the server does not accept connections at all until the model is
loaded, so readiness earns its keep later: a service whose database or downstream model is
unavailable, or that is shutting down, should report not ready while staying alive.

:::{admonition} Definition: readiness probe
:class: tip
A **readiness probe** asks whether an instance can serve requests now, for example whether its
model is loaded; failing it removes the instance from traffic without restarting it.
:::

The docs add a warning that is easy to miss: "Incorrect implementation of liveness probes can lead
to cascading failures." A liveness check that calls the model, or a database, will fail when that
dependency is slow, and an orchestrator that then restarts every instance at once turns a slow
dependency into an outage. Keep liveness trivial and put the dependency checks in readiness.

## Latency, throughput and capacity

```{index} latency, throughput, tail latency
```

**Latency** is how long one request takes, from the caller's point of view. **Throughput** is how
many requests the service completes per second. They are related, and the relation is the subject
of this section, but they are different numbers, and a service can have excellent throughput and
unacceptable latency at the same time.

### Report percentiles

Latency is a distribution, and its mean hides the part users notice. Google's SRE book puts it
this way: "We generally prefer to work with percentiles rather than the mean (arithmetic average)
of a set of values. Doing so makes it possible to consider the long tail of data points," and "a
high-order percentile, such as the 99th or 99.9th, shows you a plausible worst-case value"
([SRE book, Service level objectives](https://sre.google/sre-book/service-level-objectives/)). The
p50 is the median request; the p95 is the latency that 95% of requests beat; the p99 is where the
slowest one in a hundred begins.

[Lecture 11](../l11/notes.md) timed GPU kernels and reported "the *minimum* over repeated trials
rather than the mean," and that was right for its purpose, which was to measure how fast the
computation can go with interference removed. A service is judged on the opposite question: how
slow it gets for the requests that meet the interference. Report a percentile, and report the
concurrency it was measured at, because the same service has a different p95 under every load.

:::{admonition} Definition: tail latency
:class: tip
**Tail latency** is the latency of the slowest requests, reported as a high percentile such as the
p95 or p99, which is what a user waiting on a slow request experiences.
:::

### The tail at scale

```{index} hedged request
```

The tail matters more than intuition suggests because requests fan out. Dean and Barroso's
[The Tail at Scale](https://www.barroso.org/publications/TheTailAtScale.pdf) (CACM 2013, author's
copy) gives the arithmetic: "consider a system where each server typically responds in 10ms but
with a 99th-percentile latency of one second. If a user request is handled on just one such
server, one user request in 100 will be slow." If it must wait for 100 such servers, "63% of user
requests will take more than one second," which is $1 - 0.99^{100}$. Figure 4 draws the curve.
A real Google service in the paper shows the effect: "The 99th-percentile latency for a single
random request to finish, measured at the root, is 10ms. However, the 99th-percentile latency for
all requests to finish is 140ms."

```{figure} figures/fanout.png
:alt: Share of requests that are slow against the number of servers each request waits for, on a log axis. With each server slow one time in 100, 100 servers give 63 percent; with each slow one time in 10,000, 2,000 servers give 18 percent.
:width: 85%

Figure 4. If each of $n$ servers is slow with probability $p$, a request that waits for all of
them is slow with probability $1-(1-p)^n$. The marked points are Dean and Barroso's two examples.
Computed in `figures/make_figures.py`.
```

The paper's remedy is to send a second copy of a slow request. "Issue the same request to multiple
replicas and use the results from whichever replica responds first. We term such requests 'hedged
requests'." Sending the hedge only after a 10 ms delay "reduces the 99.9th-percentile latency for
retrieving all 1,000 values from 1,800ms to 74ms while sending just 2% more requests." Engineering
pipelines fan out too. [Lecture 18](../l18/notes.md)'s retrieval pipeline runs a search,
then a re-ranker that cost "a thousand times the cost of the search itself," then a language
model; the request is as slow as the sum of its stages, and as unlucky as its unluckiest one.

### Little's law and saturation

```{index} Little's law, utilization
```

One identity connects the three numbers you can measure. **Little's law** states that "under
steady state conditions, the average number of items in a queuing system equals the average rate
at which items arrive multiplied by the average time that an item spends in the system"
([Little and Graves, 2008](https://www.ic.unicamp.br/~nfonseca/MO648/doc/Little%27s%20Law-Published.pdf),
a course mirror of the book chapter), written $L = \lambda W$. It holds for any queue in steady
state, whatever the distributions, which makes it a check on any load test: the concurrency,
divided by the throughput, should equal the mean latency.

:::{admonition} Definition: Little's law
:class: tip
**Little's law** says that in steady state the average number of requests in a system equals their
arrival rate times the average time each one spends there, $L = \lambda W$.
:::

The service's load test passes that check at every level. With 8 clients each sending a request,
waiting for the answer and sending the next, one worker completed 1,799 requests per second at a
mean latency of 4.43 ms, and $1799 \times 0.00443 = 7.97$, the 8 clients. NVIDIA's documentation
for its inference server gives numbers that pass the same check: at 8 concurrent requests and 272
inferences per second, the mean latency must be about 29 ms, and the reported p95 is 36 ms
([Triton, Optimization](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/optimization.html)).

Figure 5 shows what happens as load grows. One worker's throughput rose from 1,144 requests per
second with one client to about 1,730 with four, and then stopped rising, staying between 1,730
and 1,830. Every client added after
that waited in a queue: from 8 to 16 to 32 clients the median latency went from 4.4 to 8.7 to 17.1
ms, doubling with the clients, while throughput stayed flat. Little's law says it must, because
with throughput fixed at the service's capacity $X$, the latency of $N$ clients is $W = N/X$.
Four workers lifted the ceiling to between 2,560 and 3,140 requests per second. That curve is
noisier, because at 32 clients the client processes and the server workers compete for the
laptop's 14 cores.

```{figure} figures/latency.png
:alt: Left, p50 and p95 latency against concurrent clients for one and four workers; one worker's p50 doubles from 4.4 to 17.1 ms between 8 and 32 clients. Right, throughput: one worker flattens at about 1,800 requests per second from 4 clients, four workers reach between 2,560 and 3,140.
:width: 100%

Figure 5. The concrete strength service under closed-loop load, one mix per request, client and
server on the same Apple M4 Pro laptop, one process per client. Latency is a floor: a real network
adds to every point. Measured by `figures/make_figures.py`.
```

Measuring this was itself instructive. The first version of the load test drove every client from
one Python process, and its throughput fell from about 1,570 to 321 requests per second between 8
and 32 clients, with a p95 of 327 ms. Four server workers did not change that (319 requests per
second), which put the limit
in the load generator. Running one process per client gave Figure 5. [Lecture 5](../l05/notes.md)
warned that "A benchmark measures one workload on one machine"; a load test also measures the
machine that sends the load.

Queueing theory explains why services are not run near their capacity. For the simplest queue, the
M/M/1, the mean time in the system is $T = 1/(\mu - \lambda)$, with service rate $\mu$ and arrival
rate $\lambda$ ([Bertsekas and Gallager, *Data Networks*, ch. 3](https://web.mit.edu/dimitrib/www/Queueing_Data_Nets.pdf),
eq. 3.26, free from the author). Divided by the service time $1/\mu$ it is $1/(1-\rho)$, where
$\rho = \lambda/\mu$ is the **utilization**. At 50% utilization a request spends twice its
service time in the system; at 90%, ten times; at 95%, twenty (Figure 6). Variability in the
service time makes it worse, which is what the Pollaczek-Khinchine formula in the same chapter
adds. The counterintuitive corollary appears in Harchol-Balter's
[*Performance Modeling and Design of Computer Systems*](https://www.cs.cmu.edu/~harchol/PerformanceModeling/chpt1.pdf)
(chapter 1, CMU): when the arrival rate doubles, keeping the same mean response time takes a server
that is "Less than double" as fast.

```{figure} figures/saturation.png
:alt: Time in system divided by service time against utilization, rising from 1 at zero utilization to 2 at 50 percent, 5 at 80 percent, 10 at 90 percent and 20 at 95 percent.
:width: 80%

Figure 6. Mean time in an M/M/1 queue, in units of the service time, against utilization,
$1/(1-\rho)$. Computed in `figures/make_figures.py`.
```

When arrivals exceed capacity anyway, the service should say so rather than queue without limit.
[Lecture 6](../l06/notes.md)'s backpressure is the principle: a pipeline "signals upstream to slow
down rather than silently dropping data or exhausting memory." Over HTTP the signals are status
429 (too many requests) and 503 (unavailable), and a client that receives one should back off, as
the cost section describes.

### Batching

```{index} dynamic batching
```

Each request pays a fixed overhead before the model does any work: parsing, validation, routing,
the network. Batching amortizes it, and you have met the trade four times already. L3's loader
was slow because it sent "two million separate statements, each a round trip to the server with
its own transaction overhead" until `COPY` sent them at once. L5's vectorized comparison ran over
a whole column in 0.2 ms. [Lecture 15](../l15/notes.md) chose four experiments at once, `q=4`,
because the lab had four reactors.

The service has both endpoints, so the trade can be measured (Figure 7). One mix per request cost
0.89 ms per prediction. A request carrying 10 mixes took 0.93 ms, so 93 µs each; 100 mixes,
16 µs each; 1,000 mixes, 9.1 µs each. A thousand-mix batch is a hundred times cheaper per
prediction, because almost all of a single request's cost was overhead and not the five small
networks. The same arithmetic decides how a design loop should call a surrogate. An optimizer
that asks one point at a time pays the overhead on every point; one that can propose candidates
in batches, as L15's batch acquisition does, pays it once per batch.

```{figure} figures/batching.png
:alt: Time per prediction against mixes per request on log axes, falling from 890 microseconds for one mix to 93 for 10, 16 for 100 and 9 for 1,000.
:width: 80%

Figure 7. Time per prediction against mixes per request, one client, one worker. Measured by
`figures/make_figures.py`.
```

Batching costs latency, because a request that waits to be grouped with others waits. Inference
servers make that trade explicit. NVIDIA Triton's **dynamic batching** combines requests on the
server, and its documentation tells you to "trade off increased latency for increased throughput"
by raising the maximum batch size or setting a nonzero batch delay, `max_queue_delay_microseconds`
([Triton, Dynamic batcher](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/batcher.html)).
Its own example goes from about 73 inferences per second without batching to 272 with it, "without
increasing latency," which is NVIDIA's measurement of NVIDIA's server and should be read as an
illustration.

### Language models

```{index} time to first token, server-sent events, continuous batching
```

A language model changes which latency matters. The user watches the answer appear, so the first
number is the **time to first token**, which Anthropic's documentation defines as "the time it
takes for the model to generate the first token of the response, from when the prompt was sent"
([Anthropic, Reducing latency](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency)).
The second is the inter-token latency, "the average time between consecutive tokens"
([NVIDIA NIM, Metrics](https://docs.nvidia.com/nim/benchmarking/llm/metrics)). Total latency is
roughly the first plus the second times the number of tokens generated, so output length
dominates: "cutting 50% of your output tokens may cut ~50% of your latency"
([OpenAI, Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization)).
[Lecture 17](../l17/notes.md) put the same point in budget terms: "Cost and time are counted in
tokens."

Streaming sends tokens as they are generated, usually over **server-sent events**, an HTTP
response that stays open and delivers a sequence of `text/event-stream` messages
([WHATWG HTML, Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)).
Anthropic's API streams this way
([Streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)). MDN notes two
limits: the connection is one-way, and without HTTP/2 a browser allows only "a very low number (6)"
of them per site
([MDN, Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)).
Streaming changes what the user sees, not the total work: the last token arrives no sooner.

Serving a language model yourself is dominated by batching. Generating one token at a time is
memory-bound, and the vLLM paper states the consequence: the sequential process "underutilizing
the computation power of GPUs and limiting the serving throughput. Improving the throughput is
possible by batching multiple requests together." It found that existing systems used only "20.4%
- 38.2%" of their key-value cache memory for actual token state, and vLLM's paged memory improved
throughput "by 2-4× with the same level of latency" ([Kwon et al., 2023](https://arxiv.org/pdf/2309.06180)).
Orca introduced scheduling at the level of single generation steps, now called **continuous
batching**, and reported "36.9× throughput improvement at the same level of latency" for GPT-3 175B
against FasterTransformer ([Yu et al., OSDI 2022](https://www.usenix.org/conference/osdi22/presentation/yu)).

### What latency costs, and the numbers that circulate

Two numbers about the business cost of latency appear in nearly every talk on the subject: that
Amazon found every 100 ms of latency cost 1% of sales, and that Google found an extra 500 ms cost
20% of traffic. Following them to their sources changes both.

The Google figure comes from Greg Linden's 2006 report of a talk by Marissa Mayer. Users had asked
for 30 results per page instead of 10; Google tried it, and traffic fell. "The page with 10
results took .4 seconds to generate. The page with 30 results took .9 seconds. Half a second delay
caused a 20% drop in traffic" ([Linden, 2006](https://glinden.blogspot.com/2006/11/marissa-mayer-at-web-20.html)).
The experiment changed the number of results, and latency was the explanation offered afterwards
for its outcome. The Amazon figure has an even thinner source. It appears as one bullet on a slide
from Linden's 2006 Stanford talk, "+100 ms @ Amazon -1% sales," with no method, no sample size and
no word "every" ([slides, linked from Linden's blog](https://glinden.blogspot.com/2006/12/slides-from-my-talk-at-stanford.html)).
Kohavi and colleagues' 2007 guide to controlled experiments cited that slide, and turned Google's
"traffic" into "revenues" ([Kohavi et al., KDD 2007](https://exp-platform.com/Documents/GuideControlledExperiments.pdf)),
and the versions in circulation descend from there.

Google later ran the controlled experiment. Injecting delays into search for a sample of users,
Brutlag found that "increasing web search latency 100 to 400 ms reduces the daily number of
searches per user by 0.2% to 0.6%," and that 50 ms had no measurable effect
([Brutlag, Google, 2009](https://services.google.com/fh/files/blogs/google_delayexp.pdf)). Per
millisecond, that is twenty to thirty times smaller than the 500 ms story, measured on the same
search engine with a controlled design. It measured searches per user, not sales, so it neither
confirms nor refutes the Amazon bullet, whose experiment the slide does not describe. Latency costs something
measurable; the circulating numbers are not the measurement.

:::{admonition} What a practitioner should take from this
:class: tip
When a latency target is justified by "every 100 ms costs 1%", ask for the experiment. For an
interactive tool, the defensible target comes from your own users or from a controlled study like
Brutlag's. For a surrogate inside a design loop, it comes from arithmetic you can do yourself: the
number of calls the optimizer makes times the latency per call, against how long the engineer is
willing to wait. This is the same habit as checking [Lecture 1](../l01/notes.md)'s "10% of the
code" figure, which turned out not to be in the paper it is attributed to.
:::

## Cost

```{index} cost per request, exponential backoff, retry storm
```

Cost per request is the price of whatever is doing the work, divided by how much work it does.
For a CPU service, the measured capacity gives the second number directly. One worker
process sustained about 1,800 single-mix requests per second here, which is about 6.5 million
predictions per core-hour; with 1,000-mix batches at 9.1 µs per prediction, it is about 400
million. Multiply by whatever a core-hour costs on your platform and you have a cost per
prediction, and the factor of sixty between the two shows that the request pattern matters more
than the hardware price. Two adjustments come from earlier lectures. An ensemble of $M$ models
costs $M$ times one model, as [Lecture 14](../l14/notes.md) said of training and evaluation alike,
which is the serving argument for its cheaper alternatives. And idle time is paid for unless the
platform scales to zero, in which case the cold start is the price.

For a hosted language model, cost is metered in tokens, and input and output tokens are priced
separately. On 2026-11-04 Anthropic's pricing page listed Claude Sonnet 5.5 at $2 per million input
tokens and $10 per million output tokens, with output five times the input price for every model
shown ([Anthropic, Pricing](https://platform.claude.com/docs/en/about-claude/pricing)). An answer
built like L18's, with 3,000 tokens of retrieved context and a 300-token reply, costs
$3000 \times 2/10^6 + 300 \times 10/10^6 = \$0.009$, nine dollars per thousand answers. The same
page lists a Batch API with "a 50 percent discount on both input and output tokens" for work that
can wait, and prompt caching, where a cache write costs 1.25 times the base input price and a read
a fraction of it, which pays "after one cache read for the 5-minute duration"
([Anthropic, Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)).
Prices change; read the page on the day you estimate, and record the date with the estimate.

The cost that surprises people is the one they add themselves, through retries. Marc Brooker's
article for the Amazon Builders' Library starts from the observation that "Retries are 'selfish.'
In other words, when a client retries, it spends more of the server's time to get a higher chance
of success," and that when a system is overloaded "retries can make the overload worse instead of
better." Layers multiply it: "a five-deep stack of service calls" with three attempts at each
layer increases the load on the database "243x," so "our best practice is to retry at a single
point in the stack"
([Brooker, Timeouts, retries, and backoff with jitter](https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter)).
A **retry storm** is that amplification in action, a slow service receiving several times its
normal load from clients that are trying to help. The remedies are a timeout on every call, a cap
on retries, and **exponential backoff** with randomness added so that clients that failed together
do not retry together: "The solution isn't to remove backoff. It's to add jitter"
([Brooker, Exponential backoff and jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)).
A retry is only safe if the request is: "APIs with side effects aren't safe to retry unless they
provide idempotency." [Lecture 5](../l05/notes.md) defined a stage as idempotent "when running it
twice has the same effect as running it once," and [Lecture 6](../l06/notes.md) told you to "Assume
at-least-once." A prediction endpoint is idempotent by nature. An endpoint that writes a result,
places an order, or starts an experiment is not, unless you make it so.

The clicker that runs during these lectures is a small worked example of cost against a limit. Its
README budgets "a 40-person class near 24k requests a session against a 100k/day budget," the
free tier of the platform it runs on, so a class of 160 would come within a few percent of it in one
session.

## Releasing changes safely

```{index} canary release, staged rollout, rollback, service level objective, error budget, postmortem
```

```{index} see: SLO; service level objective
```

Each of the incidents below started with a change. They are useful because each failed in a
specific, general way, and each maps onto something you will plausibly deploy. They are told from
the organizations' own postmortems; a **postmortem**, in the SRE book's definition, is "a written
record of an incident, its impact, the actions taken to mitigate or resolve it, the root cause(s),
and the follow-up actions to prevent the incident from recurring," written to identify causes
"without indicting any individual or team"
([SRE book, Postmortem culture](https://sre.google/sre-book/postmortem-culture/)).

### Every change is a deploy: CrowdStrike, 19 July 2024

```{index} pair: case study; CrowdStrike outage
```

At 04:09 UTC on 19 July 2024 CrowdStrike "released a content configuration update for the Windows
sensor," a data file read by the existing program, with no new code. Its root-cause analysis gives the
mechanism: "The new IPC Template Type defined 21 input parameter fields, but the integration code
that invoked the Content Interpreter with Channel File 291's Template Instances supplied only 20
input values," and the result was an out-of-bounds memory read in the sensor on every machine that took the
update. Tests had used a wildcard for the 21st field, so they never exercised the mismatch.
The update was reverted 78 minutes after release, and among the remedies is that "Each Template
Instance should be deployed in a staged rollout"
([CrowdStrike, Root cause analysis](https://www.crowdstrike.com/wp-content/uploads/2024/08/Channel-File-291-Incident-Root-Cause-Analysis-08.06.2024.pdf)).
The widely quoted figure of 8.5 million machines is Microsoft's estimate, "less than one percent of
all Windows machines"
([Microsoft, 20 July 2024](https://blogs.microsoft.com/blog/2024/07/20/helping-our-customers-through-the-crowdstrike-outage/)),
not a number from CrowdStrike's reports.

:::{admonition} What a practitioner should take from this
:class: tip
A new set of model weights, a new feature schema, or a new calibration factor is a content update
in exactly this sense: data that changes what running code does. It needs the same staged release
as code. Test the interface between the new content and the code that consumes it with real
values, since a wildcard or a default in the test is where CrowdStrike's mismatch hid, and make the
consumer reject malformed input, as the service's manifest check rejects an artifact that does not
match.
:::

### Canaries, staged rollouts and error budgets

A **canary** release, in the SRE workbook's definition, is "a partial and time-limited deployment
of a change in a service and its evaluation. This evaluation helps us decide whether or not to
proceed with the rollout" ([SRE workbook, Canarying releases](https://sre.google/workbook/canarying-releases/)).
A **staged rollout** repeats that in widening rings: a few percent of traffic, then more, then all,
with a check at each step and a **rollback**, a return to the previous version, if the check fails.
[Lecture 1](../l01/notes.md) promised exactly this: "staged rollout so a bad model does not reach
everyone at once, and the ability to roll back."

:::{admonition} Definition: canary release
:class: tip
A **canary release** sends a change to a small, time-limited share of traffic and compares it with
the current version before deciding whether to roll it out further.
:::

The check needs a number. The SRE book defines a service level indicator as "a carefully defined
quantitative measure of some aspect of the level of service," such as the p95 latency or the share
of requests that succeed, and a **service level objective** as "a target value or range of values
for a service level that is measured by an SLI" ([SRE book, Service level objectives](https://sre.google/sre-book/service-level-objectives/)).
The **error budget** is the failure the objective allows: an SLO of 99.999% of queries served per
quarter "means that the service's error budget is a failure rate of 0.001%," and the budget
"determines how unreliable the service is allowed to be within a single quarter"
([SRE book, Embracing risk](https://sre.google/sre-book/embracing-risk/)). A canary that spends the
budget faster than the old version is rolled back. The same chapter gives the argument against
chasing nines: "a user on a 99% reliable smartphone cannot tell the difference between 99.99% and
99.999% service reliability!"

### Verify what is running: Knight Capital, and this website

```{index} pair: case study; Knight Capital
```

Knight's deployment failed at the step after the code was written: the new version reached seven of
eight servers, nobody checked the eighth, and the rollback removed the new code from the seven
servers that were behaving correctly, which "worsened the problem" (SEC order). A deploy is
complete when you have confirmed, on every instance, that the artifact you tested is the one
running, and a rollback is a change that deserves the same understanding as the release it undoes.
The 97 warning emails are the other failure: they reached a group of staff before the open, as
messages nobody had designed to be alerts or was expected to read.

This website applies the first lesson to itself. After the August 2026 failure, every build writes
a file, `build-info.json`, recording the commit it was built from, and a final job fetches that file
from the live site and fails unless it names the commit just built. Two details in that job came
from getting it wrong first. It polls for about three minutes, because "Pages reports success
slightly before the CDN serves the new build, so poll rather than fetching once," and it adds a
cache-busting query string, so that a cache cannot answer with the old file. CLAUDE.md records the
principle in two sentences: "*The run is green.* That does not tell you the site updated," and "*The
page returns 200.* That does not tell you it rendered." For a model service the equivalent is
`/readyz` returning the model version, checked against the version you meant to deploy, from
outside the service. Running the tests against your own function and never against the deployed
endpoint misses every bug in serialization, configuration and the network.

### Backups you have restored: GitLab, 31 January 2017

```{index} pair: case study; GitLab database outage
```

[Lecture 3](../l03/notes.md) described PostgreSQL as a server you must "back up." GitLab's
postmortem is the case for testing that you can restore. During an incident involving replication
lag, an engineer ran a command meant for the secondary database server on the primary: "The engineer
terminated the process a second or two after noticing their mistake, but at this point around 300 GB
of data had already been removed." Then the backups failed in turn. "The backup procedure was using
pg_dump 9.2, while our database is running PostgreSQL 9.6," so the backups were not being made;
the failure notices went by email and were rejected, so "we were never aware of the backups failing,
until it was too late"; and disk snapshots were not enabled. GitLab restored from a snapshot an
engineer happened to have taken six hours earlier and lost "roughly 5,000 projects, 5,000 comments
and 700 new user accounts," with the site down for about 18 hours. Asked why the backups were not
tested, the postmortem answers: "Because there was no ownership"
([GitLab, Postmortem](https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/)).
A line often attributed to this incident, that five of five backup methods failed, does not appear
in the postmortem; it comes from posts made on the day.

:::{admonition} What a practitioner should take from this
:class: tip
Treat a backup you have never restored as untested. Schedule restores, time them, and alert on a backup that
did not appear as well as on one that reported an error, because GitLab's errors were reported to an
inbox that rejected them. The `pg_dump` version mismatch is the same kind of failure as the service's
scikit-learn check: two components that must agree on a version, and nothing checking that they do.
:::

### Tools that enforce invariants: AWS S3, 28 February 2017

```{index} pair: case study; AWS S3 outage
```

An engineer running "an established playbook executed a command which was intended to remove a small
number of servers," and "one of the inputs to the command was entered incorrectly and a larger set of
servers was removed than intended." The servers removed supported two subsystems that every S3 request
in the region depends on, both needed "a full restart," and AWS had "not completely restarted the
index subsystem or the placement subsystem in our larger regions for many years," so nobody knew how
long it would take; it took about four hours. The status dashboard depended on S3 and could not be
updated. The fix put the invariant in the tool: "We have modified this tool to remove capacity more
slowly and added safeguards to prevent capacity from being removed when it will take any subsystem
below its minimum required capacity level" ([AWS, Summary of the S3 service disruption](https://aws.amazon.com/message/41926/)).
For a model service the analogue is a deploy script that refuses to take the last ready instance out
of service, and a monitoring page that does not run on the system it monitors.

### A fast global channel: Cloudflare, 2 July 2019

```{index} pair: case study; Cloudflare outage
```

"An engineer working on the firewall team deployed a minor change to the rules for XSS detection via
an automatic process," through a system that "can push changes globally in seconds." The new rule
contained "a regular expression that backtracked enormously and exhausted CPU used for HTTP/HTTPS
serving," and Cloudflare's network was down for 27 minutes. The postmortem lists the contributing
causes in its own words, among them that "A protection that would have helped prevent excessive CPU
use by a regular expression was removed by mistake during a refactoring of the WAF weeks prior," and
that "The SOP allowed a non-emergency rule change to go globally into production without a staged
rollout." The rule had been deployed in simulate mode, which records what it would have done, and
simulate mode still runs the rule, so it still spent the CPU
([Cloudflare, Details of the outage](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/)).
A shadow deployment of a model, scoring live traffic without acting on it, has the same property: it
costs what the model costs, on the machines serving real traffic.

### Small incidents from this course

The course's own services have failed in small ways, each documented in its README, and each is the
kind of thing you will meet in your first deployment. The plant stream's message broker would not
start because "Debian's `mosquitto` package is built without WebSocket support," and its log said
"`Unable to start any listening sockets`," which names the symptom and not the cause. The proxy in
front of it would have cut every connection during a simulated outage, because nginx's default
`proxy_read_timeout` is 60 seconds; the configuration sets 3600. The broker's version is pinned,
because an unattended upgrade mid-semester could change how it authenticates students. The clicker's
README records that "Forgetting `--remote` is the classic D1 mistake," after which every vote failed
with "no such table," and that a new hostname has "no certificate for the first minute or several."
Each was found by running the real service on the real network, and none would have shown up on a
laptop.

## Limitations and trade-offs

**You often do not need a service.** If the caller is your own pipeline, import the model. If nobody
waits for the answer, run a batch job. A service adds a process to keep alive, a contract to version,
a port to secure and a bill that arrives whether or not anyone calls it. [Lecture 5](../l05/notes.md)'s
advice applies: "Exhaust one good machine before adding a cluster."

**FastAPI is a request router.** It is good at validating requests, routing them and documenting the
contract. It is a poor place for long computation: its own documentation sends "heavy background
computation" to "bigger tools like Celery"
([FastAPI, Background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)). CPU-bound
Python shares one interpreter lock per process, so throughput scales with processes, and each process
holds its own copy of the model.

**Dedicated inference servers earn their place at scale.** Triton batches requests across clients and
manages GPU memory; vLLM does the same for language models with paged attention and continuous
batching. Both add a system to learn and run, and for a small surrogate on a CPU they add nothing a
FastAPI service with a batch endpoint does not already do.

**Orchestration has weight.** Kubernetes gives you probes, replicas, rolling updates and rollbacks,
and asks for a cluster, a team that understands it, and a configuration larger than the service.
A managed container platform, or one virtual machine running the container, serves many engineering
workloads with a fraction of the operating cost.

**Serverless trades latency for idle cost.** Scale to zero makes an unused service free and makes the
first request after a quiet period wait for a cold start. Keeping instances warm removes the wait and
the saving together.

**The browser is free to serve and hard to control.** The L18 chat costs the course nothing per
question and keeps every question private, and it depends on the student's GPU, browser and patience
for a first download measured in minutes.

| Option | Good for | Bad at | Reach for something else when |
|---|---|---|---|
| In process | one caller in the same language | callers with other environments | more than one program needs the model |
| FastAPI service | a typed contract, several callers | heavy compute per request | requests run for minutes (use a job queue) |
| Inference server (Triton, vLLM) | GPU batching across clients | small CPU models | the model fits on a CPU and traffic is modest |
| Serverless | bursty or rare traffic | first-request latency | the p95 target is below the cold start |
| Batch | nobody waits | freshness | a person or program needs the answer now |
| Browser | privacy, zero serving cost | large models, old hardware | users cannot download or run the model |

## In-class demo

The demo notebook, [`l21-deployment.ipynb`](l21-deployment.ipynb), runs the service from `service/app.py` on your own
machine, in Colab or locally, with no cloud account and no Docker needed. It fits Lecture 14's
ensemble on concrete and writes the artifact and its manifest; exercises the endpoints in process
with FastAPI's test client, including the 422 and the out-of-domain flag; starts uvicorn in the
background and loads it with a closed-loop client at several concurrencies, checking Little's law on
the result; compares one request at a time against a batch; reproduces the `async def` stall; and
points a short optimization loop in the style of Lecture 15 at the endpoint and counts its calls. The
Docker cells, which build the image, read `docker history`, and recover the deleted file from a layer,
run only where Docker is installed and say so otherwise. Every figure in these notes was produced by
`figures/make_figures.py`, which runs the same service and records the machine it ran on.

## Summary

Deploying a model means deciding where it runs, what it promises its callers, how it is packaged,
how fast and at what cost it answers, and how it changes without harm, and this course had already
made each decision for something other than a model. The service built here answers in about a
millisecond at low load, rejects impossible inputs with a 422 that names the field, flags inputs
outside its training data because its interval does not widen there, loads its model once and
refuses an artifact whose hash or library version does not match its manifest. Packaged from the
lockfile into an image that downloads as 126 MB, it rebuilds in seconds after a code change, and a key passed the wrong
way into that image is readable from its history. Under load, one worker saturated at about 1,800
requests per second and then queued, exactly as Little's law requires, while batching made each
prediction a hundred times cheaper. The incidents show that most failures come from the change
rather than the code: a server not updated, a field count that did not match, a backup that was
never restored, a global push without a canary. The defences are a staged release, a check of what
is actually running, and a restore you have rehearsed, and they apply to a calibration factor as much
as to a program.

## Resources

- [FastAPI, Lifespan events](https://fastapi.tiangolo.com/advanced/events/). Loading a model once,
  with the docs' own ML example; the place to start.
- [FastAPI, Concurrency and async / await](https://fastapi.tiangolo.com/async/). When `def` runs in a
  threadpool and when `async def` blocks the server.
- [FastAPI, Deployments concepts](https://fastapi.tiangolo.com/deployment/concepts/) and
  [FastAPI in containers](https://fastapi.tiangolo.com/deployment/docker/). Workers, memory per
  worker, replication, and the exec-form `CMD`.
- [Astral, Using uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/) and
  [Using uv with PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/). The Dockerfile in
  these notes, line by line, and how to get the CPU-only `torch`.
- [Docker, Building best practices](https://docs.docker.com/build/building/best-practices/) and
  [Build secrets](https://docs.docker.com/build/building/secrets/). Multi-stage builds, non-root
  users, and why build arguments are not for secrets.
- [Kubernetes, Liveness, readiness and startup probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/).
  The clearest statement of what each health check is for, and the warning about liveness probes.
- [The Twelve-Factor App, Config](https://12factor.net/config). Configuration in the environment,
  and the open-source litmus test.
- [scikit-learn, Model persistence](https://scikit-learn.org/stable/model_persistence.html) and
  [PyTorch, Serialization semantics](https://docs.pytorch.org/docs/2.15/notes/serialization.html).
  What each format can and cannot do safely.
- [Dean and Barroso, The Tail at Scale](https://www.barroso.org/publications/TheTailAtScale.pdf)
  (CACM 2013, author's copy). Why the p99 of a component becomes the median of a system, and hedged
  requests.
- [Harchol-Balter, Performance Modeling and Design of Computer Systems, chapter 1](https://www.cs.cmu.edu/~harchol/PerformanceModeling/chpt1.pdf)
  (CMU, free sample chapter). Queueing intuition, including the design examples that defeat it.
- [Little and Graves, Little's Law](https://www.ic.unicamp.br/~nfonseca/MO648/doc/Little%27s%20Law-Published.pdf)
  (book chapter, course mirror). The law, its conditions, and how to use it as a check.
- [Google SRE book, Service level objectives](https://sre.google/sre-book/service-level-objectives/)
  and [SRE workbook, Canarying releases](https://sre.google/workbook/canarying-releases/). Percentiles,
  SLOs, error budgets, and how to evaluate a canary.
- [Google, Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml).
  Training-serving skew and the rules that prevent it, from the people who named it.
- [Brooker, Timeouts, retries, and backoff with jitter](https://builder.aws.com/content/3EumjoZascWd1oZiEgL8ORlv3qE/timeouts-retries-and-backoff-with-jitter)
  (Amazon Builders' Library). Why retries amplify load, and how to retry without causing an outage.
- [Brutlag, Speed matters for Google web search](https://services.google.com/fh/files/blogs/google_delayexp.pdf)
  (Google, 2009). The controlled latency experiment to cite instead of the folklore.
- [NVIDIA Triton, Dynamic batcher](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/batcher.html)
  and [Kwon et al., vLLM](https://arxiv.org/pdf/2309.06180) (SOSP 2023). Batching as the throughput
  lever, for models in general and for language models.
- The postmortems: [SEC order on Knight Capital](https://www.sec.gov/files/litigation/admin/2013/34-70694.pdf)
  (opens in a browser; automated downloads are refused),
  [CrowdStrike root cause analysis](https://www.crowdstrike.com/wp-content/uploads/2024/08/Channel-File-291-Incident-Root-Cause-Analysis-08.06.2024.pdf),
  [GitLab](https://about.gitlab.com/blog/postmortem-of-database-outage-of-january-31/),
  [AWS S3](https://aws.amazon.com/message/41926/) and
  [Cloudflare](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/). Each is
  short, specific, and written by the people who had to fix it.

## Assignment

No assignment is released with this session. It is optional, and no assignment depends on it.

## Practice module

<a href="../../game/#/l21"><strong>Practice module for this session</strong></a>, for participation
credit.
