# L21 notes plan: deployment (private)

Companion to the L21 block in `wk12.md`. Not published: `course/modules` is in
`exclude_patterns`. Written 2026-11-04 from three research passes. A repo pass mapped every
earlier lecture and the course's own infrastructure. Two web passes covered serving mechanics,
then latency, cost and incidents. Every external claim below was fetched and matched to a
verbatim quote that day. Items marked **CHECK** still need a hand check before the notes cite
them.

## The argument in one paragraph

A model on your laptop is not a deliverable (L1's own words). Deployment turns it into something
other people and programs depend on. That forces five decisions:

1. where it runs;
2. what contract it offers;
3. how it is packaged;
4. how fast and at what cost it answers;
5. how you change it without breaking the people who depend on it.

None of these is new to the student. The course has already made each decision at least once,
for a database server (L3), an embedded engine (L4), a broker (L6), a model registry (L10) and a
model running in the browser (L18). It has also made them for its own site, clicker and plant
stream. This lecture makes the pattern explicit and applies it to a model. Every section opens
with the earlier system that made the same choice, then goes deeper.

## Structure (H2 sections, in order)

Follows CLAUDE.md section 4. Opens with an `At a glance` admonition that carries the slides,
practice and demo lines, and states that there is no assignment.

### 1. `## Why this matters` (2 to 4 paragraphs)
- **Open on Knight Capital.** The SEC order (Release 34-70694) is the source for each fact:
  - The new RLP code reached seven of eight SMARS servers. The order says "one of Knight's
    technicians did not copy the new code to one of the eight SMARS computer servers".
  - The new code "repurposed a flag that was formerly used to activate the Power Peg code".
  - Uninstalling the new code from the seven good servers "worsened the problem".
  - The system sent 97 warning emails before the open.
  - It made "4 million executions in 154 stocks ... in approximately 45 minutes".
  - "Knight lost more than $460 million". Use the SEC figure, not the $440M that circulates.
- **Then the course's own.** On 2026-08-06 the build job was green, `deploy-pages` timed out,
  and the site served the previous commit. Source: the `book.yml` verify comment and
  CLAUDE.md section 8.
- **The point to land, in plain words:** a deploy that reports success is not evidence the
  thing you tested is the thing running.
- No figure. Index this section's case under the case-study heading (see section 7).

### 2. `## Learning objectives`
Verbatim from `wk12.md`.

### 3. `## Where a model runs`
**Open with the database decision the student already made.** L4: DuckDB "runs inside your own
process, with no server to start, no connection to manage". L3: PostgreSQL is "a server you
must run, secure, back up, monitor, and connect to within its connection limits". A model faces
the same choice.

**Five options, one documented property each (all verified):**
- **In-process.** The caller imports the model.
  - scikit-learn: none of the persistence methods support "loading a model trained with a
    different version of scikit-learn".
  - ONNX Runtime `InferenceSession` runs inside the caller.
- **Long-running service.** A Kubernetes Deployment runs "an application workload, usually one
  that doesn't maintain state". Course instances: L6's broker, and the plant stream on the Pi.
- **Serverless container or function.**
  - Cloud Run can "scale to zero when idle to reduce costs".
  - Cloud Run minimum instances avoid slow starts and "do incur billing costs".
  - Lambda: "Cold starts typically occur in under 1% of invocations. The duration of a cold
    start varies from under 100 ms to over 1 second". The largest contributor is initialization
    code, which for a model is the weight load.
  - Lambda's image limit is 10 GB, which rules out the larger CUDA images.
  - Course instance: the clicker as a Cloudflare Worker with a D1 database.
- **Batch.** SageMaker batch transform, "when you don't need a persistent endpoint". Course
  instance: L5's batch stages.
- **The browser.**
  - Transformers.js: "Run Transformers directly in your browser, with no need for a server".
  - ONNX Runtime Web supports all operators in WASM but "only a subset" on WebGPU.
  - Course instances: the L18 chat (WebGPU, secure context only, 15 to 20 minute first load)
    and the practice game (no network call at all). The first load is the cold start in its
    most extreme form.
- **Decision table**: call pattern, latency budget, who pays for idle time, what the caller
  must install, and a course example for each.
- **Definition ribbon**: none here. The ribbon goes on "cold start" if anywhere.

### 4. `## The service contract`
- **Open with L1.** FastAPI exposes "typed request and response schemas, which is also a data
  contract with your callers". Then L6's data contract, and L3's "a typed column is still not a
  validated column".

**`### Request and response models`**
- Pydantic `Field(ge=, le=)` on the eight concrete inputs, using L9's training ranges.
- Invalid input gets a `RequestValidationError` and a 422. **Demonstrate the 422 live; no doc
  prose states the number.**
- The response carries:
  - the mean;
  - the interval (L14's recalibrated ensemble, s = 1.66 on the grouped split);
  - an out-of-domain flag, motivated by L14's "The guarantee did not fail. Its condition was
    not met.";
  - the model version.
- The response model "will limit and filter the output data ... particularly important for
  security".
- OpenAPI comes from the types.
- Index: `Pydantic`, `OpenAPI`. Reuse `data contract` and `FastAPI`, both already indexed.

**`### Loading the model once`**
- `lifespan` handler. The FastAPI docs' own example is an ML model: "you don't want to do it
  for every request".
- `on_event` is deprecated.
- Workers: "if you start 4 processes (4 workers), each will consume 1 GB of RAM".
- Uvicorn uses spawn, not pre-fork, so weights are not shared between workers.
- **CHECK** the rendered uvicorn.org page; it was verified only on GitHub `Kludex/uvicorn`.

**`### def, async def, and a blocking model`**
- FastAPI runs a `def` "in an external threadpool ... (as it would block the server)", and says
  "If you just don't know, use normal def".
- A CPU-bound `predict` inside `async def` stalls every client. The docs frame blocking as I/O,
  so **demonstrate the stall rather than cite it**.
- Mention BackgroundTasks only with the docs' own caveat that heavy compute belongs in "bigger
  tools like Celery".

**`### Model artifacts`**
- **L10's registry.** The winner was "registered and loaded back", 7.41 MPa.
- **scikit-learn.**
  - pickle, joblib and cloudpickle: "Loading can execute arbitrary code".
  - skops is "More secure".
  - ONNX is the "Most secure option", though "not all models are supported".
  - The version lock (quoted in section 3).
- **PyTorch.**
  - Whole-model pickle is "bound to the specific classes and the exact directory structure".
    Save a `state_dict` instead. L12 already writes `best_{name}.pt`.
  - `torch.load` "Never load data from an untrusted source". `weights_only=True` has been the
    default since 2.6, so old whole-model code breaks.
  - TorchScript "is deprecated, please use torch.export instead". Its page is gone from 2.11+
    docs, so cite the 2.10 page.
  - ONNX export with `dynamo=True` is "the recommended and default way". L13 named ONNX as
    SiNDAE's export format.
- **The manifest.** Library versions, data hash and artifact SHA-256. This builds on L2's "the
  recipe that produced the model".

**`### Training-serving skew`**
- L1: "a feature computed one way in training and another way in serving".
- L8: serve the fitted `Pipeline`, scaler included.
- L7: every feature must exist at request time.
- Rules of ML:
  - Rule #29 "save the set of features used at serving time".
  - Rule #32 "Re-use code between your training pipeline and your serving pipeline".
  - The YouTube home page example (qualitative only).
- L18: the embedding model name and version "belong in the index's metadata".
- The course's own instance: the chat embeds index and query with the same runtime, because a
  Python index and a JavaScript query "would disagree by enough to reorder close results"
  (`chat/README.md`).
- Index: `training-serving skew` (check spelling against L1 first; L1 does not index it now)
  and `pair: failure mode; training-serving skew`.

### 5. `## Packaging the service`
- **Open with L2.** "When you need to freeze the entire stack down to the system libraries, the
  tool is a container." Then L1's container paragraph and L3's `docker-compose.yml`, the
  students' first container.

**`### A Dockerfile from the lockfile`** (uv guide; **CHECK** the rendered pages)
- Copy a pinned uv binary from the distroless image.
- `uv sync --frozen --no-install-project` in its own cached layer, then `COPY`, then
  `uv sync --locked`.
- `UV_LINK_MODE=copy` with a cache mount.
- `UV_COMPILE_BYTECODE=1`. It improves startup "at the cost of increased installation time and
  image size".
- A multi-stage build with `--no-editable`.
- `.venv` in `.dockerignore`.
- Docker's layer rule: "Once a layer changes, then all downstream layers need to be rebuilt".
- **Name the disagreement.** FastAPI's Docker page exports `requirements.txt` and uses pip. The
  notes use `uv sync --locked` because it keeps L2's lockfile as the single source of truth.
- Exec-form `CMD`, "to ensure that FastAPI can shutdown gracefully and lifespan events are
  triggered".
- `USER` non-root.
- FastAPI under Kubernetes: "a single (Uvicorn) process per container".
- The FastAPI Gunicorn image is deprecated.

**`### Image size and the GPU you do not need`**

All figures dated 2026-11-04; they move with each release.

| Item | Size | Source |
|---|---|---|
| Linux `torch` 2.15.0 wheel | 539 MB, and its CUDA deps add more than 1 GB (cuDNN alone 519 MB) | PyPI JSON |
| CPU wheel | about 210 MB | `download.pytorch.org` HEAD |
| `python:3.12-slim` | 43 MB | Docker Hub |
| `nvidia/cuda` runtime | 2.16 GB | Docker Hub |
| `pytorch/pytorch` runtime | 3.29 GB | Docker Hub |
| `pytorch/pytorch` devel | 13.85 GB | Docker Hub |

- uv's PyTorch guide: PyPI hosts "GPU-accelerated wheels on Linux". Show the CPU index config.
- Tie to L11: "For a model the size of this session's, the CPU is the correct choice", and a
  GPU is "a throughput device with a large fixed cost per kernel launch".
- Figure: image sizes, from `make_figures.py` with the dated numbers.

**`### Configuration and secrets`**
- This is the first time the course teaches it. L1 and L2 never mention keys. L18 says "as in L1
  and L2", which is wrong; fix that line in L18 separately.
- Twelve-factor: "stores config in environment variables", and the open-source litmus test.
- Docker:
  - Build args and ENV "persist in the final image".
  - Build args are "visible in the docker history command".
  - Use `--mount=type=secret`.
- OWASP on not hardcoding secrets with ENV or ARG.
- GitHub: "rotate the affected credential immediately".
- **Demonstrate, do not cite,** that a COPY'd-then-deleted file survives in an earlier layer.
  No doc sentence states it; it follows from "each of these layers, once created, are
  immutable".
- Course examples:
  - L3's compose file ("for a local teaching database only; do not reuse them");
  - the plant stream's mode-640 secret file that "never goes near the repository";
  - the game's `secrets.GAME_MAC_KEY`, and the CI step that refuses to publish the development
    key.
- Index: `secret`, `twelve-factor app`.

**`### Health checks`**
- L3's `pg_isready` health check.
- Docker `HEALTHCHECK` catches "a web server stuck in an infinite loop ... even though the
  server process is still running".
- Kubernetes:
  - Liveness probes catch a deadlock.
  - Readiness covers "loading files, and warming caches".
  - Startup probes delay both.
  - "Incorrect implementation of liveness probes can lead to cascading failures."
- So `/healthz` answers "is the process alive" and `/readyz` answers "is the model loaded".
- The plant stream's `Restart=always` is the systemd analogue.
- Index: `health check`, `liveness probe`, `readiness probe`. Reuse `container`.
- **Definition ribbon**: readiness probe.

### 6. `## Latency, throughput and capacity`

**`### Percentiles`**
- SRE book: "We generally prefer to work with percentiles rather than the mean".
- L11 reported minimums, which is correct for a microbenchmark of compute. A service is judged
  on the tail the user waits through.
- Index: `latency`, `throughput`, `tail latency`, `percentile`. Use `p95` in prose only.
- **Definition ribbon**: tail latency.

**`### The tail at scale`**
- Dean and Barroso, author's copy:
  - one server in 100 slow makes "63% of user requests" slow with a fan-out of 100
    (1 − 0.99^100; students can derive it);
  - the Table 1 service: 10 ms p99 for one request, 140 ms for all;
  - hedged requests cut p99.9 "from 1,800ms to 74ms while sending just 2% more requests".
- Connect to L18's per-stage latency: re-ranking cost "a thousand times the cost of the search
  itself".
- Index: `hedged request`.
- Figure: the fan-out curve, computed.

**`### Little's law and saturation`**
- Little and Graves (open mirror): L = λW.
- Worked check on NVIDIA's numbers:
  - 4 concurrent at 73.4/s gives W ≈ 54 ms (reported p95 65.6 ms);
  - 8 at 272/s gives W ≈ 29 ms (reported p95 36 ms).
- M/M/1: T = 1/(μ − λ), so the wait grows as 1/(1 − ρ). Cite Bertsekas and Gallager eq. 3.24 to
  3.26 (scanned PDF; quote equations, not prose).
- Harchol-Balter (CMU), design example 1: doubling the arrival rate needs "Less than double"
  the speed. This is the counterintuitive result.
- L6's backpressure: "signals upstream to slow down rather than silently dropping data". At
  the HTTP level that is a 429 or 503.
- Index: `Little's law`, `utilization`.
- Figure: wait against utilization, computed.

**`### Batching`**
- **Throughput against latency, already met four times:**
  - L3's "two million separate statements, each a round trip" against `COPY`;
  - L5's vectorized 0.2 ms comparison;
  - L15's `q=4` batch of experiments;
  - Triton's dynamic batcher, which trades "increased latency for increased throughput" via
    `max_queue_delay_microseconds`; its 272 against 73 inferences per second is NVIDIA's own
    example, so say so.
- The demo's `/predict_batch` against single calls, measured.
- Index: `dynamic batching`. Reuse `micro-batch` (L6) if the comparison is drawn.

**`### Language models`**
- Time to first token and inter-token latency (Anthropic and NVIDIA NIM definitions).
- OpenAI: "cutting 50% of your output tokens may cut ~50% of your latency".
- Streaming over SSE (WHATWG, MDN). MDN's footgun: six connections per browser without HTTP/2.
- Continuous batching:
  - Orca: 36.9×, on GPT-3 175B against FasterTransformer;
  - vLLM: 2 to 4×, and only 20.4% to 38.2% of KV cache in use in prior systems.
- L18's capstone: an answer takes about 25 seconds in the browser.
- Index: `time to first token`, `server-sent events`, `continuous batching`.

**`### What latency costs, and the numbers that circulate`**
- Trace "+100 ms costs Amazon 1%" to Linden's 2006 slide bullet: "+500 ms -20% traffic @ Google
  +100 ms @ Amazon -1% sales". The slide has no "every" and no method.
- The Google number came from a 10 against 30 results test, with latency as an uncontrolled
  variable (Linden's blog on Mayer's talk).
- Kohavi et al. 2007 restated it and turned "traffic" into "revenues".
- The controlled number is Brutlag 2009: 100 to 400 ms cost 0.2% to 0.6% of daily searches per
  user, and 50 ms had no measurable effect.
- This is the same move as L1's "10% of code" claim. Put it in a `What a practitioner should
  take from this` box.

### 7. `## Cost`
- **Per request:**
  - CPU service: instance price divided by sustained throughput at the p95 target.
  - Ensemble: L14's "M networks cost M times as much to train and to evaluate", and DPOSE's one
    extra layer.
  - GPU-hours.
  - LLM: input and output tokens priced separately. Quote the Anthropic page **with the date**:
    on 2026-11-04 output was 5× input for every model shown. The Batch API gives a 50%
    discount. Prompt caching writes at 1.25× and reads at 0.1× of base input, and is "worth it
    after one read" for the 5-minute TTL.
- **Idle cost:** warm minimum instances against cold starts.
- **Retries:**
  - "Retries are 'selfish'".
  - Five layers with three retries each is "243x" load on the database.
  - "retry at a single point in the stack".
  - Exponential backoff with jitter: "The solution isn't to remove backoff. It's to add
    jitter."
  - "APIs with side effects aren't safe to retry unless they provide idempotency". Tie to L5's
    idempotent stages and L6's at-least-once delivery.
- The clicker's capacity budget, "24k requests a session against a 100k/day budget", is a
  worked cost-to-limit example from the course.
- Do not duplicate `course/optional/mlops.md` on cost over time. That page is unpublished;
  name nothing in it.
- Index: `cost per request`, `exponential backoff`, `retry storm`. Reuse `idempotency`.

### 8. `## Releasing changes safely`
Each case gets a `###` subsection with a `What a practitioner should take from this` box.

**`### Every change is a deploy: CrowdStrike, 19 July 2024`**
- A "content configuration update", not code.
- "21 input parameter fields ... supplied only 20 input values", an out-of-bounds read.
- Testing used a wildcard for the 21st field.
- Fixed in 78 minutes.
- The fix is staged rollout with canary rings.
- "8.5 million Windows devices" is Microsoft's estimate, not CrowdStrike's. Say so.
- Model weights and feature schemas are content in exactly this sense.

**`### Canaries and staged rollouts`**
- SRE workbook: "a partial and time-limited deployment of a change ... and its evaluation".
- L1 already promised "staged rollout so a bad model does not reach everyone at once, and the
  ability to roll back".
- SLI, SLO and SLA definitions; the error budget. SRE: "a user on a 99% reliable smartphone
  cannot tell the difference between 99.99% and 99.999%".
- Index: `canary release`, `staged rollout`, `rollback`, `service level objective`,
  `error budget`. Add `see: SLO; service level objective` and `see: SLI; service level
  indicator`.

**`### Verify the artifact that is running: Knight Capital again, and this site`**
- Every replica, every time. Rollback is a change.
- This site's `build-info.json` stamp and the polling, cache-busting `verify` job, which
  CLAUDE.md calls the answer to "*The run is green.* That does not tell you the site updated".
- The `curl -s` without `-L` trap after HTTPS enforcement: a 301 page where JSON was expected.

**`### Backups you have restored: GitLab, 31 January 2017`**
- The database link the student cares about most. L3's PostgreSQL is "a server you must ...
  back up".
- "around 300 GB of data had already been removed".
- "pg_dump 9.2, while our database is running PostgreSQL 9.6".
- Failure emails were rejected: "we were never aware of the backups failing".
- Restored from an LVM snapshot 6 hours old: "roughly 5,000 projects, 5,000 comments and 700
  new user accounts" lost, and about 18 hours down. "Because there was no ownership".
- **Do not** repeat "5 out of 5 backups failed". It is not in the postmortem.

**`### Tools that enforce invariants: AWS S3, 28 February 2017`**
- "one of the inputs to the command was entered incorrectly".
- Index and placement subsystems had not been fully restarted "for many years".
- The fix removes capacity more slowly and refuses to go below the minimum.
- The status dashboard depended on S3.

**`### A fast global channel: Cloudflare, 2 July 2019`**
- A WAF regex pushed globally in seconds: "backtracked enormously".
- The CPU protection had been removed in a refactor.
- "simulate mode" still executed.
- 27 minutes. Staged rollout for rules afterwards.

**`### The course's own small incidents`**
- Debian's mosquitto "built without WebSocket support", failing with "no message naming the
  actual cause".
- nginx's default 60 s `proxy_read_timeout` cutting connections.
- Pinning mosquitto against unattended upgrades.
- D1 without `--remote` ("no such table: vote").
- A new hostname with no certificate for the first minutes.
- These are small, documented and true, which is why they teach.

**Index:** `pair: case study; Knight Capital`, `pair: case study; CrowdStrike outage`,
`pair: case study; GitLab database outage`, `pair: case study; AWS S3 outage`,
`pair: case study; Cloudflare outage`, `postmortem`.

### 9. `## Limitations and trade-offs`
- When not to build a service: an in-process library or a nightly batch job serves most
  engineering surrogates. This is L5's "Exhaust one good machine before adding a cluster."
- What FastAPI is bad at: heavy compute (Celery, per its own docs), and CPU-bound Python under
  the GIL.
- When a dedicated inference server earns its place (Triton, vLLM).
- Kubernetes' operational weight against a single VM or a managed container service.
- Serverless cold starts against paying for warm instances.
- The browser: free to serve and private, but limited by WebGPU operator support and the first
  load.
- A pros and cons table.

### 10. `## In-class demo`, 11. `## Summary`, 12. `## Resources`, 13. `## Assignment` ("None"), 14. `## Practice module`
- **Summary:** one paragraph. No forward references, and L22 is unreleased.
- **Resources:** the readings list in `wk12.md`, one annotation line each, plus Harchol-Balter
  ch. 1, Brutlag 2009, the vLLM paper and the Triton docs.

## Connections, by lecture (for cross-reference links)

Link with `[Lecture N](../lNN/notes.md)` only if that lecture is released when L21 is written.
L19 and L20 are unreleased at the time of writing.

| Lecture | Hook in L21 | Quote to reuse |
|---|---|---|
| L1 | containers, FastAPI, staged rollout, skew | "Your model runs on your laptop. That is not a deliverable." |
| L2 | lockfile → container | "When you need to freeze the entire stack ... the tool is a container" |
| L3 | server you must run, back up; compose health check; demo credentials | "a server you must run, secure, back up, monitor" |
| L4 | in-process engine | "no server to start, no connection to manage" |
| L5 | idempotency, batch, one machine first | "Exhaust one good machine before adding a cluster." |
| L6 | broker as a long-lived service, backpressure, at-least-once, data contract | "Assume at-least-once" |
| L7 | features that exist at request time | "the 2:03 PM reading has not happened yet" |
| L8 | serve the fitted Pipeline | (code comment on reusing means and spreads) |
| L9 | concrete dataset; extrapolation → range checks | "stays flat at its last leaf" |
| L10 | model registry | "registered and loaded back" |
| L11 | eval(), no_grad(), CPU choice, minimum vs percentile | "the CPU is the correct choice" |
| L12 | checkpoint as artifact | "Checkpointing to disk does the same job and also survives a crash" |
| L13 | ONNX; inference that runs a solver | "a file format to export the trained network" |
| L14 | interval and out-of-domain flag in the response; ensemble cost | "The guarantee did not fail. Its condition was not met." |
| L15 | the optimizer as the client; q=4 | "Its overhead, seconds per step, is small compared with an experiment." |
| L17 | tokens as budget | "Cost and time are counted in tokens" |
| L18 | per-stage latency; embedding pinning; browser chat; keys | "a query embedded with a different model ... silently ruins retrieval" |

## Figures (`lectures/l21/figures/make_figures.py`)
1. **Fan-out tail.** P(at least one slow) = 1 − (1 − p)^n for p = 0.01 and 0.0001, marking
   Dean and Barroso's 63% and roughly one in five.
2. **Waiting time against utilization** for M/M/1, with the NVIDIA Little's-law points
   overlaid.
3. **Measured latency.** p50 and p95 of the demo service at concurrency 1, 2, 4, 8 and 16, one
   request at a time against `/predict_batch`, on the machine that ran the script. State that
   machine.
4. **Image and wheel sizes**, dated 2026-11-04.
5. **Where a model runs**: an original diagram of the five options, with the course system
   that used each.

## Demo notebook (`l21-deployment.ipynb`, generated by `build_notebook.py`)
- Must run top to bottom in Colab. That means `uvicorn` started with `subprocess.Popen` on
  127.0.0.1, waiting on `/readyz`, and killed in the last cell.
- Pin seeds.
- Docker cells check `shutil.which("docker")` and print what they would have done otherwise.
- **Data:** concrete from the UCI zip, exactly as L14 downloads it.
- **Deliberate breakage, with a markdown cell saying so** (CLAUDE.md section 6):
  - the `async def` stall;
  - a 422 for an out-of-range mix;
  - the secret recovered from `docker history`, where Docker exists.
- **Cost cell:** prices as parameters with the date they were read. No hardcoded "current"
  price.

## Index terms
- **New** (check each against the course with the CLAUDE.md section 4b grep first): Docker,
  Dockerfile, image layer, Pydantic, OpenAPI, lifespan, readiness probe, liveness probe,
  health check, secret, twelve-factor app, training-serving skew, latency, throughput, tail
  latency, percentile, hedged request, Little's law, utilization, dynamic batching, time to
  first token, server-sent events, continuous batching, cold start, serverless, cost per
  request, exponential backoff, retry storm, canary release, staged rollout, rollback,
  service level objective, error budget, postmortem.
- **The five case studies**, as `pair: case study; ...`.
- **Reuse, do not respell:** container, FastAPI, lockfile, uv, embedded database, DuckDB,
  idempotency, caching, backpressure, data contract, micro-batch, model registry, inference,
  GPU, deep ensemble, split conformal prediction, surrogate model, WebGPU.
- The list is longer than twenty. Trim to the twenty terms the notes actually define.

## Practice bank
- `game/content/l21.yml` at `pool_version: 3`, because `pools/l21.json` already holds v1 and v2
  from the archived evaluation bank.
- Objectives `l21-o1` to `l21-o5` as in `wk12.md`.
- Twenty items, `serve: 10`.
- Good items:
  - the 63% derivation;
  - a Little's-law calculation;
  - which probe fails while the model loads;
  - why a secret in `ENV` leaks;
  - why the folklore number is weak;
  - what Knight's rollback did.

## To check before writing
- **CHECK** the rendered uv and uvicorn pages. They were verified only on GitHub sources:
  `astral-sh/uv` `docs/guides/integration/docker.md` and `pytorch.md`, and `Kludex/uvicorn`
  `docs/deployment/index.md` and `settings.md`.
- **CHECK** that the SEC PDF opens in a browser. It returns 403 to plain curl without a contact
  User-Agent.
- **CHECK** the Microsoft blog link, which 403'd once and then opened.
- Re-read every price on the day the notes are written, and date it.
- Decide whether L19 and L20 are released before L21. That decides links or prose.
- Fix the line in L18 that credits L1 and L2 with teaching API-key handling. Do it in a
  separate change.
- `course/schedule.md` titles L18 and L19 differently from their notes (RAG and agents in the
  schedule; context engineering and RAG in the notes). This predates this work. Resolve it
  before L21 cites either by title.

## Where the raw research is
The three agents' raw downloads are in the session scratchpad, which is not kept. Everything
the notes need is quoted above or in the `wk12.md` readings. Re-fetch any source before quoting
it at length.
