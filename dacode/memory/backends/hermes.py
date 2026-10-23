"""Hermes adapter — query another agent's vault index over a subprocess.

This is an *optional* backend: DaCode ships its own store (``local``), and this
adapter exists for setups that already maintain an embedding index elsewhere.
The defaults point at Hermes' semantic-vault-search skill, but every path is
overridable:

* ``DACODE_SEMANTIC_SCRIPT`` — the search script (must accept
  ``<query> --top N --json`` and print a JSON list of
  ``{rel_path, title, similarity, excerpt}``)
* ``DACODE_SEMANTIC_PYTHON`` — interpreter that has that script's deps
* ``DACODE_SEMANTIC_TIMEOUT`` — seconds (default 20)

A missing script, a dead network, or garbage output all mean "no hits" — the
keyword pass continues.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from dacode.memory.backends import SemanticHit

__all__ = ["HermesIndexBackend", "SemanticIndex", "DEFAULT_SCRIPT", "DEFAULT_PYTHON"]

DEFAULT_SCRIPT = "~/.hermes/skills/note-taking/semantic-vault-search/scripts/search_vault.py"
DEFAULT_PYTHON = "~/.hermes/venvs/semantic-vault-search/bin/python"


class HermesIndexBackend:
    """Query an external embedding index (Hermes by default) via subprocess."""

    name = "hermes"

    def __init__(
        self,
        vault: str | Path | None = None,
        *,
        script: str | Path | None = None,
        python: str | Path | None = None,
        timeout: float | None = None,
        runner=None,
    ) -> None:
        self.vault = Path(vault).expanduser() if vault else None
        self.script = Path(
            script or os.environ.get("DACODE_SEMANTIC_SCRIPT") or DEFAULT_SCRIPT
        ).expanduser()
        self.python = Path(
            python or os.environ.get("DACODE_SEMANTIC_PYTHON") or DEFAULT_PYTHON
        ).expanduser()
        self.timeout = float(timeout or os.environ.get("DACODE_SEMANTIC_TIMEOUT", "20"))
        self._runner = runner or self._run_pipeline

    @property
    def detail(self) -> str:
        return f"script={self.script}"

    def available(self) -> bool:
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
        if not query or not query.strip() or not self.available():
            return []
        try:
            raw = self._runner(query, top)
            data = json.loads(raw or "[]")
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
            print(f"[hermes] unavailable: {exc}", file=sys.stderr)
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


SemanticIndex = HermesIndexBackend
