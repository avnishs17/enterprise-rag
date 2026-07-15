import logfire

from app.agents.state import AgentState
from app.services.retrieval.qdrant_service import search_enterprise_knowledge
from app.services.retrieval.ranking_service import rerank_documents


def retrieve_node(state: AgentState):
    """Retrieves and reranks relevant knowledge-base documents."""

    query = state["current_query"]

    with logfire.span("Knowledge retrieval"):
        logfire.info("Searching Qdrant.", query=query)

        raw_results = search_enterprise_knowledge(query, limit=15)

        logfire.info(
            "Qdrant search completed.",
            candidate_count=len(raw_results),
        )

        doc_contents = [doc["content"] for doc in raw_results]

        with logfire.span("Semantic reranking"):
            reranked_contents = rerank_documents(
                query,
                doc_contents,
                top_n=5,
            )

            logfire.info(
                "Semantic reranking completed.",
                document_count=len(reranked_contents),
            )

        formatted_docs = [
            f"CONTENT: {doc}"
            for doc in reranked_contents
        ]

    return {
        "documents": formatted_docs,
        "status": "Found technical context.",
        "plan": state["plan"] + ["Context Retrieved"],
    }
