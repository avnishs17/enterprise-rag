"""Enterprise Agentic RAG API."""

from app.utils.warnings import configure_warning_filters

# Apply filters before importing LangGraph/NeMo transitively through app modules.
configure_warning_filters()

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import settings
from app.services.conversation_routes import router as conversation_router
from app.services.health.routes import router as health_router
from app.ingestion.routes import router as ingest_router
from app.utils.security import verify_api_key
from app.services.startup import lifespan
from app.services.streaming import StreamQueryRequest, query_events, stream_query
from app.utils.observability import configure_logfire

configure_logfire()

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


app = FastAPI(title="Enterprise Agentic RAG API", lifespan=lifespan)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_hosts,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(conversation_router)

Instrumentator().instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
)


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
async def query(
    request: Request,
    body: StreamQueryRequest,
    _api_key: str = Depends(verify_api_key),
):
    """Run the same Mem0-backed pipeline as /query/stream and collect its result."""
    answer_parts: list[str] = []
    thought_process: list[str] = []
    sources: list[str] = []
    error: str | None = None

    async for event, data in query_events(body.q, body.thread_id):
        if event == "token":
            answer_parts.append(data["content"])
        elif event == "thought":
            thought_process.append(data["content"])
        elif event == "source":
            sources = data["chunks"]
        elif event == "error":
            error = data["message"]

    if error:
        return {"question": body.q, "answer": "", "thought_process": thought_process, "status": "error", "sources": sources, "message": error}

    return {
        "question": body.q,
        "answer": "".join(answer_parts),
        "thought_process": thought_process,
        "status": "Response generated.",
        "sources": sources,
    }


@app.post("/query/stream")
@rate_limit()
async def query_stream(
    request: Request,
    body: StreamQueryRequest,
    _api_key: str = Depends(verify_api_key),
):
    return stream_query(q=body.q, thread_id=body.thread_id)
