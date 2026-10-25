"""Local backend — DaCode's own embeddings, no other agent required.

Vectors live in ``~/.local/state/dacode/embeddings.db`` (``DACODE_EMBED_DB``)
and are produced by whatever OpenAI-compatible endpoint is configured
(``DACODE_EMBED_BASE_URL`` / ``DACODE_EMBED_MODEL`` / ``DACODE_EMBED_API_KEY``
— see :mod:`dacode.memory.embedder`). Same machine, same file, no shared state
with any other tool.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _contained(vault: Path, relative: str) -> Path | None:
    """`vault / relative` only if it really stays inside the vault."""
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    resolved = (vault / candidate).resolve()
    try:
        resolved.relative_to(vault.resolve())
    except ValueError:
        return None
    return resolved

from dacode.memory.backends import SemanticHit
from dacode.memory.embedder import EmbedError, Embedder
from dacode.memory.vectors import VectorStore

__all__ = ["LocalStoreBackend"]

_FRONTMATTER = ("---",)


def _read_note_head(path: Path, *, width: int = 300) -> tuple[str, str]:
    """Return ``(title, excerpt)`` cheaply — only for the few top hits."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:8000]
    except OSError:
        return "", ""
    title = ""
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front = text[3:end]
            body = text[end + 4 :]
            for line in front.splitlines():
                key, sep, value = line.partition(":")
                if sep and key.strip().lower() == "title":
                    title = value.strip().strip('"').strip("'")
                    break
    flat = " ".join(body.split())
    return title or path.stem, flat[:width]


class LocalStoreBackend:
    """Semantic retrieval from DaCode's own vector store."""

    name = "local"

    def __init__(
        self,
        vault: str | Path | None = None,
        *,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
    ) -> None:
        self.vault = Path(vault).expanduser().resolve() if vault else None
        self.embedder = embedder or Embedder()
        self.store = store or VectorStore()

    @property
    def detail(self) -> str:
        if not self.embedder.configured:
            return "no embedder (set DACODE_EMBED_BASE_URL + DACODE_EMBED_MODEL)"
        return f"{self.embedder.model} · {self.store.count(model=self.embedder.model)} vectors"

    def available(self) -> bool:
        if self.vault is None or not self.embedder.configured:
            return False
        return self.store.count(model=self.embedder.model) > 0

    def search(self, query: str, top: int = 8) -> list[SemanticHit]:
        if not query or not query.strip() or not self.available():
            return []
        try:
            vector = self.embedder.embed_one(query)
        except EmbedError as exc:
            print(f"[local] query embedding failed: {exc}", file=sys.stderr)
            return []
        hits: list[SemanticHit] = []
        for hit in self.store.search(vector, top=top, model=self.embedder.model):
            path = _contained(self.vault, hit.path)
            if path is None:
                continue
            title, excerpt = _read_note_head(path)
            hits.append(
                SemanticHit(
                    rel_path=hit.path,
                    title=title or path.stem,
                    similarity=max(0.0, min(1.0, hit.score)),
                    excerpt=excerpt,
                )
            )
        return hits
