import asyncio
import json
import time
from typing import Optional

import logfire
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.nodes.planner import planner_node
from app.agents.nodes.responder import generate_node_stream
from app.agents.nodes.retriever import retrieve_node
from app.agents.state import AgentState
from app.guardrails import guard
from app.memory import get_relevant_memories, is_enabled as mem0_enabled, save_exchange
from app.metrics import GUARDRAILS_BLOCKS_TOTAL, RAG_REQUEST_DURATION, RAG_REQUESTS_TOTAL

_conversations: dict[str, list[dict]] = {}
_conversations_lock = asyncio.Lock()


class StreamQueryRequest(BaseModel):
    q: str
    thread_id: Optional[str] = "default_user"


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _stream_generator(q: str, thread_id: str):
    loop = asyncio.get_running_loop()
    start = time.perf_counter()

    # 1. Guardrails
    rail_fired, rail_response = await loop.run_in_executor(None, guard, q)

    if rail_fired:
        GUARDRAILS_BLOCKS_TOTAL.labels(blocked="true").inc()
        RAG_REQUESTS_TOTAL.labels(status="blocked").inc()
        RAG_REQUEST_DURATION.observe(time.perf_counter() - start)

        logfire.info("Request blocked by guardrails.", thread_id=thread_id)
        yield _sse("thought", {"content": "Intent: Guardrails Fired"})
        yield _sse("thought", {"content": "Retrieval: Skipped"})
        yield _sse("token", {"content": rail_response})
        yield _sse("done", {"sources": []})
        return

    GUARDRAILS_BLOCKS_TOTAL.labels(blocked="false").inc()

    # 2. Build initial state with conversation history
    async with _conversations_lock:
        history = _conversations.get(thread_id, [])
        messages = history + [{"role": "user", "content": q}]

    state: AgentState = {
        "messages": messages,
        "current_query": q,
        "documents": [],
        "plan": ["Start"],
        "status": "Initializing.",
    }

    # 3. Retrieve relevant memories from Mem0
    if mem0_enabled():
        yield _sse("thought", {"content": "Memory: Retrieving relevant memories..."})
        memories = await loop.run_in_executor(None, get_relevant_memories, q, thread_id)
        if memories:
            state["memories"] = memories
            yield _sse("thought", {"content": f"Memory: Found relevant context ({len(memories.split(chr(10)))} items)"})

    # 4. Run planner
    try:
        plan_result = await loop.run_in_executor(None, planner_node, state)
        state.update(plan_result)
    except Exception as e:
        logfire.error(f"Planner failed: {e}")
        yield _sse("error", {"message": "Failed to classify your request."})
        yield _sse("done", {"sources": []})
        return

    for step in plan_result.get("plan", []):
        yield _sse("thought", {"content": step})

    # 6. Run retriever if needed
    if state["current_query"] != "CONVERSATIONAL":
        try:
            retrieve_result = await loop.run_in_executor(None, retrieve_node, state)
            state.update(retrieve_result)
        except Exception as e:
            logfire.error(f"Retriever failed: {e}")
            retrieve_result = {"documents": [], "plan": ["Retrieval: Failed"]}
            state.update(retrieve_result)

        for step in retrieve_result.get("plan", []):
            yield _sse("thought", {"content": step})

    # 7. Stream responder tokens
    try:
        for token in generate_node_stream(state):
            yield _sse("token", {"content": token})

        result = generate_node_stream.last_result
        sources = state.get("documents", [])
        RAG_REQUESTS_TOTAL.labels(status="success").inc()
    except Exception as e:
        logfire.error(f"Responder failed: {e}")
        yield _sse("error", {"message": "Failed to generate response."})
        result = {"final_answer": "", "status": "error"}
        sources = []
        RAG_REQUESTS_TOTAL.labels(status="error").inc()

    RAG_REQUEST_DURATION.observe(time.perf_counter() - start)

    # 8. Save conversation history
    if result and result.get("final_answer"):
        async with _conversations_lock:
            _conversations[thread_id] = messages + [
                {"role": "assistant", "content": result["final_answer"]}
            ]

        # Save to Mem0 long-term memory
        if mem0_enabled():
            await loop.run_in_executor(
                None,
                save_exchange,
                messages[-1:] + [{"role": "assistant", "content": result["final_answer"]}],
                thread_id,
            )

    # 9. Yield sources and done
    source_texts = []
    for doc in sources:
        if doc.startswith("CONTENT: "):
            source_texts.append(doc[len("CONTENT: "):])
        else:
            source_texts.append(doc)

    sources_used = []
    if state.get("memories"):
        sources_used.append("memory")
    if state.get("current_query") == "CONVERSATIONAL":
        sources_used.append("conversation_history")
    else:
        sources_used.append("rag_documents")

    yield _sse("source", {"chunks": source_texts})
    yield _sse("done", {"sources_used": sources_used})


def stream_query(q: str, thread_id: str):
    return StreamingResponse(
        _stream_generator(q, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
