import logfire
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.nodes.planner import planner_node
from app.agents.nodes.responder import generate_node
from app.agents.nodes.retriever import retrieve_node
from app.agents.state import AgentState
from app.config import settings


def create_checkpointer() -> BaseCheckpointSaver:
    """Creates a Postgres checkpointer with an in-memory fallback."""
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            conninfo=settings.postgres_uri,
            max_size=20,
            open=False,
            timeout=10,
            num_workers=3,
            check=ConnectionPool.check_connection,
            max_idle=240,
        )

        # Verify connectivity before using the Postgres checkpointer.
        pool.open()
        connection = pool.getconn()
        pool.putconn(connection)

        # Run Neon-compatible migrations outside a transaction.
        try:
            with PostgresSaver.from_conn_string(
                settings.postgres_uri
            ) as setup_saver:
                setup_saver.setup()

        except Exception:
            logfire.exception(
                "Postgres checkpointer setup failed. "
                "Falling back to MemorySaver."
            )
            pool.close()
            return MemorySaver()

        checkpointer = PostgresSaver(pool)
        logfire.info("Postgres checkpointer configured.")
        return checkpointer

    except Exception:
        logfire.exception(
            "Postgres checkpointer unavailable. "
            "Falling back to MemorySaver. State will not persist across restarts."
        )
        return MemorySaver()


def build_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> StateGraph:
    """Builds and compiles the LangGraph RAG workflow."""
    if checkpointer is None:
        checkpointer = create_checkpointer()

    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("responder", generate_node)

    def route_planner(state: AgentState):
        """Routes conversational requests directly to the responder."""
        if state["current_query"] == "CONVERSATIONAL":
            return "responder"

        return "retriever"

    workflow.set_entry_point("planner")

    workflow.add_conditional_edges(
        "planner",
        route_planner,
        {
            "retriever": "retriever",
            "responder": "responder",
        },
    )

    workflow.add_edge("retriever", "responder")
    workflow.add_edge("responder", END)

    return workflow.compile(checkpointer=checkpointer)


# The application initializes the graph explicitly during startup to prevent
# duplicate checkpointers and support dependency injection in tests.
