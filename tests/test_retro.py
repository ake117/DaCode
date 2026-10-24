"""dacode retro — turns the runlog into specific harness advice."""

from __future__ import annotations

import json
import time
from pathlib import Path

from dacode import retro


def _write_log(path: Path, events: list[dict]) -> Path:
    now = time.time()
    with path.open("w", encoding="utf-8") as handle:
        for i, event in enumerate(events):
            handle.write(json.dumps({"ts": now - i, **event}) + "\n")
    return path


def test_counts_runs_passes_and_rounds(tmp_path):
    log = _write_log(tmp_path / "runlog.jsonl", [
        {"type": "run", "task": "task A", "rounds": 1, "passed": True},
        {"type": "run", "task": "task A", "rounds": 3, "passed": False},
        {"type": "probe", "task": "task A", "elapsed_s": 12.0, "critique_passed": True},
    ])
    report = retro.build_report(since_days=7, log_path=log)

    assert report.events == 3
    task = report.tasks[0]
    assert task.task == "task A"
    assert task.runs == 2
    assert task.pass_rate == 0.5
    assert task.avg_rounds == 2.0
    assert task.avg_variant_s == 12.0


def test_low_pass_rate_suggests_a_test_first_contract(tmp_path):
    log = _write_log(tmp_path / "runlog.jsonl", [
        {"type": "run", "task": "vague prose task", "rounds": 2, "passed": False},
        {"type": "run", "task": "vague prose task", "rounds": 2, "passed": False},
        {"type": "run", "task": "vague prose task", "rounds": 2, "passed": True},
    ])
    report = retro.build_report(since_days=7, log_path=log)
    assert any("contract as tests first" in tip for tip in report.suggestions)


def test_slow_variants_suggest_timeout_and_parallel(tmp_path):
    log = _write_log(tmp_path / "runlog.jsonl", [
        {"type": "run", "task": "slow", "rounds": 1, "passed": True},
        {"type": "probe", "task": "slow", "elapsed_s": 400.0},
    ])
    report = retro.build_report(since_days=7, log_path=log)
    tips = " ".join(report.suggestions)
    assert "--variant-timeout" in tips and "--parallel" in tips


def test_test_tampering_is_called_out(tmp_path):
    log = _write_log(tmp_path / "runlog.jsonl", [
        {"type": "run", "task": "cheat", "rounds": 1, "passed": True},
        {"type": "probe", "task": "cheat", "elapsed_s": 5.0, "findings": ["tests_skipped"]},
    ])
    report = retro.build_report(since_days=7, log_path=log)
    assert any("deleted or skipped tests" in tip for tip in report.suggestions)


def test_ignores_events_outside_the_window(tmp_path):
    old = time.time() - 40 * 86400
    path = tmp_path / "runlog.jsonl"
    path.write_text(json.dumps({"ts": old, "type": "run", "task": "ancient", "passed": False}) + "\n")
    report = retro.build_report(since_days=7, log_path=path)
    assert report.tasks == []
    assert report.events == 0


def test_missing_log_is_not_an_error(tmp_path):
    report = retro.build_report(since_days=7, log_path=tmp_path / "absent.jsonl")
    assert report.tasks == []
    assert report.suggestions


def test_task_filter_and_json_shape(tmp_path):
    log = _write_log(tmp_path / "runlog.jsonl", [
        {"type": "run", "task": "alpha work", "rounds": 1, "passed": True},
        {"type": "run", "task": "beta work", "rounds": 1, "passed": False},
    ])
    report = retro.build_report(since_days=7, log_path=log, task_filter="beta")
    assert [t.task for t in report.tasks] == ["beta work"]
    payload = report.to_dict()
    assert payload["tasks"][0]["pass_rate"] == 0.0
    assert isinstance(payload["suggestions"], list)


def test_render_text_includes_a_row_and_the_suggestions(tmp_path):
    log = _write_log(tmp_path / "runlog.jsonl", [
        {"type": "run", "task": "render me", "rounds": 1, "passed": True},
    ])
    text = retro.render_text(retro.build_report(since_days=7, log_path=log))
    assert "render me" in text
    assert "Suggestions:" in text
