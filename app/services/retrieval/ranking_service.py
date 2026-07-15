import time

import logfire
import requests
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from app.config import settings

_ranker = None


class _JinaReranker:
    """
    A wrapper around the Jina reranker API.
    """

    def rerank(self, query: str, documents: list[str], top_n: int)->list[str]:
        """
        Score and re-rank (reorder) the documents against the query via Jina API.
        """

        response = requests.post(
            settings.JINA_RERANK_URL,
            headers={
                "Authorization": f"Bearer {settings.JINA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.JINA_RERANK_MODEL,
                "query": query,
                "documents": documents,
                "top_n": top_n,
                "return_documents": True,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()

        results = payload.get("results", [])

        # Results are already sorted by relevance score (descending)
        reranked_docs = []

        for res in results[:top_n]:
            doc_text = res.get("document")
            if doc_text is None:
                # Fallback to original index if document text is missing
                index = res.get("index")
                if index is not None and  0<= index < len(documents):
                    doc_text = documents[index]
            if doc_text is not None:
                reranked_docs.append(doc_text)

        return reranked_docs


def  _get_reranker() -> _JinaReranker:
    """
    Returns the Jine reranker wrapper (lazy sigleton)
    """
    global _ranker
    if _ranker is None:
        logfire.info("Initializing Jina reranker v3 via API...")
        _ranker = _JinaReranker()
    return _ranker


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
    before_sleep=before_sleep_log(logfire, "warning"),
)
def _rerank(query: str, documents: list[str], top_n: int) -> list[str]:
    """Core Jina API reranking with retry on transient failures."""
    ranker = _get_reranker()
    return ranker.rerank(query, documents, top_n)


def rerank_documents(query: str, documents: list[str], top_n: int = 5) -> list[str]:
    """
    Reranks documents by semantic relevance and preserves the original order on failure.
    """
    if not documents:
        return []

    if not settings.JINA_API_KEY:
        logfire.warning("JINA_API_KEY is not set. Skipping reranking.")
        return documents[:top_n]

    start_time = time.time()
    logfire.info(
        "[Reranker] Sending documents to Jina Reranker API.",
        document_count=len(documents),
    )

    try:
        reranked_docs = _rerank(query, documents, top_n)
        duration = time.time() - start_time

        logfire.info(f"[Reranker] Document reranking completed. Done in {duration:.2f} seconds.")
        return reranked_docs

    except Exception as e:
        logfire.error(
            f"[Reranker] Document reranking failed after retries : {e}"
        )
        # Fallback to original order on failure
        return documents[:top_n]
