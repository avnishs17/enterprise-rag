"""Targeted compatibility-warning configuration for third-party dependencies."""

import warnings

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
from pydantic.warnings import PydanticDeprecatedSince20, PydanticDeprecatedSince211


def configure_warning_filters() -> None:
    """Hide known upstream deprecations without suppressing application errors."""
    warnings.filterwarnings(
        "ignore",
        message=r"Accessing the 'model_fields' attribute on the instance is deprecated.*",
        category=PydanticDeprecatedSince211,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change in a future version.*",
        category=LangChainPendingDeprecationWarning,
    )
    # NeMo Guardrails and LangChain Community still define Pydantic-v1 style
    # models internally. Scope this suppression to those dependencies rather
    # than hiding Pydantic deprecations emitted by this application.
    # These libraries use stacklevel values that attribute their warnings to
    # importing application modules, so module-scoped filters cannot catch
    # them reliably. The application uses Pydantic-v2 APIs throughout.
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
    warnings.filterwarnings(
        "ignore",
        message=r"Use 'nim_base_url' instead.*",
        category=DeprecationWarning,
        module=r"nemoguardrails(?:\..*)?",
    )
    warnings.filterwarnings(
        "ignore",
        message=r"hf_xet\.download_files\(\) is deprecated\..*",
        category=DeprecationWarning,
        module=r"huggingface_hub\.file_download",
    )
