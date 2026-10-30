"""DaCode-owned vector store — SQLite + exact cosine, no external database.

One row per vault note holds a normalized float32 vector, so similarity is a
dot product. ~580 notes × 768 dims ≈ 1.8 MB, and a full scan is milliseconds —
a vector database would be more machinery than this problem needs.

Indexing is incremental by ``(mtime, model, dims)``: unchanged notes are
skipped, deleted notes are pruned, and switching embedding models requires an
explicit ``rebuild`` (mixing models in one store silently ruins every score).
"""

from __future__ import annotations

import array
import math
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dacode.memory.embedder import Embedder

__all__ = ["VectorStore", "VectorHit", "default_path"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    model TEXT NOT NULL,
    dims INTEGER NOT NULL,
    vector BLOB NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_model ON notes(model);
"""


def default_path() -> Path:
    return Path("~/.local/state/dacode/embeddings.db").expanduser()


@dataclass(frozen=True)
class VectorHit:
    path: str
    score: float


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class VectorStore:
    def __init__(self, path: str | Path | None = None) -> None:
        raw = path or os.environ.get("DACODE_EMBED_DB") or default_path()
        self.path = Path(raw).expanduser()
        parent = self.path.parent
        created = not parent.exists()
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if created:
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass
        self._con = sqlite3.connect(str(self.path), timeout=10.0)
        self._con.executescript(_SCHEMA)

    # -- writes ------------------------------------------------------------

    def upsert(self, rel_path: str, mtime: float, model: str, dims: int, vector: list[float]) -> None:
        blob = array.array("f", _normalize(vector)).tobytes()
        with self._con:
            self._con.execute(
                "INSERT INTO notes(path, mtime, model, dims, vector, updated)"
                " VALUES(?,?,?,?,?,strftime('%s','now'))"
                " ON CONFLICT(path) DO UPDATE SET"
                " mtime=excluded.mtime, model=excluded.model, dims=excluded.dims,"
                " vector=excluded.vector, updated=excluded.updated",
                (rel_path, mtime, model, dims, blob),
            )

    def prune(self, keep: set[str]) -> int:
        rows = [row[0] for row in self._con.execute("SELECT path FROM notes").fetchall()]
        stale = [path for path in rows if path not in keep]
        with self._con:
            for path in stale:
                self._con.execute("DELETE FROM notes WHERE path = ?", (path,))
        return len(stale)

    def index(
        self,
        vault: str | Path,
        embedder: Embedder,
        *,
        rebuild: bool = False,
        max_note_chars: int = 200_000,
        include_glob: str = "**/*.md",
        exclude_dirs: tuple[str, ...] = (".obsidian", ".git", ".trash"),
    ) -> dict:
        """Embed new/changed notes. Returns counts for the caller to report."""
        vault = Path(vault).expanduser().resolve()
        if rebuild:
            with self._con:
                self._con.execute("DELETE FROM notes")
        seen_models = {row[0] for row in self._con.execute("SELECT DISTINCT model FROM notes")}
        if seen_models and embedder.model not in seen_models:
            raise RuntimeError(
                f"store holds {sorted(seen_models)} but the embedder is {embedder.model!r};"
                " pass rebuild=True (mix models and every similarity is noise)"
            )
        existing = {
            row[0]: (row[1], row[2])
            for row in self._con.execute("SELECT path, mtime, dims FROM notes")
        }
        excluded = {name.lower() for name in exclude_dirs}
        todo: list[tuple[str, float, str]] = []
        keep: set[str] = set()
        for note in vault.glob(include_glob):
            if not note.is_file() or any(part.lower() in excluded for part in note.parts):
                continue
            rel = str(note.relative_to(vault))
            keep.add(rel)
            try:
                mtime = note.stat().st_mtime
            except OSError:
                continue
            known = existing.get(rel)
            if known and abs(known[0] - mtime) < 1e-6:
                continue
            try:
                text = note.read_text(encoding="utf-8", errors="replace")[:max_note_chars]
            except OSError:
                continue
            todo.append((rel, mtime, text))
        pruned = self.prune(keep)
        embedded = 0
        if todo:
            vectors = embedder.embed([text for _, _, text in todo])
            for (rel, mtime, _), vector in zip(todo, vectors):
                self.upsert(rel, mtime, embedder.model, len(vector), vector)
                embedded += 1
        total = self._con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        return {
            "embedded": embedded,
            "skipped": len(keep) - embedded,
            "pruned": pruned,
            "total": total,
            "model": embedder.model,
        }

    # -- reads -------------------------------------------------------------

    def search(self, query_vector: list[float], top: int = 8, *, model: str | None = None) -> list[VectorHit]:
        query = _normalize(query_vector)
        sql = "SELECT path, vector, model FROM notes"
        args: tuple = ()
        if model:
            sql += " WHERE model = ?"
            args = (model,)
        hits: list[VectorHit] = []
        for path, blob, _row_model in self._con.execute(sql, args):
            stored = array.array("f")
            stored.frombytes(blob)
            if len(stored) != len(query):
                continue  # different dims — not comparable
            score = sum(a * b for a, b in zip(query, stored))
            hits.append(VectorHit(path=path, score=score))
        hits.sort(key=lambda hit: -hit.score)
        return hits[:top]

    def count(self, *, model: str | None = None) -> int:
        if model:
            return self._con.execute("SELECT COUNT(*) FROM notes WHERE model = ?", (model,)).fetchone()[0]
        return self._con.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

    def models(self) -> list[str]:
        return [row[0] for row in self._con.execute("SELECT DISTINCT model FROM notes")]

    def close(self) -> None:
        self._con.close()
