"""Tests for the LLM layer."""

from __future__ import annotations

import pytest

from dacode.llm import StubLLM, build_llm
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
