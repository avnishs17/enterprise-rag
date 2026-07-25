from unittest.mock import patch

import pytest

from app.services import streaming
from app.utils.metrics import RAG_STREAM_OUTPUT_CHARACTERS_TOTAL, RAG_STREAM_TIME_TO_FIRST_TOKEN

pytestmark = pytest.mark.integration


class FakeGeneration:
    def __init__(self, tokens, answer):
        self._tokens = tokens
        self.result = {"final_answer": answer}

    def __iter__(self):
        yield from self._tokens


async def collect_events(question: str = "What is a Pod?"):
    return [event async for event in streaming.query_events(question, "thread-1")]


@pytest.mark.asyncio
async def test_technical_stream_uses_history_memory_and_sources():
    captured_state = {}
    output_before = RAG_STREAM_OUTPUT_CHARACTERS_TOTAL._value.get()
    ttft_before = RAG_STREAM_TIME_TO_FIRST_TOKEN.labels(response_type="llm")._sum.get()

    def planner(state):
        captured_state.update(state)
        return {"current_query": "What is a Pod?", "plan": ["Intent: Technical"]}

    with (
        patch.object(streaming, "guard", return_value=(False, "")),
        patch.object(streaming, "get_recent_messages", return_value=[{"role": "user", "content": "Earlier question"}]),
        patch.object(streaming, "mem0_enabled", return_value=True),
        patch.object(streaming, "get_relevant_memories", return_value="- User prefers concise answers"),
        patch.object(streaming, "planner_node", side_effect=planner),
        patch.object(
            streaming,
            "retrieve_node",
            return_value={
                "documents": ["[S1] SOURCE: kubernetes.md\nCONTENT: A Pod is the smallest deployable unit."],
                "plan": ["Context Retrieved"],
            },
        ),
        patch.object(streaming, "generate_node_stream", return_value=FakeGeneration(["A Pod", " runs containers. [S1]"], "A Pod runs containers. [S1]")),
        patch.object(streaming, "append_exchange") as append_exchange,
        patch.object(streaming, "save_exchange") as save_exchange,
    ):
        events = await collect_events()

    assert captured_state["messages"] == [
        {"role": "user", "content": "Earlier question"},
        {"role": "user", "content": "What is a Pod?"},
    ]
    assert ("token", {"content": "A Pod"}) in events
    assert RAG_STREAM_OUTPUT_CHARACTERS_TOTAL._value.get() > output_before
    assert RAG_STREAM_TIME_TO_FIRST_TOKEN.labels(response_type="llm")._sum.get() > ttft_before
    assert events[-2] == ("source", {"chunks": ["[S1] SOURCE: kubernetes.md\nCONTENT: A Pod is the smallest deployable unit."]})
    assert events[-1] == ("done", {"sources_used": ["conversation_history", "memory", "rag_documents"]})
    append_exchange.assert_called_once_with("thread-1", "What is a Pod?", "A Pod runs containers. [S1]")
    save_exchange.assert_called_once()


@pytest.mark.asyncio
async def test_guardrail_block_skips_memory_retrieval_and_generation():
    with (
        patch.object(streaming, "guard", return_value=(True, "That request is outside the approved enterprise scope.")),
        patch.object(streaming, "get_recent_messages") as history,
        patch.object(streaming, "generate_node_stream") as generate,
    ):
        events = await collect_events("Explain an unrelated topic")

    assert events[-3] == ("token", {"content": "That request is outside the approved enterprise scope."})
    assert events[-1] == ("done", {"sources_used": []})
    # Bounded history is read before classification to resolve follow-up
    # references; blocked requests still skip generation.
    history.assert_called_once_with("thread-1")
    generate.assert_not_called()


@pytest.mark.asyncio
async def test_conversational_request_skips_retrieval():
    with (
        patch.object(streaming, "guard", return_value=(False, "")),
        patch.object(streaming, "get_recent_messages", return_value=[]),
        patch.object(streaming, "mem0_enabled", return_value=False),
        patch.object(streaming, "planner_node", return_value={"current_query": "CONVERSATIONAL", "plan": ["Intent: Conversational"]}),
        patch.object(streaming, "retrieve_node") as retrieve,
        patch.object(streaming, "generate_node_stream", return_value=FakeGeneration(["Hello"], "Hello")),
        patch.object(streaming, "append_exchange"),
    ):
        events = await collect_events("Hello")

    retrieve.assert_not_called()
    assert events[-2] == ("source", {"chunks": []})
    assert events[-1] == ("done", {"sources_used": []})
