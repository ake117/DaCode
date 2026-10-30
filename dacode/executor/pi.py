"""PiExecutor — drive the Pi coding agent (``~/bin/pi``) non-interactively.

Pi runs with ``--print`` inside the trial worktree.  The variant's
``system_prompt`` and the seeded memory snippets are passed through
``--system-prompt`` / ``--append-system-prompt``; the task text is the trailing
message.  Pi's own provider/model settings (openrouter +
deepseek/deepseek-v4.1-flash) are used unless overridden here.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from dacode.executor.base import ExecResult
from dacode.sandbox.bwrap import IsolationPolicy, IsolationUnavailable, wrap_command

if TYPE_CHECKING:
    from dacode.harness.models import HarnessVariant


def provider_env(provider: str | None, base: dict[str, str]) -> dict[str, str]:
    """The child environment, with provider-key aliases applied.

    DaCode's registry names the z.ai key ``GLM_API_KEY`` (llm/providers.py), but
    Pi's own provider layer reads ``ZAI_API_KEY`` for the same provider id — so a
    user following DaCode's docs got Pi dying with "No API key found for zai"
    while the key sat one name away the whole time. An existing ``ZAI_API_KEY``
    always wins.
    """
    if provider == "zai" and base.get("GLM_API_KEY") and not base.get("ZAI_API_KEY"):
        return {**base, "ZAI_API_KEY": base["GLM_API_KEY"]}
    return base


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

    def _sandbox_policy(self, binary_path: str | None) -> IsolationPolicy:
        """The executor's policy: agent binary, node runtime, agent state dir.

        Node needs the same realpath treatment as the agent binary: pi's shebang
        is ``#!/usr/bin/env node``, and a Node install under the home directory
        (nvm/fnm/volta) is hidden by the home tmpfs, so ``env node`` falls through
        to an older system interpreter and Pi dies with a SyntaxError.
        ``$NODE_PATH`` stays bound for setups that point it at extra module roots.
        """
        policy = self.isolation.with_paths(
            Path(binary_path).resolve().parent if binary_path else None,
            os.environ.get("NODE_PATH"),
        )
        node = shutil.which("node")
        if node:
            real = Path(node).resolve()
            policy = policy.with_paths(real, real.parent)
        # pi 1.4 takes a lock file next to everything it reads (settings,
        # auth, models), so a read-only ~/.pi breaks even reading. Mount the
        # agent directory writable; auth.json is still masked by the policy's
        # hidden_files, which wrap_command applies after writable binds.
        # The writable mount shadows the earlier read-only bind of the
        # binary's directory (and of the node runtime just above), so both are
        # re-bound read-only *after* it: otherwise a trial could replace an
        # executable the host itself runs outside the sandbox (audit #3).
        return dataclasses.replace(
            policy,
            writable_paths=policy.writable_paths + (Path.home() / ".pi",),
            protected_paths=tuple({
                p for p in (
                    Path(binary_path).resolve().parent if binary_path else None,
                    (Path(shutil.which("node")).resolve().parent
                     if shutil.which("node") else None),
                ) if p
            }),
        )

    def run(self, variant: "HarnessVariant", workspace: str | Path) -> ExecResult:
        if self._resolve_binary() is None:
            return ExecResult(
                exit_code=127,
                stderr=f"PiExecutor: '{self.binary}' not found on PATH",
                command="",
            )
        env = provider_env(self.provider, dict(os.environ))
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
            policy = self._sandbox_policy(binary_path)
            try:
                cmd = wrap_command(cmd, workspace=workspace, policy=policy, env=env)
            except IsolationUnavailable as exc:
                return ExecResult(exit_code=126, stderr=f"isolation unavailable: {exc}", command="")
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
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
