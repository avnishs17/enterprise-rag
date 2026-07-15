import logfire

from app.agents.state import AgentState
from app.gateway import get_langchain_llm


# Portkey-backed LLM with routing, retries, and caching.
llm = get_langchain_llm(feature="planner")


def planner_node(state: AgentState):
    """Classifies the request as conversational or generates a technical search query."""
    history = ""

    for message in state["messages"][:-1]:
        role = "User" if message["role"] == "user" else "Assistant"
        history += f"{role}: {message['content']}\n"

    user_message = (
        state["messages"][-1]["content"]
        if state["messages"]
        else ""
    )

    prompt = f"""
You are an intelligent assistant planner.

Analyze the conversation history and latest user message.

CONVERSATION HISTORY:
{history}

LATEST MESSAGE:
"{user_message}"

Task:
1. If the latest message is a greeting (hi, hello) or a question that can be answered using ONLY the conversation history above (e.g., "what is my name"), respond with 'CONVERSATIONAL'.
2. If it is a technical question about Kubernetes, Intel, or Networking that requires fresh documentation, output a refined search query.

Output only "CONVERSATIONAL" or the refined search query.
"""

    with logfire.span("Planner decision"):
        decision = llm.invoke(prompt).content.strip()

        logfire.info(
            f"Planner decision completed. Intent Identified: {decision}",
        )

    if decision == "CONVERSATIONAL":
        return {
            "current_query": "CONVERSATIONAL",
            "status": "Handling conversationally using conversation history.",
            "plan": [
                "Intent: Conversational/Memory",
                "Retrieval: Skipped",
            ],
        }

    return {
        "current_query": decision,
        "status": f"Technical research required. Searching for: {decision}",
        "plan": [
            "Intent: Technical",
            f"Search query: {decision}",
        ],
    }
