"""Pluggable memory backends.

DaCode owns its memory by default (``local``: embeddings in its own SQLite
store). Other agents' memories are adapters — ``hermes`` ships in-tree as one
example, and any third party can add their own without touching this file:

* ``DACODE_SEMANTIC_BACKEND=local``    (default via ``auto``)
* ``DACODE_SEMANTIC_BACKEND=hermes``   (opt-in adapter for Hermes' index)
* ``DACODE_SEMANTIC_BACKEND=off``      (keyword retrieval only)
* ``DACODE_SEMANTIC_BACKEND=pkg.mod:make_backend`` — your own factory,
  called with the vault path, returning an object with ``available()`` and
  ``search(query, top=8) -> list[SemanticHit]``.

``auto`` tries the in-tree backends in :data:`AUTO_ORDER` and takes the first
one that reports itself available, so a public clone works with zero config
(keyword), gets semantic recall as soon as an embedder is configured, and
never depends on another agent being installed.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

__all__ = [
    "AUTO_ORDER",
    "REGISTRY",
    "SemanticBackend",
    "SemanticHit",
    "available",
    "register",
    "resolve",
    "status",
]


@dataclass(frozen=True)
class SemanticHit:
    """One retrieval hit from a semantic backend."""

    rel_path: str
    title: str
    similarity: float
    excerpt: str


@runtime_checkable
class SemanticBackend(Protocol):
    name: str

    def available(self) -> bool: ...

    def search(self, query: str, top: int = 8) -> list[SemanticHit]: ...


REGISTRY: dict[str, Callable[..., SemanticBackend]] = {}
AUTO_ORDER: tuple[str, ...] = ("local", "hermes")


def register(name: str, factory: Callable[..., SemanticBackend]) -> None:
    """Register a backend factory (called with the vault path)."""
    REGISTRY[name] = factory


def _load_builtin() -> None:
    if "local" in REGISTRY and "hermes" in REGISTRY:
        return
    from dacode.memory.backends.hermes import HermesIndexBackend
    from dacode.memory.backends.local import LocalStoreBackend

    register("local", LocalStoreBackend)
    register("hermes", HermesIndexBackend)


def resolve(spec: str | None, vault: Path | str | None) -> SemanticBackend | None:
    """Resolve ``spec`` to a usable backend, or ``None`` (keyword only)."""
    _load_builtin()
    name = (spec or "auto").strip()
    lowered = name.lower()
    if lowered in {"off", "0", "false", "no", "none"}:
        return None
    if lowered == "auto":
        for candidate in AUTO_ORDER:
            factory = REGISTRY.get(candidate)
            if factory is None:
                continue
            try:
                backend = factory(vault)
                if backend.available():
                    return backend
            except Exception:  # noqa: BLE001 - a broken backend must not break retrieval
                continue
        return None
    if ":" in name:  # third-party escape hatch: module:factory
        module_name, _, attr = name.partition(":")
        factory = getattr(importlib.import_module(module_name), attr)
        backend = factory(vault)
        return backend if backend.available() else None
    factory = REGISTRY.get(lowered)
    if factory is None:
        raise ValueError(f"unknown memory backend {name!r}; known: {sorted(REGISTRY)}")
    backend = factory(vault)
    return backend if backend.available() else None


def status(vault: Path | str | None) -> list[dict]:
    """Availability report for every in-tree backend (for the CLI)."""
    _load_builtin()
    report = []
    for name in sorted(REGISTRY):
        try:
            backend = REGISTRY[name](vault)
            report.append(
                {
                    "name": name,
                    "available": bool(backend.available()),
                    "detail": getattr(backend, "detail", "") or "",
                }
            )
        except Exception as exc:  # noqa: BLE001 - report, never raise
            report.append({"name": name, "available": False, "detail": str(exc)})
    return report


def available(vault: Path | str | None = None) -> bool:
    """True when some semantic backend can serve ``vault``."""
    return resolve("auto", vault) is not None
