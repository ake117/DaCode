"""Tests for the vault memory layer."""

from __future__ import annotations

from dacode.memory import Lesson, VaultMemory


def test_retrieve_ranks_the_relevant_note_first(vault):
    mem = VaultMemory(vault)
    hits = mem.retrieve("git worktree sandbox")
    assert hits, "expected at least one hit"
    assert hits[0].path.name == "Sandbox.md"
    assert hits[0].score > 0


def test_retrieve_returns_nothing_for_unrelated_query(vault):
    mem = VaultMemory(vault)
    hits = mem.retrieve("quantum chromodynamics lattice")
    assert hits == []


def test_retrieve_respects_limit(vault):
    mem = VaultMemory(vault)
    hits = mem.retrieve("harness sandbox recursion", limit=1)
    assert len(hits) == 1


def test_ingest_writes_a_retrievable_note(vault):
    mem = VaultMemory(vault)
    path = mem.ingest(Lesson(title="Trial Lesson Note", body="a durable body text", tags=["dacode"]))
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Trial Lesson Note" in text
    assert "a durable body text" in text
    assert "type: lesson" in text

    hits = mem.retrieve("durable body text")
    assert any(hit.path == path for hit in hits)
