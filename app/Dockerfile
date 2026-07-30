# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

ARG TORCH_VARIANT=cpu
ENV TORCH_VARIANT=${TORCH_VARIANT}

# Some transitive deps (e.g. annoy via NeMo Guardrails) compile native wheels.
# Keep compilers in the builder stage only; they are not copied to runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into /app/.venv. The app itself is copied in the
# runtime stage and loaded via PYTHONPATH so dependency layers cache cleanly.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# The lockfile and default image use CPU-only Torch. CUDA is an explicit
# build-time opt-in so the normal local/AKS image does not carry GPU libraries.
RUN if [ "$TORCH_VARIANT" = "cuda" ]; then \
      uv pip install --python /app/.venv/bin/python --reinstall --index-url https://pypi.org/simple torch==2.13.0; \
    elif [ "$TORCH_VARIANT" != "cpu" ]; then \
      echo "TORCH_VARIANT must be cpu or cuda" >&2; exit 1; \
    fi

FROM python:3.11-slim-bookworm AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# curl is used by the container healthcheck. libmagic helps upload MIME/file
# detection paths used by unstructured/python-magic dependencies. libgomp1 is
# needed by common ML/numeric wheels used transitively by rerank/embedding deps.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libmagic1 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser pyproject.toml README.md ./

RUN mkdir -p processed_data \
    && chown appuser:appuser processed_data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
