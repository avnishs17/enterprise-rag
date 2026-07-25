import pytest

from evals.live import is_blocked, score_rag_sample, summarize
from evals.ragas_metrics import MAX_CONTEXT_CHARS, _inputs, _metric_inputs

pytestmark = pytest.mark.unit


def test_rag_scoring_requires_valid_source_citations():
    sample = {
        "id": "sample", "question": "question", "required_terms": ["pod", "ip"], "expected_source": "architecture.pptx"
    }
    response = {
        "answer": "A Pod has an IP address. [S1]",
        "sources": ["[S1] SOURCE: architecture.pptx\nCONTENT: Pods have a cluster unique IP."],
        "thought_process": ["Intent: Technical"],
    }

    result = score_rag_sample(sample, response, 12.5)

    assert result["expected_source_found"] is True
    assert result["citation_present"] is True
    assert result["citation_valid"] is True
    assert result["required_term_recall"] == 1.0


def test_ragas_input_uses_live_response_sources_and_reference():
    result = {
        "question": "What is a Pod?",
        "answer": "A Pod runs containers. [S1]",
        "reference": "A Pod is the smallest deployable Kubernetes unit.",
        "sources": ["x" * (MAX_CONTEXT_CHARS + 1)],
    }

    inputs = _inputs(result)

    assert inputs["user_input"] == result["question"]
    assert inputs["response"] == result["answer"]
    assert inputs["reference"] == result["reference"]
    assert len(inputs["retrieved_contexts"][0]) == MAX_CONTEXT_CHARS


def test_ragas_metric_inputs_match_metric_signatures():
    result = {
        "question": "What is a Pod?",
        "answer": "A Pod runs containers. [S1]",
        "reference": "A Pod is the smallest deployable Kubernetes unit.",
        "sources": ["[S1] source"],
    }

    assert set(_metric_inputs("faithfulness", result)) == {"user_input", "response", "retrieved_contexts"}
    assert set(_metric_inputs("answer_relevancy", result)) == {"user_input", "response"}
    assert set(_metric_inputs("context_precision", result)) == {"user_input", "reference", "retrieved_contexts"}
    assert set(_metric_inputs("context_recall", result)) == {"user_input", "reference", "retrieved_contexts"}
    assert set(_metric_inputs("answer_correctness", result)) == {"user_input", "response", "reference"}


def test_guardrail_detection_uses_current_thought_process_contract():
    assert is_blocked({"thought_process": ["Intent: Guardrails Fired"]}) is True
    assert is_blocked({"thought_process": ["Intent: Technical"]}) is False


def test_summary_reports_rag_guardrail_and_conversation_metrics():
    summary = summarize(
        [{"retrieval_used": True, "expected_source_found": True, "citation_present": True, "citation_valid": True, "required_term_recall": 1.0, "latency_ms": 10}],
        [
            {"expected_blocked": True, "actual_blocked": True, "correct": True},
            {"expected_blocked": False, "actual_blocked": False, "correct": True},
        ],
        [{"passed": True}],
    )

    assert summary["rag_citation_validity"] == 1.0
    assert summary["guardrail_precision"] == 1.0
    assert summary["guardrail_recall"] == 1.0
    assert summary["conversation_pass_rate"] == 1.0
