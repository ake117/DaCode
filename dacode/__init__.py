"""DaCode — The Ultimate Autonomous Engineering Rig.

A 5-layer coding-agent rig that combines:

  1. Semantic Vault Memory   (dacode.memory)     — retrieve lessons, ingest new ones
  2. Harness² Optimizer      (dacode.harness)    — Propose-Probe-Compose recursion
  3. Executor                (dacode.executor)   — Pi coding agent / script / stub
  4. pstack Discipline       (dacode.discipline) — adversarial critic + real checks
  5. Isolated Git Sandbox    (dacode.sandbox)    — per-task worktree + checkpoints

The entry point is :class:`dacode.orchestrator.DaCodeRig`.
"""

from __future__ import annotations

__version__ = "0.5.2"

__all__ = ["__version__"]
