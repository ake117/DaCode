"""Tests for the run log recorder and judge evaluation."""

from __future__ import annotations

import pytest

from dacode.harness.models import HarnessVariant
from dacode.harness.optimizer import HarnessOptimizer
from dacode.jeval import collect_cases, evaluate, summarize
from dacode.llm import StubLLM
from dacode.runlog import load_events, record
from dacode.sandbox import GitSandbox


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "runlog.jsonl"
    monkeypatch.setenv("DACODE_RUNLOG", str(path))
    return path


def test_record_and_load_round_trip(log_path):
    record({"type": "compose", "task": "t", "chosen_id": "v2"})
    record({"type": "run", "task": "t", "passed": True})
    events = load_events(str(log_path))
    assert [e["type"] for e in events] == ["compose", "run"]
    assert events[0]["chosen_id"] == "v2"
    assert "ts" in events[0]


def test_record_off_writes_nothing(log_path, monkeypatch):
    monkeypatch.setenv("DACODE_RUNLOG", "off")
    record({"type": "probe"})
    assert not log_path.exists()


def test_load_events_skips_malformed_lines(log_path):
    log_path.write_text('{"type": "run"}\nnot json\n\n{"type": "probe"}\n', encoding="utf-8")
    events = load_events(str(log_path))
    assert [e["type"] for e in events] == ["run", "probe"]


class _RecordingJudge:
    def __init__(self, choice, confidence=0.9):
        self.choice_value = choice
        self.confidence = confidence
        self.seen_states = []

    def choice(self, *, state, instructions, criteria, min_confidence=0.5):
        self.seen_states.append(state)
        return self.choice_value, self.confidence


def _case(task="t", winner="v2"):
    return {
        "task": task,
        "table": [
            {"id": "v2", "label": "good", "score": 1.0, "tests_passed": 10, "tests_total": 10, "passed": True},
            {"id": "v3", "label": "bad", "score": 0.5, "tests_passed": 5, "tests_total": 10, "passed": False},
        ],
        "winner_id": winner,
    }


def test_collect_cases_keeps_only_gate_verified_multi_option_events():
    events = [
        {"type": "compose", "task": "t", "chosen_id": "v2", "table": _case()["table"]},
        {"type": "compose", "task": "u", "chosen_id": "v3", "table": _case()["table"]},
        {"type": "compose", "task": "s", "chosen_id": "v2", "table": _case()["table"][:1]},
        {"type": "probe", "task": "t"},
    ]
    cases = collect_cases(events)
    assert len(cases) == 1
    assert cases[0]["winner_id"] == "v2"


def test_evaluate_counts_agree_and_disagree():
    cases = [_case(task="a", winner="v2"), _case(task="b", winner="v3")]
    report = evaluate(cases, _RecordingJudge("v2"))
    assert report["agree"] == 1
    assert report["disagree"] == 1
    assert report["agreement_rate"] == 0.5


def test_evaluate_counts_no_confidence_separately():
    report = evaluate([_case(task="a")], _RecordingJudge(None, 0.1))
    assert report["no_confidence"] == 1
    assert report["agreement_rate"] is None


def test_evaluate_limit_caps_cases():
    cases = [_case(task=str(i)) for i in range(5)]
    assert evaluate(cases, _RecordingJudge("v2"), limit=2)["total"] == 2


def test_summarize_lists_disagreements():
    text = summarize(evaluate([_case(task="a", winner="v3")], _RecordingJudge("v2")))
    assert "disagree" in text


def test_compose_records_the_pick(log_path, rig_repo):
    a = HarnessVariant(label="a")
    a.score = 0.2
    b = HarnessVariant(label="b")
    b.score = 0.9
    llm = StubLLM(default="")  # empty compose reply → deterministic ranking
    opt = HarnessOptimizer(llm=llm, sandbox=GitSandbox(rig_repo), executor=None, critic=None)
    assert opt.compose("t", [a, b]) is b
    events = load_events(str(log_path))
    assert len(events) == 1
    assert events[0]["type"] == "compose"
    assert events[0]["chooser"] == "ranking"
    assert events[0]["chosen_id"] == b.id
    assert [row["id"] for row in events[0]["table"]] == [b.id, a.id]  # score order, best first


def test_cli_judge_eval_reports_no_data(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DACODE_RUNLOG", str(tmp_path / "empty.jsonl"))
    from dacode.cli import main

    assert main(["judge-eval"]) == 1
    assert "no gate-verified" in capsys.readouterr().out
