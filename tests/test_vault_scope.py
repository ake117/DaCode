"""Scoped vault retrieval: one machine vault, per-project lesson lines.

A run scoped to ``etf9`` must see ``Projects/etf9/Lessons`` plus the
vault-wide ``shared/Lessons`` — and nothing else, through any retrieval path
(keyword globs, semantic blends) and despite symlinks or path normalisation
that would otherwise cross project lines. Proven in simulation (Nov 2026)
before implementation; the symlink guard mirrors the gate's own rule from
PR #14.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from dacode.memory import VaultMemory


@pytest.fixture()
def scoped_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for project in ("DaCode", "etf9", "AP_QT_Generator"):
        lessons = vault / "Projects" / project / "Lessons"
        lessons.mkdir(parents=True)
        (lessons / f"{project.lower()}-lesson.md").write_text(
            f"---\ntitle: {project} lesson on {project.lower()} matters\n---\n"
            f"Secret idiom of {project}.\n"
        )
    shared = vault / "shared" / "Lessons"
    shared.mkdir(parents=True)
    (shared / "rig-lesson.md").write_text(
        "---\ntitle: Rig lesson about task text\n---\nForbid test edits.\n"
    )
    return vault


def _titles(memory: VaultMemory, query: str) -> set[str]:
    return {hit.title for hit in memory.retrieve(query, limit=20)}


def test_a_scoped_run_sees_only_its_project_plus_shared(scoped_vault: Path):
    etf9 = VaultMemory(scoped_vault, scope="etf9", semantic="off")
    titles = _titles(etf9, "lesson matters idiom")
    assert any("etf9" in t for t in titles)
    assert any("Rig lesson" in t for t in titles)
    assert not any("AP_QT_Generator" in t for t in titles)
    assert not any("DaCode lesson" in t for t in titles)


def test_a_symlink_inside_a_scope_cannot_import_another_project_lesson(
    scoped_vault: Path,
):
    victim = scoped_vault / "Projects" / "AP_QT_Generator" / "Lessons" / "ap-lesson.md"
    link = scoped_vault / "Projects" / "etf9" / "Lessons" / "evil-link.md"
    link.symlink_to(victim)
    etf9 = VaultMemory(scoped_vault, scope="etf9", semantic="off")
    assert "AP_QT_Generator lesson on ap_qt_generator matters" not in _titles(etf9, "idiom")


def test_a_semantic_hit_cannot_cross_projects_by_normalising_a_rel_path(
    scoped_vault: Path,
):
    class FakeIndex:
        def search(self, query, top):
            from dacode.memory import SemanticHit

            return [
                SemanticHit(rel_path="Projects/AP_QT_Generator/../etf9/Lessons/etf9-lesson.md", score=0.9),
                SemanticHit(rel_path="Projects/AP_QT_Generator/Lessons/ap-lesson.md", score=0.8),
            ]

    etf9 = VaultMemory(
        scoped_vault, scope="etf9", semantic="auto", semantic_index=FakeIndex()
    )
    titles = _titles(etf9, "anything at all")
    assert not any("AP_QT_Generator" in t for t in titles)
    assert any("etf9" in t for t in titles)


def test_scoped_ingest_writes_to_its_own_project_and_refuses_others(scoped_vault: Path):
    from dacode.memory import Lesson

    etf9 = VaultMemory(scoped_vault, scope="etf9", semantic="off")
    lesson = Lesson(title="T", body="b", tags=[], source_task="t")
    path = etf9.ingest(lesson)
    assert path.parent == scoped_vault / "Projects" / "etf9" / "Lessons"
    with pytest.raises(ValueError):
        etf9.ingest(lesson, folder="Projects/AP_QT_Generator/Lessons")


def test_scope_none_keeps_the_whole_vault_readable(scoped_vault: Path):
    whole = VaultMemory(scoped_vault, semantic="off")
    titles = _titles(whole, "idiom lesson")
    assert any("AP_QT_Generator" in t for t in titles)
    assert any("etf9" in t for t in titles)
