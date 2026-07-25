import warnings

import logfire

# NeMo imports legacy Pydantic-v1 model definitions (and transitively imports
# legacy LangChain Community integrations). Capture and discard those import-
# time third-party deprecations without hiding runtime warnings from our code.
with warnings.catch_warnings(record=True):
    from nemoguardrails import LLMRails, RailsConfig

from app.config import settings
from app.gateway import get_fallback_langchain_llm, get_langchain_llm
from app.guardrails.colang_rules import COLANG_CONTENT, RAIL_INDICATORS, YAML_CONTENT
from app.services.safety import classify_with_groq_safeguard

_rails: LLMRails | None = None
_fallback_rails: LLMRails | None = None

_GENERIC_BLOCK_RESPONSE = (
    "I can only help with approved Kubernetes, Intel hardware, and enterprise "
    "networking topics, and I can't assist with unsafe requests."
)


def initialize_nemo_rails() -> None:
    """Initialize the legacy NeMo implementation for rollback or A/B testing."""
    global _rails, _fallback_rails

    config = RailsConfig.from_content(colang_content=COLANG_CONTENT, yaml_content=YAML_CONTENT)
    _rails = LLMRails(config, llm=get_langchain_llm(feature="guardrails"))
    # Portkey owns failover when enabled. In direct mode, keep a second rail
    # instance so a Nebius outage does not disable guardrail checks.
    _fallback_rails = None if settings.USE_PORTKEY else LLMRails(config, llm=get_fallback_langchain_llm())

    logfire.info(
        "NeMo Guardrails initialized.",
        model=settings.PRIMARY_MODEL if settings.USE_PORTKEY else settings.NEBIUS_MODEL,
        fallback_enabled=not settings.USE_PORTKEY,
    )


def initialize_rails() -> None:
    """Initialize only the guardrail provider selected for production traffic."""
    if settings.GUARDRAIL_PROVIDER == "nemo":
        initialize_nemo_rails()
    elif settings.GUARDRAIL_PROVIDER == "groq_safeguard":
        logfire.info("Groq GPT-OSS-Safeguard selected for guardrails.", model=settings.GROQ_SAFEGUARD_MODEL)
    else:
        raise ValueError("GUARDRAIL_PROVIDER must be 'nemo' or 'groq_safeguard'")


def guard_with_nemo(
    message: str, history: list[dict[str, str]] | None = None
) -> tuple[bool, str | None]:
    """Run the legacy NeMo policy flow; used for rollback and A/B comparison."""
    if _rails is None:
        raise RuntimeError("NeMo Guardrails are not initialized")

    messages = [{"role": "user", "content": message}]
    try:
        result = _rails.generate(messages=messages)
    except Exception:
        if _fallback_rails is None:
            raise
        logfire.exception("Primary guardrail LLM failed; routing to Groq fallback.")
        result = _fallback_rails.generate(messages=messages)

    content = result.get("content", "") if isinstance(result, dict) else str(result)
    fired = any(indicator in content for indicator in RAIL_INDICATORS)
    if fired:
        logfire.info("Guardrail triggered.", query=message[:80], provider="nemo")
        return True, content

    logfire.info("Guardrail evaluation passed.", provider="nemo")
    return False, None


def guard(message: str, history: list[dict[str, str]] | None = None) -> tuple[bool, str | None]:
    """Evaluate one input with the selected provider and fail closed on errors."""
    with logfire.span("Guardrails check", provider=settings.GUARDRAIL_PROVIDER):
        if settings.GUARDRAIL_PROVIDER == "nemo":
            return guard_with_nemo(message, history)

        if settings.GUARDRAIL_PROVIDER != "groq_safeguard":
            raise ValueError("GUARDRAIL_PROVIDER must be 'nemo' or 'groq_safeguard'")

        try:
            decision = classify_with_groq_safeguard(message, history)
        except Exception:
            # A moderation outage must never turn into an unreviewed generation.
            logfire.exception("Groq Safeguard failed; blocking request.")
            return True, _GENERIC_BLOCK_RESPONSE

        if decision.blocked:
            logfire.info("Guardrail triggered.", query=message[:80], provider="groq_safeguard", rule_ids=decision.rule_ids)
            return True, _GENERIC_BLOCK_RESPONSE

        logfire.info("Guardrail evaluation passed.", provider="groq_safeguard")
        return False, None
