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
import shlex
import shutil
import subprocess
import tempfile
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
    "GLM_API_KEY",
    "ZAI_API_KEY",  # Pi's own name for the z.ai key — see executor/pi.py
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
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
    #: Files replaced by /dev/null inside the sandbox (a repository's own .env, an
    #: agent's auth file): readable parent, invisible file.
    hidden_files: tuple[Path, ...] = field(default_factory=tuple)
    #: Extra directories bound read-write (the gate's JUnit report directory).
    writable_paths: tuple[Path, ...] = field(default_factory=tuple)
    #: Paths re-bound read-only *after* the writable binds. Later mounts shadow
    #: earlier ones, so a read-only entry in ``read_only_paths`` that lives under
    #: a ``writable_paths`` parent is silently shadowed — an executor policy that
    #: makes ``~/.pi`` writable for the agent's lock file would otherwise leave
    #: the agent's own binary directory writable, and a trial could replace the
    #: executable the host runs next (follow-up audit, Oct 2026). Anything listed
    #: here wins over the writable ancestor above it.
    protected_paths: tuple[Path, ...] = field(default_factory=tuple)

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
            hidden_files=self.hidden_files,
            writable_paths=self.writable_paths,
            protected_paths=self.protected_paths,
        )


_AVAILABLE: bool | None = None
_EMPTY_MASK: str | None = None


def _empty_mask_file() -> str:
    """Return a reusable 0-byte file on the host for masking hidden_files."""
    import atexit

    global _EMPTY_MASK
    if _EMPTY_MASK is not None and os.path.isfile(_EMPTY_MASK):
        return _EMPTY_MASK
    fd, path = tempfile.mkstemp(prefix="dacode-empty-mask-")
    os.close(fd)
    _EMPTY_MASK = path
    atexit.register(lambda p=path: Path(p).unlink(missing_ok=True))
    return path


def available(*, probe: bool = True) -> bool:
    """True when bwrap is present *and* can actually create namespaces.

    Being on PATH is not enough: Ubuntu 24.04 restricts unprivileged user
    namespaces (AppArmor, ``max_user_namespaces=0``) and containers often block
    them, in which case every wrapped command would fail with bwrap's own exit
    code 1 instead of failing closed (external audit, Oct 2026). The probe runs
    once and is cached.
    """
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    binary = shutil.which("bwrap")
    if binary is None:
        _AVAILABLE = False
        return False
    if not probe:
        _AVAILABLE = True
        return True
    try:
        proc = subprocess.run(
            [binary, "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev",
             "--unshare-pid", "--die-with-parent", "/bin/true"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        _AVAILABLE = False
        return False
    _AVAILABLE = proc.returncode == 0
    return _AVAILABLE


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


def exposes_home(path: str | Path, home: str | Path | None = None) -> bool:
    """Would mounting ``path`` re-expose the home directory?

    True when the path *is* ``$HOME``, an ancestor of it, or a directory/file
    under it that holds credentials (see :func:`_is_home_secret`). Bind targets
    that pass this check are safe to expose read-write; the rest must stay out.
    """
    home_path = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return True  # unreadable/unresolvable path: fail closed
    if resolved == home_path or home_path.is_relative_to(resolved):
        return True
    return _is_home_secret(resolved, home_path)


def wrap_command(
    command: Sequence[str],
    *,
    workspace: str | Path,
    policy: IsolationPolicy,
    env: dict[str, str] | None = None,
    home: str | Path | None = None,
    read_only_workspace: bool = False,
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
    # Host sockets live under /run (/run/user/$UID/bus, ssh-agent, docker.sock) and
    # /var/tmp keeps other processes' droppings; neither belongs in a trial.
    argv += ["--tmpfs", "/run", "--tmpfs", "/var/tmp"]

    # A networked trial needs name resolution. On systemd-resolved hosts
    # /etc/resolv.conf is a symlink into /run — which the sandbox just replaced
    # with an empty tmpfs — so the name dangles and DNS dies. Bind the real
    # directory back over the tmpfs (a file bind onto the dangling symlink name
    # fails: bwrap cannot create through it). Regular-file hosts need nothing.
    if policy.network:
        resolv = Path("/etc/resolv.conf")
        try:
            target = resolv.resolve(strict=True)
        except OSError:
            target = resolv
        if target.is_file() and target.parent != Path("/etc"):
            argv += ["--ro-bind", str(target.parent), str(target.parent)]

    for path in policy.read_only_paths:
        for candidate in _bind_candidates(
            Path(path).expanduser(),
            home=home_path,
            workspace=workspace_path,
            trust_workspace=read_only_workspace,
        ):
            argv += ["--ro-bind", str(candidate), str(candidate)]

    # Writable binds come before the masks: a hidden file inside a writable
    # directory (the agent's auth.json under a writable ~/.pi, or <repo>/.env
    # inside workspace_path during measure_baseline) must stay hidden.
    for extra in policy.writable_paths:
        target = Path(extra).expanduser().resolve()
        if target.is_dir():
            argv += ["--bind", str(target), str(target)]

    # A read-only workspace bind is for runs that only measure (the untouched
    # repo's baseline): the gate's sandbox must not be able to write the main
    # checkout. Trial workspaces stay read-write — that is where trials commit.
    bind_flag = "--ro-bind" if read_only_workspace else "--bind"
    argv += [bind_flag, str(workspace_path), str(workspace_path)]

    # Protected re-binds come after the writable binds (including workspace_path)
    # so they shadow them: a read-only mount on a child of a writable parent is
    # the only way the child actually stays read-only (later mounts win).
    protected_targets = [Path(extra).expanduser().resolve() for extra in policy.protected_paths]
    ws_dot_git = workspace_path / ".git"
    if not read_only_workspace and not ws_dot_git.is_symlink() and ws_dot_git.exists():
        if ws_dot_git not in protected_targets:
            protected_targets.append(ws_dot_git)
    for target in protected_targets:
        if target.exists():
            argv += ["--ro-bind", str(target), str(target)]

    # Files the policy hides are replaced by an empty regular file, so a
    # repository's own .env (or an agent's auth file) reads back as empty even
    # though its parent is mounted. /dev/null cannot be used: a bind of the
    # character device denies reads outright (EACCES), which readers treat as a
    # hard error instead of "no secrets here". Masks are emitted last on purpose
    # — later mounts shadow earlier ones.
    if any(
        Path(h).expanduser().exists() and not Path(h).expanduser().is_dir()
        for h in policy.hidden_files
    ):
        empty = _empty_mask_file()
        for hidden in policy.hidden_files:
            target = Path(hidden).expanduser()
            if target.exists() and not target.is_dir():
                argv += ["--ro-bind", empty, str(target.resolve())]

    argv += ["--chdir", str(workspace_path)]

    environment = allowed_env(policy, env)
    # TMPDIR from the host may point inside the home tmpfs; inside the sandbox the
    # only temp directory that exists is /tmp.
    environment["TMPDIR"] = "/tmp"
    for name, value in environment.items():
        argv += ["--setenv", name, value]
    argv += ["--", *command]
    return argv


#: Credentials, state stores, vaults, and personal directories under $HOME that
#: are never bound into a sandbox through read_only_paths / exposes_home.
HOME_SECRET_DIRS: tuple[str, ...] = (
    ".ssh", ".gnupg", ".aws", ".kube", ".docker", ".password-store", ".mozilla",
    ".thunderbird", ".config", ".cache", ".pki", ".azure", ".gsutil", ".subversion",
    ".1password", ".bitwarden", ".op", ".vault", ".terraform.d", ".pulumi",
    "Documents", "Downloads", "Desktop",
)
HOME_SECRET_FILES: tuple[str, ...] = (
    ".env", ".git-credentials", ".netrc", ".npmrc", ".pypirc", ".pgpass", ".my.cnf",
    ".boto", ".s3cfg", ".rclone.conf", ".vault-token",
    ".bash_history", ".zsh_history", ".sh_history", ".python_history",
    ".node_repl_history", ".lesshst", ".viminfo", ".wget-hsts",
)
HOME_SECRET_RELATIVE: tuple[str, ...] = (
    ".hermes/.env", ".hermes/config.yaml", ".hermes/google_token.json",
    ".config/gcloud", ".config/gh", ".docker/config.json",
    ".pi/agent/auth.json",
    ".gemini/antigravity/mcp_config.json", ".gemini/oauth_creds.json", ".gemini/google_accounts.json",
    ".local/state", ".local/share/keyrings", ".local/share/gnupg", ".local/share/dacode",
    ".cargo/credentials", ".cargo/credentials.toml", ".gem/credentials", ".composer/auth.json",
)
#: Top-level $HOME directories where only specific binary/runtime subtrees may be bound read-only.
HOME_SCOPED_ALLOW: dict[str, tuple[str, ...]] = {
    ".pi": (".pi/bin", ".pi/agent/bin"),
    ".gemini": (".gemini/bin", ".gemini/antigravity/bin"),
    ".hermes": (".hermes/tools", ".hermes/venvs"),
}
#: Known interpreter/toolchain prefixes under $HOME allowed when resolving a
#: read-only baseline venv's base prefix out of a workspace.
HOME_RUNTIME_PREFIXES: tuple[str, ...] = (
    ".pyenv", ".asdf", ".nvm", ".fnm", ".volta", ".bun", ".rye", ".uv",
    ".poetry", ".virtualenvs", ".venvs", ".conda", "miniconda3", "miniforge3",
    "mambaforge", ".rustup", ".cargo/bin", ".hermes/tools", ".hermes/venvs",
    ".local/bin", ".local/lib", ".local/lib64", ".local/pipx",
    ".local/share/uv", ".local/share/mise", ".local/share/fnm",
    ".local/share/pyenv", ".local/share/virtualenvs", ".local/share/pipx",
)


def _in_workspace(path: Path, workspace: str | Path | None) -> bool:
    """Does ``path`` pass through ``workspace`` before following leaf symlinks?"""
    if workspace is None:
        return False
    try:
        ws_real = Path(workspace).expanduser().resolve()
        p_abs = Path(os.path.abspath(os.path.expanduser(str(path))))
    except OSError:
        return False
    for candidate in (p_abs, *p_abs.parents):
        try:
            if candidate.resolve() == ws_real:
                return True
        except OSError:
            continue
    return False


def _is_allowed_workspace_target(path: Path, home: Path) -> bool:
    """May a symlink or pyvenv.cfg inside a read-only workspace bind ``path``?"""
    if exposes_home(path, home=home):
        return False
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    if resolved == Path("/run") or resolved.is_relative_to(Path("/run")):
        return False
    try:
        rel = resolved.relative_to(home).as_posix()
    except ValueError:
        return True
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in HOME_RUNTIME_PREFIXES)


def _is_home_secret(path: Path, home: Path) -> bool:
    """Is this a credential, state, or personal path under $HOME?"""
    try:
        relative = path.resolve().relative_to(home)
    except (OSError, ValueError):
        return False
    if not relative.parts:
        return False
    name = relative.name
    if name in HOME_SECRET_FILES or name.startswith(".env."):
        return True
    top = relative.parts[0]
    text = relative.as_posix()
    if top in HOME_SCOPED_ALLOW:
        allowed = HOME_SCOPED_ALLOW[top]
        return not any(text == entry or text.startswith(entry + "/") for entry in allowed)
    if top in HOME_SECRET_DIRS:
        return True
    return any(text == entry or text.startswith(entry + "/") for entry in HOME_SECRET_RELATIVE)


def _bind_candidates(
    path: Path,
    *,
    home: Path | None = None,
    workspace: str | Path | None = None,
    trust_workspace: bool = False,
) -> list[Path]:
    """A path plus what it really points at.

    A venv's ``bin/python`` is usually a symlink into the base interpreter, which
    may live under the home directory we just emptied — binding only the symlink
    leaves a dangling target and every command dies with
    ``execvp …: No such file or directory``. Bind the target (and its prefix) too,
    unless ``path`` originates inside an untrusted trial workspace.
    """
    home_path = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    from_workspace = _in_workspace(path, workspace)
    if from_workspace and not trust_workspace:
        return []
    out: list[Path] = []

    if not from_workspace:
        for candidate in (path,):
            if candidate.exists() and not exposes_home(candidate, home=home_path):
                out.append(candidate)
    try:
        real = path.resolve()
    except OSError:
        real = None
    if real is not None and real != path:
        if real.exists() and not exposes_home(real, home=home_path):
            if not from_workspace or _is_allowed_workspace_target(real, home_path):
                out.append(real)
        prefix = real.parent.parent  # <prefix>/bin/python → <prefix>
        if prefix.exists() and not exposes_home(prefix, home=home_path):
            # Never bind a top-level directory of $HOME (~/.local, ~/.hermes) just
            # because a symlink resolved inside it: that exposes the state store and
            # anything else kept there. Bind the immediate parent instead.
            target = real.parent if prefix.parent == home_path else prefix
            if not exposes_home(target, home=home_path):
                if not from_workspace or _is_allowed_workspace_target(target, home_path):
                    out.append(target)
    return list(dict.fromkeys(out))


def describe(policy: IsolationPolicy) -> str:
    """One line for `dacode layers` and run summaries."""
    if not policy.enabled:
        return "off (trial code has host access)"
    bits = [f"bwrap {bwrap_version() or '?'}", "net:on" if policy.network else "net:off"]
    if policy.read_only_paths:
        bits.append("ro:" + ",".join(p.name for p in policy.read_only_paths))
    return " · ".join(bits)


def interpreter_binds(
    command: Iterable[str],
    *,
    workspace: str | Path | None = None,
    home: str | Path | None = None,
    trust_workspace: bool = False,
) -> tuple[Path, ...]:
    """Everything the sandbox needs to start the test interpreter.

    A venv under the home directory disappears with the home tmpfs, and its
    ``bin/python`` is a symlink into a base install that may also live under home.
    Bind, in order: the interpreter itself, its venv root (detected by
    ``pyvenv.cfg``), the base prefix named in that file, and the resolved target.
    Paths inside an untrusted trial workspace never add host mounts.
    """
    python = _python_token(command)
    if python is None or not python.is_absolute():
        return ()
    home_path = Path(home).expanduser().resolve() if home is not None else Path.home().resolve()
    from_workspace = _in_workspace(python, workspace)
    if from_workspace and not trust_workspace:
        return ()
    candidates: list[Path] = [] if from_workspace else [python, python.parent]
    venv_root = python.parent.parent
    cfg = venv_root / "pyvenv.cfg"
    if cfg.is_file() and not cfg.is_symlink():
        if not from_workspace:
            candidates.append(venv_root)
        try:
            for line in cfg.read_text(errors="ignore").splitlines():
                key, sep, value = line.partition("=")
                if sep and key.strip().lower() == "home":
                    base_bin = Path(value.strip())
                    if not base_bin.is_absolute():
                        continue
                    candidates.append(base_bin)
                    base_prefix = base_bin.parent
                    if base_prefix != home_path and base_prefix.parent != home_path:
                        candidates.append(base_prefix)
                    elif base_prefix == home_path / ".local":
                        candidates.extend((home_path / ".local" / "lib", home_path / ".local" / "lib64"))
        except OSError:
            pass
    out: list[Path] = []
    for p in candidates:
        if not p.exists() or exposes_home(p, home=home_path):
            continue
        if from_workspace and not _is_allowed_workspace_target(p, home_path):
            continue
        if p not in out:
            out.append(p)
    return tuple(out)


def _iter_command_tokens(command: Iterable[str]) -> list[str]:
    items = [str(t) for t in command]
    if (
        len(items) >= 3
        and Path(items[0]).name.lower() in {"bash", "bash.exe", "sh"}
        and items[1] in {"-c", "-lc"}
    ):
        try:
            return shlex.split(items[2])
        except ValueError:
            return items[2].split()
    return items


def _python_token(command: Iterable[str]) -> Path | None:
    for text in _iter_command_tokens(command):
        if text.endswith("python") or text.endswith("python3") or "/python" in text:
            return Path(text)
    return None


def interpreter_root(command: Iterable[str]) -> Path | None:
    """The directory holding the interpreter in a test command, if it is an absolute path."""
    for token in _iter_command_tokens(command):
        if token.endswith("python") or "/python" in token or token.endswith("python3"):
            path = Path(token)
            if path.is_absolute():
                return path.parent
    return None
