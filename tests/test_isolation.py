"""Isolation (#8): a trial gets a worktree, not the machine.

The unit tests pin the argv contract (what is bound, what is hidden, which env
vars pass, whether sockets are allowed) without needing namespaces. The
integration tests run real bwrap when it is installed and skip otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from dacode.discipline.critic import PstackCritic
from dacode.executor.pi import PiExecutor
from dacode.sandbox import bwrap as bwrap_mod
from dacode.sandbox.bwrap import (
    IsolationPolicy,
    IsolationUnavailable,
    allowed_env,
    interpreter_root,
    wrap_command,
)

HAS_BWRAP = shutil.which("bwrap") is not None
needs_bwrap = pytest.mark.skipif(not HAS_BWRAP, reason="bubblewrap not installed")


def _argv(**kwargs) -> list[str]:
    policy = kwargs.pop("policy", IsolationPolicy(enabled=True))
    return wrap_command(kwargs.pop("command", ["bash", "-lc", "true"]),
                        workspace=kwargs.pop("workspace", Path.cwd()), policy=policy, **kwargs)


# --- argv contract ---------------------------------------------------------

def test_disabled_policy_returns_the_command_unchanged():
    cmd = ["python", "-m", "pytest"]
    assert wrap_command(cmd, workspace=Path.cwd(), policy=IsolationPolicy(enabled=False)) == cmd


def test_missing_bwrap_raises_instead_of_running_unsandboxed(monkeypatch):
    monkeypatch.setattr(bwrap_mod, "available", lambda: False)
    with pytest.raises(IsolationUnavailable):
        wrap_command(["true"], workspace=Path.cwd(), policy=IsolationPolicy(enabled=True))


def test_network_is_unshared_by_default():
    assert "--unshare-net" in _argv()


def test_network_can_be_allowed():
    assert "--unshare-net" not in _argv(policy=IsolationPolicy(enabled=True, network=True))


def test_the_workspace_is_the_only_writable_place():
    argv = _argv(workspace=Path.cwd())
    index = argv.index("--bind")
    assert argv[index + 1] == argv[index + 2] == str(Path.cwd().resolve())


def test_home_is_replaced_by_an_empty_tmpfs():
    argv = _argv(home=Path.home())
    index = argv.index("--tmpfs")
    assert argv[index + 1] == str(Path.home().resolve())


def test_read_only_paths_are_bound_when_they_exist(tmp_path):
    real = tmp_path / "venv"
    real.mkdir()
    missing = tmp_path / "absent"
    argv = _argv(policy=IsolationPolicy(enabled=True, read_only_paths=(real, missing)))
    assert str(real) in argv
    assert str(missing) not in argv


def test_environment_is_cleared_and_allow_listed(monkeypatch):
    argv = _argv()
    assert "--clearenv" in argv
    env = {"PATH": "/usr/bin", "OPENROUTER_API_KEY": "secret", "AWS_SECRET_ACCESS_KEY": "nope"}
    names = [argv[i + 1] for i, token in enumerate(argv) if token == "--setenv"]
    assert "PATH" in names
    assert "OPENROUTER_API_KEY" not in names       # network is off
    assert "AWS_SECRET_ACCESS_KEY" not in names    # never allow-listed


def test_provider_keys_pass_only_with_network():
    env = {"OPENROUTER_API_KEY": "secret"}
    offline = allowed_env(IsolationPolicy(enabled=True, network=False), env)
    online = allowed_env(IsolationPolicy(enabled=True, network=True), env)
    assert "OPENROUTER_API_KEY" not in offline
    assert online["OPENROUTER_API_KEY"] == "secret"


def test_the_working_directory_is_the_workspace():
    argv = _argv(workspace=Path.cwd())
    index = argv.index("--chdir")
    assert argv[index + 1] == str(Path.cwd().resolve())


def test_interpreter_root_finds_an_absolute_python():
    root = interpreter_root(("/opt/venv/bin/python", "-m", "pytest"))
    assert root == Path("/opt/venv/bin")
    assert interpreter_root(("python", "-m", "pytest")) is None


# --- components refuse to pretend ------------------------------------------

def test_pi_executor_reports_a_missing_sandbox_instead_of_running(monkeypatch, tmp_path):
    monkeypatch.setattr(bwrap_mod, "available", lambda: False)
    executor = PiExecutor(isolation=IsolationPolicy(enabled=True))
    result = executor.run(_variant(), tmp_path)
    assert result.exit_code == 126
    assert "isolation unavailable" in result.stderr


def test_critic_fails_the_gate_when_the_sandbox_disappears(monkeypatch, tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_a():\n    assert True\n")
    monkeypatch.setattr(bwrap_mod, "available", lambda: False)
    critic = PstackCritic(
        test_command=(sys.executable, "-m", "pytest", "-q"),
        isolation=IsolationPolicy(enabled=True),
    )
    report = critic.review_workspace(tmp_path)
    assert report.exit_code == 125
    assert report.passed is False


def _variant():
    from dacode.harness.models import HarnessVariant

    return HarnessVariant(payload={"task": "x"})


# --- real namespaces -------------------------------------------------------

@needs_bwrap
def test_a_sandboxed_command_cannot_read_the_home_directory(tmp_path):
    secret = Path.home() / ".dacode-isolation-probe"
    secret.write_text("host-only")
    try:
        argv = wrap_command(
            ["bash", "-lc", f"cat {secret}"],
            workspace=tmp_path,
            policy=IsolationPolicy(enabled=True),
        )
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        assert "host-only" not in proc.stdout
    finally:
        secret.unlink(missing_ok=True)


@needs_bwrap
def test_a_sandboxed_command_can_write_inside_the_workspace(tmp_path):
    argv = wrap_command(
        ["bash", "-lc", "echo inside > made.txt"],
        workspace=tmp_path,
        policy=IsolationPolicy(enabled=True),
    )
    subprocess.run(argv, capture_output=True, text=True, timeout=60, check=True)
    assert (tmp_path / "made.txt").read_text().strip() == "inside"


@needs_bwrap
def test_a_sandboxed_command_cannot_open_a_socket(tmp_path):
    argv = wrap_command(
        [sys.executable, "-c",
         "import socket; socket.create_connection(('1.1.1.1', 53), timeout=3); print('CONNECTED')"],
        workspace=tmp_path,
        policy=IsolationPolicy(enabled=True),
    )
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert "CONNECTED" not in proc.stdout


@needs_bwrap
def test_the_gate_can_run_a_real_suite_inside_the_sandbox(tmp_path):
    (tmp_path / "test_inner.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(
        test_command=(sys.executable, "-m", "pytest", "-q"),
        isolation=IsolationPolicy(enabled=True),
    )
    report = critic.review_workspace(tmp_path)
    assert report.exit_code == 0, report.findings
    assert (report.tests_total, report.tests_passed) == (1, 1)


def test_the_gate_never_gets_the_network_even_when_the_executor_does(rig_repo):
    """Found by an external audit: one shared policy gave the gate sockets + keys."""
    from dacode.config import DaCodeConfig
    from dacode.orchestrator import DaCodeRig

    cfg = DaCodeConfig(repo=rig_repo, isolate="bwrap", isolate_network=True)
    rig = DaCodeRig(cfg)

    assert rig.isolation is not None and rig.isolation.network is True
    assert rig.critic.isolation is not None
    assert rig.critic.isolation.network is False
    # and the environment the gate sees carries no provider keys
    from dacode.sandbox.bwrap import allowed_env

    assert "OPENROUTER_API_KEY" not in allowed_env(rig.critic.isolation, {"OPENROUTER_API_KEY": "x"})
