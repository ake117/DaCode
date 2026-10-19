"""ScriptExecutor — run a fixed command inside the workspace.

Used for the CLI demo path and for tests, where the "implementation" is a shell
command the variant carries in ``variant.payload['command']``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dacode.executor.base import ExecResult

if TYPE_CHECKING:
    from dacode.harness.models import HarnessVariant


class ScriptExecutor:
    """Runs ``variant.payload['command']`` (str or list) in the workspace."""

    def __init__(self, *, default_command: str | None = None, timeout: float = 300.0, shell: bool = True) -> None:
        self.default_command = default_command
        self.timeout = timeout
        self.shell = shell

    def run(self, variant: "HarnessVariant", workspace: str | Path) -> ExecResult:
        command = variant.payload.get("command", self.default_command)
        if not command:
            return ExecResult(exit_code=2, stderr="ScriptExecutor: no command provided", command="")
        argv = command if isinstance(command, list) else command
        try:
            proc = subprocess.run(
                argv,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=self.shell and isinstance(command, str),
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
