"""Enterprise Agentic RAG API."""

import logfire

from app.config import settings

logfire.configure(
    token=settings.LOGFIRE_TOKEN,
    advanced=logfire.AdvancedOptions(base_url=settings.LOGFIRE_BASE_URL) if settings.LOGFIRE_BASE_URL else None,
)

import time
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from app.agents.graph import build_graph
from app.guardrails import guard, initialize_rails
from app.health import router as health_router
from app.ingestion.routes import router as ingest_router
from app.metrics import GUARDRAILS_BLOCKS_TOTAL, RAG_REQUEST_DURATION, RAG_REQUESTS_TOTAL
from app.streaming import StreamQueryRequest, stream_query
from app.logging import set_request_id
from app.services.health.connection_checker import check_all_connections, log_connection_summary

_security = HTTPBearer(auto_error=False)


def _init_rate_limiter():
    """Initializes Redis-backed rate limiting with an in-memory fallback."""
    from limits.storage import RedisStorage
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.extension import _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address

    try:
        storage = RedisStorage(settings.redis_url)

        if not storage.check() or not storage.storage.ping():
            raise ConnectionError("Redis did not respond to ping")

        app.state.limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=settings.redis_url,
        )
        app.state.rate_limiter_storage = "redis"
        logfire.info("Rate limiting initialized using Redis.")

    except Exception as e:
        app.state.limiter = Limiter(key_func=get_remote_address)
        app.state.rate_limiter_storage = "memory"
        logfire.warning(f"Redis unavailable ({e}); using in-memory rate limiting.")

    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return True


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    """Validates the bearer token when API authentication is enabled."""
    if not settings.API_KEY:
        return None

    if not credentials or credentials.credentials != settings.API_KEY:
        logfire.warning("Unauthorized request: invalid or missing API key.")

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials


def _get_limiter_rule(times: int, seconds: int) -> str:
    """Converts a rate limit into SlowAPI rule syntax."""
    if seconds % 60 == 0:
        return f"{times}/{seconds // 60}minute"

    if seconds % 3600 == 0:
        return f"{times}/{seconds // 3600}hour"

    return f"{times}/{seconds}second"


class _AppLimiter:
    """Applies the rate limiter initialized during application startup."""

    def limit(self, rule_or_callable):
        def decorator(func):
            import asyncio
            import functools

            is_async = asyncio.iscoroutinefunction(func)

            if is_async:

                @functools.wraps(func)
                async def wrapper(*args, **kwargs):
                    limiter = getattr(app.state, "limiter", None)
                    if limiter is None:
                        return await func(*args, **kwargs)
                    rule = rule_or_callable() if callable(rule_or_callable) else rule_or_callable
                    return await limiter.limit(rule)(func)(*args, **kwargs)

            else:

                @functools.wraps(func)
                def wrapper(*args, **kwargs):
                    limiter = getattr(app.state, "limiter", None)
                    if limiter is None:
                        return func(*args, **kwargs)
                    rule = rule_or_callable() if callable(rule_or_callable) else rule_or_callable
                    return limiter.limit(rule)(func)(*args, **kwargs)

            return wrapper

        return decorator


app_limiter = _AppLimiter()


def rate_limit(times: int = None, seconds: int = None):
    """Applies the configured request rate limit."""

    def _resolve_rule() -> str:
        return _get_limiter_rule(
            times or settings.RATE_LIMIT_PER_MINUTE,
            seconds or 60,
        )

    return app_limiter.limit(_resolve_rule)


app = FastAPI(title="Enterprise Agentic RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(ingest_router)

Instrumentator().instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
)


@app.on_event("startup")
def startup_event():
    """Initializes application services and validates external connections."""

    initialize_rails()

    app.state.rag_agent = build_graph()
    app.state.rate_limiter_enabled = _init_rate_limiter()

    connection_results = check_all_connections()
    all_healthy = log_connection_summary(connection_results)

    if settings.STRICT_STARTUP and not all_healthy:
        failed = [
            name
            for name, result in connection_results.items()
            if not result.healthy
        ]
        raise RuntimeError(
            f"STRICT_STARTUP enabled; failing services: {', '.join(failed)}"
        )

    if not settings.API_KEY:
        logfire.warning(
            "RAG_API_KEY is not set. The /query endpoint is publicly accessible."
        )


class QueryRequest(BaseModel):
    q: str
    thread_id: Optional[str] = "default_user"


@app.get("/")
def home():
    """Returns the API status."""
    return {"message": "Enterprise LangGraph RAG API is live."}


@app.get("/graph")
def get_graph_image(_api_key: str = Depends(verify_api_key)):
    """Returns a Mermaid image of the agent workflow."""
    try:
        png_bytes = app.state.rag_agent.get_graph().draw_mermaid_png()
        return Response(content=png_bytes, media_type="image/png")

    except Exception as e:
        return {
            "error": f"Could not generate graph image: {e}",
        }


@app.post("/query")
@rate_limit()
def query(
    request: Request,
    body: QueryRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Runs the RAG pipeline and returns the generated response."""
    q = body.q
    thread_id = body.thread_id
    request_id = str(uuid.uuid4())

    set_request_id(request_id)

    start = time.perf_counter()

    with logfire.span(
        "/query",
        request_id=request_id,
        thread_id=thread_id,
    ):
        rail_fired, rail_response = guard(q)

        if rail_fired:
            GUARDRAILS_BLOCKS_TOTAL.labels(blocked="true").inc()
            RAG_REQUESTS_TOTAL.labels(status="blocked").inc()
            RAG_REQUEST_DURATION.observe(time.perf_counter() - start)

            logfire.info(
                "Request blocked by guardrails.",
                request_id=request_id,
                thread_id=thread_id,
            )

            return {
                "question": q,
                "answer": rail_response,
                "thought_process": [
                    "Intent: Guardrails Fired",
                    "Retrieval: Skipped",
                ],
                "status": "Blocked by guardrails.",
                "sources": [],
            }

        GUARDRAILS_BLOCKS_TOTAL.labels(blocked="false").inc()

        try:
            initial_state = {
                "messages": [
                    {
                        "role": "user",
                        "content": q,
                    }
                ],
                "current_query": q,
                "documents": [],
                "plan": ["Start"],
                "status": "Initializing graph.",
            }

            config = {
                "configurable": {
                    "thread_id": thread_id,
                }
            }

            final_output = app.state.rag_agent.invoke(
                initial_state,
                config=config,
            )

            RAG_REQUESTS_TOTAL.labels(status="success").inc()
            RAG_REQUEST_DURATION.observe(time.perf_counter() - start)

            logfire.info(
                "RAG pipeline completed.",
                request_id=request_id,
                thread_id=thread_id,
            )

            return {
                "question": q,
                "answer": final_output.get("final_answer"),
                "thought_process": final_output.get("plan"),
                "status": final_output.get("status"),
                "sources": final_output.get("documents", []),
            }

        except Exception as e:
            RAG_REQUESTS_TOTAL.labels(status="error").inc()
            RAG_REQUEST_DURATION.observe(time.perf_counter() - start)

            logfire.error(
                f"RAG pipeline failed: {e}",
                request_id=request_id,
                thread_id=thread_id,
            )

            return JSONResponse(
                status_code=500,
                content={
                    "request_id": request_id,
                    "status": "error",
                    "message": "Failed to process request. Please try again later.",
                },
            )


@app.post("/query/stream")
@rate_limit()
async def query_stream(
    request: Request,
    body: StreamQueryRequest,
    _api_key: str = Depends(verify_api_key),
):
    return stream_query(q=body.q, thread_id=body.thread_id or "default_user")
