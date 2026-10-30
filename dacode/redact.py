"""Redaction of credentials on their way into anything that persists.

The rig writes to three places a secret must not reach: the runlog (JSONL), the
state store (SQLite, and out through the MCP server), and lesson notes in the
vault. The rule is simple — redact at the boundary, so no future caller has to
remember.

Patterns are deliberately conservative: a false positive costs one replaced token
in a log line, a false negative leaks a key.
"""

from __future__ import annotations

import os
import re

REDACTED = "[REDACTED]"

#: Ordered; each is applied to every string that crosses a boundary.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}")),
    ("groq", re.compile(r"\bgsk_[A-Za-z0-9]{16,}")),
    ("google", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}")),
    ("huggingface", re.compile(r"\bhf_[A-Za-z0-9]{16,}")),
    ("openrouter", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{16,}")),
    ("github", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("gitlab", re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{16,}")),
    ("aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("url_userinfo", re.compile(r"(https?://[^/\s:@]+):[^/\s@]{8,}@")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer", re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]{12,}")),
    ("basic", re.compile(r"(?i)\b(basic)\s+[A-Za-z0-9+/=]{16,}")),
)

#: Env names whose *values* are secret even when they do not look like a token.
#: Kept in step with every ``*_API_KEY`` the env allow-list and the sandbox
#: NETWORK_ENV will route (env.py, sandbox/bwrap.py) — a key the rig passes to
#: trials must not survive a redact boundary, and z.ai's keys carry no ``sk-``
#: prefix for the patterns below to catch (GLM/ZAI omission found in the
#: follow-up audit, Oct 2026).
_SECRET_ENV = (
    "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
    "XAI_API_KEY", "GLM_API_KEY", "ZAI_API_KEY", "JEV_API_KEY",
    "DACODE_EMBED_API_KEY",
)

_MIN_SECRET_LEN = 8


def _env_values() -> list[str]:
    return [
        value
        for name in _SECRET_ENV
        if (value := os.environ.get(name)) and len(value) >= _MIN_SECRET_LEN
    ]


def redact(text: str) -> str:
    """Replace credentials in ``text`` with :data:`REDACTED`."""
    if not text:
        return text
    out = text
    for value in _env_values():
        if value in out:
            out = out.replace(value, REDACTED)
    for _name, pattern in _PATTERNS:
        out = pattern.sub(_replace, out)
    return out


def _replace(match: re.Match[str]) -> str:
    """Keep the scheme word (``Bearer``) or URL user prefix, drop the token."""
    if match.groups():
        prefix = match.group(1)
        if prefix.startswith(("http://", "https://")):
            return f"{prefix}:{REDACTED}@"
        return f"{prefix} {REDACTED}"
    return REDACTED


def redact_event(event: dict) -> dict:
    """Redact every string in an event, recursively. Never mutates the input."""
    if not isinstance(event, dict):
        return event

    def _walk(value):
        if isinstance(value, str):
            return redact(value)
        if isinstance(value, dict):
            return {key: _walk(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_walk(item) for item in value]
        return value

    return {key: _walk(value) for key, value in event.items()}
