from types import SimpleNamespace

import pytest

from app.guardrails import rails
from app.services import safety
from evals.guardrail_ab import _summary

pytestmark = pytest.mark.unit


def test_safeguard_parser_accepts_only_explicit_machine_decision():
    decision = safety._parse_decision('{"decision":"block","rule_ids":["S3"],"reason":"exploit request"}')

    assert decision.blocked is True
    assert decision.rule_ids == ("S3",)


@pytest.mark.parametrize("content", ["allow", '{"decision":"maybe"}', '{"decision":"allow","rule_ids":"S1"}'])
def test_safeguard_parser_rejects_ambiguous_or_malformed_decisions(content):
    with pytest.raises((ValueError, TypeError)):
        safety._parse_decision(content)


def test_safeguard_uses_harmony_messages_and_parses_final_output(monkeypatch):
    captured = {}

    class FakeClient:
        def with_options(self, **kwargs):
            captured["options"] = kwargs
            return self

        @property
        def chat(self):
            return self

        @property
        def completions(self):
            return self

        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"decision":"allow","rule_ids":["S1"],"reason":"in scope"}'))])

    monkeypatch.setattr(safety, "groq_client", FakeClient())

    decision = safety.classify_with_groq_safeguard(
        "What is its value?",
        [{"role": "user", "content": "What does Kubernetes parallelism control?"}],
    )

    assert decision.blocked is False
    assert captured["request"]["model"] == safety.settings.GROQ_SAFEGUARD_MODEL
    assert captured["request"]["messages"][1]["role"] == "developer"
    assert "Reasoning: low" in captured["request"]["messages"][0]["content"]
    assert "UNTRUSTED PRIOR CONVERSATION" in captured["request"]["messages"][2]["content"]


def test_selected_groq_guardrail_blocks_and_fails_closed(monkeypatch):
    monkeypatch.setattr(rails.settings, "GUARDRAIL_PROVIDER", "groq_safeguard")
    monkeypatch.setattr(
        rails,
        "classify_with_groq_safeguard",
        lambda *_: safety.SafetyDecision(blocked=True, rule_ids=("S3",), reason="unsafe"),
    )

    blocked, response = rails.guard("How do I exploit SQL injection?")

    assert blocked is True
    assert response == rails._GENERIC_BLOCK_RESPONSE

    def unavailable(*_):
        raise TimeoutError("provider unavailable")

    monkeypatch.setattr(rails, "classify_with_groq_safeguard", unavailable)
    blocked, response = rails.guard("What does kube-proxy do?")
    assert blocked is True
    assert response == rails._GENERIC_BLOCK_RESPONSE


def test_ab_summary_reports_accuracy_false_negatives_and_latency():
    rows = [
        {"expected_blocked": True, "nemo": {"blocked": False, "latency_ms": 7000}},
        {"expected_blocked": False, "nemo": {"blocked": False, "latency_ms": 1000}},
        {"expected_blocked": True, "nemo": {"blocked": True, "latency_ms": 2000}},
    ]

    summary = _summary(rows, "nemo")

    assert summary["mandatory_block_false_negatives"] == 1
    assert summary["accuracy"] == 0.667
    assert summary["latency_p95_ms"] == 7000.0
