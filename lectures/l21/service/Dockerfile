# The L21 concrete strength service, built from uv.lock.
# Follows Astral's "Using uv in Docker" guide: https://docs.astral.sh/uv/guides/integration/docker/
#
#   docker build -t concrete-service .           # the model/ directory must be present
#   docker run --rm -p 8000:8000 concrete-service
#
# Two stages. The first has uv and builds the virtual environment; the second copies only that
# environment, the code and the model onto a slim Python image.

FROM python:3.12-slim AS build
# A pinned uv binary from the official distroless image. Pin it: tags can move.
COPY --from=ghcr.io/astral-sh/uv:0.10.3 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, in their own layer, so editing app.py does not reinstall scikit-learn.
# --locked fails the build if uv.lock no longer matches pyproject.toml. --no-dev leaves out the
# training and measurement tools.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

FROM python:3.12-slim
# Run as an unprivileged user: the service needs no root.
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY app.py ./
COPY model/ ./model/
ENV PATH="/app/.venv/bin:$PATH" MODEL_DIR=/app/model
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)"]
# Exec form, so uvicorn is PID 1, receives SIGTERM, and the lifespan shutdown runs.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
