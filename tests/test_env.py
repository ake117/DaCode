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
    load_env(env)
    assert os.environ["ALREADY_SET"] == "original"
    assert os.environ["NEW_KEY"] == "fromfile"


def test_load_env_first_path_wins(tmp_path, monkeypatch):
    monkeypatch.delenv("WHO_WINS", raising=False)
    first = tmp_path / "a.env"
    second = tmp_path / "b.env"
    first.write_text("WHO_WINS=first\n", encoding="utf-8")
    second.write_text("WHO_WINS=second\n", encoding="utf-8")
    load_env(first, second)
    assert os.environ["WHO_WINS"] == "first"


def test_load_env_skips_empty_values(tmp_path, monkeypatch):
    monkeypatch.delenv("EMPTY_ONE", raising=False)
    env = tmp_path / ".env"
    env.write_text("EMPTY_ONE=\n", encoding="utf-8")
    load_env(env)
    assert "EMPTY_ONE" not in os.environ
