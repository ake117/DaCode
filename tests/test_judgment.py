"""Tests for the Jev (System One) judgment layer and its compose() wiring.

The judge only ever makes *bounded picks* among already-probed variants.
Pass/fail verdicts stay with the critic gate — these tests lock that
boundary in: a judge failure or low-confidence answer must fall through
to the deterministic path, never change it.
"""

from __future__ import annotations

import pytest

from dacode.harness.models import HarnessVariant, ProbeResult
from dacode.harness.optimizer import HarnessOptimizer
from dacode.judgment import JevJudge, SystemOneError, build_judge

CRITERIA = {"v2": "score=1.0", "v3": "score=0.9"}


# --- JevJudge unit tests (fake transport, no network) -----------------------


def _transport_returning(choice="v3", confidence=0.9):
    captured = {}

    def transport(payload):
        captured.update(payload)
        return {
            "model": "jev-test",
            "answers": {
                "pick": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": confidence,
                    "probabilities": {},
                }
            },
            "usage": {"input_tokens": 10, "output_tokens": 2},
        }

    transport.captured = captured
    return transport


def test_choice_returns_option_and_confidence():
    transport = _transport_returning(choice="v3", confidence=0.9)
    judge = JevJudge(transport=transport)
    assert judge.choice(state="s", instructions="i", criteria=CRITERIA) == ("v3", 0.9)
    # the request pins the versioned model and carries the choice question
    assert transport.captured["model"] == "jev-1.13.0"
    question = transport.captured["questions"]["pick"]
    assert question["type"] == "choice"
    assert question["criteria"] == CRITERIA


def test_choice_below_min_confidence_returns_none():
    judge = JevJudge(transport=_transport_returning(choice="v3", confidence=0.2))
    assert judge.choice(state="s", instructions="i", criteria=CRITERIA) == (None, 0.2)


def test_choice_unknown_option_raises():
    judge = JevJudge(transport=_transport_returning(choice="v9", confidence=0.9))
    with pytest.raises(SystemOneError):
        judge.choice(state="s", instructions="i", criteria=CRITERIA)


def test_choice_transport_failure_raises():
    def boom(payload):
        raise OSError("network down")

    judge = JevJudge(transport=boom)
    with pytest.raises(SystemOneError):
        judge.choice(state="s", instructions="i", criteria=CRITERIA)


def test_choice_without_key_raises(monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    judge = JevJudge()
    with pytest.raises(SystemOneError):
        judge.choice(state="s", instructions="i", criteria=CRITERIA)


def test_build_judge_off_by_default():
    assert build_judge(None) is None
    assert build_judge("off") is None


def test_build_judge_jev():
    assert isinstance(build_judge("jev"), JevJudge)


# --- compose() wiring: the judge picks among probed variants only -----------


class _StubJudge:
    def __init__(self, pick=None, confidence=0.9, error=None):
        self._pick = pick
        self._confidence = confidence
        self._error = error
        self.calls = []

    def choice(self, *, state, instructions, criteria, min_confidence=0.5):
        self.calls.append({"state": state, "criteria": criteria})
        if self._error is not None:
            raise self._error
        if self._pick is None:
            return None, self._confidence
        return self._pick, self._confidence


class _GhostLLM:
    """An LLM whose answer never parses — compose must fall back."""

    name = "ghost"

    def complete(self, system, user):
        return "not-json"


def _probed(label, score, passed=True):
    variant = HarnessVariant(label=label)
    variant.score = score
    variant.probe = ProbeResult(
        variant_id=variant.id,
        workspace=f"/tmp/{label}",
        exit_code=0,
        tests_total=10,
        tests_passed=10 if passed else 5,
        critique_passed=passed,
        critique_score=1.0 if passed else 0.0,
    )
    return variant


def _optimizer(judge):
    return HarnessOptimizer(
        llm=_GhostLLM(),
        sandbox=None,
        executor=None,
        critic=None,
        judge=judge,
    )


def test_compose_prefers_a_confident_judge_pick_over_ranking():
    winner = _probed("strong", 1.0)
    other = _probed("weak", 0.5, passed=False)
    judge = _StubJudge(pick=other.id, confidence=0.9)
    result = _optimizer(judge).compose("add a docstring", [winner, other])
    assert result is other  # the judge's pick beats the measured ranking
    assert judge.calls[0]["criteria"].keys() == {winner.id, other.id}
    assert "add a docstring" in judge.calls[0]["state"]
    assert "critique_passed=True" in judge.calls[0]["criteria"][winner.id]


def test_compose_falls_back_to_ranking_on_low_confidence():
    winner = _probed("strong", 1.0)
    other = _probed("weak", 0.5, passed=False)
    judge = _StubJudge(pick=None, confidence=0.2)
    result = _optimizer(judge).compose("task", [winner, other])
    assert result is winner  # measured ranking decides


def test_compose_falls_back_when_the_judge_fails():
    winner = _probed("strong", 1.0)
    other = _probed("weak", 0.5, passed=False)
    judge = _StubJudge(error=SystemOneError("HTTP 503"))
    result = _optimizer(judge).compose("task", [winner, other])
    assert result is winner  # a judge failure must not kill the run


def test_compose_skips_the_judge_for_a_single_variant():
    only = _probed("only", 1.0)
    judge = _StubJudge(pick=only.id)
    result = _optimizer(judge).compose("task", [only])
    assert result is only
    assert judge.calls == []  # nothing to decide — the judge is never asked
