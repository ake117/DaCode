"""Pluggable LLM backends for DaCode.

Every backend implements the :class:`LLMClient` protocol — a single
``complete(system, user) -> str`` call.  This keeps the rig dependency-free
(``urllib`` only) while working against any OpenAI-compatible endpoint:

* local llama.cpp server   — ``http://127.0.0.1:18434/v1``
* OpenRouter / OpenAI      — ``https://openrouter.ai/api/v1``
* a deterministic stub      — for tests
"""

from __future__ import annotations

from dacode.llm.base import LLMClient, LLMError
from dacode.llm.openai_compat import OpenAICompatClient
from dacode.llm.stub import StubLLM

__all__ = ["LLMClient", "LLMError", "OpenAICompatClient", "StubLLM", "build_llm"]


def build_llm(kind: str, **kwargs) -> LLMClient:
    """Factory used by the CLI / config layer.

    kind: "stub" | "local" | "openrouter" | "openai"
    """
    kind = (kind or "stub").lower()
    if kind == "stub":
        return StubLLM(**kwargs)
    if kind == "local":
        return OpenAICompatClient(
            base_url=kwargs.get("base_url", "http://127.0.0.1:18434/v1"),
            model=kwargs.get("model", "local"),
            api_key=kwargs.get("api_key"),
        )
    if kind == "openrouter":
        import os

        return OpenAICompatClient(
            base_url="https://openrouter.ai/api/v1",
            model=kwargs.get("model", "deepseek/deepseek-v4.1-flash"),
            api_key=kwargs.get("api_key") or os.environ.get("OPENROUTER_API_KEY"),
        )
    if kind == "openai":
        import os

        return OpenAICompatClient(
            base_url="https://api.openai.com/v1",
            model=kwargs.get("model", "gpt-4o-mini"),
            api_key=kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY"),
        )
    raise ValueError(f"unknown llm kind: {kind!r}")
