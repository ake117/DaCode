"""Layer 1 — Semantic Vault Memory.

Two jobs, straight from the blueprint's workflow lifecycle:

* **Initialization & Context** — before a task runs, ``retrieve()`` pulls the
  most relevant prior lessons/patterns out of the Obsidian vault so they seed
  the harness.
* **Memory Ingestion** — after a task passes, ``ingest()`` writes the lesson
  back as a note so the rig is smarter next time.

Retrieval is keyword/TF scoring over markdown notes — dependency-free and
deterministic. When the Hermes semantic index is installed, embedding hits
(``dacode.memory.semantic``) are blended into the ranking; any failure in that
backend silently degrades to keywords.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dacode.memory.backends import SemanticHit, SemanticBackend, resolve, status
from dacode.memory.backends.hermes import SemanticIndex

__all__ = [
    "VaultMemory",
    "MemoryHit",
    "Lesson",
    "SemanticBackend",
    "SemanticHit",
    "SemanticIndex",
    "resolve",
    "status",
]

_WORD_RE = re.compile(r"[A-Za-z0-9_]{3,}|[\u0E00-\u0E7F]{2,}")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

# Words too common to carry signal in either language.
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "you", "your", "how", "what", "when", "where", "which", "into", "not",
    "แต่", "และ", "หรือ", "ของ", "ที่", "ใน", "การ", "ความ", "ให้", "ได้",
    "เป็น", "กับ", "จาก", "นี้", "นั้น", "แล้ว", "จะ", "มี",
}


@dataclass(frozen=True)
class MemoryHit:
    path: Path
    title: str
    score: float
    snippet: str
    tags: tuple[str, ...] = ()


@dataclass
class Lesson:
    title: str
    body: str
    tags: list[str] = field(default_factory=list)
    source_task: str = ""
    created: str = ""


def _resolve_in_vault(vault: Path, relative: str | Path) -> Path | None:
    """Resolve ``relative`` inside ``vault`` or return None.

    A semantic backend or an embeddings row is untrusted input (it can be a `..`
    path or an absolute one); without this the note reader would happily return the
    head of any host file into a prompt.
    """
    candidate = Path(relative)
    if candidate.is_absolute():
        return None
    resolved = (vault / candidate).resolve()
    try:
        resolved.relative_to(vault.resolve())
    except ValueError:
        return None
    return resolved


class VaultMemory:
    """Keyword-retrieval memory backed by a markdown vault."""

    def __init__(
        self,
        vault_path: str | Path,
        *,
        include_globs: tuple[str, ...] = ("**/*.md",),
        exclude_dirs: tuple[str, ...] = (".obsidian", ".git", ".trash", "templates"),
        max_note_chars: int = 200_000,
        semantic: bool | str = "auto",
        semantic_index: SemanticIndex | None = None,
    ) -> None:
        self.vault = Path(vault_path).expanduser().resolve()
        self.include_globs = include_globs
        self.exclude_dirs = {d.lower() for d in exclude_dirs}
        self.max_note_chars = max_note_chars
        self.semantic_mode = semantic
        self._semantic_index = semantic_index
        self._semantic_checked = semantic_index is not None
        self._semantic_failed = False

    # -- reading -----------------------------------------------------------

    def _iter_notes(self):
        seen: set[Path] = set()
        for pattern in self.include_globs:
            for path in self.vault.glob(pattern):
                if not path.is_file() or path in seen:
                    continue
                if any(part.lower() in self.exclude_dirs for part in path.parts):
                    continue
                seen.add(path)
                yield path

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict, str]:
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return {}, text
        raw, body = match.group(1), text[match.end():]
        meta: dict = {}
        for line in raw.splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
        return meta, body

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t.lower() for t in _WORD_RE.findall(text) if t.lower() not in _STOPWORDS]

    def _score(self, query_tokens: list[str], title: str, body: str) -> float:
        """TF score: title hits weigh 3x, body hits 1x."""
        title_l = title.lower()
        body_l = body.lower()
        score = 0.0
        for token in set(query_tokens):
            title_hits = title_l.count(token)
            body_hits = body_l.count(token)
            if title_hits or body_hits:
                score += 3.0 * title_hits + 1.0 * body_hits
        return score

    def _semantic(self) -> SemanticBackend | None:
        """Lazy-resolve the semantic backend once; ``None`` means off.

        The instance setting is a backend name (``auto`` / ``local`` /
        ``hermes`` / ``module:factory`` / ``off``). ``DACODE_SEMANTIC_BACKEND``
        overrides it globally, and ``DACODE_SEMANTIC=off`` stays the kill
        switch that tests rely on.
        """
        if isinstance(self.semantic_mode, bool):
            mode = "auto" if self.semantic_mode else "off"
        else:
            mode = str(self.semantic_mode).strip() or "auto"
        env_mode = (
            os.environ.get("DACODE_SEMANTIC_BACKEND")
            or os.environ.get("DACODE_SEMANTIC")
            or ""
        ).strip()
        if env_mode:
            mode = env_mode
        if mode.lower() in {"off", "false", "0", "no", "none"}:
            return None
        if self._semantic_checked:
            return self._semantic_index
        self._semantic_checked = True
        try:
            self._semantic_index = resolve(mode, self.vault)
        except Exception as exc:  # noqa: BLE001 - misconfig must not break retrieval
            print(f"[memory] backend {mode!r} unusable: {exc}", file=sys.stderr)
            self._semantic_index = None
        return self._semantic_index

    def _semantic_hits(self, query: str, limit: int) -> list[SemanticHit]:
        """Semantic hits for ``query``; a failure disables the backend for good."""
        index = self._semantic()
        if index is None or self._semantic_failed:
            return []
        try:
            return index.search(query, top=max(limit * 2, 8))
        except Exception as exc:  # noqa: BLE001 - retrieval must never break a run
            self._semantic_failed = True
            print(f"[memory] semantic retrieval disabled: {exc}", file=sys.stderr)
            return []

    def _tags_of(self, path: Path) -> tuple[str, ...]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:4000]
        except OSError:
            return ()
        meta, _ = self._split_frontmatter(text)
        return tuple(
            t.strip() for t in str(meta.get("tags", "")).replace(",", " ").split() if t.strip()
        )

    def _blend(
        self,
        keyword_hits: list[MemoryHit],
        semantic_hits: list[SemanticHit],
        limit: int,
    ) -> list[MemoryHit]:
        """Merge both rankings: 60% embedding similarity + 40% normalized TF."""
        top_kw = max((hit.score for hit in keyword_hits), default=0.0) or 1.0
        merged: dict[Path, MemoryHit] = {}
        for hit in keyword_hits:
            merged[hit.path.resolve()] = MemoryHit(
                path=hit.path,
                title=hit.title,
                score=round(0.4 * hit.score / top_kw, 3),
                snippet=hit.snippet,
                tags=hit.tags,
            )
        for sem in semantic_hits:
            target = _resolve_in_vault(self.vault, sem.rel_path)
            if target is None:
                continue
            key = target.resolve()
            base = merged.get(key)
            if base is None:
                if not key.is_file():
                    continue
                base = MemoryHit(
                    path=key,
                    title=sem.title or key.stem,
                    score=0.0,
                    snippet=sem.excerpt or "",
                    tags=self._tags_of(key),
                )
            similarity = max(0.0, min(1.0, sem.similarity))
            merged[key] = MemoryHit(
                path=base.path,
                title=base.title,
                score=round(base.score + 0.6 * similarity, 3),
                snippet=base.snippet or sem.excerpt,
                tags=base.tags,
            )
        ranked = sorted(merged.values(), key=lambda hit: (-hit.score, str(hit.path)))
        return ranked[:limit]

    def retrieve(self, query: str, limit: int = 5, *, min_score: float = 0.5) -> list[MemoryHit]:
        """Return the ``limit`` best notes for ``query``, best first.

        Keyword/TF scoring always runs. When the Hermes semantic index is
        reachable, embedding hits are blended in (60% similarity + 40%
        normalized keyword score); a semantic failure silently degrades to the
        keyword ranking.
        """
        if not query or not query.strip():
            return []
        tokens = self._tokenize(query)
        if not tokens:
            return []
        hits: list[MemoryHit] = []
        for note in self._iter_notes():
            try:
                text = note.read_text(encoding="utf-8", errors="replace")[: self.max_note_chars]
            except OSError:
                continue
            meta, body = self._split_frontmatter(text)
            title = meta.get("title") or note.stem
            score = self._score(tokens, str(title), body)
            if score >= min_score:
                hits.append(
                    MemoryHit(
                        path=note,
                        title=str(title),
                        score=round(score, 3),
                        snippet=self._snippet(tokens, body),
                        tags=tuple(
                            t.strip() for t in str(meta.get("tags", "")).replace(",", " ").split()
                            if t.strip()
                        ),
                    )
                )
        hits.sort(key=lambda h: (-h.score, str(h.path)))
        semantic_hits = self._semantic_hits(query, limit)
        if not semantic_hits:
            return hits[:limit]
        return self._blend(hits, semantic_hits, limit)

    @staticmethod
    def _snippet(tokens: list[str], body: str, width: int = 200) -> str:
        """Return the first window of ``body`` that mentions a query token."""
        body_flat = " ".join(body.split())
        lowered = body_flat.lower()
        pos = -1
        for token in tokens:
            pos = lowered.find(token)
            if pos != -1:
                break
        if pos == -1:
            return body_flat[:width]
        start = max(0, pos - width // 3)
        return body_flat[start : start + width]

    # -- writing -----------------------------------------------------------

    def ingest(self, lesson: Lesson, *, folder: str = "Projects/DaCode/Lessons") -> Path:
        """Persist ``lesson`` as a markdown note. Returns the written path."""
        target_dir = self.vault / folder
        target_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9\u0E00-\u0E7F]+", "-", lesson.title).strip("-")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = target_dir / f"{stamp}-{slug}.md"
        created = lesson.created or datetime.now().strftime("%Y-%m-%d")
        tags = "\n".join(f"  - {t}" for t in lesson.tags) or "  - dacode/lesson"
        frontmatter = (
            "---\n"
            f"title: {json.dumps(lesson.title, ensure_ascii=False)}\n"
            f"created: {created}\n"
            "type: lesson\n"
            "source: dacode\n"
            f"source_task: {json.dumps(lesson.source_task or 'n/a', ensure_ascii=False)}\n"
            "tags:\n"
            f"{tags}\n"
            "---\n\n"
        )
        path.write_text(frontmatter + lesson.body.rstrip() + "\n", encoding="utf-8")
        return path
