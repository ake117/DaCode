"""PiExecutor — drive the Pi coding agent (``~/bin/pi``) non-interactively.

Pi runs with ``--print`` inside the trial worktree.  The variant's
``system_prompt`` and the seeded memory snippets are passed through
``--system-prompt`` / ``--append-system-prompt``; the task text is the trailing
message.  Pi's own provider/model settings (openrouter +
deepseek/deepseek-v4.1-flash) are used unless overridden here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dacode.executor.base import ExecResult
from dacode.sandbox.bwrap import IsolationPolicy, IsolationUnavailable, wrap_command

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
        isolation: IsolationPolicy | None = None,
    ) -> None:
        self.binary = binary
        self.provider = provider
        self.model = model
        self.timeout = timeout
        self.extra_args = tuple(extra_args)
        self.tools = tuple(tools)
        self.isolation = isolation

    def _resolve_binary(self) -> str | None:
        """The real binary, symlinks resolved.

        bwrap makes $HOME a tmpfs, so a launcher symlink like ``~/bin/pi``
        (pointing into ``~/.pi/agent/bin``) dangles inside the sandbox and
        ``execvp`` fails with a bare "No such file or directory". Executing the
        resolved path works because the rig binds the real location read-only.
        """
        found = shutil.which(self.binary)
        return os.path.realpath(found) if found else None

    def build_command(self, variant: "HarnessVariant", task: str) -> list[str]:
        cmd = [self.binary, "--print", "--mode", "text"]
        model = variant.model or self.model
        if self.provider and model:
            cmd += ["--provider", self.provider, "--model", model]
        if variant.system_prompt:
            # Space form: pi 1.4 rejects the `--opt=value` spelling. A prompt
            # that starts with "-" gets a leading newline so no parser, on any
            # version, can read it as a flag (audit M3, resurfaced on 1.4).
            prompt = ("\n" + variant.system_prompt
                      if variant.system_prompt.startswith("-") else variant.system_prompt)
            cmd += ["--system-prompt", prompt]
        for snippet in variant.memory_snippets:
            snippet = "\n" + snippet if snippet.startswith("-") else snippet
            cmd += ["--append-system-prompt", snippet]
        # A trial is one-shot and the sandbox binds ~/.pi read-only, so there is
        # nowhere to save a session — and no reason to keep one.
        cmd.append("--no-session")
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
        resolved = self._resolve_binary()
        if resolved:
            # Exec the real file: see _resolve_binary for why the PATH name is
            # not trustworthy inside the sandbox.
            cmd[0] = resolved
        if self.isolation is not None and self.isolation.enabled:
            # The agent needs its own binary, config and (to reach a model) the
            # network; everything else stays hidden.
            binary_path = self._resolve_binary()
            import dataclasses

            policy = self.isolation.with_paths(
                Path(binary_path).resolve().parent if binary_path else None,
                os.environ.get("NODE_PATH"),
            )
            # pi 1.4 takes a lock file next to everything it reads (settings,
            # auth, models), so a read-only ~/.pi breaks even reading. Mount the
            # agent directory writable; auth.json is still masked by the policy's
            # hidden_files, which wrap_command applies after writable binds.
            policy = dataclasses.replace(
                policy,
                writable_paths=policy.writable_paths + (Path.home() / ".pi",),
            )
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
