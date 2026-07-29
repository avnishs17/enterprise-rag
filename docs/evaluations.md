# Evaluations

The project has two evaluation layers:

1. **Deterministic live evals** call `/query` and `/query/stream` and check retrieval, sources, citations, guardrails, conversation memory, and latency.
2. **RAGAS quality evals** score saved or fresh answers with LLM-judge metrics plus Jina embeddings.

## Deterministic evals

Start the backend first. For repeated local evals, use a higher local rate limit:

```bash
RATE_LIMIT_PER_MINUTE=100 uv run uvicorn app.main:app --reload --port 8000
```

Run deterministic checks:

```bash
uv run python -m evals.run
```

This writes `evals/latest_report.json`.

## RAGAS evals

### Recommended path

After a clean deterministic run, run only RAGAS on the saved report. This avoids another live `/query` pass and avoids backend 429s:

```bash
uv run python -m evals.run \
  --ragas-from-report evals/latest_report.json \
  --judge-provider nebius \
  --judge-delay 10 \
  --ragas-score-timeout 180
```

This uses Nebius credits for the RAGAS judge and Jina for embeddings.

### Fresh full run

Use this only when you intentionally want to regenerate live answers and then run RAGAS in one command:

```bash
uv run python -m evals.run --ragas --judge-delay 15 --ragas-score-timeout 180
```

This calls `/query` again and may hit local API rate limits unless the backend was started with a higher eval-only limit.

### Judge provider options

```bash
# Groq judge; use only when Groq quota is available.
uv run python -m evals.run \
  --ragas-from-report evals/latest_report.json \
  --judge-provider groq \
  --judge-delay 15

# Nebius judge; reads NEBIUS_API_KEY, NEBIUS_BASE_URL, and NEBIUS_MODEL from .env.
uv run python -m evals.run \
  --ragas-from-report evals/latest_report.json \
  --judge-provider nebius \
  --judge-delay 10 \
  --ragas-score-timeout 180
```

### Smoke-test RAGAS cheaply

```bash
uv run python -m evals.run \
  --ragas-from-report evals/latest_report.json \
  --judge-provider nebius \
  --ragas-limit 2 \
  --ragas-metrics faithfulness,answer_relevancy \
  --judge-delay 10
```

## Useful flags

- `--ragas-from-report evals/latest_report.json`: run RAGAS only on a saved deterministic report; does not call `/query`.
- `--judge-provider groq|nebius|custom`: choose the RAGAS judge provider.
- `--judge-delay N`: sleep between judge samples to reduce provider 429s.
- `--ragas-score-timeout N`: timeout/retry one RAGAS metric/sample call.
- `--ragas-limit N`: score only the first N successful RAG samples.
- `--ragas-metrics a,b`: score a subset such as `faithfulness,answer_relevancy`.
- `--ragas-context-chars N`: cap characters per retrieved context sent to RAGAS.

The evaluator reads `.env`. Override settings when needed:

```bash
EVAL_BACKEND_URL=http://localhost:8000 \
EVAL_API_KEY="$RAG_API_KEY" \
EVAL_JUDGE_PROVIDER=nebius \
uv run python -m evals.run --ragas-from-report evals/latest_report.json --judge-delay 10
```

Reports are written to `evals/latest_report.json` (ignored by Git). RAGAS uses the external judge model plus Jina's OpenAI-compatible embedding API; it does not download or run a local embedding model.

## Current baseline

Latest validated baseline using deterministic evals plus RAGAS from the saved report with Nebius as the judge:

```bash
uv run python -m evals.run
uv run python -m evals.run \
  --ragas-from-report evals/latest_report.json \
  --judge-provider nebius \
  --judge-delay 10 \
  --ragas-score-timeout 180
```

Deterministic summary:

| Metric | Score |
|---|---:|
| RAG retrieval rate | 1.000 |
| Expected source recall | 1.000 |
| Citation coverage | 1.000 |
| Citation validity | 1.000 |
| Required term recall | 0.958 |
| Guardrail precision/recall/accuracy | 1.000 / 1.000 / 1.000 |
| Conversation pass rate | 1.000 |
| Average live latency | 11.76s |

RAGAS summary:

| Metric | Score |
|---|---:|
| Faithfulness | 0.988 |
| Answer relevancy | 0.897 |
| Context precision | 0.939 |
| Context recall | 1.000 |
| Answer correctness | 0.728 |

Interpretation: retrieval, citations, guardrails, and conversation memory are passing strongly. The main quality-improvement target is answer correctness/detail alignment, while keeping faithfulness high.

## Guardrail A/B evaluation

Compare the legacy NeMo flow directly with Groq's `openai/gpt-oss-safeguard-20b` without starting the API server:

```bash
uv run python -m evals.guardrail_ab
```

The evaluator runs `evals/guardrail_ab_dataset.json` through both classifiers, records decision accuracy, mandatory-block false negatives, agreement, and p50/p95 latency in `evals/guardrail_ab_report.json`.

The baseline A/B trial selected Groq Safeguard; it is now the default via `GUARDRAIL_PROVIDER=groq_safeguard`. Set `GUARDRAIL_PROVIDER=nemo` only for an explicit rollback. Tune the classifier with `GROQ_SAFEGUARD_MODEL` and `GROQ_SAFEGUARD_TIMEOUT_SECONDS`.
