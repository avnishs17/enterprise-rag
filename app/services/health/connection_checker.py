"""Run health checks for all external services.

Usage:
    python -m app.services.health.connection_checker
"""

from __future__ import annotations

import sys
from typing import Callable

import logfire
import requests
from psycopg_pool import ConnectionPool
from qdrant_client import QdrantClient
from redis import Redis

from app.config import settings
from app.gateway.client import portkey_client


class ConnectionResult:
    """Represents the result of a service health check."""

    def __init__(self, name: str, healthy: bool, message: str = ""):
        self.name = name
        self.healthy = healthy
        self.message = message

    def to_dict(self) -> dict[str, object]:
        status = "ok" if self.healthy else "unavailable"
        if self.message:
            status = f"{status}: {self.message}"
        return {
            "status": status,
            "healthy": self.healthy,
            "message": self.message,
        }


def _check_neon_postgres() -> ConnectionResult:
    """Checks Neon Postgres connectivity."""
    pool = None
    conn = None

    try:
        pool = ConnectionPool(
            conninfo=settings.postgres_uri,
            min_size=1,
            max_size=2,
            open=True,
            timeout=5,
            check=ConnectionPool.check_connection,
        )
        conn = pool.getconn(timeout=5)

        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

        return ConnectionResult("postgres", True, "Neon Postgres reachable")

    except Exception as e:
        logfire.warning(f"Postgres health check failed: {e}")
        return ConnectionResult("postgres", False, str(e))

    finally:
        if conn is not None and pool is not None:
            try:
                pool.putconn(conn)
            except Exception:
                pass

        if pool is not None:
            try:
                pool.close(timeout=5)
            except Exception:
                pass


def _check_upstash_redis() -> ConnectionResult:
    """Checks Upstash Redis connectivity."""
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
        return ConnectionResult("redis", True, "Upstash Redis reachable")

    except Exception as e:
        logfire.warning(f"Redis health check failed: {e}")
        return ConnectionResult("redis", False, str(e))


def _check_qdrant() -> ConnectionResult:
    """Checks Qdrant connectivity."""
    try:
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=5,
        )
        client.get_collections()
        return ConnectionResult("qdrant", True, "Qdrant reachable")

    except Exception as e:
        logfire.warning(f"Qdrant health check failed: {e}")
        return ConnectionResult("qdrant", False, str(e))


def _check_portkey_gateway() -> ConnectionResult:
    """Checks Portkey gateway connectivity."""
    try:
        response = portkey_client.chat.completions.create(
            model=f"@{settings.PORTKEY_PRIMARY_SLUG}/gpt-5-mini",
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_completion_tokens=100,
            timeout=10,
        )

        if response.choices and response.choices[0].message.content is not None:
            return ConnectionResult(
                "llm_gateway",
                True,
                "Portkey gateway reachable",
            )

        raise RuntimeError("Empty response")

    except Exception as e:
        logfire.warning(f"Portkey gateway health check failed: {e}")
        return ConnectionResult("llm_gateway", False, str(e))

def _check_portkey_fallback() -> ConnectionResult:
    """Checks Portkey fallback provider connectivity."""
    try:
        response = portkey_client.chat.completions.create(
            model=f"@{settings.PORTKEY_FALLBACK_SLUG}/{settings.FALLBACK_LLM_MODEL}",
            messages=[{"role": "user", "content": "Say hello in one word."}],
            max_completion_tokens=100,
            timeout=10,
        )

        if response.choices and response.choices[0].message.content is not None:
            return ConnectionResult(
                "llm_fallback",
                True,
                "Portkey fallback reachable",
            )

        raise RuntimeError("Empty response")

    except Exception as e:
        logfire.warning(f"Portkey fallback health check failed: {e}")
        return ConnectionResult("llm_fallback", False, str(e))

def _check_jina_embeddings() -> ConnectionResult:
    """Checks Jina Embeddings API connectivity."""
    if not settings.JINA_API_KEY:
        return ConnectionResult(
            "jina_embeddings",
            False,
            "JINA_API_KEY not set",
        )

    try:
        response = requests.post(
            settings.JINA_EMBEDDING_URL,
            headers={
                "Authorization": f"Bearer {settings.JINA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.JINA_MODEL,
                "task": "retrieval.query",
                "normalized": True,
                "input": ["probe"],
            },
            timeout=15,
        )
        response.raise_for_status()

        if not response.json().get("data"):
            raise RuntimeError("Empty embedding data")

        return ConnectionResult(
            "jina_embeddings",
            True,
            "Jina Embeddings API reachable",
        )

    except Exception as e:
        logfire.warning(f"Jina Embeddings health check failed: {e}")
        return ConnectionResult("jina_embeddings", False, str(e))


def _check_jina_reranker() -> ConnectionResult:
    """Checks Jina Reranker API connectivity."""
    if not settings.JINA_API_KEY:
        return ConnectionResult(
            "jina_reranker",
            False,
            "JINA_API_KEY not set",
        )

    try:
        response = requests.post(
            settings.JINA_RERANK_URL,
            headers={
                "Authorization": f"Bearer {settings.JINA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.JINA_RERANK_MODEL,
                "query": "health check",
                "documents": ["document one", "document two"],
                "top_n": 2,
                "return_documents": True,
            },
            timeout=15,
        )
        response.raise_for_status()

        if "results" not in response.json():
            raise RuntimeError("Missing results")

        return ConnectionResult(
            "jina_reranker",
            True,
            "Jina Reranker API reachable",
        )

    except Exception as e:
        logfire.warning(f"Jina Reranker health check failed: {e}")
        return ConnectionResult("jina_reranker", False, str(e))


def _check_logfire() -> ConnectionResult:
    """Checks whether Logfire is configured."""
    if not settings.LOGFIRE_TOKEN:
        return ConnectionResult("logfire", False, "LOGFIRE_TOKEN not set")

    return ConnectionResult("logfire", True, "Logfire configured")


def _check_langsmith() -> ConnectionResult:
    """Checks LangSmith connectivity."""
    if not settings.LANGSMITH_API_KEY:
        return ConnectionResult(
            "langsmith",
            False,
            "LANGSMITH_API_KEY not set",
        )

    try:
        response = requests.get(
            f"{settings.LANGSMITH_ENDPOINT}/ok",
            headers={"x-api-key": settings.LANGSMITH_API_KEY},
            timeout=5,
        )
        response.raise_for_status()

        return ConnectionResult(
            "langsmith",
            True,
            f"LangSmith reachable (project: {settings.LANGSMITH_PROJECT})",
        )

    except Exception as e:
        logfire.warning(f"LangSmith health check failed: {e}")
        return ConnectionResult("langsmith", False, str(e))


# Ordered list of all checks to run during startup and /ready.
_CHECKERS: list[Callable[[], ConnectionResult]] = [
    _check_neon_postgres,
    _check_upstash_redis,
    _check_qdrant,
    _check_portkey_gateway,
    _check_portkey_fallback,
    _check_jina_embeddings,
    _check_jina_reranker,
    _check_logfire,
    _check_langsmith,
]


def check_all_connections() -> dict[str, ConnectionResult]:
    """Runs all service health checks."""
    results: dict[str, ConnectionResult] = {}

    for checker in _CHECKERS:
        result = checker()
        results[result.name] = result

    return results


def log_connection_summary(results: dict[str, ConnectionResult]) -> bool:
    """Logs connection results and returns whether all checks passed."""
    healthy = all(result.healthy for result in results.values())

    for name, result in results.items():
        logfire.info(f"{name}: {result.message or result.to_dict()['status']}")

    if healthy:
        logfire.info("All external connections are healthy.")
    else:
        logfire.warning("Some external connections are unavailable.")

    return healthy


def _print_cli_report(results: dict[str, ConnectionResult]) -> int:
    """Prints a CLI report and returns an exit code."""
    healthy = True

    print("\nExternal Connection Health Report")
    print("=" * 50)

    for name, result in results.items():
        status = "OK" if result.healthy else "FAIL"
        print(f"{status:4} {name:20} {result.message}")

        if not result.healthy:
            healthy = False

    print("=" * 50)

    if healthy:
        print("All connections healthy.")
        return 0

    print("One or more connections failed.")
    return 1


if __name__ == "__main__":
    sys.exit(_print_cli_report(check_all_connections()))
