"""Tests for the SQLite local state store (memory.db)."""

from __future__ import annotations

import pytest

from dacode import state
from dacode.runlog import record


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "memory.db"
    monkeypatch.setenv("DACODE_MEMORY_DB", str(path))
    return path


def _run_event(**over):
    event = {
        "type": "run",
        "ts": 1000.0,
        "task": "Add a docstring to the sandbox module",
        "rounds": 1,
        "passed": True,
        "needs_human_review": False,
        "best_id": "v2",
        "best_score": 1.0,
    }
    event.update(over)
    return event


def _probe_event(**over):
    event = {
        "type": "probe",
        "ts": 1001.0,
        "task": "Add a docstring to the sandbox module",
        "variant_id": "v3",
        "label": "test-first",
        "score": 0.92,
        "tests_passed": 61,
        "tests_total": 66,
        "critique_passed": False,
        "exit_code": 1,
    }
    event.update(over)
    return event


def _compose_event(**over):
    event = {
        "type": "compose",
        "ts": 1002.0,
        "task": "Add a docstring to the sandbox module",
        "chosen_id": "v2",
        "chooser": "judge",
        "table": [
            {"id": "v2", "label": "minimal", "score": 1.0, "passed": True},
            {"id": "v3", "label": "test-first", "score": 0.92, "passed": False},
        ],
    }
    event.update(over)
    return event


def test_ingest_counts_into_stats(db_path):
    state.ingest(_run_event())
    state.ingest(_probe_event())
    state.ingest(_compose_event())
    info = state.stats()
    assert info["enabled"] is True
    assert info["runs"] == 1
    assert info["runs_passed"] == 1
    assert info["variants"] == 1
    assert info["variants_failed"] == 1
    assert info["picks"] == 1
    assert info["fts"] is True


def test_search_matches_english_tokens(db_path):
    state.ingest(_run_event())
    hits = state.search("docstring")
    assert hits and "docstring" in hits[0]["task"]


def test_search_matches_thai_substrings(db_path):
    state.ingest(_run_event(task="ปรับ lookup chain ให้ใช้ repo dotenv เท่านั้น"))
    assert state.search("lookup chain")


def test_search_returns_empty_for_noise(db_path):
    state.ingest(_run_event())
    assert state.search("zzz-unfindable-token") == []


def test_failures_returns_only_gate_failures(db_path):
    state.ingest(_probe_event())
    state.ingest(_probe_event(variant_id="v4", label="winner", critique_passed=True))
    rows = state.failures()
    assert [row["label"] for row in rows] == ["test-first"]


def test_failures_can_filter_by_task(db_path):
    state.ingest(_probe_event(task="improve slugify"))
    state.ingest(_probe_event(task="fix the parser"))
    rows = state.failures(task="slugify")
    assert len(rows) == 1 and "slugify" in rows[0]["task"]


def test_ingest_never_raises_on_garbage(db_path):
    state.ingest({})
    state.ingest({"type": "unknown", "task": "x"})
    state.ingest({"type": "probe", "ts": "not-a-number"})
    assert state.stats()["runs"] == 0


def test_store_can_be_disabled(monkeypatch):
    monkeypatch.setenv("DACODE_MEMORY_DB", "off")
    state.ingest(_run_event())
    assert state.stats() == {"enabled": False}
    assert state.search("docstring") == []
    assert state.failures() == []


def test_rebuild_recreates_from_events(db_path):
    events = [_run_event(), _probe_event(), _compose_event()]
    assert state.rebuild(events) == 3
    assert state.stats()["variants"] == 1
    assert state.rebuild(events) == 3  # idempotent: wipe + replay
    assert state.stats()["variants"] == 1


def test_record_mirrors_into_the_store(db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("DACODE_RUNLOG", str(tmp_path / "runlog.jsonl"))
    record(_run_event())
    assert state.stats()["runs"] == 1
