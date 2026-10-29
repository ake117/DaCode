"""`dacode watch` — the dashboard renders what the run log actually says."""

from __future__ import annotations

import json

import pytest

from dacode.watch import render, split_runs, watch


def _events():
    return [
        {"type": "probe", "ts": 100.0, "task": "fix the slug",
         "variant_id": "v1", "label": "regex-slug", "exit_code": 1,
         "tests_passed": 0, "tests_total": 2, "elapsed_s": 8.0,
         "findings": ["tests_modified"]},
        {"type": "probe", "ts": 110.0, "task": "fix the slug",
         "variant_id": "v2", "label": "charset-map", "exit_code": 0,
         "tests_passed": 2, "tests_total": 2, "elapsed_s": 9.5,
         "findings": []},
        {"type": "compose", "ts": 120.0, "task": "fix the slug",
         "chooser": "critic", "chosen_id": "v2", "table": []},
        {"type": "run", "ts": 121.0, "task": "fix the slug", "passed": True,
         "rounds": 1, "best_id": "v2", "best_score": 1.0},
    ]


def test_the_dashboard_shows_the_pass_with_its_best_variant():
    text = render(_events(), log_name="runlog.jsonl")
    assert "✓" in text and "PASS" in text
    assert "best v2 [charset-map] (score 1)" in text
    assert "1 runs · 1 passed (100%)" in text
    assert "2 probes" in text
    assert "charset-map" in text  # the winning label surfaces in history


def test_an_in_progress_run_lists_probes_and_findings():
    events = [e for e in _events() if e["type"] != "run"]
    text = render(events, log_name="runlog.jsonl")
    assert "▶ RUN IN PROGRESS" in text
    assert "regex-slug" in text
    assert "tests_modified" in text          # findings are the whole point
    assert "tests 0/2" in text and "tests 2/2" in text
    assert "chooser=critic" in text


def test_a_failed_run_is_marked_and_needs_human_gets_its_own_flag():
    events = _events()
    events[-1] = {**events[-1], "passed": False, "best_score": 0.999}
    assert "✗" in render(events)
    events[-1] = {**events[-1], "needs_human_review": True}
    text = render(events)
    assert "⚑" in text and "needs-human" in text


def test_split_runs_separates_finished_blocks_from_the_open_one():
    blocks, current = split_runs(_events() + [_events()[0]])
    assert len(blocks) == 1 and blocks[0][-1]["type"] == "run"
    assert current and current[0]["type"] == "probe"  # trailing probe = live run


def test_an_empty_log_renders_a_quiet_placeholder(capsys):
    assert "(no runs recorded yet" in render([])


def test_watch_once_prints_the_frame_from_a_real_log_file(tmp_path, capsys):
    log = tmp_path / "runlog.jsonl"
    log.write_text("\n".join(json.dumps(e) for e in _events()) + "\n")
    frame = watch(path=log, once=True)
    assert "fix the slug" in frame          # --once returns the frame...


def test_a_torn_last_line_does_not_break_the_frame(tmp_path):
    log = tmp_path / "runlog.jsonl"
    log.write_text(json.dumps(_events()[0]) + "\n" + '{"type": "pro')  # writer mid-flush
    text = render(list(__import__("dacode.runlog", fromlist=["load_events"])
                       .load_events(log)))
    assert "regex-slug" in text  # the good line survived, the torn one was skipped


@pytest.mark.parametrize("history,expected", [(1, 1), (10, 10)])
def test_history_bounds_the_finished_runs_shown(history, expected):
    events = []
    for i in range(12):
        events.append({"type": "run", "ts": i, "task": f"task {i}",
                       "passed": bool(i % 2), "rounds": 1,
                       "best_id": f"v{i}", "best_score": 0.5})
    text = render(events, history=history)
    shown = text.count("PASS") + text.count("FAIL")
    assert shown == expected
