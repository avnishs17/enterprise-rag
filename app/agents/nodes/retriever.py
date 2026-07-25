import time

import logfire

from app.agents.state import AgentState
from app.services.retrieval.qdrant_service import search_enterprise_knowledge
from app.services.retrieval.ranking_service import rerank_documents
from app.utils.metrics import RAG_PIPELINE_STAGE_DURATION


def retrieve_node(state: AgentState):
    """Retrieves and reranks relevant knowledge-base documents."""

    query = state["current_query"]

    with logfire.span("Knowledge retrieval"):
        logfire.info("Searching Qdrant.", query=query)

        search_started = time.perf_counter()
        raw_results = search_enterprise_knowledge(query, limit=15)
        RAG_PIPELINE_STAGE_DURATION.labels(stage="qdrant_search").observe(time.perf_counter() - search_started)

        logfire.info(
            "Qdrant search completed.",
            candidate_count=len(raw_results),
        )

        doc_contents = [doc["content"] for doc in raw_results]
        sources_by_content: dict[str, list[str]] = {}
        for doc in raw_results:
            sources_by_content.setdefault(doc["content"], []).append(doc["source"])

        with logfire.span("Semantic reranking"):
            rerank_started = time.perf_counter()
            reranked_contents = rerank_documents(
                query,
                doc_contents,
                top_n=5,
            )
            RAG_PIPELINE_STAGE_DURATION.labels(stage="rerank").observe(time.perf_counter() - rerank_started)

            logfire.info(
                "Semantic reranking completed.",
                document_count=len(reranked_contents),
            )

        formatted_docs = []
        for index, content in enumerate(reranked_contents, start=1):
            matching_sources = sources_by_content.get(content, [])
            source = matching_sources.pop(0) if matching_sources else "Knowledge base"
            formatted_docs.append(f"[S{index}] SOURCE: {source}\nCONTENT: {content}")

    return {
        "documents": formatted_docs,
        "status": "Found technical context.",
        "plan": state["plan"] + ["Context Retrieved"],
    }
