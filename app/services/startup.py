"""FastAPI application lifecycle and startup service initialization."""

from contextlib import asynccontextmanager

import logfire
from fastapi import FastAPI
from langgraph.checkpoint.memory import MemorySaver

from app.agents.graph import build_graph
from app.config import settings
from app.guardrails import initialize_rails
from app.services.health.connection_checker import check_all_connections, log_connection_summary
from app.utils.rate_limiting import initialize_rate_limiter
from app.utils.warnings import configure_warning_filters


def initialize_services(application: FastAPI) -> None:
    """Initialize application dependencies and validate external connections."""
    if settings.is_production and not settings.API_KEY:
        raise RuntimeError("RAG_API_KEY must be set when ENVIRONMENT=production")

    # NeMo changes warning filters during import, so refresh the narrow
    # third-party compatibility filters immediately before parsing its config.
    configure_warning_filters()
    initialize_rails()

    # Query endpoints use the shared Mem0 pipeline. The graph remains only for
    # the optional workflow image and therefore uses an in-memory checkpoint.
    application.state.rag_agent = build_graph(checkpointer=MemorySaver())
    application.state.rate_limiter_enabled = initialize_rate_limiter(application)

    connection_results = check_all_connections()
    all_healthy = log_connection_summary(connection_results)
    if settings.STRICT_STARTUP and not all_healthy:
        failed = [name for name, result in connection_results.items() if not result.healthy]
        raise RuntimeError(f"STRICT_STARTUP enabled; failing services: {', '.join(failed)}")

    if not settings.API_KEY:
        logfire.warning("RAG_API_KEY is not set; this is only appropriate for local development.")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """FastAPI lifespan hook for startup-managed services."""
    initialize_services(application)
    yield
