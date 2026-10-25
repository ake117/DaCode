"""Tests for the Jev (System One) judgment layer and its compose() wiring.

The judge only ever makes *bounded picks* among already-probed variants.
Pass/fail verdicts stay with the critic gate — these tests lock that
boundary in: a judge failure or low-confidence answer must fall through
to the deterministic path, never change it.
"""

from __future__ import annotations

import pytest

from dacode.executor.base import ExecResult
from dacode.harness.models import HarnessVariant, ProbeResult
from dacode.discipline import PstackCritic
from dacode.harness.optimizer import HarnessOptimizer
from dacode.llm import StubLLM
from dacode.sandbox import GitSandbox
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


def test_the_judge_may_pick_among_passing_variants():
    strong = _probed("strong", 1.0)
    other = _probed("also-passing", 0.5)
    judge = _StubJudge(pick=other.id, confidence=0.9)
    result = _optimizer(judge).compose("add a docstring", [strong, other])
    assert result is other  # among gate passes, judgment decides
    assert "add a docstring" in judge.calls[0]["state"]


def test_the_judge_cannot_pick_a_variant_that_failed_the_gate():
    """Audit C5: a failing variant used to be offered, and could win."""
    winner = _probed("strong", 1.0)
    failing = _probed("tampered", 1.0, passed=False)
    judge = _StubJudge(pick=failing.id, confidence=0.99)
    result = _optimizer(judge).compose("add a docstring", [failing, winner])
    assert result is winner
    # one candidate left, so the judge is not consulted at all — and the failing
    # variant is never offered as an option
    assert not judge.calls


def test_when_nothing_passes_the_judge_still_gets_a_choice():
    first = _probed("a", 0.5, passed=False)
    second = _probed("b", 0.4, passed=False)
    judge = _StubJudge(pick=second.id, confidence=0.9)
    result = _optimizer(judge).compose("task", [first, second])
    assert result is second


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


# --- run() triage: the judge steers the loop after a failed round -----------

import json as _json
from pathlib import Path as _Path

PROPOSE_JSON = _json.dumps(
    [
        {"label": "good", "system_prompt": "implement carefully", "tools": []},
        {"label": "bad", "system_prompt": "do nothing", "tools": []},
    ]
)


class _CalcExecutor:
    """Writes calc.py only for `good_label`; records runs; model is switchable."""

    model = "weak-start"

    def __init__(self, good_label: str = "never") -> None:
        self.good_label = good_label
        self.seen: list[str] = []

    def run(self, variant: HarnessVariant, workspace: str) -> ExecResult:
        self.seen.append(variant.label)
        if variant.label == self.good_label:
            (_Path(workspace) / "calc.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
            return ExecResult(exit_code=0, stdout="wrote calc.py")
        return ExecResult(exit_code=0, stdout="no-op")


class _TriageJudge:
    """compose questions → (None, 0.0); triage questions → the scripted action."""

    def __init__(self, action=None, confidence=0.9, error=None):
        self.action = action
        self.confidence = confidence
        self.error = error
        self.triage_calls = []

    def choice(self, *, state, instructions, criteria, min_confidence=0.5):
        if "new_proposal" in criteria:  # the triage question
            self.triage_calls.append({"state": state, "criteria": dict(criteria)})
            if self.error is not None:
                raise self.error
            if self.action is None:
                return None, self.confidence
            return self.action, self.confidence
        return None, 0.0  # the compose question → deterministic ranking


def _run_optimizer(rig_repo, executor, judge, budget=2, escalate=None):
    llm = StubLLM(responses={"Propose 2 variants": PROPOSE_JSON}, default="")
    return HarnessOptimizer(
        llm=llm,
        sandbox=GitSandbox(rig_repo),
        executor=executor,
        critic=PstackCritic(),
        judge=judge,
        budget=budget,
        variants_per_round=2,
        escalation_models=[escalate] if escalate else None,
    )


def test_run_human_review_stops_before_budget(rig_repo):
    judge = _TriageJudge(action="human_review")
    executor = _CalcExecutor()
    opt = _run_optimizer(rig_repo, executor, judge, budget=3, escalate="m1")
    result = opt.run("implement calc.add")
    assert result.rounds == 1  # stopped with budget to spare
    assert result.needs_human_review is True
    assert result.passed is False
    assert result.lesson_path is None
    assert len(executor.seen) == 2  # only round 1's two probes
    assert set(judge.triage_calls[0]["criteria"]) == {
        "new_proposal",
        "retry_same",
        "escalate_model",
        "human_review",
    }
    assert "Round 1 of 3" in judge.triage_calls[0]["state"]
    assert "implement calc.add" in judge.triage_calls[0]["state"]


def test_run_retry_same_reprobes_the_same_variants(rig_repo):
    judge = _TriageJudge(action="retry_same")
    executor = _CalcExecutor()
    opt = _run_optimizer(rig_repo, executor, judge, budget=2)
    result = opt.run("implement calc.add")
    assert result.rounds == 2
    assert result.passed is False
    assert executor.seen == ["good", "bad", "good", "bad"]  # same variants twice
    assert len(result.variants) == 2  # retries are not double-counted


def test_run_escalate_model_switches_the_executor(rig_repo):
    judge = _TriageJudge(action="escalate_model")
    executor = _CalcExecutor()
    opt = _run_optimizer(rig_repo, executor, judge, budget=2, escalate="claude-sonnet-4-5")
    result = opt.run("implement calc.add")
    assert result.rounds == 2
    assert executor.model == "claude-sonnet-4-5"
    assert "escalate_model" in judge.triage_calls[0]["criteria"]


def test_run_triage_failure_defaults_to_new_proposal(rig_repo):
    judge = _TriageJudge(error=SystemOneError("HTTP 503"))
    executor = _CalcExecutor()
    opt = _run_optimizer(rig_repo, executor, judge, budget=2)
    result = opt.run("implement calc.add")
    assert result.rounds == 2
    assert result.needs_human_review is False
    assert len(executor.seen) == 4  # round 2 proposed fresh variants (2 + 2)
    assert len(result.variants) == 4


def test_run_without_judge_never_flags_human_review(rig_repo):
    executor = _CalcExecutor()
    opt = _run_optimizer(rig_repo, executor, judge=None, budget=2)
    result = opt.run("implement calc.add")
    assert result.rounds == 2
    assert result.needs_human_review is False
