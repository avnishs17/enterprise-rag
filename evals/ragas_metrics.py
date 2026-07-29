"""Optional RAGAS quality scoring for results collected from the live RAG API."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

MAX_CONTEXTS = 5
MAX_CONTEXT_CHARS = 4_000


@dataclass(frozen=True)
class RagasConfig:
    api_key: str
    base_url: str
    model: str
    embedding_api_key: str
    embedding_base_url: str = "https://api.jina.ai/v1"
    embedding_model: str = "jina-embeddings-v3"
    delay_seconds: float = 1.0
    score_timeout_seconds: float = 180.0
    sample_limit: int | None = None
    metric_names: tuple[str, ...] | None = None
    max_context_chars: int = MAX_CONTEXT_CHARS


def _inputs(result: dict[str, Any], max_context_chars: int = MAX_CONTEXT_CHARS) -> dict[str, Any]:
    """Map the current evaluator report schema to RAGAS's single-turn schema."""
    return {
        "user_input": result["question"],
        "response": result["answer"],
        "reference": result["reference"],
        "retrieved_contexts": [source[:max_context_chars] for source in result["sources"][:MAX_CONTEXTS]],
    }


def _metric_inputs(
    metric_name: str, result: dict[str, Any], max_context_chars: int = MAX_CONTEXT_CHARS
) -> dict[str, Any]:
    """Return only the fields accepted by each RAGAS metric version."""
    inputs = _inputs(result, max_context_chars)
    required = {
        "faithfulness": ("user_input", "response", "retrieved_contexts"),
        "answer_relevancy": ("user_input", "response"),
        "context_precision": ("user_input", "reference", "retrieved_contexts"),
        "context_recall": ("user_input", "reference", "retrieved_contexts"),
        "answer_correctness": ("user_input", "response", "reference"),
    }[metric_name]
    return {key: inputs[key] for key in required}


def _build_metrics(config: RagasConfig):
    """Construct judge and embedding clients only when RAGAS is requested."""
    from ragas.embeddings import OpenAIEmbeddings
    from ragas.llms import llm_factory
    from ragas.metrics.collections import (
        AnswerCorrectness,
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    judge = llm_factory(
        config.model,
        provider="openai",
        client=AsyncOpenAI(api_key=config.api_key, base_url=config.base_url, timeout=60.0, max_retries=2),
    )
    # Jina exposes an OpenAI-compatible embeddings endpoint. Reusing it avoids
    # downloading a local model and keeps eval similarity in the same embedding
    # family as production retrieval.
    embeddings = OpenAIEmbeddings(
        client=AsyncOpenAI(api_key=config.embedding_api_key, base_url=config.embedding_base_url, timeout=60.0, max_retries=2),
        model=config.embedding_model,
    )
    return {
        "faithfulness": Faithfulness(llm=judge),
        "answer_relevancy": AnswerRelevancy(llm=judge, embeddings=embeddings),
        "context_precision": ContextPrecision(llm=judge),
        "context_recall": ContextRecall(llm=judge),
        "answer_correctness": AnswerCorrectness(llm=judge, embeddings=embeddings),
    }


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    status_code = getattr(error, "status_code", None)
    return status_code == 429 or "429" in text or "rate limit" in text or "too many requests" in text


async def _score_with_retry(
    metric: Any, inputs: dict[str, Any], *, attempts: int = 5, timeout_seconds: float = 180.0
) -> float:
    for attempt in range(attempts):
        try:
            score = await asyncio.wait_for(metric.abatch_score([inputs]), timeout=timeout_seconds)
            return float(score[0].value)
        except Exception as error:
            if not (_is_rate_limit_error(error) or isinstance(error, TimeoutError)) or attempt == attempts - 1:
                raise
            sleep_seconds = min(60.0, (2 ** attempt) * 5.0) + random.uniform(0.0, 1.0)
            await asyncio.sleep(sleep_seconds)
    raise RuntimeError("unreachable")


async def run_ragas_metrics(results: list[dict[str, Any]], config: RagasConfig) -> dict[str, Any]:
    """Score live RAG responses sequentially to respect judge-provider limits."""
    usable = [result for result in results if result["answer"] and result["sources"] and not result["blocked"]]
    if not usable:
        raise ValueError("No successful, grounded RAG responses are available for RAGAS scoring.")

    metrics = _build_metrics(config)
    if config.metric_names:
        unknown = set(config.metric_names) - set(metrics)
        if unknown:
            raise ValueError(f"Unknown RAGAS metric(s): {', '.join(sorted(unknown))}")
        metrics = {name: metrics[name] for name in config.metric_names}
    if config.sample_limit:
        usable = usable[:config.sample_limit]
    report: dict[str, Any] = {}
    for metric_index, (metric_name, metric) in enumerate(metrics.items(), start=1):
        rows = []
        print(f"RAGAS metric {metric_index}/{len(metrics)}: {metric_name}", flush=True)
        for index, result in enumerate(usable):
            print(f"  scoring {index + 1}/{len(usable)}: {result['id']}", flush=True)
            score = await _score_with_retry(
                metric,
                _metric_inputs(metric_name, result, config.max_context_chars),
                timeout_seconds=config.score_timeout_seconds,
            )
            rows.append({"id": result["id"], "score": round(score, 3)})
            if config.delay_seconds and index < len(usable) - 1:
                await asyncio.sleep(config.delay_seconds)
        report[metric_name] = {
            "average": round(sum(row["score"] for row in rows) / len(rows), 3),
            "samples": rows,
        }
    return report
