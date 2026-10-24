"""bwrap isolation for trials — the worktree protects the repo, this protects the host.

A trial runs model-written code. The git worktree gives it a private branch, not
a private machine: without isolation it can read `~/.ssh`, write outside the
checkout, and talk to anything. Bubblewrap gives us namespaces without a daemon
and without root.

Design choices:

- **Read-only root, private home.** The whole filesystem is mounted read-only and
  the user's home is replaced by an empty tmpfs, then the trial workspace is bound
  read-write on top. Paths the executor legitimately needs (a venv, the agent's
  own config) are re-bound explicitly, read-only.
- **Network off by default.** A test suite has no business opening sockets. The Pi
  executor *does* need the network to reach a model, so the caller opts in with
  ``network=True``; the critic never does.
- **Cleared environment, explicit allow-list.** Provider keys are passed only when
  asked for, so a stray `AWS_SECRET_ACCESS_KEY` in the shell cannot leak into a
  trial by accident.

Fail closed: if bwrap is missing, ``wrap`` raises ``IsolationUnavailable`` and the
CLI says so, rather than silently running unsandboxed.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

__all__ = [
    "IsolationPolicy",
    "IsolationUnavailable",
    "available",
    "bwrap_version",
    "wrap_command",
]

#: Variables a trial normally needs to function at all.
BASE_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR", "TERM")

#: Passed only when the caller opts in with ``network=True`` (an agent needs its key).
NETWORK_ENV = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "XAI_API_KEY",
)


class IsolationUnavailable(RuntimeError):
    """bwrap is not installed (or cannot create namespaces) on this host."""


@dataclass(frozen=True)
class IsolationPolicy:
    """How much of the host a trial may see."""

    enabled: bool = True
    network: bool = False
    #: Extra paths bound read-only (a venv, the agent's config directory…).
    read_only_paths: tuple[Path, ...] = field(default_factory=tuple)
    #: Extra environment variable names to pass through.
    env_allow: tuple[str, ...] = field(default_factory=tuple)

    def with_paths(self, *paths: str | Path | None) -> "IsolationPolicy":
        """Return a copy with more read-only bindings (None entries are ignored)."""
        extra = tuple(Path(p).expanduser() for p in paths if p)
        merged: list[Path] = list(self.read_only_paths)
        for path in extra:
            if path not in merged:
                merged.append(path)
        return IsolationPolicy(
            enabled=self.enabled,
            network=self.network,
            read_only_paths=tuple(merged),
            env_allow=self.env_allow,
        )


def available() -> bool:
    """True when bwrap is on PATH (it is a setuid/namespace helper, not a service)."""
    return shutil.which("bwrap") is not None


def bwrap_version() -> str | None:
    if not available():
        return None
    try:
        import subprocess

        proc = subprocess.run(["bwrap", "--version"], capture_output=True, text=True, timeout=10)
    except OSError:
        return None
    return (proc.stdout or proc.stderr).strip() or None


def allowed_env(
    policy: IsolationPolicy,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """The environment a trial may see: base + allow-list, and network keys only if permitted."""
    source = dict(os.environ if env is None else env)
    names = list(BASE_ENV) + list(policy.env_allow)
    if policy.network:
        names += list(NETWORK_ENV)
    return {name: source[name] for name in dict.fromkeys(names) if name in source}


def wrap_command(
    command: Sequence[str],
    *,
    workspace: str | Path,
    policy: IsolationPolicy,
    env: dict[str, str] | None = None,
    home: str | Path | None = None,
) -> list[str]:
    """Prefix ``command`` with a bwrap invocation implementing ``policy``."""
    if not policy.enabled:
        return list(command)
    if not available():
        raise IsolationUnavailable(
            "bwrap is not installed — install bubblewrap or run with isolation disabled"
        )

    workspace_path = Path(workspace).expanduser().resolve()
    if not workspace_path.is_dir():
        raise FileNotFoundError(f"workspace does not exist: {workspace_path}")

    home_path = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()

    argv: list[str] = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--unshare-cgroup-try",
        "--clearenv",
        # Read-only host, then hide the home directory, then expose what is needed.
        "--ro-bind", "/", "/",
    ]
    if home_path.is_dir():
        argv += ["--tmpfs", str(home_path)]
    if not policy.network:
        argv += ["--unshare-net"]

    # /proc, /dev and /tmp come before any bind: a workspace under /tmp would
    # otherwise be mounted over by the tmpfs and bwrap would fail to chdir.
    argv += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"]

    for path in policy.read_only_paths:
        for candidate in _bind_candidates(Path(path).expanduser(), home=home_path):
            argv += ["--ro-bind", str(candidate), str(candidate)]

    # The trial workspace is the only writable place that survives the run.
    argv += ["--bind", str(workspace_path), str(workspace_path)]
    argv += ["--chdir", str(workspace_path)]

    environment = allowed_env(policy, env)
    # TMPDIR from the host may point inside the home tmpfs; inside the sandbox the
    # only temp directory that exists is /tmp.
    environment["TMPDIR"] = "/tmp"
    for name, value in environment.items():
        argv += ["--setenv", name, value]
    argv += ["--", *command]
    return argv


def _bind_candidates(path: Path, *, home: Path | None = None) -> list[Path]:
    """A path plus what it really points at.

    A venv's ``bin/python`` is usually a symlink into the base interpreter, which
    may live under the home directory we just emptied — binding only the symlink
    leaves a dangling target and every command dies with
    ``execvp …: No such file or directory``. Bind the target (and its prefix) too.
    """
    home_path = home or Path.home().resolve()
    out: list[Path] = []

    def _exposes_home(candidate: Path) -> bool:
        """Binding $HOME or an ancestor of it would undo the home tmpfs."""
        try:
            resolved = candidate.resolve()
        except OSError:
            return False
        return resolved == home_path or home_path.is_relative_to(resolved)

    for candidate in (path,):
        if candidate.exists() and not _exposes_home(candidate):
            out.append(candidate)
    try:
        real = path.resolve()
    except OSError:
        real = None
    if real is not None and real != path:
        if real.exists() and not _exposes_home(real):
            out.append(real)
        prefix = real.parent.parent  # <prefix>/bin/python → <prefix>
        if prefix.exists() and not _exposes_home(prefix):
            out.append(prefix)
    return list(dict.fromkeys(out))


def describe(policy: IsolationPolicy) -> str:
    """One line for `dacode layers` and run summaries."""
    if not policy.enabled:
        return "off (trial code has host access)"
    bits = [f"bwrap {bwrap_version() or '?'}", "net:on" if policy.network else "net:off"]
    if policy.read_only_paths:
        bits.append("ro:" + ",".join(p.name for p in policy.read_only_paths))
    return " · ".join(bits)


def interpreter_binds(command: Iterable[str]) -> tuple[Path, ...]:
    """Everything the sandbox needs to start the test interpreter.

    A venv under the home directory disappears with the home tmpfs, and its
    ``bin/python`` is a symlink into a base install that may also live under home.
    Bind, in order: the interpreter itself, its venv root (detected by
    ``pyvenv.cfg``), the base prefix named in that file, and the resolved target.
    """
    python = _python_token(command)
    if python is None or not python.is_absolute():
        return ()
    candidates: list[Path] = [python, python.parent]
    venv_root = python.parent.parent
    cfg = venv_root / "pyvenv.cfg"
    if cfg.is_file():
        candidates.append(venv_root)
        try:
            for line in cfg.read_text(errors="ignore").splitlines():
                if line.lower().startswith("home"):
                    base_bin = Path(line.split("=", 1)[1].strip())
                    candidates.append(base_bin)
                    candidates.append(base_bin.parent)
        except OSError:
            pass
    return tuple(dict.fromkeys(p for p in candidates if p.exists()))


def _python_token(command: Iterable[str]) -> Path | None:
    for token in command:
        text = str(token)
        if text.endswith("python") or text.endswith("python3") or "/python" in text:
            return Path(text)
    return None


def interpreter_root(command: Iterable[str]) -> Path | None:
    """The directory holding the interpreter in a test command, if it is an absolute path."""
    for token in command:
        if token.endswith("python") or "/python" in token or token.endswith("python3"):
            path = Path(token)
            if path.is_absolute():
                return path.parent
    return None
