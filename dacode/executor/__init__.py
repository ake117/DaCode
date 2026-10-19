"""Layer 3 — Executors: the thing that actually changes code in a trial.

An executor receives a :class:`~dacode.harness.models.HarnessVariant` and a
workspace directory, does the work, and returns an :class:`ExecResult`.  The rig
does not care *how* the change happens — Pi, a raw script, or a test double all
satisfy the same protocol, which keeps the optimizer unit-testable.
"""

from __future__ import annotations

from dacode.executor.base import ExecResult, Executor
from dacode.executor.pi import PiExecutor
from dacode.executor.script import ScriptExecutor

__all__ = ["ExecResult", "Executor", "PiExecutor", "ScriptExecutor"]
