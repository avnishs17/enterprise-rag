"""Durable, bounded per-thread conversation history backed by Redis."""

import json
from typing import Any

import logfire
from redis import Redis

from app.config import settings

_client: Redis | None = None


def _get_client() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


def _key(thread_id: str) -> str:
    return f"rag:conversation:{thread_id}"


def get_recent_messages(thread_id: str) -> list[dict[str, str]]:
    """Load the bounded exact history for one validated thread ID."""
    try:
        raw_messages = _get_client().lrange(
            _key(thread_id),
            -settings.MAX_CONVERSATION_MESSAGES,
            -1,
        )
        messages: list[dict[str, str]] = []
        for raw in raw_messages:
            message: dict[str, Any] = json.loads(raw)
            if message.get("role") in {"user", "assistant"} and isinstance(message.get("content"), str):
                messages.append({"role": message["role"], "content": message["content"]})
        return messages
    except Exception:
        logfire.exception("Could not load conversation history.", thread_id=thread_id)
        return []


def delete_history(thread_id: str) -> None:
    """Remove the exact Redis transcript for a thread."""
    try:
        _get_client().delete(_key(thread_id))
    except Exception:
        logfire.exception("Could not delete conversation history.", thread_id=thread_id)


def append_exchange(thread_id: str, question: str, answer: str) -> None:
    """Append an exact exchange and expire it after the configured retention period."""
    entries = [
        json.dumps({"role": "user", "content": question}),
        json.dumps({"role": "assistant", "content": answer}),
    ]
    try:
        client = _get_client()
        with client.pipeline() as pipeline:
            pipeline.rpush(_key(thread_id), *entries)
            pipeline.ltrim(_key(thread_id), -settings.MAX_CONVERSATION_MESSAGES, -1)
            pipeline.expire(_key(thread_id), settings.CONVERSATION_HISTORY_TTL_SECONDS)
            pipeline.execute()
    except Exception:
        # A history outage must not discard an otherwise completed answer.
        logfire.exception("Could not persist conversation history.", thread_id=thread_id)
