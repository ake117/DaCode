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


def _pi_auth_key(provider: str) -> str | None:
    """Fall back to the Pi coding agent's auth store (~/.pi/agent/auth.json).

    On this machine the OpenRouter key lives in Pi's auth file rather than the
    environment, so DaCode reuses it instead of demanding a duplicate secret.
    """
    import json
    import os

    path = os.path.expanduser("~/.pi/agent/auth.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    entry = data.get(provider)
    if isinstance(entry, dict):
        key = entry.get("key") or entry.get("apiKey")
        if isinstance(key, str) and key.strip():
            return key.strip()
    if isinstance(entry, str) and entry.strip():
        return entry.strip()
    return None


def build_llm(kind: str, **kwargs) -> LLMClient:
    """Factory used by the CLI / config layer.

    kind: "stub" | "local" | "openrouter" | "openai"
    """
    kind = (kind or "stub").lower()
    if kind == "stub":
        allowed = {k: v for k, v in kwargs.items() if k in {"responses", "default", "fail_on"}}
        return StubLLM(**allowed)
    if kind == "local":
        return OpenAICompatClient(
            base_url=kwargs.get("base_url", "http://127.0.0.1:18434/v1"),
            model=kwargs.get("model", "local"),
            api_key=kwargs.get("api_key"),
        )
    if kind == "openrouter":
        import os

        key = kwargs.get("api_key") or os.environ.get("OPENROUTER_API_KEY") or _pi_auth_key("openrouter")
        return OpenAICompatClient(
            base_url="https://openrouter.ai/api/v1",
            model=kwargs.get("model", "deepseek/deepseek-v4.1-flash"),
            api_key=key,
        )
    if kind == "openai":
        import os

        key = kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY") or _pi_auth_key("openai")
        return OpenAICompatClient(
            base_url="https://api.openai.com/v1",
            model=kwargs.get("model", "gpt-4o-mini"),
            api_key=key,
        )
    raise ValueError(f"unknown llm kind: {kind!r}")
