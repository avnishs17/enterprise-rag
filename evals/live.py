"""Live API client and deterministic scoring for the current RAG contract."""

from __future__ import annotations

import json
import random
import re
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import requests

_CITATION = re.compile(r"\[S(\d+)]")
_SOURCE_LABEL = re.compile(r"\[S(\d+)] SOURCE:")


@dataclass(frozen=True)
class EvalClient:
    base_url: str
    api_key: str | None = None
    timeout_seconds: int = 120

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _request_with_retry(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self.base_url.rstrip('/')}{path}"
        for attempt in range(5):
            response = requests.request(method, url, headers=self.headers, timeout=self.timeout_seconds, **kwargs)
            if response.status_code != 429 or attempt == 4:
                response.raise_for_status()
                return response
            retry_after = response.headers.get("retry-after")
            sleep_seconds = float(retry_after) if retry_after else min(60.0, (2 ** attempt) * 2.0) + random.uniform(0.0, 0.5)
            time.sleep(sleep_seconds)
        raise RuntimeError("unreachable")

    def query(self, question: str, thread_id: str) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        response = self._request_with_retry(
            "POST",
            "/query",
            json={"q": question, "thread_id": thread_id},
        )
        return response.json(), round((time.perf_counter() - started) * 1000, 1)

    def delete_conversation(self, thread_id: str) -> None:
        self._request_with_retry("DELETE", f"/conversations/{thread_id}")

    def stream_query(self, question: str, thread_id: str) -> tuple[dict[str, Any], float]:
        """Collect the current SSE contract, including done.sources_used."""
        started = time.perf_counter()
        response = self._request_with_retry(
            "POST",
            "/query/stream",
            json={"q": question, "thread_id": thread_id},
            stream=True,
        )
        event, data_lines = "", []
        answer, thoughts, sources, sources_used = [], [], [], []
        for raw_line in response.iter_lines(decode_unicode=True):
            line = raw_line or ""
            if not line:
                if event and data_lines:
                    data = json.loads("\n".join(data_lines))
                    if event == "token":
                        answer.append(data["content"])
                    elif event == "thought":
                        thoughts.append(data["content"])
                    elif event == "source":
                        sources = data["chunks"]
                    elif event == "done":
                        sources_used = data.get("sources_used", [])
                event, data_lines = "", []
            elif line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        return {
            "answer": "".join(answer),
            "thought_process": thoughts,
            "sources": sources,
            "sources_used": sources_used,
        }, round((time.perf_counter() - started) * 1000, 1)


def is_blocked(response: dict[str, Any]) -> bool:
    return any("intent: guardrails fired" in step.lower() for step in response.get("thought_process", []))


def _term_recall(answer: str, required_terms: Iterable[str]) -> float:
    terms = list(required_terms)
    if not terms:
        return 1.0
    answer = answer.lower()
    return round(sum(term.lower() in answer for term in terms) / len(terms), 3)


def score_rag_sample(sample: dict[str, Any], response: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    answer = response.get("answer", "")
    sources = response.get("sources", [])
    citations = set(_CITATION.findall(answer))
    source_labels = set(_SOURCE_LABEL.findall("\n".join(sources)))
    expected_source = sample["expected_source"].lower()
    return {
        "id": sample["id"],
        "question": sample["question"],
        "reference": sample.get("reference", ""),
        "answer": answer,
        "sources": sources,
        "latency_ms": latency_ms,
        "blocked": is_blocked(response),
        "retrieval_expected": True,
        "retrieval_used": bool(sources),
        "expected_source_found": any(expected_source in source.lower() for source in sources),
        "citation_present": bool(citations),
        "citation_valid": bool(citations) and citations.issubset(source_labels),
        "required_term_recall": _term_recall(answer, sample["required_terms"]),
    }


def run_rag_samples(client: EvalClient, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for sample in samples:
        thread_id = f"eval-rag-{uuid.uuid4().hex}"
        try:
            response, latency_ms = client.query(sample["question"], thread_id)
            results.append(score_rag_sample(sample, response, latency_ms))
        finally:
            client.delete_conversation(thread_id)
    return results


def run_guardrail_samples(client: EvalClient, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for sample in samples:
        thread_id = f"eval-guard-{uuid.uuid4().hex}"
        try:
            response, latency_ms = client.query(sample["input"], thread_id)
            actual = is_blocked(response)
            expected = sample["expected_blocked"]
            results.append({**sample, "actual_blocked": actual, "correct": actual == expected, "latency_ms": latency_ms})
        finally:
            client.delete_conversation(thread_id)
    return results


def run_conversation_samples(client: EvalClient, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for sample in samples:
        thread_id = f"eval-conversation-{uuid.uuid4().hex}"
        turns = []
        try:
            for index, turn in enumerate(sample["turns"]):
                response, latency_ms = client.stream_query(turn["question"], thread_id)
                turns.append({
                    "question": turn["question"], "answer": response["answer"], "latency_ms": latency_ms,
                    "required_term_recall": _term_recall(response["answer"], turn["required_terms"]),
                    "sources_used": response["sources_used"],
                    "history_used": index > 0 and "conversation_history" in response["sources_used"],
                })
            results.append({"id": sample["id"], "turns": turns, "passed": all(t["required_term_recall"] > 0 for t in turns) and turns[-1]["history_used"]})
        finally:
            client.delete_conversation(thread_id)
    return results


def _mean(items: list[dict[str, Any]], key: str) -> float:
    return round(sum(float(item[key]) for item in items) / len(items), 3) if items else 0.0


def summarize(rag: list[dict[str, Any]], guardrails: list[dict[str, Any]], conversations: list[dict[str, Any]]) -> dict[str, float]:
    tp = sum(r["expected_blocked"] and r["actual_blocked"] for r in guardrails)
    fp = sum(not r["expected_blocked"] and r["actual_blocked"] for r in guardrails)
    fn = sum(r["expected_blocked"] and not r["actual_blocked"] for r in guardrails)
    return {
        "rag_retrieval_rate": _mean(rag, "retrieval_used"),
        "rag_expected_source_recall": _mean(rag, "expected_source_found"),
        "rag_citation_coverage": _mean(rag, "citation_present"),
        "rag_citation_validity": _mean(rag, "citation_valid"),
        "rag_required_term_recall": _mean(rag, "required_term_recall"),
        "rag_average_latency_ms": _mean(rag, "latency_ms"),
        "guardrail_precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
        "guardrail_recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
        "guardrail_accuracy": _mean(guardrails, "correct"),
        "conversation_pass_rate": _mean(conversations, "passed"),
    }
