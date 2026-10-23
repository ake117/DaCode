"""Embedding client for any OpenAI-compatible ``/v1/embeddings`` endpoint.

DaCode should not care *who* produces vectors: Ollama, llama.cpp, vLLM,
LM Studio, OpenAI, Mistral and friends all speak this shape, and a local
server means no API key and no network. Configuration is env-only so a public
clone works without editing code:

* ``DACODE_EMBED_BASE_URL`` — e.g. ``http://127.0.0.1:11434/v1`` (Ollama)
* ``DACODE_EMBED_MODEL``    — e.g. ``bge-m3``, ``nomic-embed-text``,
  ``text-embedding-3-small``
* ``DACODE_EMBED_API_KEY``  — optional; falls back to ``OPENAI_API_KEY``
* ``DACODE_EMBED_TIMEOUT``  — seconds per request (default 60)
* ``DACODE_EMBED_BATCH``    — texts per request (default 16)
* ``DACODE_EMBED_DIMS``     — request a specific vector length (``dimensions``
  in the OpenAI payload). Gemini's ``gemini-embedding-2`` defaults to 3072 and
  truncates to 768/1536 on request; OpenAI's ``text-embedding-3-*`` does the
  same. Leave unset to accept the provider default.

``configured`` is False until a base URL and a model are present, which is how
the memory layer decides to fall back to keyword retrieval.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

__all__ = ["Embedder", "EmbedError"]


class EmbedError(RuntimeError):
    """Raised when the embedding endpoint rejects a request."""


class Embedder:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        *,
        timeout: float | None = None,
        batch: int | None = None,
        dims: int | None = None,
        transport=None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("DACODE_EMBED_BASE_URL") or "").rstrip("/")
        self.model = model or os.environ.get("DACODE_EMBED_MODEL") or ""
        self.api_key = (
            api_key
            or os.environ.get("DACODE_EMBED_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or ""
        )
        self.timeout = float(timeout or os.environ.get("DACODE_EMBED_TIMEOUT", "60"))
        self.batch = max(1, int(batch or os.environ.get("DACODE_EMBED_BATCH", "16")))
        raw_dims = dims if dims is not None else os.environ.get("DACODE_EMBED_DIMS")
        self.dims = int(raw_dims) if raw_dims else None
        self._transport = transport or self._post

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model)

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise EmbedError(f"{self.base_url}: {exc}") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` in batches; returns one vector per input, in order."""
        if not self.configured:
            raise EmbedError("no embedding endpoint configured (DACODE_EMBED_BASE_URL/MODEL)")
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch):
            chunk = texts[start : start + self.batch]
            payload = {"model": self.model, "input": chunk}
            if self.dims:
                payload["dimensions"] = self.dims  # provider truncates (MRL)
            data = self._transport(payload)
            rows = data.get("data") if isinstance(data, dict) else None
            if not isinstance(rows, list) or len(rows) != len(chunk):
                raise EmbedError(f"endpoint returned {len(rows) if isinstance(rows, list) else 'no'} vectors for {len(chunk)} inputs")
            for row in rows:
                vector = row.get("embedding") if isinstance(row, dict) else None
                if not isinstance(vector, list) or not vector:
                    raise EmbedError("endpoint returned an empty embedding")
                if self.dims and len(vector) != self.dims:
                    raise EmbedError(
                        f"endpoint ignored dimensions={self.dims} and returned {len(vector)}"
                    )
                vectors.append([float(value) for value in vector])
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
