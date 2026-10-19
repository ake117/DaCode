"""LLM client protocol shared by every backend."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(RuntimeError):
    """Raised when a backend cannot produce a completion."""


@runtime_checkable
class LLMClient(Protocol):
    """Minimal contract every LLM backend must satisfy."""

    @property
    def name(self) -> str:
        """Human-readable identifier, e.g. ``stub`` or ``model@host``."""
        ...

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Return the model's text answer for ``user`` under ``system``."""
        ...
