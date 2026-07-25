from unittest.mock import MagicMock, patch

import pytest

from app.agents.nodes.retriever import retrieve_node
from app.gateway import client as gateway
from app.services.retrieval.ranking_service import _JinaReranker
from app.utils.metrics import LLM_FALLBACKS_TOTAL

pytestmark = pytest.mark.unit


def test_retriever_preserves_source_labels_after_reranking():
    raw_results = [
        {"content": "first chunk", "source": "first.pdf"},
        {"content": "second chunk", "source": "second.md"},
    ]
    state = {"current_query": "question", "plan": ["Start"]}

    with (
        patch("app.agents.nodes.retriever.search_enterprise_knowledge", return_value=raw_results),
        patch("app.agents.nodes.retriever.rerank_documents", return_value=["second chunk", "first chunk"]),
    ):
        result = retrieve_node(state)

    assert result["documents"] == [
        "[S1] SOURCE: second.md\nCONTENT: second chunk",
        "[S2] SOURCE: first.pdf\nCONTENT: first chunk",
    ]


def test_jina_reranker_normalizes_document_object():
    response = MagicMock()
    response.json.return_value = {"results": [{"document": {"text": "second"}, "index": 1}]}
    with patch("app.services.retrieval.ranking_service.requests.post", return_value=response):
        assert _JinaReranker().rerank("q", ["first", "second"], 1) == ["second"]


def test_direct_route_falls_back_to_groq_and_applies_generation_settings(monkeypatch):
    monkeypatch.setattr(gateway.settings, "USE_PORTKEY", False)
    primary = MagicMock(side_effect=RuntimeError("Nebius unavailable"))
    fallback_before = LLM_FALLBACKS_TOTAL.labels(mode="completion")._value.get()
    fallback_response = MagicMock()
    fallback = MagicMock(return_value=fallback_response)

    with (
        patch.object(gateway.nebius_client.chat.completions, "create", primary),
        patch.object(gateway.groq_client.chat.completions, "create", fallback),
    ):
        response = gateway.create_chat_completion(messages=[{"role": "user", "content": "hello"}])

    assert response is fallback_response
    fallback.assert_called_once()
    kwargs = fallback.call_args.kwargs
    assert kwargs["temperature"] == gateway.settings.LLM_TEMPERATURE
    assert kwargs["frequency_penalty"] == gateway.settings.LLM_FREQUENCY_PENALTY
    assert kwargs["seed"] == gateway.settings.LLM_SEED
    assert kwargs["timeout"] == gateway.settings.LLM_REQUEST_TIMEOUT_SECONDS
    assert LLM_FALLBACKS_TOTAL.labels(mode="completion")._value.get() > fallback_before


def test_stream_falls_back_only_before_first_token(monkeypatch):
    monkeypatch.setattr(gateway.settings, "USE_PORTKEY", False)
    fallback = MagicMock(return_value=iter(["fallback-token"]))

    with (
        patch.object(gateway.nebius_client.chat.completions, "create", side_effect=RuntimeError("before output")),
        patch.object(gateway.groq_client.chat.completions, "create", fallback),
    ):
        assert list(gateway.create_chat_completion(messages=[], stream=True)) == ["fallback-token"]

    def partial_stream():
        yield "primary-token"
        raise RuntimeError("after output")

    with (
        patch.object(gateway.nebius_client.chat.completions, "create", return_value=partial_stream()),
        patch.object(gateway.groq_client.chat.completions, "create", fallback),
        pytest.raises(RuntimeError, match="after output"),
    ):
        assert list(gateway.create_chat_completion(messages=[], stream=True)) == ["primary-token"]

    assert fallback.call_count == 1
