"""Run deterministic live RAG, guardrail, citation, and conversation evaluations.

Usage:
    uv run python -m evals.run
    uv run python -m evals.run --backend-url http://localhost:8000 --api-key "$RAG_API_KEY"
"""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from evals.live import EvalClient, run_conversation_samples, run_guardrail_samples, run_rag_samples, summarize
from evals.ragas_metrics import RagasConfig, run_ragas_metrics

load_dotenv()

EVAL_DIR = Path(__file__).parent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the live Enterprise Agentic RAG API.")
    parser.add_argument("--backend-url", default=os.getenv("EVAL_BACKEND_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY") or os.getenv("RAG_API_KEY"))
    parser.add_argument("--dataset", type=Path, default=EVAL_DIR / "golden_dataset.json")
    parser.add_argument("--output", type=Path, default=EVAL_DIR / "latest_report.json")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--ragas", action="store_true", help="Run LLM-judge RAGAS metrics after the live API evaluation.")
    parser.add_argument(
        "--ragas-from-report",
        type=Path,
        default=None,
        help="Run only RAGAS using an existing eval report, avoiding another live API pass.",
    )
    parser.add_argument("--judge-api-key", default=os.getenv("EVAL_JUDGE_API_KEY") or os.getenv("JUDGE_GROQ_API_KEY"))
    parser.add_argument("--judge-base-url", default=os.getenv("EVAL_JUDGE_BASE_URL") or os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    parser.add_argument("--judge-model", default=os.getenv("EVAL_JUDGE_MODEL", "llama-3.3-70b-versatile"))
    parser.add_argument("--embedding-api-key", default=os.getenv("EVAL_EMBEDDING_API_KEY") or os.getenv("JINA_API_KEY"))
    parser.add_argument("--embedding-base-url", default=os.getenv("EVAL_EMBEDDING_BASE_URL", "https://api.jina.ai/v1"))
    parser.add_argument("--embedding-model", default=os.getenv("EVAL_EMBEDDING_MODEL") or os.getenv("JINA_MODEL", "jina-embeddings-v3"))
    parser.add_argument("--judge-delay", type=float, default=1.0, help="Seconds between judge samples (default: 1).")
    parser.add_argument("--ragas-score-timeout", type=float, default=180.0, help="Seconds before retrying one RAGAS metric/sample score.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.ragas_from_report:
        report = json.loads(args.ragas_from_report.read_text())
        rag = report["rag_samples"]
        print(f"Running RAGAS only for {len(rag)} RAG samples from {args.ragas_from_report}...")
        args.ragas = True
    else:
        dataset = json.loads(args.dataset.read_text())
        client = EvalClient(args.backend_url, args.api_key, args.timeout)

        print(f"Running {len(dataset['rag_samples'])} RAG samples against {args.backend_url}...")
        rag = run_rag_samples(client, dataset["rag_samples"])
        print(f"Running {len(dataset['guardrail_samples'])} guardrail samples...")
        guardrails = run_guardrail_samples(client, dataset["guardrail_samples"])
        print(f"Running {len(dataset['conversation_samples'])} conversation-history samples...")
        conversations = run_conversation_samples(client, dataset["conversation_samples"])

        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "backend_url": args.backend_url,
            "summary": summarize(rag, guardrails, conversations),
            "rag_samples": rag,
            "guardrail_samples": guardrails,
            "conversation_samples": conversations,
        }

    if args.ragas:
        if not args.judge_api_key:
            raise ValueError("--ragas requires EVAL_JUDGE_API_KEY or JUDGE_GROQ_API_KEY.")
        if not args.embedding_api_key:
            raise ValueError("--ragas requires EVAL_EMBEDDING_API_KEY or JINA_API_KEY.")
        print("Running sequential RAGAS judge metrics...")
        report["ragas"] = asyncio.run(
            run_ragas_metrics(
                rag,
                RagasConfig(
                    api_key=args.judge_api_key,
                    base_url=args.judge_base_url,
                    model=args.judge_model,
                    embedding_api_key=args.embedding_api_key,
                    embedding_base_url=args.embedding_base_url,
                    embedding_model=args.embedding_model,
                    delay_seconds=args.judge_delay,
                    score_timeout_seconds=args.ragas_score_timeout,
                ),
            )
        )
    args.output.write_text(json.dumps(report, indent=2) + "\n")

    print("\nEvaluation summary")
    for key, value in report["summary"].items():
        print(f"  {key}: {value}")
    if report.get("ragas"):
        print("\nRAGAS summary")
        for key, value in report["ragas"].items():
            print(f"  {key}: {value['average']}")
    print(f"\nReport written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
