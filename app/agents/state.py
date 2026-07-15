import operator
from typing import Annotated, List, TypedDict


class AgentState(TypedDict):
    """Shared state passed between nodes in the agent workflow."""

    # Append new messages instead of replacing the conversation history.
    messages: Annotated[List[dict], operator.add]
    current_query: str
    documents: List[str]
    plan: List[str]
    status: str
    final_answer: str
