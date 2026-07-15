import logfire
from langchain_openai import ChatOpenAI
from nemoguardrails import LLMRails, RailsConfig

from app.config import settings
from app.guardrails.colang_rules import (
    COLANG_CONTENT,
    RAIL_INDICATORS,
    YAML_CONTENT,
)

_rails: LLMRails | None = None


def initialize_rails() -> None:
    """Initializes the NeMo Guardrails singleton for intent classification."""
    global _rails

    guard_llm = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model="gpt-5-mini",
    )

    config = RailsConfig.from_content(
        colang_content=COLANG_CONTENT,
        yaml_content=YAML_CONTENT,
    )

    _rails = LLMRails(config, llm=guard_llm)

    logfire.info(
        "NeMo Guardrails initialized.",
        model="gpt-5-mini",
    )


def guard(message: str) -> tuple[bool, str | None]:
    """Evaluates a message and returns whether a guardrail was triggered."""
    if _rails is None:
        logfire.warning(
            "Guardrails are not initialized. Skipping guardrail evaluation."
        )
        return False, None

    with logfire.span("Guardrails check"):
        result = _rails.generate(
            messages=[
                {
                    "role": "user",
                    "content": message,
                }
            ]
        )

        content = (
            result.get("content", "")
            if isinstance(result, dict)
            else str(result)
        )

        fired = any(
            indicator in content
            for indicator in RAIL_INDICATORS
        )

        if fired:
            logfire.info(
                "Guardrail triggered.",
                query=message[:80],
            )
            return True, content

        logfire.info("Guardrail evaluation passed.")

        return False, None
