"""AgyExecutor — drive the Antigravity CLI (``agy``) non-interactively.

agy has no ``--system-prompt`` flag, so the variant's system prompt rides at
the top of the ``-p`` prompt body, followed by an explicit execute-directly
guard. Two agy behaviours burned real runs and are pinned here:

- ``--mode plan`` (any plan mode) stops at an approval gate and writes nothing
  — trials must run with the default mode and ``--dangerously-skip-permissions``.
- In print mode a prompt that looks like a slash command is expanded as one;
  ``--disable-slash-commands`` turns that off.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dacode.executor.base import ExecResult
from dacode.harness.optimizer import DEFAULT_SYSTEM_PROMPT
from dacode.sandbox.bwrap import IsolationPolicy, IsolationUnavailable, wrap_command

if TYPE_CHECKING:
    from dacode.harness.models import HarnessVariant


class AgyExecutor:
    """Run one harness variant through ``agy -p`` inside the trial worktree."""

    def __init__(
        self,
        *,
        binary: str = "agy",
        model: str | None = "gemini-4-argon-high",
        timeout: float = 900.0,
        extra_args: tuple[str, ...] = (),
        isolation: IsolationPolicy | None = None,
    ) -> None:
        self.binary = binary
        self.model = model
        self.timeout = timeout
        self.extra_args = tuple(extra_args)
        self.isolation = isolation

    def _resolve_binary(self) -> str | None:
        # Same realpath treatment as Pi: a launcher symlink under the home
        # directory dangles inside the sandbox's home tmpfs, and exec'ing the
        # PATH name then fails with a bare "No such file or directory".
        found = shutil.which(self.binary)
        return os.path.realpath(found) if found else None

    def build_command(self, variant: "HarnessVariant", task: str) -> list[str]:
        system = variant.system_prompt or DEFAULT_SYSTEM_PROMPT
        # agy has no system-prompt flag: the harness rules ride at the top of
        # the prompt body, then a guard against its plan/approval gates, then
        # the task text last.
        prompt = (
            f"{system}\n\n"
            "Work directly: never ask questions, never request confirmation, "
            "never present a plan for approval — make the change now.\n\n"
            f"Task:\n{task}"
        )
        # A prompt that starts with "-" could be read as a flag on any version.
        if prompt.startswith("-"):
            prompt = "\n" + prompt
        cmd = [
            self.binary,
            "-p", prompt,
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
        ]
        model = variant.model or self.model
        if model:
            cmd += ["--model", model]
        cmd += list(self.extra_args)
        return cmd

    def _sandbox_policy(self, binary_path: str | None) -> IsolationPolicy:
        """The executor's policy: agy binary, node runtime, agy state dir.

        Only called from run() with isolation enabled, so ``self.isolation``
        is not None here.

        agy is a Node CLI like pi (same shebang realpath issue), and its
        conversation/state tree lives under ``~/.gemini`` — the home tmpfs
        makes that directory fresh per trial, so bind it writable for the
        run. The binary and node directories are re-bound read-only after
        the writable mount for the same audit-#3 reason as Pi's policy.
        """
        assert self.isolation is not None
        policy = self.isolation.with_paths(
            Path(binary_path).resolve().parent if binary_path else None,
            os.environ.get("NODE_PATH"),
        )
        node = shutil.which("node")
        node_dir = Path(node).resolve().parent if node else None
        if node_dir:
            policy = policy.with_paths(node_dir, node_dir)
        return dataclasses.replace(
            policy,
            writable_paths=policy.writable_paths + (Path.home() / ".gemini",),
            protected_paths=tuple({
                p for p in (
                    Path(binary_path).resolve().parent if binary_path else None,
                    node_dir,
                ) if p
            }),
        )

    def run(self, variant: "HarnessVariant", workspace: str | Path) -> ExecResult:
        if self._resolve_binary() is None:
            return ExecResult(
                exit_code=127,
                stderr=f"AgyExecutor: '{self.binary}' not found on PATH",
                command="",
            )
        cmd = self.build_command(variant, variant.payload.get("task", ""))
        resolved = self._resolve_binary()
        if resolved:
            cmd[0] = resolved
        if self.isolation is not None and self.isolation.enabled:
            binary_path = self._resolve_binary()
            policy = self._sandbox_policy(binary_path)
            try:
                cmd = wrap_command(cmd, workspace=workspace, policy=policy)
            except IsolationUnavailable as exc:
                return ExecResult(exit_code=126, stderr=f"isolation unavailable: {exc}", command="")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                exit_code=124,
                stdout=str(exc.stdout or ""),
                stderr=f"agy timed out after {self.timeout}s",
                timed_out=True,
                command=" ".join(cmd),
            )
        return ExecResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=" ".join(cmd),
        )
