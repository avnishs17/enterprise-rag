"""Shared streaming and non-streaming query execution.

Both API endpoints use this pipeline so Mem0 retrieval and persistence have
identical behavior.  Short-term in-process conversation state is deliberately
not used: it is unsafe across workers and would make endpoint behavior diverge.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import logfire
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agents.nodes.planner import planner_node
from app.agents.nodes.responder import StreamGeneration, generate_node_stream
from app.agents.nodes.retriever import retrieve_node
from app.agents.state import AgentState
from app.guardrails import guard
from app.services.conversation import append_exchange, get_recent_messages
from app.services.memory import get_relevant_memories, save_exchange
from app.services.memory import is_enabled as mem0_enabled
from app.utils.metrics import (
    GUARDRAILS_BLOCKS_TOTAL,
    RAG_ACTIVE_STREAMS,
    RAG_PIPELINE_STAGE_DURATION,
    RAG_REQUEST_DURATION,
    RAG_REQUESTS_TOTAL,
    RAG_STREAM_OUTPUT_CHARACTERS_TOTAL,
    RAG_STREAM_TIME_TO_FIRST_TOKEN,
)


class StreamQueryRequest(BaseModel):
    q: str = Field(min_length=1, max_length=8_000)
    thread_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

    @field_validator("q")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank")
        return value


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _produce_stream_tokens(
    generation: StreamGeneration,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[tuple[str, object]],
) -> None:
    """Consume one generation in one worker thread.

    A Logfire/OpenTelemetry span uses ContextVar tokens which must be entered
    and exited in the same thread. Calling ``next()`` through a new
    ``asyncio.to_thread`` call for every token can violate that requirement.
    """
    try:
        for token in generation:
            loop.call_soon_threadsafe(queue.put_nowait, ("token", token))
    except BaseException as error:
        loop.call_soon_threadsafe(queue.put_nowait, ("error", error))
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, ("done", None))


async def query_events(q: str, thread_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """Run one query and emit structured events for either HTTP endpoint."""
    loop = asyncio.get_running_loop()
    start = time.perf_counter()

    # The safety classifier receives bounded recent history only to resolve
    # references such as "what is its value?". It still classifies the latest
    # user message, and treats history as untrusted reference material.
    history = await asyncio.to_thread(get_recent_messages, thread_id)
    guard_started = time.perf_counter()
    rail_fired, rail_response = await asyncio.to_thread(guard, q, history)
    RAG_PIPELINE_STAGE_DURATION.labels(stage="guardrails").observe(time.perf_counter() - guard_started)
    if rail_fired:
        GUARDRAILS_BLOCKS_TOTAL.labels(blocked="true").inc()
        RAG_REQUESTS_TOTAL.labels(status="blocked").inc()
        RAG_REQUEST_DURATION.observe(time.perf_counter() - start)
        logfire.info("Request blocked by guardrails.", thread_id=thread_id)
        yield "thought", {"content": "Intent: Guardrails Fired"}
        yield "thought", {"content": "Retrieval: Skipped"}
        RAG_STREAM_TIME_TO_FIRST_TOKEN.labels(response_type="guardrail").observe(time.perf_counter() - start)
        RAG_STREAM_OUTPUT_CHARACTERS_TOTAL.inc(len(rail_response))
        yield "token", {"content": rail_response}
        yield "source", {"chunks": []}
        yield "done", {"sources_used": []}
        return

    GUARDRAILS_BLOCKS_TOTAL.labels(blocked="false").inc()

    # Exact Redis history preserves the latest thread turns. Mem0 remains the
    # semantic long-term memory layer and is fetched separately below.
    state: AgentState = {
        "messages": history + [{"role": "user", "content": q}],
        "current_query": q,
        "documents": [],
        "plan": ["Start"],
        "status": "Initializing.",
    }

    if mem0_enabled():
        yield "thought", {"content": "Memory: Retrieving relevant memories..."}
        memory_started = time.perf_counter()
        memories = await loop.run_in_executor(None, get_relevant_memories, q, thread_id)
        RAG_PIPELINE_STAGE_DURATION.labels(stage="memory").observe(time.perf_counter() - memory_started)
        if memories:
            state["memories"] = memories
            yield "thought", {
                "content": f"Memory: Found relevant context ({len(memories.splitlines())} items)"
            }

    try:
        planner_started = time.perf_counter()
        plan_result = await asyncio.to_thread(planner_node, state)
        RAG_PIPELINE_STAGE_DURATION.labels(stage="planner").observe(time.perf_counter() - planner_started)
        state.update(plan_result)
    except Exception:
        logfire.exception("Planner failed.", thread_id=thread_id)
        RAG_REQUESTS_TOTAL.labels(status="error").inc()
        RAG_REQUEST_DURATION.observe(time.perf_counter() - start)
        yield "error", {"message": "Unable to process this request. Please try again."}
        yield "done", {"sources_used": []}
        return

    for step in plan_result.get("plan", []):
        yield "thought", {"content": step}

    if state["current_query"] != "CONVERSATIONAL":
        try:
            retrieval_started = time.perf_counter()
            retrieve_result = await asyncio.to_thread(retrieve_node, state)
            RAG_PIPELINE_STAGE_DURATION.labels(stage="retrieval").observe(time.perf_counter() - retrieval_started)
            state.update(retrieve_result)
        except Exception:
            logfire.exception("Retriever failed.", thread_id=thread_id)
            retrieve_result = {"documents": [], "plan": ["Retrieval: Failed"]}
            state.update(retrieve_result)

        for step in retrieve_result.get("plan", []):
            yield "thought", {"content": step}

    result: dict[str, Any] | None = None
    sources = state.get("documents", [])
    first_token_emitted = False
    generation_started = time.perf_counter()
    try:
        generation = generate_node_stream(state)
        token_queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()
        worker = asyncio.create_task(
            asyncio.to_thread(_produce_stream_tokens, generation, loop, token_queue)
        )
        try:
            while True:
                event, payload = await token_queue.get()
                if event == "token":
                    content = str(payload)
                    if not first_token_emitted:
                        first_token_emitted = True
                        RAG_STREAM_TIME_TO_FIRST_TOKEN.labels(response_type="llm").observe(time.perf_counter() - start)
                    RAG_STREAM_OUTPUT_CHARACTERS_TOTAL.inc(len(content))
                    yield "token", {"content": content}
                elif event == "error":
                    raise payload  # type: ignore[misc]
                elif event == "done":
                    break
            await worker
        finally:
            # A synchronous provider stream cannot be force-cancelled safely;
            # consume its task exception so disconnects do not leak warnings.
            if not worker.done():
                worker.add_done_callback(lambda task: task.exception())

        result = generation.result
        if not result:
            raise RuntimeError("Streaming provider finished without a result")
        RAG_PIPELINE_STAGE_DURATION.labels(stage="generation").observe(time.perf_counter() - generation_started)
        RAG_REQUESTS_TOTAL.labels(status="success").inc()
    except asyncio.CancelledError:
        # The client left; do not persist a partial assistant response.
        raise
    except Exception:
        logfire.exception("Responder failed.", thread_id=thread_id)
        RAG_REQUESTS_TOTAL.labels(status="error").inc()
        sources = []
        yield "error", {"message": "Unable to generate a response. Please try again."}

    RAG_REQUEST_DURATION.observe(time.perf_counter() - start)

    if result and result.get("final_answer"):
        answer = result["final_answer"]
        # Persist exact recent history independently of Mem0. This is what
        # makes follow-up questions reliable across API workers/restarts.
        await asyncio.to_thread(append_exchange, thread_id, q, answer)

        if mem0_enabled():
            try:
                await loop.run_in_executor(
                    None,
                    save_exchange,
                    [
                        {"role": "user", "content": q},
                        {"role": "assistant", "content": answer},
                    ],
                    thread_id,
                )
            except Exception:
                # Memory outages must not turn a completed answer into a failed request.
                logfire.exception("Could not persist Mem0 exchange.", thread_id=thread_id)

    source_texts = [doc.removeprefix("CONTENT: ") for doc in sources]
    sources_used: list[str] = []
    if history:
        sources_used.append("conversation_history")
    if state.get("memories"):
        sources_used.append("memory")
    if state.get("current_query") != "CONVERSATIONAL":
        sources_used.append("rag_documents")

    yield "source", {"chunks": source_texts}
    yield "done", {"sources_used": sources_used}


async def _sse_generator(q: str, thread_id: str) -> AsyncIterator[str]:
    RAG_ACTIVE_STREAMS.inc()
    try:
        async for event, data in query_events(q, thread_id):
            yield _sse(event, data)
    finally:
        RAG_ACTIVE_STREAMS.dec()


def stream_query(q: str, thread_id: str) -> StreamingResponse:
    return StreamingResponse(
        _sse_generator(q, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
