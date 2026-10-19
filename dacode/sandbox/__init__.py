"""Layer 5 — Isolated Git sandbox (worktrees + checkpoints).

Every experiment the rig runs happens in its own ``git worktree`` on a branch
named ``<prefix>/<task-id>``.  That gives three properties the blueprint asks
for:

* **Isolation** — a trial can wreck its own files without touching the base
  checkout or sibling trials.
* **Checkpointing** — commit inside the trial, then ``rollback`` to any ref.
* **Cleanup** — remove the worktree and branch when the trial loses.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["GitSandbox", "GitError", "SandboxError", "WorktreeInfo"]


class GitError(RuntimeError):
    """A git command exited non-zero."""


class SandboxError(RuntimeError):
    """The sandbox could not perform the requested operation."""


def _safe_slug(value: str) -> str:
    """Turn an arbitrary task id into a filesystem/branch-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    return slug or "task"


@dataclass(frozen=True)
class WorktreeInfo:
    path: Path
    branch: str | None
    head: str | None
    detached: bool
    bare: bool


class GitSandbox:
    """Manage per-task git worktrees for isolated experiments."""

    def __init__(
        self,
        repo: str | Path,
        sandbox_root: str | Path | None = None,
        *,
        base_ref: str = "HEAD",
        branch_prefix: str = "dacode/trial",
        git_bin: str = "git",
    ) -> None:
        self.repo = Path(repo).expanduser().resolve()
        self.sandbox_root = (
            Path(sandbox_root).expanduser().resolve()
            if sandbox_root is not None
            else self.repo.parent / ".dacode" / "worktrees"
        )
        self.base_ref = base_ref
        self.branch_prefix = branch_prefix
        self.git_bin = git_bin

    # -- internals ---------------------------------------------------------

    def _run(self, *args: str, cwd: str | Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.git_bin, *args],
            cwd=str(cwd or self.repo),
            capture_output=True,
            text=True,
        )

    def _git(self, *args: str, cwd: str | Path | None = None, check: bool = True) -> str:
        proc = self._run(*args, cwd=cwd)
        if check and proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({proc.returncode}) in {cwd or self.repo}: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout

    def _branch_for(self, task_id: str) -> str:
        return f"{self.branch_prefix}/{_safe_slug(task_id)}"

    def _assert_has_commits(self) -> None:
        proc = self._run("rev-parse", "--verify", "HEAD")
        if proc.returncode != 0:
            raise SandboxError(
                f"repository at {self.repo} has no commits; create an initial "
                "commit before asking DaCode to branch a trial worktree"
            )

    # -- public API --------------------------------------------------------

    def worktree_path(self, task_id: str) -> Path:
        """Deterministic worktree path for ``task_id`` (may not exist yet)."""
        return self.sandbox_root / _safe_slug(task_id)

    def create(self, task_id: str, *, base_ref: str | None = None) -> Path:
        """Create a fresh isolated worktree for ``task_id``.

        Raises :class:`SandboxError` if the path already exists.
        """
        self._assert_has_commits()
        path = self.worktree_path(task_id)
        if path.exists():
            raise SandboxError(f"worktree already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        branch = self._branch_for(task_id)
        # -B resets an existing branch so re-running a task id is deterministic.
        self._git("worktree", "add", "-B", branch, str(path), base_ref or self.base_ref)
        return path

    def checkpoint(self, task_id: str, message: str) -> str:
        """Stage everything in the worktree and commit. Returns the new SHA."""
        path = self.worktree_path(task_id)
        if not path.exists():
            raise SandboxError(f"no worktree for task {task_id!r} at {path}")
        self._git("add", "-A", cwd=path)
        self._git("commit", "--allow-empty", "-m", message, cwd=path)
        return self._git("rev-parse", "HEAD", cwd=path).strip()

    def head_sha(self, task_id: str) -> str:
        return self._git("rev-parse", "HEAD", cwd=self.worktree_path(task_id)).strip()

    def rollback(self, task_id: str, ref: str = "HEAD~1") -> str:
        """Hard-reset the trial worktree to ``ref``. Returns the resulting SHA."""
        path = self.worktree_path(task_id)
        self._git("reset", "--hard", ref, cwd=path)
        self._git("clean", "-fd", cwd=path)
        return self._git("rev-parse", "HEAD", cwd=path).strip()

    def remove(self, task_id: str, *, delete_branch: bool = True, force: bool = True) -> None:
        """Tear the worktree down; optionally delete its branch."""
        path = self.worktree_path(task_id)
        if path.exists():
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(path))
            self._git(*args)
        self._git("worktree", "prune", check=False)
        if delete_branch:
            self._git("branch", "-D", self._branch_for(task_id), check=False)

    def list(self) -> list[WorktreeInfo]:
        """Return every worktree registered with the repo."""
        out = self._git("worktree", "list", "--porcelain")
        infos: list[WorktreeInfo] = []
        cur: dict[str, object] = {}
        for line in out.splitlines():
            if not line.strip():
                if cur:
                    infos.append(_to_info(cur))
                    cur = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                cur["path"] = value
            elif key == "branch":
                cur["branch"] = value.removeprefix("refs/heads/")
            elif key == "HEAD":
                cur["head"] = value
            elif key == "detached":
                cur["detached"] = True
            elif key == "bare":
                cur["bare"] = True
        if cur:
            infos.append(_to_info(cur))
        return infos


def _to_info(cur: dict) -> WorktreeInfo:
    return WorktreeInfo(
        path=Path(str(cur.get("path", ""))),
        branch=cur.get("branch") if isinstance(cur.get("branch"), str) else None,
        head=cur.get("head") if isinstance(cur.get("head"), str) else None,
        detached=bool(cur.get("detached", False)),
        bare=bool(cur.get("bare", False)),
    )
