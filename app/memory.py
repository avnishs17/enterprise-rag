import logfire
from mem0 import MemoryClient
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from app.config import settings

_client: MemoryClient | None = None


def _get_client() -> MemoryClient | None:
    global _client
    if _client is None and settings.MEM0_API_KEY:
        _client = MemoryClient(api_key=settings.MEM0_API_KEY)
    return _client


def is_enabled() -> bool:
    return bool(settings.MEM0_API_KEY)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=3),
    reraise=False,
    before_sleep=before_sleep_log(logfire, "warning"),
)
def save_exchange(messages: list[dict], thread_id: str) -> None:
    client = _get_client()
    if client is None:
        return

    client.add(messages, user_id=thread_id)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=3),
    reraise=False,
    before_sleep=before_sleep_log(logfire, "warning"),
)
def get_relevant_memories(query: str, thread_id: str, limit: int = 5) -> str:
    client = _get_client()
    if client is None:
        return ""

    results = client.search(
        query,
        filters={"user_id": thread_id},
        limit=limit,
    )
    memories = results.get("results", [])
    if not memories:
        return ""

    lines = [m["memory"] for m in memories if m.get("memory")]
    if not lines:
        return ""

    return "\n".join(f"- {line}" for line in lines)
