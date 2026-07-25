"""LLM clients and routing.

Portkey can be enabled when its account/config is available. Otherwise requests
are sent directly to Nebius and transparently retried once through Groq when
Nebius fails before producing output.
"""

from collections.abc import Iterator
from typing import Any

import logfire
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI, OpenAI
from portkey_ai import PORTKEY_GATEWAY_URL, createHeaders

from app.config import settings
from app.utils.metrics import LLM_FALLBACKS_TOTAL


def _make_portkey_headers(feature: str = "rag") -> dict[str, str]:
    if not settings.PORTKEY_PRIMARY_CONFIG_ID:
        raise ValueError("PORTKEY_PRIMARY_CONFIG_ID must be set when USE_PORTKEY=true")
    return createHeaders(
        api_key=settings.PORTKEY_API_KEY,
        config_id=settings.PORTKEY_PRIMARY_CONFIG_ID,
        metadata={"feature": feature, "_user": "rag-system", "environment": settings.ENVIRONMENT},
    )


nebius_client = OpenAI(api_key=settings.NEBIUS_API_KEY, base_url=settings.NEBIUS_BASE_URL)
groq_client = OpenAI(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL)

# Do not construct/configure Portkey in direct mode: an expired gateway account
# must not prevent the application from starting or serving Nebius requests.
portkey_client: OpenAI | None = None
if settings.USE_PORTKEY:
    portkey_client = OpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        default_headers=_make_portkey_headers(),
    )


def _direct_completion(messages: list[dict[str, Any]], stream: bool, **kwargs: Any):
    if not stream:
        try:
            return nebius_client.chat.completions.create(
                model=settings.NEBIUS_MODEL, messages=messages, stream=False, **kwargs
            )
        except Exception as error:
            logfire.warning("Nebius request failed; routing to Groq fallback.", error=str(error))
            LLM_FALLBACKS_TOTAL.labels(mode="completion").inc()
            return groq_client.chat.completions.create(
                model=settings.FALLBACK_LLM_MODEL, messages=messages, stream=False, **kwargs
            )

    def stream_with_fallback() -> Iterator[Any]:
        emitted = False
        try:
            primary_stream = nebius_client.chat.completions.create(
                model=settings.NEBIUS_MODEL, messages=messages, stream=True, **kwargs
            )
            for chunk in primary_stream:
                emitted = True
                yield chunk
            return
        except Exception as error:
            # Never restart a response after tokens have reached the user.
            if emitted:
                raise
            logfire.warning("Nebius stream failed before output; routing to Groq fallback.", error=str(error))
            LLM_FALLBACKS_TOTAL.labels(mode="stream").inc()

        fallback_stream = groq_client.chat.completions.create(
            model=settings.FALLBACK_LLM_MODEL, messages=messages, stream=True, **kwargs
        )
        yield from fallback_stream

    return stream_with_fallback()


def create_chat_completion(
    *, messages: list[dict[str, Any]], stream: bool = False, feature: str = "rag", **kwargs: Any
):
    """Create a completion through Portkey or the direct Nebius→Groq route."""
    generation_kwargs = {
        "temperature": settings.LLM_TEMPERATURE,
        "frequency_penalty": settings.LLM_FREQUENCY_PENALTY,
        # This is an SDK read/idle timeout. It prevents an upstream model
        # stream that stops yielding chunks from holding a request forever.
        "timeout": settings.LLM_REQUEST_TIMEOUT_SECONDS,
        **kwargs,
    }
    # Nebius and Groq both support seed; leave it out of Portkey because a
    # future configured provider may not accept that parameter.
    if not settings.USE_PORTKEY:
        generation_kwargs.setdefault("seed", settings.LLM_SEED)

    if settings.USE_PORTKEY:
        if portkey_client is None:  # Defensive; should be impossible after startup.
            raise RuntimeError("Portkey client is not configured")
        return portkey_client.chat.completions.create(
            model=f"@{settings.PORTKEY_PRIMARY_SLUG}/{settings.PRIMARY_MODEL}",
            messages=messages,
            stream=stream,
            **generation_kwargs,
        )
    return _direct_completion(messages, stream, **generation_kwargs)


def get_langchain_llm(feature: str = "rag") -> ChatOpenAI:
    """Return the primary LangChain client used by NeMo Guardrails."""
    if settings.USE_PORTKEY:
        return ChatOpenAI(
            api_key=settings.PORTKEY_API_KEY,
            base_url=PORTKEY_GATEWAY_URL,
            model=f"@{settings.PORTKEY_PRIMARY_SLUG}/{settings.PRIMARY_MODEL}",
            default_headers=_make_portkey_headers(feature),
        )
    return ChatOpenAI(
        api_key=settings.NEBIUS_API_KEY,
        base_url=settings.NEBIUS_BASE_URL,
        model=settings.NEBIUS_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        seed=settings.LLM_SEED,
        frequency_penalty=settings.LLM_FREQUENCY_PENALTY,
    )


def get_fallback_langchain_llm() -> ChatOpenAI:
    """Return Groq for non-Portkey Guardrails failover."""
    return ChatOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url=settings.GROQ_BASE_URL,
        model=settings.FALLBACK_LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        seed=settings.LLM_SEED,
        frequency_penalty=settings.LLM_FREQUENCY_PENALTY,
    )


def get_async_openai_client(feature: str = "rag") -> AsyncOpenAI:
    """Return the primary async client for integrations that require one."""
    if settings.USE_PORTKEY:
        return AsyncOpenAI(
            api_key=settings.PORTKEY_API_KEY,
            base_url=PORTKEY_GATEWAY_URL,
            default_headers=_make_portkey_headers(feature),
        )
    return AsyncOpenAI(api_key=settings.NEBIUS_API_KEY, base_url=settings.NEBIUS_BASE_URL)


def extract_cache_status(response: Any) -> str:
    """Read Portkey cache status; direct-provider responses are cache misses."""
    for attr in ("_raw_response", "_response", "_http_response", "headers"):
        raw = getattr(response, attr, None)
        if raw is not None:
            headers = getattr(raw, "headers", None)
            if headers is not None:
                status = headers.get("x-portkey-cache-status", "")
                if status:
                    return status.upper()
    return "MISS"
