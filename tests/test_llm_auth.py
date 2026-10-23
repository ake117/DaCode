"""Policy tests: where DaCode does and does not look for keys.

Standing instruction (2026-10-20): secrets come from the real environment and
the target repo's ``.env`` only. Pi's auth store (``~/.pi/agent/auth.json``)
and the Hermes dotenv (``~/.hermes/.env``) are never read.
"""

from __future__ import annotations

import json
from pathlib import Path

from dacode.env import DEFAULT_ENV_PATHS, load_env
from dacode.llm import build_llm


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_llm_ignores_the_pi_auth_store(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _write(tmp_path / ".pi" / "agent" / "auth.json", {"openrouter": {"key": "sk-from-pi"}})
    client = build_llm("openrouter")
    assert client.api_key is None  # the store is not consulted


def test_build_llm_uses_the_provider_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    client = build_llm("openrouter", model="deepseek/deepseek-v4.1-flash")
    assert client.api_key == "sk-from-env"
    assert client.model == "deepseek/deepseek-v4.1-flash"
    assert client.base_url == "https://openrouter.ai/api/v1"


def test_build_llm_prefers_an_explicit_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    assert build_llm("openrouter", api_key="sk-explicit").api_key == "sk-explicit"


def test_default_env_paths_exclude_the_hermes_dotenv():
    assert DEFAULT_ENV_PATHS == ("{repo}/.env",)


def test_load_env_ignores_the_hermes_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / ".env").write_text("JEV_API_KEY=from-hermes\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("OPENROUTER_API_KEY=from-repo\n", encoding="utf-8")

    loaded = load_env(*[p.replace("{repo}", str(repo)) for p in DEFAULT_ENV_PATHS])

    assert loaded == {"OPENROUTER_API_KEY": "from-repo"}
    assert "JEV_API_KEY" not in loaded


def test_load_env_never_clobbers_the_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-real-env")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("OPENROUTER_API_KEY=sk-from-file\n", encoding="utf-8")
    load_env(*[p.replace("{repo}", str(repo)) for p in DEFAULT_ENV_PATHS])
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-real-env"
