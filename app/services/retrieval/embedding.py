import time

import logfire
import requests
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

_active_model = None
_model_type: str | None = None



def load_fallback():
    """
    Load the local mxbai fallback model.
    """
    from sentence_transformers import SentenceTransformer

    logfire.info(f"Loading fallback embedding model ({settings.FALLBACK_MODEL}, {settings.EMBEDDING_DIM}-dim).")
    return SentenceTransformer(settings.FALLBACK_MODEL)


def _probe_jina_api() -> bool:
    if not settings.JINA_API_KEY:
        logfire.info("JINA_API_KEY not set - will use local fallback embeddings.")
        return False

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
            timeout=30,
        )

        if not response.ok:
            logfire.error(
                "Jina API probe returned an error",
                status_code=response.status_code,
                response_body=response.text,
            )
            print(response.status_code)
            print(response.text)

        response.raise_for_status()

        payload = response.json()

        if not payload.get("data"):
            raise RuntimeError("Jina API returned empty data")

        logfire.info(
            "Jina Embeddings API ready",
            model=settings.JINA_MODEL,
            dimensions=settings.EMBEDDING_DIM,
        )
        return True

    except Exception as e:
        logfire.warning(
            f"Jina Embeddings API probe failed: {e}. "
            "Will use local fallback embeddings."
        )
        return False

def _initialize_model():
    """
    Initialize the embedding model once per process.
    Called lazily on first embed call
    """

    global _active_model, _model_type
    if _active_model is not None or _model_type is not None:
        return

    if _probe_jina_api():
        _model_type = "jina"
        _active_model = None
    else:
        _model_type = "fallback"
        _active_model = load_fallback()

def get_embedding_dim() -> int:
    """
    Returns the embedding dimension of the active model.
    Call after _initialize_model()
    """
    _initialize_model()
    return settings.EMBEDDING_DIM

# Jina API embedding
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=120),
    reraise=True,
    before_sleep=before_sleep_log(logfire, "warning"),
    retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError, requests.HTTPError)),
)
def embed_jina_batch(texts: list[str], task: str) -> list[list[float]]:
    """Call the Jina Embeddings API for a single batch."""
    response = requests.post(
        settings.JINA_EMBEDDING_URL,
        headers={
            "Authorization": f"Bearer {settings.JINA_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.JINA_MODEL,
            "task": task,
            "normalized": True,
            "input": texts,
        },
        timeout=60,
    )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            raise requests.HTTPError(f"429 Too Many Requests — retry after {retry_after}s", response=response)

    response.raise_for_status()
    payload = response.json()

    results = payload.get("data", [])
    # Sort by index because the API may not preserve order in rare cases
    results_sorted = sorted(results, key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in results_sorted]


def _embed_jina(texts: list[str], task: str) -> list[list[float]]:
    """Embed texts via the Jina API in batches with retry and inter-batch delay."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), settings.BATCH_SIZE):
        batch = texts[i : i + settings.BATCH_SIZE]
        with logfire.span("Embed batch via Jina API", start=i, size=len(batch)):
            embeddings = embed_jina_batch(batch, task)
            all_embeddings.extend(embeddings)
        # Throttle between batches to respect rate limits
        if i + settings.BATCH_SIZE < len(texts):
            time.sleep(settings.JINA_RATE_LIMIT_DELAY)
    return all_embeddings



# Fallback embedding

def _embed_fallback_batch(texts: list[str]) -> list[list[float]]:
    """Embed texts using the local mxbai model."""
    embeddings = _active_model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()


def _embed_fallback(texts: list[str]) -> list[list[float]]:
    """Embed texts via the local fallback model in batches."""
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), settings.BATCH_SIZE):
        batch = texts[i : i + settings.BATCH_SIZE]
        with logfire.span("Embed batch via fallback model", start=i, size=len(batch)):
            all_embeddings.extend(_embed_fallback_batch(batch))
    return all_embeddings


# Unified embedding with runtime fallback
def _ensure_fallback():
    """Switch to the local fallback model if not already active."""
    global _active_model, _model_type
    if _model_type != "fallback":
        logfire.warning("Switching to local fallback embeddings.")
        _active_model = load_fallback()
        _model_type = "fallback"

def _embed(texts: list[str], task: str) -> list[list[float]]:
    """Embed texts using the active provider, falling back to local on failure."""
    _initialize_model()

    if _model_type == "jina":
        try:
            return _embed_jina(texts, task)
        except Exception as e:
            logfire.error(f"Jina Embeddings API failed: {e}. Falling back to local model.")
            _ensure_fallback()

    return _embed_fallback(texts)


# Public API

def embed_query(query: str) -> list[float]:
    """Embed a single query."""
    return _embed([query], task="retrieval.query")[0]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of document texts."""
    return _embed(texts, task="retrieval.passage")
