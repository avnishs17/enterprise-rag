# Enterprise Agentic RAG

A streaming enterprise RAG assistant for approved Kubernetes, Intel hardware, and networking knowledge. It uses Qdrant retrieval, Jina embeddings/reranking, Redis exact thread history, Mem0 semantic memory, Groq GPT-OSS-Safeguard policy classification, and direct Nebius → Groq LLM failover. The prior NeMo policy flow remains available as an explicit rollback option.

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

## Run the application

Start the backend from the repository root:

```bash
fuser -k 8000/tcp || true
uv run uvicorn app.main:app --reload --port 8000
```

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

## Live evaluations

Start the backend first. The evaluator uses fresh thread IDs and deletes each test conversation when finished, so it does not retain evaluation history in Redis or Mem0.

```bash
# Deterministic checks: retrieval, expected source, citations, guardrails,
# latency, and Redis conversation-history behavior
uv run python -m evals.run

# Add RAGAS LLM-judge metrics: faithfulness, answer relevancy,
# context precision/recall, and answer correctness
uv run python -m evals.run --ragas
```

The evaluator reads `.env`. Override settings when needed:

```bash
EVAL_BACKEND_URL=http://localhost:8000 \
EVAL_API_KEY="$RAG_API_KEY" \
EVAL_JUDGE_API_KEY="$JUDGE_GROQ_API_KEY" \
uv run python -m evals.run --ragas --judge-delay 2
```

Reports are written to `evals/latest_report.json` (ignored by Git). RAGAS uses the external judge model plus Jina's OpenAI-compatible embedding API; it does not download or run a local embedding model. Run it deliberately rather than on every local edit because it consumes judge and embedding API calls.

### Guardrail A/B evaluation

Compare the legacy NeMo flow directly with Groq's
`openai/gpt-oss-safeguard-20b` without starting the API server:

```bash
uv run python -m evals.guardrail_ab
```

The evaluator runs `evals/guardrail_ab_dataset.json` through both classifiers,
records decision accuracy, mandatory-block false negatives, agreement, and
p50/p95 latency in `evals/guardrail_ab_report.json`. The baseline A/B trial
selected Groq Safeguard; it is now the default via
`GUARDRAIL_PROVIDER=groq_safeguard`. Set `GUARDRAIL_PROVIDER=nemo` only for an
explicit rollback. The classifier uses the same `GROQ_API_KEY`; tune its model
or timeout with `GROQ_SAFEGUARD_MODEL` and `GROQ_SAFEGUARD_TIMEOUT_SECONDS`.

## Current operational limitations

- Upload job state uses in-process memory and FastAPI background tasks. Replace it with a durable worker queue before multi-worker production deployment.
- `RAG_API_KEY` is service authentication, not user authentication or tenant isolation. Add identity, authorization, and tenant-scoped data access before production.
- The approved-domain guardrail policy is authoritative. Ingesting a document does not authorize a new domain.
