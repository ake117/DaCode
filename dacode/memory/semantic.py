"""Compatibility shim — the semantic layer is now a backend registry.

Kept so old imports keep working:

* :class:`SemanticHit`        — the hit dataclass (``dacode.memory.backends``)
* :class:`SemanticIndex`      — the Hermes adapter (``backends/hermes.py``)
* :func:`available`           — is any semantic backend usable right now?

New code should use :func:`dacode.memory.backends.resolve` /
:func:`dacode.memory.backends.status`.
"""

from __future__ import annotations

from dacode.memory.backends import SemanticHit, available as _available
from dacode.memory.backends.hermes import (
    DEFAULT_PYTHON,
    DEFAULT_SCRIPT,
    HermesIndexBackend,
    SemanticIndex,
)

__all__ = [
    "DEFAULT_PYTHON",
    "DEFAULT_SCRIPT",
    "HermesIndexBackend",
    "SemanticHit",
    "SemanticIndex",
    "available",
]


def available(vault=None) -> bool:
    """True when a semantic backend (local or an adapter) can serve the vault."""
    return _available(vault)
