"""Layer 1 — Semantic Vault Memory.

Two jobs, straight from the blueprint's workflow lifecycle:

* **Initialization & Context** — before a task runs, ``retrieve()`` pulls the
  most relevant prior lessons/patterns out of the Obsidian vault so they seed
  the harness.
* **Memory Ingestion** — after a task passes, ``ingest()`` writes the lesson
  back as a note so the rig is smarter next time.

Retrieval is keyword/TF scoring over markdown notes — dependency-free and
deterministic.  A semantic backend can be layered on later by implementing the
same interface (see ``score_note`` hook).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

__all__ = ["VaultMemory", "MemoryHit", "Lesson"]

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


class VaultMemory:
    """Keyword-retrieval memory backed by a markdown vault."""

    def __init__(
        self,
        vault_path: str | Path,
        *,
        include_globs: tuple[str, ...] = ("**/*.md",),
        exclude_dirs: tuple[str, ...] = (".obsidian", ".git", ".trash", "templates"),
        max_note_chars: int = 200_000,
    ) -> None:
        self.vault = Path(vault_path).expanduser().resolve()
        self.include_globs = include_globs
        self.exclude_dirs = {d.lower() for d in exclude_dirs}
        self.max_note_chars = max_note_chars

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

    def retrieve(self, query: str, limit: int = 5, *, min_score: float = 0.5) -> list[MemoryHit]:
        """Return the ``limit`` best notes for ``query``, best first."""
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
        return hits[:limit]

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
            f'title: "{lesson.title}"\n'
            f"created: {created}\n"
            "type: lesson\n"
            "source: dacode\n"
            f"source_task: {lesson.source_task or 'n/a'}\n"
            "tags:\n"
            f"{tags}\n"
            "---\n\n"
        )
        path.write_text(frontmatter + lesson.body.rstrip() + "\n", encoding="utf-8")
        return path
