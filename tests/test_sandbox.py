"""Tests for the git sandbox layer."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dacode.sandbox import GitSandbox, SandboxError


def _branches(repo: Path) -> str:
    return subprocess.run(
        ["git", "branch", "--list"], cwd=str(repo), capture_output=True, text=True
    ).stdout


def test_create_makes_isolated_worktree_on_its_own_branch(git_repo):
    sb = GitSandbox(git_repo)
    path = sb.create("task-a")
    assert path.is_dir()
    assert path != git_repo
    assert (path / "README.md").is_file()
    assert "dacode/trial/task-a" in _branches(git_repo)


def test_checkpoint_commits_and_rollback_restores_prior_content(git_repo):
    sb = GitSandbox(git_repo)
    path = sb.create("t")
    (path / "new.txt").write_text("hello", encoding="utf-8")
    sha1 = sb.checkpoint("t", "add new.txt")
    (path / "new.txt").write_text("changed", encoding="utf-8")
    sha2 = sb.checkpoint("t", "change new.txt")
    assert sha1 != sha2

    sb.rollback("t", "HEAD~1")
    assert (path / "new.txt").read_text(encoding="utf-8") == "hello"


def test_remove_deletes_worktree_and_branch(git_repo):
    sb = GitSandbox(git_repo)
    path = sb.create("t")
    sb.remove("t")
    assert not path.exists()
    assert "dacode/trial/t" not in _branches(git_repo)


def test_create_twice_raises(git_repo):
    sb = GitSandbox(git_repo)
    sb.create("t")
    with pytest.raises(SandboxError):
        sb.create("t")


def test_create_without_commits_raises(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    sb = GitSandbox(repo)
    with pytest.raises(SandboxError):
        sb.create("t")


def test_list_includes_base_and_trial_worktrees(git_repo):
    sb = GitSandbox(git_repo)
    trial = sb.create("t")
    paths = {info.path for info in sb.list()}
    assert git_repo in paths
    assert trial in paths
