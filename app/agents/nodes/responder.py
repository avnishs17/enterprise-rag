from dataclasses import dataclass
from typing import Iterator

import logfire
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from app.agents.state import AgentState
from app.config import settings
from app.gateway import create_chat_completion, extract_cache_status

RESPONSE_FORMAT_INSTRUCTIONS = """
FORMAT REQUIREMENTS:
- Return a clear, concise answer in GitHub-flavored Markdown.
- Use headings, bullets, numbered steps, and fenced code blocks only when useful.
- Answer once. Do not repeat the question, a sentence, a paragraph, or the full answer.
- Cite each source label separately: write `[S1] [S2]`, never a combined label such as `[S1, S2]`.
- Do not include hidden reasoning, planning notes, or a preamble about the response format.
"""


def _history_from_messages(messages: list[dict], max_tokens: int = 2000) -> str:
    if max_tokens <= 0:
        recent = messages[:-1]
    else:
        char_budget = max_tokens * 4
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
    for message in recent:
        role = "User" if message["role"] == "user" else "Assistant"
        lines.append(f"{role}: {message['content']}")
    return "\n".join(lines)


def generate_node(state: AgentState):
    """Generates a conversational or context-grounded response through Portkey."""
    query = state["current_query"]
    history = _history_from_messages(state["messages"], settings.MAX_HISTORY_TOKENS)
    memories = state.get("memories", "")

    user_message = (
        state["messages"][-1]["content"]
        if state["messages"]
        else ""
    )

    if query == "CONVERSATIONAL":
        logfire.info("Generating conversational response using memory.")

        memories_section = f"\nRELEVANT MEMORIES:\n{memories}\n" if memories else ""

        prompt = f"""
You are a friendly and helpful enterprise AI assistant.

Answer the latest user message using the conversation history and relevant memories below.{memories_section}
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

        memories_section = f"\nRELEVANT MEMORIES:\n{memories}\n" if memories else ""

        prompt = f"""
You are a senior technical architect.

Answer the user's question using the provided TECHNICAL CONTEXT. Cite factual claims with the matching source label, for example [S1]. Do not cite a source that does not support the claim. If the context does not support an answer, say so plainly.

TECHNICAL CONTEXT:
{context}{memories_section}
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
    return create_chat_completion(
        feature="responder",
        messages=[{"role": "user", "content": prompt}],
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
    before_sleep=before_sleep_log(logfire, "warning"),
)
def _stream_response(prompt: str):
    """Streams an LLM response token by token via Portkey."""
    return create_chat_completion(
        feature="responder",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )


def build_rag_prompt(state: AgentState) -> str:
    """Builds the prompt from state, shared by sync and streaming paths."""
    query = state["current_query"]
    history = _history_from_messages(state["messages"], settings.MAX_HISTORY_TOKENS)
    memories = state.get("memories", "")

    user_message = (
        state["messages"][-1]["content"]
        if state["messages"]
        else ""
    )

    if query == "CONVERSATIONAL":
        memories_section = f"\nRELEVANT MEMORIES:\n{memories}\n" if memories else ""

        return f"""
You are a friendly and helpful enterprise AI assistant.
{RESPONSE_FORMAT_INSTRUCTIONS}
Answer the latest user message using the conversation history and relevant memories below.{memories_section}
CONVERSATION HISTORY:
{history}

LATEST MESSAGE:
"{user_message}"
"""

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

    memories_section = f"\nRELEVANT MEMORIES:\n{memories}\n" if memories else ""

    return f"""
You are a senior technical architect.
{RESPONSE_FORMAT_INSTRUCTIONS}
Answer the user's question using the provided TECHNICAL CONTEXT. Cite factual claims with the matching source label, for example [S1]. Do not cite a source that does not support the claim. If the context does not support an answer, say so plainly.

TECHNICAL CONTEXT:
{context}{memories_section}
CONVERSATION HISTORY:
{history}

USER QUESTION:
"{user_message}"
"""


@dataclass
class StreamGeneration:
    """A single streaming generation and its request-local final result."""

    state: AgentState
    result: dict | None = None

    def __iter__(self) -> Iterator[str]:
        prompt = build_rag_prompt(self.state)

        with logfire.span("LLM synthesis (streaming)"):
            stream = _stream_response(prompt)
            full_content: list[str] = []

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_content.append(token)
                    yield token

            content = "".join(full_content)
            cache_status = extract_cache_status(stream)

            if cache_status == "HIT":
                logfire.info("Streaming response served from Portkey cache.")

            logfire.info("Streaming LLM response completed.")
            self.result = {
                "final_answer": content,
                "status": "Response generated.",
                "plan": self.state["plan"] + (["Cache: Hit"] if cache_status == "HIT" else []),
                "messages": [{"role": "assistant", "content": content}],
            }


def generate_node_stream(state: AgentState) -> StreamGeneration:
    """Create a request-local streaming generation.

    The completed result lives on the returned object, not module state, so
    simultaneous users cannot read or overwrite one another's response.
    """
    return StreamGeneration(state=state)
