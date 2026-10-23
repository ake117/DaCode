"""Tests for DaCode's own embedding store, the local backend, and the registry."""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

import pytest

from dacode.memory.backends import SemanticHit, resolve, status
from dacode.memory.backends.local import LocalStoreBackend
from dacode.memory.embedder import EmbedError, Embedder
from dacode.memory.vectors import VectorStore


class _HashEmbedder(Embedder):
    """Deterministic bag-of-words vectors — no network, stable across runs."""

    def __init__(self, dims: int = 16, model: str = "fake-embed") -> None:
        super().__init__(base_url="http://fake", model=model, batch=4)
        self.dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dims
            for word in text.lower().split():
                vector[zlib.crc32(word.encode()) % self.dims] += 1.0
            vectors.append(vector)
        return vectors


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "Notes").mkdir(parents=True)
    (root / "Notes" / "Alpha.md").write_text(
        "---\ntitle: Alpha note\n---\n\nalpha beta gamma isolation\n", encoding="utf-8"
    )
    (root / "Notes" / "Delta.md").write_text(
        "---\ntitle: Delta note\n---\n\ndelta epsilon zeta worktrees\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def store(tmp_path):
    return VectorStore(tmp_path / "embeddings.db")


def test_index_embeds_then_prunes(vault, store):
    embedder = _HashEmbedder()
    counts = store.index(vault, embedder)
    assert counts["embedded"] == 2 and counts["total"] == 2

    again = store.index(vault, embedder)
    assert again["embedded"] == 0 and again["skipped"] == 2

    (vault / "Notes" / "Alpha.md").unlink()
    pruned = store.index(vault, embedder)
    assert pruned["pruned"] == 1 and pruned["total"] == 1


def test_changed_note_is_re_embedded(vault, store, monkeypatch):
    embedder = _HashEmbedder()
    store.index(vault, embedder)
    note = vault / "Notes" / "Alpha.md"
    note.write_text("---\ntitle: Alpha note\n---\n\nrewritten body\n", encoding="utf-8")
    note.touch()  # ensure a distinct mtime
    counts = store.index(vault, embedder)
    assert counts["embedded"] == 1


def test_search_ranks_by_cosine(vault, store):
    embedder = _HashEmbedder()
    store.index(vault, embedder)
    hits = store.search(embedder.embed_one("alpha beta"), top=2, model=embedder.model)
    assert hits[0].path.endswith("Alpha.md")
    assert hits[0].score > hits[1].score


def test_model_switch_requires_rebuild(vault, store):
    store.index(vault, _HashEmbedder(model="model-a"))
    with pytest.raises(RuntimeError, match="rebuild"):
        store.index(vault, _HashEmbedder(model="model-b"))
    counts = store.index(vault, _HashEmbedder(model="model-b"), rebuild=True)
    assert counts["embedded"] == 2 and counts["model"] == "model-b"


def test_local_backend_serves_hits(vault, store):
    embedder = _HashEmbedder()
    store.index(vault, embedder)
    backend = LocalStoreBackend(vault, embedder=embedder, store=store)
    assert backend.available() is True
    hits = backend.search("delta epsilon", top=2)
    assert hits and hits[0].rel_path.endswith("Delta.md")
    assert hits[0].title == "Delta note"
    assert hits[0].excerpt


def test_local_backend_unavailable_without_vectors(vault, store):
    backend = LocalStoreBackend(vault, embedder=_HashEmbedder(), store=store)
    assert backend.available() is False
    assert backend.search("anything") == []


def test_local_backend_unavailable_without_embedder(vault, store):
    backend = LocalStoreBackend(vault, embedder=_HashEmbedder(), store=store)
    store.index(vault, backend.embedder)
    blind = LocalStoreBackend(vault, embedder=Embedder(base_url="", model=""), store=store)
    assert blind.available() is False


def test_resolve_off_and_unknown_names(vault, store):
    assert resolve("off", vault) is None
    with pytest.raises(ValueError, match="unknown memory backend"):
        resolve("nope", vault)


def test_resolve_auto_skips_local_without_an_embedder(vault, monkeypatch):
    monkeypatch.delenv("DACODE_EMBED_BASE_URL", raising=False)
    monkeypatch.delenv("DACODE_EMBED_MODEL", raising=False)
    backend = resolve("auto", vault)
    assert backend is None or backend.name != "local"


def test_resolve_auto_prefers_local_when_configured(vault, store, monkeypatch):
    embedder = _HashEmbedder(model="fake-embed")
    store.index(vault, embedder)
    monkeypatch.setenv("DACODE_EMBED_BASE_URL", "http://fake/v1")
    monkeypatch.setenv("DACODE_EMBED_MODEL", "fake-embed")
    backend = resolve("auto", vault)
    assert backend is not None and backend.name == "local"  # independent store wins


def test_third_party_backend_via_module_factory(vault, tmp_path, monkeypatch):
    module = tmp_path / "my_agent_memory.py"
    module.write_text(
        "from dacode.memory.backends import SemanticHit\n"
        "\n"
        "class Backend:\n"
        "    name = 'myagent'\n"
        "    def available(self):\n"
        "        return True\n"
        "    def search(self, query, top=8):\n"
        "        return [SemanticHit('Notes/Alpha.md', 'Alpha', 0.5, 'from my agent')]\n"
        "\n"
        "def make_backend(vault):\n"
        "    return Backend()\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    backend = resolve("my_agent_memory:make_backend", vault)
    assert backend is not None and backend.name == "myagent"
    assert backend.search("x")[0].excerpt == "from my agent"


def test_status_reports_both_builtin_backends(vault):
    rows = {row["name"]: row for row in status(vault)}
    assert set(rows) == {"local", "hermes"}
    assert rows["local"]["available"] is False  # no embedder/vectors in tests


def test_embedder_parses_openai_shape_and_batches():
    calls = []

    def transport(payload):
        calls.append(payload)
        return {"data": [{"embedding": [0.1, 0.2, 0.3]} for _ in payload["input"]]}

    embedder = Embedder(base_url="http://x/v1", model="m", batch=2, transport=transport)
    vectors = embedder.embed(["a", "b", "c"])
    assert len(vectors) == 3 and vectors[0] == [0.1, 0.2, 0.3]
    assert [len(call["input"]) for call in calls] == [2, 1]


def test_embedder_rejects_unconfigured_and_bad_shapes():
    with pytest.raises(EmbedError, match="configured"):
        Embedder(base_url="", model="").embed(["x"])

    short = Embedder(
        base_url="http://x/v1", model="m", transport=lambda payload: {"data": []}
    )
    with pytest.raises(EmbedError, match="vectors for"):
        short.embed(["a"])
