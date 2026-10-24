"""Configuration for a DaCode rig instance."""

from __future__ import annotations

import os
import shlex
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

    semantic: str = "auto"  # vault retrieval backend: "auto" | "on" | "off"
    judge: str | None = None  # None = off; "jev" = TypeSafe System One judge
    escalate_models: list[str] | None = None  # ladder for the judge's escalate_model triage

    test_command: tuple[str, ...] | None = None
    test_glob: str = "test_*.py"
    variant_timeout: float = 900.0  # seconds a single variant may spend executing
    parallel: int = 1  # variants probed at once (worktree creation stays serialised)
    baseline: tuple[int, int] | None = None  # (total, skipped) measured on the untouched repo

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
            semantic=os.environ.get("DACODE_SEMANTIC", "auto"),
            judge=os.environ.get("DACODE_JUDGE") or None,
            escalate_models=_env_model_ladder(),
            test_command=_env_test_command(),
            test_glob=os.environ.get("DACODE_TEST_GLOB", "test_*.py"),
            variant_timeout=float(os.environ.get("DACODE_VARIANT_TIMEOUT", "900")),
            parallel=int(os.environ.get("DACODE_PARALLEL", "1")),
        )


def _env_model_ladder() -> list[str] | None:
    """Read ``DACODE_ESCALATE_MODELS`` as a comma-separated model ladder."""
    raw = os.environ.get("DACODE_ESCALATE_MODELS")
    if not raw:
        return None
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return models or None


def _env_test_command() -> tuple[str, ...] | None:
    """Read ``DACODE_TEST_COMMAND`` as an argv tuple (shell-quoted aware)."""
    raw = os.environ.get("DACODE_TEST_COMMAND")
    return tuple(shlex.split(raw)) if raw else None


def _default_vault() -> str | None:
    candidate = Path.home() / "Documents" / "ake_obsidian"
    return str(candidate) if candidate.is_dir() else None
