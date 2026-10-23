"""Semantic retrieval backend — borrows Hermes' vault embedding index.

DaCode stays dependency-free: instead of linking ChromaDB, it shells out to
Hermes' ``search_vault.py``, which queries the Gemini ``gemini-embedding-001``
collection at ``~/.hermes/data/vault_chromadb``. The subprocess owns its own
venv and API key, so DaCode's own key policy (target repo ``.env`` only) is
untouched.

Environment overrides:

* ``DACODE_SEMANTIC`` — ``auto`` (default: on when the script exists) /
  ``on`` / ``off``.
* ``DACODE_SEMANTIC_SCRIPT`` — path to ``search_vault.py``.
* ``DACODE_SEMANTIC_PYTHON`` — interpreter of the skill venv.
* ``DACODE_SEMANTIC_TIMEOUT`` — subprocess timeout in seconds (default 20).

Nothing here raises at call time: a missing index, a dead network, or garbage
output all degrade to "no semantic hits" and keyword retrieval continues.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = ["SemanticHit", "SemanticIndex", "available"]

DEFAULT_SCRIPT = "~/.hermes/skills/note-taking/semantic-vault-search/scripts/search_vault.py"
DEFAULT_PYTHON = "~/.hermes/venvs/semantic-vault-search/bin/python"


@dataclass(frozen=True)
class SemanticHit:
    rel_path: str
    title: str
    similarity: float
    excerpt: str


class SemanticIndex:
    """Query the Hermes vault embedding index over a subprocess boundary."""

    def __init__(
        self,
        script: str | Path | None = None,
        python: str | Path | None = None,
        *,
        timeout: float | None = None,
        runner=None,
    ) -> None:
        self.script = Path(
            script or os.environ.get("DACODE_SEMANTIC_SCRIPT") or DEFAULT_SCRIPT
        ).expanduser()
        self.python = Path(
            python or os.environ.get("DACODE_SEMANTIC_PYTHON") or DEFAULT_PYTHON
        ).expanduser()
        self.timeout = float(timeout or os.environ.get("DACODE_SEMANTIC_TIMEOUT", "20"))
        self._runner = runner or self._run_pipeline

    def available(self) -> bool:
        """True when both the search script and its interpreter exist."""
        return self.script.is_file() and self.python.exists()

    def _run_pipeline(self, query: str, top: int) -> str:
        proc = subprocess.run(
            [str(self.python), str(self.script), query, "--top", str(top), "--json"],
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            raise RuntimeError(detail[-1][:300] if detail else f"exit {proc.returncode}")
        return proc.stdout

    def search(self, query: str, top: int = 8) -> list[SemanticHit]:
        """Return semantic hits, best first. Any failure yields ``[]``."""
        if not query or not query.strip() or not self.available():
            return []
        try:
            raw = self._runner(query, top)
            data = json.loads(raw or "[]")
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            print(f"[semantic] unavailable: {exc}", file=sys.stderr)
            return []
        hits: list[SemanticHit] = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                hits.append(
                    SemanticHit(
                        rel_path=str(item.get("rel_path") or ""),
                        title=str(item.get("title") or ""),
                        similarity=float(item.get("similarity") or 0.0),
                        excerpt=str(item.get("excerpt") or ""),
                    )
                )
            except (TypeError, ValueError):
                continue
        hits.sort(key=lambda hit: -hit.similarity)
        return [hit for hit in hits if hit.rel_path]


def available() -> bool:
    """True when the semantic backend is enabled and installed on this host."""
    mode = (os.environ.get("DACODE_SEMANTIC") or "auto").lower()
    if mode in {"off", "0", "false", "no"}:
        return False
    return SemanticIndex().available()
