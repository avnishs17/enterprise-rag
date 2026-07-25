"""Compare the current NeMo guardrail with Groq GPT-OSS-Safeguard.

This evaluator calls both classifiers directly, so it needs no running FastAPI
server and does not alter production request enforcement.

Usage:
    uv run python -m evals.guardrail_ab
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.guardrails import guard_with_nemo, initialize_nemo_rails
from app.services.safety import classify_with_groq_safeguard

EVAL_DIR = Path(__file__).parent


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    # Nearest-rank percentile: with a small safety suite, p95 must include the
    # slowest request rather than silently reporting the second-slowest one.
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 1)


def _nemo_result(content: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        fired, _ = guard_with_nemo(content)
        return {"blocked": fired, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as error:
        return {"blocked": None, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(error)}


def _safeguard_result(content: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        decision = classify_with_groq_safeguard(content)
        return {
            "blocked": decision.blocked,
            "rule_ids": list(decision.rule_ids),
            "reason": decision.reason,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as error:
        return {"blocked": None, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(error)}


def _summary(rows: list[dict[str, Any]], candidate: str) -> dict[str, float | int]:
    results = [row[candidate] for row in rows]
    completed = [result for result in results if result["blocked"] is not None]
    expected_blocked = [row for row in rows if row["expected_blocked"]]
    false_negatives = sum(
        result["blocked"] is False and row["expected_blocked"]
        for row, result in zip(rows, results, strict=True)
    )
    false_positives = sum(
        result["blocked"] is True and not row["expected_blocked"]
        for row, result in zip(rows, results, strict=True)
    )
    true_positives = sum(
        result["blocked"] is True and row["expected_blocked"]
        for row, result in zip(rows, results, strict=True)
    )
    correct = sum(result["blocked"] == row["expected_blocked"] for row, result in zip(rows, results, strict=True))
    latencies = [float(result["latency_ms"]) for result in completed]
    return {
        "completed": len(completed),
        "errors": len(results) - len(completed),
        "accuracy": round(correct / len(rows), 3) if rows else 0.0,
        "blocking_precision": round(true_positives / (true_positives + false_positives), 3)
        if true_positives + false_positives
        else 0.0,
        "blocking_recall": round(true_positives / len(expected_blocked), 3) if expected_blocked else 0.0,
        "mandatory_block_false_negatives": false_negatives,
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
        "latency_mean_ms": round(statistics.mean(latencies), 1) if latencies else 0.0,
    }


def run(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Run both policies sequentially to give each sample an independent result."""
    initialize_nemo_rails()
    rows = []
    for sample in samples:
        nemo = _nemo_result(sample["input"])
        safeguard = _safeguard_result(sample["input"])
        rows.append(
            {
                "id": sample["id"],
                "input": sample["input"],
                "expected_blocked": sample["expected_blocked"],
                "nemo": nemo,
                "groq_safeguard": safeguard,
                "agree": nemo["blocked"] == safeguard["blocked"],
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "samples": rows,
        "summary": {
            "nemo": _summary(rows, "nemo"),
            "groq_safeguard": _summary(rows, "groq_safeguard"),
            "agreement_rate": round(sum(row["agree"] for row in rows) / len(rows), 3) if rows else 0.0,
        },
        "acceptance_criteria": {
            "mandatory_block_false_negatives": 0,
            "require_no_accuracy_regression": True,
            "require_lower_latency_p95": True,
        },
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A/B evaluate NeMo against Groq GPT-OSS-Safeguard.")
    parser.add_argument("--dataset", type=Path, default=EVAL_DIR / "guardrail_ab_dataset.json")
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "guardrail_ab_report.json")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    samples = json.loads(args.dataset.read_text())["samples"]
    print(f"Running {len(samples)} samples through NeMo and Groq Safeguard...")
    report = run(samples)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for candidate, metrics in report["summary"].items():
        print(f"{candidate}: {metrics}")
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
