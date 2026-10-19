"""Layer 2 — Harness² Optimizer (Propose–Probe–Compose recursion).

Mirrors the Google Research Harness² idea: instead of hand-tuning the prompt
when a task fails, the rig *proposes* several harness variants, *probes* each in
an isolated sandbox, and *composes* the winner — no ground-truth labels needed.
"""

from __future__ import annotations

from dacode.harness.models import HarnessResult, HarnessVariant, ProbeResult
from dacode.harness.optimizer import HarnessOptimizer

__all__ = ["HarnessOptimizer", "HarnessVariant", "ProbeResult", "HarnessResult"]
