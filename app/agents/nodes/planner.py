import logfire

from app.agents.state import AgentState
from app.config import settings
from app.gateway import get_langchain_llm


# Portkey-backed LLM with routing, retries, and caching.
llm = get_langchain_llm(feature="planner")


def _history_from_messages(messages: list[dict]) -> str:
    if settings.MAX_HISTORY_TOKENS <= 0:
        recent = messages[:-1]
    else:
        char_budget = settings.MAX_HISTORY_TOKENS * 4
        recent = []
        total = 0
        for m in reversed(messages[:-1]):
            cost = len(m.get("content", "")) + 20
            if total + cost > char_budget:
                break
            recent.append(m)
            total += cost
        recent.reverse()

    lines = []
    for m in recent:
        role = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)


def planner_node(state: AgentState):
    """Classifies the request as conversational or generates a technical search query."""
    history = _history_from_messages(state["messages"])
    memories = state.get("memories", "")

    user_message = (
        state["messages"][-1]["content"]
        if state["messages"]
        else ""
    )

    memories_section = f"\nRELEVANT MEMORIES:\n{memories}\n" if memories else ""

    prompt = f"""
You are an intelligent assistant planner.

Analyze the conversation history, relevant memories, and latest user message.
{memories_section}
CONVERSATION HISTORY:
{history}

LATEST MESSAGE:
"{user_message}"

Task:
1. If the latest message is a greeting (hi, hello) or a question that can be answered using ONLY the conversation history or memories above (e.g., "what is my name" or referring to past topics), respond with 'CONVERSATIONAL'.
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
