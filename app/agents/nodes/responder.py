import logfire
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from app.agents.state import AgentState
from app.config import settings
from app.gateway import extract_cache_status, portkey_client


def generate_node(state: AgentState):
    """Generates a conversational or context-grounded response through Portkey."""
    query = state["current_query"]

    history = ""

    for message in state["messages"][:-1]:
        role = "User" if message["role"] == "user" else "Assistant"
        history += f"{role}: {message['content']}\n"

    user_message = (
        state["messages"][-1]["content"]
        if state["messages"]
        else ""
    )

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")

        prompt = f"""
You are a friendly and helpful enterprise AI assistant.

Answer the latest user message using the CONVERSATION HISTORY below.

CONVERSATION HISTORY:
{history}

LATEST MESSAGE:
"{user_message}"
"""
    else:
        logfire.info("Generating technical RAG response.")

        max_context_chars = 25000
        context = ""

        for document in state["documents"]:
            if len(context) + len(document) >= max_context_chars:
                logfire.warning(
                    "Context truncated to fit TPM limit.",
                    max_context_chars=max_context_chars,
                )
                break

            context += f"{document}\n\n"

        prompt = f"""
You are a senior technical architect.

Answer the user's question using the provided TECHNICAL CONTEXT.

TECHNICAL CONTEXT:
{context}

CONVERSATION HISTORY:
{history}

USER QUESTION:
"{user_message}"
"""

    with logfire.span("LLM synthesis"):
        try:
            response = _generate_response(prompt)
            content = response.choices[0].message.content
            cache_status = extract_cache_status(response)

            if cache_status == "HIT":
                logfire.info("Response served from the Portkey cache.")

                plan = state["plan"] + ["Cache: Hit"]
                status = "Response served from cache."
            else:
                logfire.info("LLM response generated.")

                plan = state["plan"]
                status = "Response generated."

            return {
                "final_answer": content,
                "status": status,
                "plan": plan,
                "messages": [
                    {
                        "role": "assistant",
                        "content": content,
                    }
                ],
            }

        except Exception:
            logfire.exception("LLM generation failed after retries.")
            raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
    before_sleep=before_sleep_log(logfire, "warning"),
)
def _generate_response(prompt: str):
    """Generates an LLM response with retries for transient failures."""
    return portkey_client.chat.completions.create(
        model=f"@{settings.PORTKEY_PRIMARY_SLUG}/{settings.PRIMARY_MODEL}",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )
