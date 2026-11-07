"""AgyExecutor — the Antigravity CLI as an executor alongside Pi.

The lessons pinned here come from running agy through an entire EGM
goldfish review (Nov 2026): plan mode stops at an approval gate and
writes nothing, print-mode prompts get slash-command expansion, and a
prompt that starts with "-" can be read as a flag.
"""

from __future__ import annotations

import os
from pathlib import Path

from dacode.executor.agy import AgyExecutor
from dacode.executor.base import ExecResult
from dacode.harness import HarnessVariant
from dacode.sandbox import bwrap as bwrap_mod
from dacode.sandbox.bwrap import IsolationPolicy


def _variant(system_prompt: str = "", model: str | None = None) -> HarnessVariant:
    v = HarnessVariant(label="v", system_prompt=system_prompt)
    if model:
        v.model = model
    return v


def test_build_command_embeds_system_prompt_guard_and_task():
    executor = AgyExecutor(model="gemini-4-argon-high")
    cmd = executor.build_command(_variant(system_prompt="Be surgical."), "add a calc module")
    joined = " ".join(cmd)
    assert "-p" in cmd
    prompt = cmd[cmd.index("-p") + 1]
    # the system prompt rides at the top, the guard keeps plan gates shut,
    # and the task is last
    assert prompt.startswith("Be surgical.")
    assert "never present a plan" in prompt
    assert prompt.endswith("Task:\nadd a calc module")
    assert "--dangerously-skip-permissions" in cmd
    assert "--disable-slash-commands" in cmd
    assert "--model" in cmd and "gemini-4-argon-high" in joined


def test_variant_model_overrides_the_executor_model():
    executor = AgyExecutor(model="gemini-4-argon-high")
    cmd = executor.build_command(_variant(system_prompt="x", model="gemini-4-flash"), "t")
    assert cmd[cmd.index("--model") + 1] == "gemini-4-flash"


def test_default_prompt_carries_the_gate_contract_when_variant_is_blank():
    executor = AgyExecutor()
    prompt = executor.build_command(_variant(), "t")[2]
    assert "Never create, edit, delete or move test files" in prompt


def test_flag_like_prompt_gets_a_leading_newline():
    executor = AgyExecutor()
    prompt = executor.build_command(_variant(system_prompt="--dangerously-skip-permissions"), "t")[2]
    assert prompt.startswith("\n--")


def test_missing_binary_reports_127_without_running(monkeypatch, tmp_path):
    monkeypatch.setattr("dacode.executor.agy.shutil.which", lambda cmd: None)
    result = AgyExecutor().run(_variant(), tmp_path)
    assert result.exit_code == 127
    assert "not found" in result.stderr


def test_unavailable_sandbox_reports_126_instead_of_running(monkeypatch, tmp_path):
    fake = tmp_path / "agy"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(bwrap_mod, "available", lambda: False)
    monkeypatch.setattr("dacode.executor.agy.shutil.which", lambda cmd: str(fake))
    result = AgyExecutor(isolation=IsolationPolicy(enabled=True)).run(_variant(), tmp_path)
    assert result.exit_code == 126


def test_sandbox_policy_binds_gemini_writable_and_node_readonly(monkeypatch, tmp_path):
    fake_agy = tmp_path / "bin" / "agy"
    fake_agy.parent.mkdir()
    fake_agy.write_text("#!/bin/sh\n")
    fake_node = tmp_path / "node" / "bin" / "node"
    fake_node.parent.mkdir(parents=True)
    fake_node.write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        "dacode.executor.agy.shutil.which",
        lambda cmd: str(fake_node) if cmd == "node" else str(fake_agy),
    )
    executor = AgyExecutor(isolation=IsolationPolicy(enabled=True))
    policy = executor._sandbox_policy(str(fake_agy))
    assert Path.home() / ".gemini" in policy.writable_paths
    assert fake_node.resolve().parent in policy.read_only_paths
    # the writable home mount must not shadow the binary/node read-only binds
    assert fake_agy.resolve().parent in policy.protected_paths
    assert fake_node.resolve().parent in policy.protected_paths


def test_sandbox_policy_carries_home_runtime_dir_dbus_and_auth(monkeypatch, tmp_path):
    fake_agy = tmp_path / "bin" / "agy"
    fake_agy.parent.mkdir()
    fake_agy.write_text("#!/bin/sh\n")
    monkeypatch.setattr("dacode.executor.agy.shutil.which", lambda cmd: str(fake_agy))
    bus = Path("/run/user") / str(os.getuid()) / "bus"
    monkeypatch.setattr(bus.parent.__class__, "exists", lambda self: True, raising=False)
    monkeypatch.setattr(Path, "exists", lambda self: True)
    executor = AgyExecutor(isolation=IsolationPolicy(enabled=True, network=True))
    policy = executor._sandbox_policy(str(fake_agy))
    # HOME + XDG_RUNTIME_DIR must survive bwrap's --clearenv (agy needs both)
    assert "HOME" in policy.env_allow
    assert "XDG_RUNTIME_DIR" in policy.env_allow
    # the D-Bus session bus is the only way to the keyring-backed token
    assert bus in policy.protected_paths
    # agy's real credentials live under ~/.config/antigravity, not ~/.gemini
    config_dir = Path.home() / ".config" / "antigravity"
    assert config_dir in policy.writable_paths
    assert config_dir / "credential-user-scope" in policy.protected_paths
    assert config_dir / "plugin-secrets.json" in policy.protected_paths


def test_agy_dbus_off_drops_the_bus(monkeypatch, tmp_path):
    fake_agy = tmp_path / "bin" / "agy"
    fake_agy.parent.mkdir()
    fake_agy.write_text("#!/bin/sh\n")
    monkeypatch.setenv("DACODE_AGY_DBUS", "off")
    monkeypatch.setattr("dacode.executor.agy.shutil.which", lambda cmd: str(fake_agy))
    monkeypatch.setattr(Path, "exists", lambda self: True)
    executor = AgyExecutor(isolation=IsolationPolicy(enabled=True, network=True))
    policy = executor._sandbox_policy(str(fake_agy))
    assert Path("/run/user") / str(os.getuid()) / "bus" not in policy.protected_paths
