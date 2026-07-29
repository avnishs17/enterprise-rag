# Local development setup

## Prerequisites

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and npm
- Configured Jina, Nebius, Groq, Qdrant, Neon Postgres, and Upstash Redis accounts

## Initial setup

```bash
# Backend dependencies, including test and evaluation tools
uv sync --extra dev

# Backend configuration — never commit the resulting .env
cp .env.example .env
# Edit .env and replace every required placeholder.

# Frontend dependencies and server-only proxy configuration
cd ui
npm install
cp .env.example .env.local
# Set RAG_API_URL and the same RAG_API_KEY configured in ../.env.
cd ..
```

`RAG_API_KEY` is optional for local-only development, but it must be set for any deployed environment. The browser never receives it: the Next.js same-origin proxy owns the backend credential.

## Run the application without Docker

Start the backend from the repository root:

```bash
fuser -k 8000/tcp || true
uv run uvicorn app.main:app --reload --port 8000
```

For repeated local eval runs, optionally raise the API rate limit for that process so the evaluator does not share a small `127.0.0.1` bucket with UI/curl traffic:

```bash
fuser -k 8000/tcp || true
RATE_LIMIT_PER_MINUTE=100 uv run uvicorn app.main:app --reload --port 8000
```

LLM provider calls use `LLM_REQUEST_TIMEOUT_SECONDS` from `.env` as a read/idle timeout so a stalled upstream synthesis request cannot hang indefinitely.

Start the frontend in a second terminal:

```bash
cd ui
fuser -k 3000/tcp || true
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Health and observability

```bash
# Liveness
curl http://localhost:8000/health

# Readiness checks all configured dependencies
curl http://localhost:8000/ready

# Prometheus metrics
curl -s http://localhost:8000/metrics | grep -E 'rag_|llm_fallback|guardrails'

# Standalone external-connection diagnostic
uv run python -m app.services.health.connection_checker
```

Key live metrics include request latency, pipeline-stage latency, streaming time-to-first-token, active streams, output volume, guardrail decisions, and Nebius → Groq fallback count.

## API examples

Use the backend directly only from trusted server-side clients. The browser UI calls `/api/rag/...` through the Next.js proxy.

```bash
export API_HEADER="Authorization: Bearer $RAG_API_KEY"

# Synchronous JSON response
curl -X POST http://localhost:8000/query \
  -H "$API_HEADER" -H 'Content-Type: application/json' \
  -d '{"q":"What does kube-proxy do?","thread_id":"demo-thread-1"}'

# Server-sent event response
curl -N -X POST http://localhost:8000/query/stream \
  -H "$API_HEADER" -H 'Content-Type: application/json' \
  -d '{"q":"What does kube-proxy do?","thread_id":"demo-thread-1"}'

# Permanently remove one thread's Redis transcript and Mem0 scope
curl -X DELETE http://localhost:8000/conversations/demo-thread-1 -H "$API_HEADER"
```

## Document ingestion

Use the UI upload panel for normal ingestion. It validates supported file types, size, MIME type, and file signature, then returns a pollable job ID.

To seed or rebuild Qdrant from a local directory:

```bash
# Ingest subdirectories under DATA/, classifying names containing true/noisy automatically
uv run python -m app.ingestion.processor DATA

# WARNING: deletes and recreates the configured Qdrant collection before ingestion
uv run python -m app.ingestion.processor DATA --wipe

# Ingest a single directory with an explicit source type
uv run python -m app.ingestion.processor DATA/true true
```

Supported uploads: PDF, HTML, TXT, DOCX, and PPTX.

## Tests and static checks

```bash
# All backend unit and integration tests
uv run pytest

# Run individual backend layers
uv run pytest -m unit
uv run pytest -m integration

# Python linting
uv run ruff check app evals tests

# Frontend unit/integration tests
cd ui && npm test

# Frontend production type/build verification
cd ui && npm run build
```
