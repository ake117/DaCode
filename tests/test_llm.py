"""Tests for the LLM layer."""

from __future__ import annotations

import pytest

from dacode.llm import PROVIDERS, StubLLM, build_llm, provider_names
from dacode.llm.base import LLMError


def test_stub_returns_marker_matched_reply():
    llm = StubLLM(responses={"alpha": "A-reply"}, default="fallback")
    assert llm.complete("sys", "please handle alpha now") == "A-reply"


def test_stub_falls_back_when_no_marker_matches():
    llm = StubLLM(responses={"alpha": "A-reply"}, default="fallback")
    assert llm.complete("sys", "unrelated request") == "fallback"


def test_stub_records_calls():
    llm = StubLLM(default="x")
    llm.complete("S1", "U1")
    llm.complete("S2", "U2")
    assert llm.calls == [("S1", "U1"), ("S2", "U2")]


def test_stub_can_be_told_to_fail():
    llm = StubLLM(fail_on="boom")
    with pytest.raises(LLMError):
        llm.complete("s", "please boom")


def test_build_llm_unknown_kind_raises():
    with pytest.raises(ValueError):
        build_llm("does-not-exist")


def test_build_llm_stub_returns_stub():
    assert build_llm("stub").name == "stub"


# --- provider presets (popular AI providers) --------------------------------


def test_build_llm_every_provider_preset_builds():
    for kind, preset in PROVIDERS.items():
        client = build_llm(kind)
        assert client.base_url == preset["base_url"]
        assert client.model == preset["default_model"]


def test_build_llm_provider_model_override():
    client = build_llm("groq", model="llama-3.1-8b-instant")
    assert client.model == "llama-3.1-8b-instant"
    assert client.base_url == "https://api.groq.com/openai/v1"


def test_build_llm_provider_resolves_env_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    assert build_llm("groq").api_key == "gsk-test"


def test_build_llm_provider_missing_key_is_none(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    assert build_llm("mistral").api_key is None


def test_anthropic_preset_carries_version_header():
    client = build_llm("anthropic")
    assert client.extra_headers.get("anthropic-version") == "2023-06-01"


def test_provider_names_cover_the_popular_set():
    names = provider_names()
    for expected in (
        "anthropic",
        "deepseek",
        "gemini",
        "groq",
        "mistral",
        "openai",
        "openrouter",
        "xai",
    ):
        assert expected in names


def test_cli_llm_help_stays_in_sync_with_the_registry():
    import argparse

    from dacode.cli import build_parser

    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    run_help = sub.choices["run"].format_help()
    for name in provider_names():
        assert name in run_help, f"--llm help is missing provider {name!r}"
