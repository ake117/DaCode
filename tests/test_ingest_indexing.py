"""Ingest must make new lessons visible to `local` semantic search.

Readiness audit (docs/design/reviews/2026-11-01, finding 19): ingest()
wrote the note but never touched embeddings.db, so a fresh lesson was
invisible to vector retrieval until someone ran `dacode memory index`
by hand.
"""

from __future__ import annotations

import dacode.memory
from dacode.memory import Lesson, VaultMemory
from dacode.memory.embedder import Embedder
from dacode.memory.vectors import VectorStore, default_path


def _lesson(title: str = "Calc lesson") -> Lesson:
    return Lesson(title=title, body="add: use a + b", tags=[], source_task="t")


def test_ingest_without_embedder_writes_note_and_touches_no_store(
    monkeypatch, tmp_path
):
    for var in ("DACODE_EMBED_DB", "DACODE_EMBED_BASE_URL", "DACODE_EMBED_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    memory = VaultMemory(tmp_path / "vault", scope="etf9", semantic="off")
    path = memory.ingest(_lesson())
    assert path.exists()
    assert not default_path().exists()


def test_ingest_autoindexes_into_the_vector_store(monkeypatch, tmp_path):
    def fake_transport(payload: dict) -> dict:
        return {"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in payload["input"]]}

    stub = Embedder(base_url="stub://embed", model="stub-model", transport=fake_transport)
    monkeypatch.setattr(dacode.memory, "Embedder", lambda: stub)
    db = tmp_path / "embeddings.db"
    monkeypatch.setenv("DACODE_EMBED_DB", str(db))
    vault = tmp_path / "vault"
    memory = VaultMemory(vault, scope="etf9", semantic="off")
    path = memory.ingest(_lesson())
    store = VectorStore(db)
    assert store.count(model="stub-model") >= 1
    rows = {row[0] for row in store._con.execute("SELECT path FROM notes")}
    assert str(path.relative_to(vault)) in rows


def test_ingest_survives_a_broken_embedding_endpoint(monkeypatch, tmp_path):
    def broken_transport(payload: dict) -> dict:
        raise RuntimeError("endpoint down")

    broken = Embedder(base_url="stub://embed", model="stub-model", transport=broken_transport)
    monkeypatch.setattr(dacode.memory, "Embedder", lambda: broken)
    db = tmp_path / "embeddings.db"
    monkeypatch.setenv("DACODE_EMBED_DB", str(db))
    memory = VaultMemory(tmp_path / "vault", scope="etf9", semantic="off")
    path = memory.ingest(_lesson())
    # the note is written; only the vector is missing — the run must not fail
    assert path.exists()
    assert VectorStore(db).count(model="stub-model") == 0
