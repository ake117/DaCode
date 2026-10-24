"""PiExecutor — drive the Pi coding agent (``~/bin/pi``) non-interactively.

Pi runs with ``--print`` inside the trial worktree.  The variant's
``system_prompt`` and the seeded memory snippets are passed through
``--system-prompt`` / ``--append-system-prompt``; the task text is the trailing
message.  Pi's own provider/model settings (openrouter +
deepseek/deepseek-v4.1-flash) are used unless overridden here.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dacode.executor.base import ExecResult

if TYPE_CHECKING:
    from dacode.harness.models import HarnessVariant


class PiExecutor:
    """Invoke the Pi coding agent as the change-making executor."""

    def __init__(
        self,
        *,
        binary: str = "pi",
        provider: str | None = "openrouter",
        model: str | None = "deepseek/deepseek-v4.1-flash",
        timeout: float = 900.0,
        extra_args: tuple[str, ...] = (),
        tools: tuple[str, ...] = (),
    ) -> None:
        self.binary = binary
        self.provider = provider
        self.model = model
        self.timeout = timeout
        self.extra_args = tuple(extra_args)
        self.tools = tuple(tools)

    def _resolve_binary(self) -> str | None:
        return shutil.which(self.binary)

    def build_command(self, variant: "HarnessVariant", task: str) -> list[str]:
        cmd = [self.binary, "--print", "--mode", "text"]
        model = variant.model or self.model
        if self.provider and model:
            cmd += ["--provider", self.provider, "--model", model]
        if variant.system_prompt:
            cmd += ["--system-prompt", variant.system_prompt]
        for snippet in variant.memory_snippets:
            cmd += ["--append-system-prompt", snippet]
        if self.tools:
            cmd += ["--tools", ",".join(self.tools)]
        cmd += list(self.extra_args)
        cmd += ["--", task]
        return cmd

    def run(self, variant: "HarnessVariant", workspace: str | Path) -> ExecResult:
        if self._resolve_binary() is None:
            return ExecResult(
                exit_code=127,
                stderr=f"PiExecutor: '{self.binary}' not found on PATH",
                command="",
            )
        cmd = self.build_command(variant, variant.payload.get("task", ""))
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
                stdout=exc.stdout or "",
                stderr=f"pi timed out after {self.timeout}s",
                timed_out=True,
                command=" ".join(cmd),
            )
        return ExecResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=" ".join(cmd),
        )
