import os
from pathlib import Path
from urllib.parse import quote, urlunsplit

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """
    Load and validate environment variables from `.env`.
    - `extra=ignore` lets `.env` keep legacy environment variables.
    - Required fields raise clear validation errors at import time if missing.
    """

    model_config = SettingsConfigDict(
        # Resolve relative to the repository, not the process working
        # directory, so API startup also works when launched from ui/.
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Embedding model configuration
    BATCH_SIZE: int = 64
    EMBEDDING_DIM: int = 1024
    PROCESSED_DATA_DIR: str = "processed_data"

    JINA_API_KEY: str
    JINA_EMBEDDING_URL: str
    JINA_MODEL: str
    JINA_RATE_LIMIT_DELAY: float = 1.0
    FALLBACK_MODEL: str

    # Reranker model configuration
    JINA_RERANK_URL: str
    JINA_RERANK_MODEL: str

    # --- LLM CONFIGURATION ---
    GROQ_API_KEY: str
    # Nebius Token Factory is OpenAI-compatible and is used by Guardrails.
    NEBIUS_API_KEY: str
    NEBIUS_BASE_URL: str = "https://api.tokenfactory.nebius.com/v1/"
    NEBIUS_MODEL: str = "google/gemma-3-27b-it"
    LLM_TEMPERATURE: float = 0.1
    LLM_SEED: int = 42
    LLM_FREQUENCY_PENALTY: float = 0.1
    # Maximum idle/read time for planner and generation provider calls. A
    # streamed response may run longer while tokens continue arriving.
    LLM_REQUEST_TIMEOUT_SECONDS: float = 45.0
    JUDGE_GROQ_API_KEY: str

    # --- LLM ROUTING ---
    # Set true only when a funded Portkey account/config is available. When
    # false, the application routes Nebius failures directly to Groq.
    USE_PORTKEY: bool = False

    # --- LLM GATEWAY (PORTKEY, optional) ---
    PORTKEY_API_KEY: str = ""
    PORTKEY_PRIMARY_SLUG: str = "nebius-slug2"
    PORTKEY_FALLBACK_SLUG: str = "groq-fallback"
    PRIMARY_MODEL: str = "google/gemma-3-27b-it"
    FALLBACK_LLM_MODEL: str = "llama-3.3-70b-versatile"
    # Dedicated policy-classification model, deliberately separate from the
    # RAG generation fallback model.
    GROQ_SAFEGUARD_MODEL: str = "openai/gpt-oss-safeguard-20b"
    GROQ_SAFEGUARD_TIMEOUT_SECONDS: float = 15.0
    # "groq_safeguard" is the production default after the A/B evaluation;
    # "nemo" remains available as an explicit rollback setting.
    GUARDRAIL_PROVIDER: str = "groq_safeguard"
    # Required only when USE_PORTKEY=true.
    PORTKEY_PRIMARY_CONFIG_ID: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # --- QDRANT VECTOR DB ---
    QDRANT_URL: str = Field(validation_alias=AliasChoices("QDRANT_URL", "QDRANT_CLUSTER_ENDPOINT"))
    QDRANT_API_KEY: str
    QDRANT_COLLECTION: str = "enterprise_rag"

    # --- NEON SERVERLESS POSTGRES (LangGraph checkpointer) ---
    NEON_DB_URL: str

    # --- UPSTASH REDIS (rate limiting) ---
    UPSTASH_REDIS_REST_URL: str
    UPSTASH_REDIS_REST_TOKEN: str

    # --- API SAFETY ---
    API_KEY: str | None = Field(default=None, alias="RAG_API_KEY")
    ENVIRONMENT: str = "development"
    RATE_LIMIT_PER_MINUTE: int = 20
    STRICT_STARTUP: bool = False
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    TRUSTED_HOSTS: str = "localhost,127.0.0.1,testserver"
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    # --- CONVERSATION ---
    # Maximum approximate tokens (~4 chars per token) of conversation history
    # sent to the LLM with each request. Older messages are dropped first
    # when the budget is exceeded. 0 = unlimited.
    MAX_HISTORY_TOKENS: int = 2000
    # Exact thread history is stored separately from Mem0 so recent turns are
    # deterministic and do not depend on semantic-memory extraction.
    MAX_CONVERSATION_MESSAGES: int = 20
    CONVERSATION_HISTORY_TTL_SECONDS: int = 30 * 24 * 60 * 60

    # --- MEM0 (long-term memory) ---
    # Mem0 Cloud API key for persisting and retrieving conversation memories.
    # Leave empty to disable long-term memory.
    MEM0_API_KEY: str = ""

    # --- OBSERVABILITY ---
    # Logfire Observability
    LOGFIRE_PROJECT: str | None = None
    LOGFIRE_TOKEN: str | None = None
    LOGFIRE_BASE_URL: str | None = None

    # LangSmith tracing
    LANGSMITH_TRACING: str = "true"
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_PROJECT: str = "enterprise-rag"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"


    @field_validator("QDRANT_API_KEY", mode="before")
    @classmethod
    def _empty_qdrant_key_as_none(cls, v):
        """Treat empty QDRANT_API_KEY as unset so local Qdrant doesn't receive a blank header."""
        if v == "" or v is None:
            return None
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in {"production", "prod"}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def trusted_hosts(self) -> list[str]:
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]

    @property
    def judge_api_key(self) -> str:
        """Dedicated judge key, falling back to the configured Nebius key."""
        return self.JUDGE_GROQ_API_KEY or self.NEBIUS_API_KEY

    @property
    def postgres_uri(self) -> str:
        """LangGraph Postgres checkpointer URI (Neon).

        Serverless Postgres closes idle connections, so append TCP keepalive
        options to keep the connection pool healthy between requests.
        """
        base = self.NEON_DB_URL.rstrip("/")
        keepalive = "keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=5"
        if "?" in base:
            return f"{base}&{keepalive}"
        return f"{base}?{keepalive}"

    @property
    def redis_url(self) -> str:
        """TLS Redis URL derived from Upstash REST credentials.

        Upstash exposes the same host for REST and TLS Redis. The REST token is
        used as the Redis password under the default username. The result is
        passed to `limits` for rate limiting and to the health checker.
        """
        host = self.UPSTASH_REDIS_REST_URL.replace("https://", "").rstrip("/")
        token = quote(self.UPSTASH_REDIS_REST_TOKEN, safe="")
        netloc = f"default:{token}@{host}"
        return urlunsplit(("rediss", netloc, "/0", "ssl_cert_reqs=required", ""))


# Singleton used across the app.
settings = Settings()  # pyright: ignore[call-arg]


def apply_langchain_env():
    """
    Write LangSmith/LangChain settings to os.environ for automatic tracing.
    Tracing is only activated when both LANGSMITH_TRACING and LANGSMITH_API_KEY
    are set — enabling tracing without a key causes LangChain to emit 401 noise
    on every LangGraph step.
    """
    if settings.LANGSMITH_TRACING and settings.LANGSMITH_API_KEY:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", settings.LANGSMITH_TRACING)
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGSMITH_API_KEY)
    if settings.LANGSMITH_PROJECT:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGSMITH_PROJECT)
    if settings.LANGSMITH_ENDPOINT:
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.LANGSMITH_ENDPOINT)


apply_langchain_env()
