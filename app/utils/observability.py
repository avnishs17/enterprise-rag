"""Process-wide observability initialization."""

import logfire

from app.config import settings

_configured = False


def configure_logfire() -> None:
    """Configure Logfire once, even when ingestion is imported by the API."""
    global _configured
    if _configured:
        return

    logfire.configure(
        token=settings.LOGFIRE_TOKEN,
        service_name=settings.LOGFIRE_PROJECT,
        advanced=logfire.AdvancedOptions(base_url=settings.LOGFIRE_BASE_URL) if settings.LOGFIRE_BASE_URL else None,
    )
    _configured = True
