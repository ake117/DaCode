"""ScriptExecutor — run a fixed command inside the workspace.

Used for the CLI demo path and for tests, where the "implementation" is a shell
command the variant carries in ``variant.payload['command']``.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dacode.executor.base import ExecResult
from dacode.sandbox.bwrap import IsolationPolicy, IsolationUnavailable, wrap_command

if TYPE_CHECKING:
    from dacode.harness.models import HarnessVariant


class ScriptExecutor:
    """Runs ``variant.payload['command']`` (str or list) in the workspace."""

    def __init__(
        self,
        *,
        default_command: str | None = None,
        timeout: float = 300.0,
        shell: bool = True,
        isolation: IsolationPolicy | None = None,
    ) -> None:
        self.default_command = default_command
        self.timeout = timeout
        self.shell = shell
        self.isolation = isolation

    def run(self, variant: "HarnessVariant", workspace: str | Path) -> ExecResult:
        command = variant.payload.get("command", self.default_command)
        if not command:
            return ExecResult(exit_code=2, stderr="ScriptExecutor: no command provided", command="")
        argv = command if isinstance(command, list) else command
        use_shell = self.shell and isinstance(command, str)
        if self.isolation is not None and self.isolation.enabled:
            # Not a login shell: inside bwrap /etc/profile would run against an
            # empty $HOME and clobber the allow-listed PATH (audit L2).
            base = ["bash", "-c", command] if use_shell else shlex.split(command)
            try:
                argv = wrap_command(base, workspace=workspace, policy=self.isolation)
                use_shell = False
            except IsolationUnavailable as exc:
                return ExecResult(exit_code=126, stderr=f"isolation unavailable: {exc}", command=str(command))
        try:
            proc = subprocess.run(
                argv,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=use_shell,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=f"timed out after {self.timeout}s",
                timed_out=True,
                command=str(command),
            )
        except FileNotFoundError as exc:
            return ExecResult(exit_code=127, stderr=str(exc), command=str(command))
        return ExecResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=str(command),
        )
