from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI, OpenAI
from portkey_ai import PORTKEY_GATEWAY_URL, createHeaders

from app.config import settings


# Portkey routing is managed through a saved configuration referenced by
# x-portkey-config-id. Retry, fallback, and caching behavior must be configured
# in Portkey because this workspace does not allow inline configurations.


def _make_headers(feature: str = "rag") -> dict:
    """Build Portkey headers that reference the primary saved config by ID."""
    if not settings.PORTKEY_PRIMARY_CONFIG_ID:
        raise ValueError(
            "PORTKEY_PRIMARY_CONFIG_ID is not set in .env. "
            "Get the real pc-... ID from the Portkey dashboard or "
            "run: PYTHONPATH=. python scripts/list_portkey_configs.py"
        )
    return createHeaders(
        api_key=settings.PORTKEY_API_KEY,
        config_id=settings.PORTKEY_PRIMARY_CONFIG_ID,
        metadata={
            "feature": feature,
            "_user": "rag-system",
            "environment": "production",
        },
    )


# OpenAI-compatible client routed through Portkey using a saved configuration.
# The configuration ID is passed through headers because inline configurations
# are disabled for this workspace.
portkey_client = OpenAI(
    api_key=settings.PORTKEY_API_KEY,
    base_url=PORTKEY_GATEWAY_URL,
    default_headers=_make_headers(),
)

def get_langchain_llm(feature: str = "rag") -> ChatOpenAI:
    """
    Creates a Portkey-backed ChatOpenAI client for use in LangChain nodes.

    Portkey exposes an OpenAI-compatible gateway, allowing ChatOpenAI to connect
    through a custom base URL. Authentication and the saved routing configuration
    are passed through request headers, while the Portkey model slug identifies
    the upstream provider and model.
    """

    return ChatOpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        model=f"@{settings.PORTKEY_PRIMARY_SLUG}/{settings.PRIMARY_MODEL}",
        default_headers=_make_headers(feature),
    )


def get_async_openai_client(feature: str = "rag") -> AsyncOpenAI:
    """Creates an async OpenAI client configured to route requests through Portkey."""
    return AsyncOpenAI(
        api_key=settings.PORTKEY_API_KEY,
        base_url=PORTKEY_GATEWAY_URL,
        default_headers=_make_headers(feature),
    )


def extract_cache_status(response) -> str:
    """Extracts the Portkey cache status from response headers, defaulting to 'MISS'."""
    for attr in ("_raw_response", "_response", "_http_response", "headers"):
        raw = getattr(response, attr, None)
        if raw is not None:
            headers = getattr(raw, "headers", None)
            if headers is not None:
                status = headers.get("x-portkey-cache-status", "")
                if status:
                    return status.upper()
    return "MISS"
