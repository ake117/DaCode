"""Configuration for a DaCode rig instance."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

__all__ = ["DaCodeConfig"]


@dataclass
class DaCodeConfig:
    repo: Path
    vault: Path | None = None
    sandbox_root: Path | None = None

    llm_kind: str = "openrouter"
    model: str = "deepseek/deepseek-v4.1-flash"
    base_url: str | None = None

    executor: str = "pi"  # "pi" | "script"
    script_command: str | None = None

    budget: int = 2
    variants_per_round: int = 2
    keep_winning_worktree: bool = False

    test_command: tuple[str, ...] | None = None

    @classmethod
    def from_env(cls, repo: str | Path | None = None) -> "DaCodeConfig":
        vault = os.environ.get("DACODE_VAULT") or _default_vault()
        return cls(
            repo=Path(repo or os.environ.get("DACODE_REPO") or os.getcwd()).expanduser().resolve(),
            vault=Path(vault).expanduser().resolve() if vault else None,
            llm_kind=os.environ.get("DACODE_LLM", "openrouter"),
            model=os.environ.get("DACODE_MODEL", "deepseek/deepseek-v4.1-flash"),
            executor=os.environ.get("DACODE_EXECUTOR", "pi"),
            budget=int(os.environ.get("DACODE_BUDGET", "2")),
            variants_per_round=int(os.environ.get("DACODE_VARIANTS", "2")),
        )


def _default_vault() -> str | None:
    candidate = Path.home() / "Documents" / "ake_obsidian"
    return str(candidate) if candidate.is_dir() else None
