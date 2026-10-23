"""Tests for the semantic retrieval backend (the Hermes index bridge)."""

from __future__ import annotations

import json
import sys

import pytest

from dacode.memory import VaultMemory
from dacode.memory.semantic import SemanticHit, SemanticIndex


class _FakeIndex:
    """Stands in for SemanticIndex — no subprocess, no network."""

    def __init__(self, hits=None, error=None):
        self.hits = list(hits or [])
        self.error = error
        self.calls = []

    def available(self) -> bool:
        return True

    def search(self, query, top=8):
        self.calls.append((query, top))
        if self.error is not None:
            raise self.error
        return list(self.hits)


@pytest.fixture(autouse=True)
def _semantic_enabled(monkeypatch):
    """The repo-wide conftest disables semantics; this module tests it."""
    monkeypatch.delenv("DACODE_SEMANTIC", raising=False)


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    notes = root / "Resources"
    notes.mkdir(parents=True)
    (notes / "Harness.md").write_text(
        "---\ntitle: Harness engineering\ntags:\n  - ai/agent\n---\n\n"
        "Propose probe compose loops keep agents honest.\n",
        encoding="utf-8",
    )
    (notes / "Worktrees.md").write_text(
        "---\ntitle: Git worktrees\n---\n\nIsolation for parallel trials.\n",
        encoding="utf-8",
    )
    return root


def test_semantic_hits_are_blended_above_wordy_notes(vault):
    # the index points at Worktrees.md although only Harness.md has the words
    fake = _FakeIndex([SemanticHit("Resources/Worktrees.md", "Git worktrees", 0.9, "Isolation")])
    mem = VaultMemory(vault, semantic=True, semantic_index=fake)
    hits = mem.retrieve("propose probe compose loops", limit=2)
    assert hits[0].title == "Git worktrees"
    assert fake.calls and fake.calls[0][0] == "propose probe compose loops"


def test_keyword_only_when_semantic_disabled(vault):
    fake = _FakeIndex([SemanticHit("Resources/Worktrees.md", "Git worktrees", 0.9, "x")])
    mem = VaultMemory(vault, semantic="off", semantic_index=fake)
    hits = mem.retrieve("propose probe compose loops")
    assert hits[0].title == "Harness engineering"
    assert fake.calls == []


def test_env_kill_switch_disables_the_backend(vault, monkeypatch):
    monkeypatch.setenv("DACODE_SEMANTIC", "off")
    assert VaultMemory(vault, semantic="auto")._semantic() is None


def test_semantic_failure_falls_back_and_disables(vault):
    fake = _FakeIndex(error=RuntimeError("gemini down"))
    mem = VaultMemory(vault, semantic=True, semantic_index=fake)
    hits = mem.retrieve("isolation for parallel trials")
    assert hits and hits[0].title == "Git worktrees"
    assert mem.retrieve("isolation")  # still works; the backend stays skipped
    assert len(fake.calls) == 1


def test_missing_note_from_index_is_skipped(vault):
    fake = _FakeIndex([SemanticHit("Resources/Ghost.md", "Ghost", 0.99, "nope")])
    mem = VaultMemory(vault, semantic=True, semantic_index=fake)
    hits = mem.retrieve("propose probe compose")
    assert all(hit.title != "Ghost" for hit in hits)


def test_index_parses_pipeline_json():
    payload = json.dumps(
        [{"rel_path": "a.md", "title": "A", "similarity": 0.5, "excerpt": "x"}]
    )
    index = SemanticIndex(
        script=__file__, python=sys.executable, runner=lambda query, top: payload
    )
    assert index.search("anything", top=3) == [SemanticHit("a.md", "A", 0.5, "x")]


def test_index_survives_garbage_output():
    index = SemanticIndex(
        script=__file__, python=sys.executable, runner=lambda query, top: "not json"
    )
    assert index.search("anything") == []


def test_index_reports_unavailable_when_script_missing(tmp_path):
    index = SemanticIndex(script=tmp_path / "missing.py", python=sys.executable)
    assert index.available() is False
    assert index.search("anything") == []
