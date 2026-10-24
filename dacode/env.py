"""Minimal ``.env`` loader — stdlib only, no python-dotenv dependency.

DaCode resolves secrets from, in priority order:

1. the real process environment
2. ``<repo>/.env``                 — per-project overrides

The Hermes dotenv (``~/.hermes/.env``) is deliberately NOT read: secrets
stay with the project they belong to (standing instruction, 2026-10-20).

Values already present in the environment always win, so exporting a variable
for one command still overrides the files.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["parse_env_file", "load_env", "DEFAULT_ENV_PATHS"]

DEFAULT_ENV_PATHS: tuple[str, ...] = ("{repo}/.env",)


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a dotenv file into a mapping. Missing file → empty mapping."""
    path = Path(path).expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


#: The only names a repository's `.env` may set. Everything else stays out of the
#: host environment: an untrusted checkout must not be able to choose
#: ``DACODE_SEMANTIC_BACKEND=package:factory`` (imports code), ``DACODE_ISOLATE=none``
#: (turns the sandbox off) or ``HTTPS_PROXY`` (intercepts the provider keys).
ENV_ALLOW_LIST: tuple[str, ...] = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "XAI_API_KEY",
    "JEV_API_KEY",
    "DACODE_EMBED_API_KEY",
    "DACODE_EMBED_BASE_URL",
    "DACODE_EMBED_MODEL",
    "DACODE_EMBED_DIMS",
    "DACODE_EMBED_BATCH",
    "DACODE_VAULT",
)


def load_env(
    *paths: str | Path,
    allow: tuple[str, ...] | None = None,
    trust: bool | None = None,
) -> dict[str, str]:
    """Load the first value found for each allowed key, without clobbering the env.

    An allow-list by default (see :data:`ENV_ALLOW_LIST`). ``trust=True`` — the
    ``DACODE_ENV_TRUST=1`` escape hatch for repositories you own — restores the old
    behaviour of importing every key, and is reported on stderr so it is never
    silent.
    """
    trusted = os.environ.get("DACODE_ENV_TRUST", "").lower() in {"1", "true", "on", "yes"}
    if trust is not None:
        trusted = trust
    allowed = None if trusted else set(allow if allow is not None else ENV_ALLOW_LIST)
    loaded: dict[str, str] = {}
    ignored: list[str] = []
    for raw in paths:
        for key, value in parse_env_file(raw).items():
            if allowed is not None and key not in allowed:
                ignored.append(key)
                continue
            if key not in os.environ and value:
                os.environ[key] = value
                loaded[key] = value
    dangerous = sorted(
        key
        for key in set(ignored)
        if key.startswith(("DACODE_", "GIT_", "PYTHON", "LD_", "BASH_ENV"))
        or key.upper().endswith("_PROXY")
    )
    if dangerous:
        import sys

        print(
            f"[env] ignored {len(dangerous)} setting(s) from .env that could change how "
            f"DaCode runs ({', '.join(dangerous[:6])}) — the .env is only trusted for "
            "provider keys; set DACODE_ENV_TRUST=1 for repositories you own",
            file=sys.stderr,
        )
    return loaded
