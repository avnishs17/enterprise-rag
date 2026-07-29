# Local Docker setup

The app is containerized as two separate runtime images:

```text
backend image  -> FastAPI / Uvicorn on :8000
frontend image -> Next.js standalone server on :3000
```

The frontend talks to the backend through Docker DNS using `RAG_API_URL=http://backend:8000`. The browser still calls the frontend same-origin proxy, so backend API keys are never shipped to browser JavaScript.

## Files

```text
app/Dockerfile       # backend image; build context is repo root
ui/Dockerfile        # frontend image; build context is ./ui
docker-compose.yml   # local two-container stack
.dockerignore
ui/.dockerignore
```

## Prerequisites

- `.env` exists at the repository root with the same service credentials used for local development.
- Docker Compose v2 is installed.

## Run both containers

```bash
# Stop any non-container dev servers first
fuser -k 8000/tcp 3000/tcp || true

# Build and start backend + frontend
DOCKER_RATE_LIMIT_PER_MINUTE=100 docker compose up --build
```

Detached mode:

```bash
DOCKER_RATE_LIMIT_PER_MINUTE=100 docker compose up -d --build
```

Open [http://localhost:3000](http://localhost:3000).

## Smoke checks

Backend health:

```bash
curl http://localhost:8000/health
```

Frontend proxy health:

```bash
curl http://localhost:3000/api/rag/health
```

Backend query:

```bash
curl -X POST http://localhost:8000/query \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q":"What does kube-proxy do?","thread_id":"docker-smoke"}'
```

Run deterministic evals against the Dockerized backend:

```bash
uv run python -m evals.run
```

Then, if needed, run RAGAS from the generated report:

```bash
uv run python -m evals.run \
  --ragas-from-report evals/latest_report.json \
  --judge-provider nebius \
  --judge-delay 10 \
  --ragas-score-timeout 180
```

## Useful commands

```bash
# Follow logs
docker compose logs -f backend frontend

# Rebuild one image after code changes
docker compose build backend
docker compose build frontend

# Stop and remove local containers/network
docker compose down

# Show resolved Compose config
docker compose config
```

Build individual images without Compose:

```bash
docker build -f app/Dockerfile -t enterprise-agentic-rag-backend:local .
docker build -f ui/Dockerfile -t enterprise-agentic-rag-frontend:local ./ui
```

## Notes

- Secrets are passed at runtime from `.env`; they are not copied into the images.
- `DOCKER_RATE_LIMIT_PER_MINUTE` is a Compose-only convenience for local eval loops. Keep production limits stricter.
- The backend image uses `LLM_REQUEST_TIMEOUT_SECONDS` from `.env` for provider read/idle timeouts.
- External services remain managed/cloud services: Qdrant, Upstash Redis, Neon, Jina, Nebius, Groq, and Mem0.
- The backend Dockerfile lives under `app/` for symmetry with `ui/Dockerfile`, but its build context remains the repo root because it needs `pyproject.toml`, `uv.lock`, and `app/`.
