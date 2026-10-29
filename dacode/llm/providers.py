"""Popular AI provider presets for :func:`dacode.llm.build_llm`.

Every provider here is OpenAI-compatible (``/chat/completions``), so one
client class serves them all — including Anthropic, whose official
compatibility layer speaks the same shape. Adding a provider is one
registry entry: ``base_url``, the env var that holds its key, a default
model.

Keys resolve in this order: explicit ``api_key`` → the provider's env var
(``cli.load_env`` loads the target repo's ``.env``). DaCode deliberately
does not read Pi's auth store (``~/.pi/agent/auth.json``) or the Hermes
dotenv (``~/.hermes/.env``) — a standing instruction from 2026-10-20.
"""

from __future__ import annotations

__all__ = ["PROVIDERS", "provider_names", "get_provider"]

PROVIDERS: dict[str, dict] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
        "default_model": "deepseek/deepseek-v4.1-flash",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    },
    "zai": {
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "env": "GLM_API_KEY",
        "default_model": "glm-5.3-flash",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "env": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5",
        "extra_headers": {"anthropic-version": "2023-06-01"},
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "env": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-flash",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "env": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "env": "MISTRAL_API_KEY",
        "default_model": "mistral-small-latest",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "env": "XAI_API_KEY",
        "default_model": "grok-4",
    },
}


def provider_names() -> list[str]:
    """Provider kinds ``build_llm`` accepts beyond ``stub`` and ``local``."""
    return sorted(PROVIDERS)


def get_provider(kind: str) -> dict | None:
    """The preset for ``kind``, or ``None`` when it is not a known provider."""
    return PROVIDERS.get(kind.lower())
