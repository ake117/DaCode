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


def load_env(*paths: str | Path) -> dict[str, str]:
    """Load the first value found for each key without clobbering the env."""
    loaded: dict[str, str] = {}
    for raw in paths:
        for key, value in parse_env_file(raw).items():
            if key not in os.environ and value:
                os.environ[key] = value
                loaded[key] = value
    return loaded
