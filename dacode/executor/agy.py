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
from dacode.sandbox.bwrap import IsolationPolicy, IsolationUnavailable, allowed_env, wrap_command

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
        gemini_dir = Path.home() / ".gemini"
        # agy's login credentials are NOT under ~/.gemini — they live in
        # ~/.config/antigravity (verified: a sandboxed trial without it dies
        # with "authentication required" while a standalone `agy -p` succeeds).
        config_dir = Path.home() / ".config" / "antigravity"
        protected: list[Path] = list(policy.protected_paths)
        for candidate in (
            Path(binary_path).resolve().parent if binary_path else None,
            node_dir,
            *(
                base / sub
                for base in (gemini_dir, gemini_dir / "antigravity")
                for sub in (
                    "hooks", "skills", "plugins", "rules", "agents", "builtin",
                    "extensions", "node_modules", "dist", "lib", "bin",
                    "settings.json", "mcp_config.json",
                )
            ),
        ):
            if candidate and candidate not in protected:
                protected.append(candidate)
        # Auth handling. agy has no env-key path: it authenticates from OAuth
        # state under ~/.gemini (unlike Pi, whose provider key arrives through
        # the environment), so masking those files by default would make every
        # sandboxed trial die at login. Default is therefore bind: the auth
        # files are re-bound READ-ONLY after the writable ~/.gemini mount (the
        # trial can use them, not rewrite them) — the same trust level as the
        # provider keys a networked trial already sees via NETWORK_ENV. The
        # gate never runs the executor's policy, so the gate still sees none
        # of this. Set DACODE_AGY_AUTH=mask to hide them instead (only works
        # if you inject credentials another way).
        hidden: list[Path] = list(policy.hidden_files)
        auth_files = (
            gemini_dir / "antigravity" / "mcp_config.json",
            gemini_dir / "oauth_creds.json",
            gemini_dir / "google_accounts.json",
            # the real login state — read-only so a trial can authenticate but
            # not rotate or exfiltrate-write the tokens it holds
            config_dir / "credential-user-scope",
            config_dir / "plugin-secrets.json",
        )
        if (os.environ.get("DACODE_AGY_AUTH") or "bind").lower() == "mask":
            for secret in auth_files:
                if secret not in hidden:
                    hidden.append(secret)
        else:
            for secret in auth_files:
                if secret not in protected:
                    protected.append(secret)
        # Auth lives in the user keyring, reached over the D-Bus session bus
        # (/run/user/$UID/bus). The sandbox tmpfs's /run hides that socket, so
        # agy falls back to a token file that does not exist and dies with
        # "authentication required" (verified with an in-sandbox strace: the
        # keyring read fails, the file fallback misses). Bind the bus socket —
        # DACODE_AGY_DBUS=off refuses it, at the cost of agy never starting.
        # Trust note: this is the *executor* policy, which already carries the
        # network and the agent's own OAuth token (bound read-only); the gate
        # never runs under it, so the tested code never sees the bus.
        if (os.environ.get("DACODE_AGY_DBUS") or "bind").lower() != "off":
            bus = Path("/run/user") / str(os.getuid()) / "bus"
            # protected_paths ro-binds after the writable mounts AND accepts
            # files — the writable loop only binds directories, which would
            # silently skip the socket. D-Bus clients locate the bus via
            # $XDG_RUNTIME_DIR, so that name rides along in env_allow.
            if bus.exists() and bus not in policy.protected_paths:
                protected.append(bus)
            if "XDG_RUNTIME_DIR" not in policy.env_allow:
                policy = dataclasses.replace(
                    policy, env_allow=policy.env_allow + ("XDG_RUNTIME_DIR",)
                )
        return dataclasses.replace(
            policy,
            # agy is a Go binary that refuses to start without $HOME, and it
            # resolves its state tree (~/.gemini) from it. bwrap clears the
            # environment, so HOME must be re-set explicitly — the value is a
            # path name, not a secret; the directory itself stays a tmpfs with
            # only the binds this policy declares.
            env_allow=policy.env_allow + ("HOME",),
            writable_paths=policy.writable_paths
            + (
                gemini_dir,
                # writable like ~/.gemini, but the two credential files inside
                # it are re-bound read-only right below (later mounts win)
                config_dir,
            ),
            protected_paths=tuple(protected),
            hidden_files=tuple(hidden),
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
            child_env = allowed_env(policy)
        else:
            child_env = allowed_env(
                IsolationPolicy(
                    enabled=False,
                    network=True if self.isolation is None else self.isolation.network,
                    env_allow=("HOME", *(self.isolation.env_allow if self.isolation else ())),
                )
            )
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=child_env,
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
