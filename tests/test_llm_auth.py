"""Tests for resolving the OpenRouter key from the Pi auth store."""

from __future__ import annotations

import json
from pathlib import Path

from dacode.llm import _pi_auth_key, build_llm


def _write_auth(home: Path, payload: dict) -> None:
    agent_dir = home / ".pi" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "auth.json").write_text(json.dumps(payload), encoding="utf-8")


def test_pi_auth_key_reads_the_provider_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_auth(tmp_path, {"openrouter": {"type": "api", "key": "sk-or-test-key"}})
    assert _pi_auth_key("openrouter") == "sk-or-test-key"


def test_pi_auth_key_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert _pi_auth_key("openrouter") is None


def test_pi_auth_key_tolerates_a_bare_string_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_auth(tmp_path, {"openrouter": "sk-or-bare"})
    assert _pi_auth_key("openrouter") == "sk-or-bare"


def test_build_llm_openrouter_uses_pi_key_when_env_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _write_auth(tmp_path, {"openrouter": {"key": "sk-or-from-pi"}})
    client = build_llm("openrouter", model="deepseek/deepseek-v4.1-flash")
    assert client.api_key == "sk-or-from-pi"
    assert client.model == "deepseek/deepseek-v4.1-flash"
    assert client.base_url == "https://openrouter.ai/api/v1"


def test_build_llm_openrouter_prefers_explicit_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_auth(tmp_path, {"openrouter": {"key": "sk-or-from-pi"}})
    client = build_llm("openrouter", api_key="sk-or-explicit")
    assert client.api_key == "sk-or-explicit"
