"""Shared pytest fixtures for the DaCode suite."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one commit and a passing test file."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dacode@test.local")
    _git(repo, "config", "user.name", "DaCode Test")
    (repo / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


@pytest.fixture
def rig_repo(tmp_path: Path) -> Path:
    """A repo whose test imports ``calc`` — a module that does not exist yet.

    Used by the harness/orchestrator/CLI tests to exercise the full loop:
    a variant "wins" only when it creates ``calc.py`` so the test passes.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dacode@test.local")
    _git(repo, "config", "user.name", "DaCode Test")
    (repo / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial failing test")
    return repo


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A miniature vault with a couple of notes to retrieve."""
    v = tmp_path / "vault"
    (v / "Resources" / "AI Agents").mkdir(parents=True)
    (v / "Resources" / "AI Agents" / "Harness2.md").write_text(
        "---\ntitle: Harness2 Recursive Harnessing\ntags:\n  - ai/agent\n---\n\n"
        "Propose Probe Compose recursion for coding agents.\n",
        encoding="utf-8",
    )
    (v / "Resources" / "AI Agents" / "Sandbox.md").write_text(
        "---\ntitle: Git Sandbox Worktrees\n---\n\n"
        "Use isolated git worktrees per trial so experiments never collide.\n",
        encoding="utf-8",
    )
    return v


@pytest.fixture(autouse=True)
def _quiet_runlog(monkeypatch, tmp_path):
    """Keep tests out of the real run log and state store."""
    monkeypatch.setenv("DACODE_RUNLOG", "off")
    monkeypatch.setenv("DACODE_MEMORY_DB", str(tmp_path / "memory.db"))
    monkeypatch.setenv("DACODE_SEMANTIC", "off")
    monkeypatch.setenv("DACODE_EMBED_DB", str(tmp_path / "embeddings.db"))
    monkeypatch.delenv("DACODE_EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("DACODE_EMBED_MODEL", raising=False)
