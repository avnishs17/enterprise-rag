"""Rate-limiter initialization shared by the FastAPI lifecycle."""

import logfire
from fastapi import FastAPI

from app.config import settings


def initialize_rate_limiter(application: FastAPI) -> bool:
    """Initialize Redis-backed rate limiting with an in-memory fallback."""
    from limits.storage import RedisStorage
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.extension import _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address

    try:
        storage = RedisStorage(settings.redis_url)
        if not storage.check() or not storage.storage.ping():
            raise ConnectionError("Redis did not respond to ping")

        application.state.limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=settings.redis_url,
        )
        application.state.rate_limiter_storage = "redis"
        logfire.info("Rate limiting initialized using Redis.")
    except Exception as error:
        application.state.limiter = Limiter(key_func=get_remote_address)
        application.state.rate_limiter_storage = "memory"
        logfire.warning(f"Redis unavailable ({error}); using in-memory rate limiting.")

    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return True
