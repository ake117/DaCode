"""Pluggable LLM backends for DaCode.

Every backend implements the :class:`LLMClient` protocol — a single
``complete(system, user) -> str`` call.  This keeps the rig dependency-free
(``urllib`` only) while working against any OpenAI-compatible endpoint:

* local llama.cpp server    — ``http://127.0.0.1:18434/v1``
* popular providers         — see ``dacode/llm/providers.py``: OpenRouter,
  OpenAI, Anthropic, Gemini, Groq, DeepSeek, Mistral, xAI
* a deterministic stub      — for tests
"""

from __future__ import annotations

from dacode.llm.base import LLMClient, LLMError
from dacode.llm.openai_compat import OpenAICompatClient
from dacode.llm.providers import PROVIDERS, get_provider, provider_names
from dacode.llm.stub import StubLLM

__all__ = [
    "LLMClient",
    "LLMError",
    "OpenAICompatClient",
    "PROVIDERS",
    "StubLLM",
    "build_llm",
    "get_provider",
    "provider_names",
]


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

    kind: "stub" | "local" | any provider preset (openrouter, openai,
    anthropic, gemini, groq, deepseek, mistral, xai — see
    ``dacode/llm/providers.py``).
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
    preset = get_provider(kind)
    if preset is None:
        raise ValueError(f"unknown llm kind: {kind!r}")

    import os

    key = (
        kwargs.get("api_key")
        or os.environ.get(preset["env"])
        or (_pi_auth_key(preset["pi"]) if preset.get("pi") else None)
    )
    return OpenAICompatClient(
        base_url=kwargs.get("base_url") or preset["base_url"],
        model=kwargs.get("model") or preset["default_model"],
        api_key=key,
        extra_headers=preset.get("extra_headers"),
    )
