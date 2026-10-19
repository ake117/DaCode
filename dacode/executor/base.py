"""Executor protocol and the shared result type."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # avoid a runtime import cycle
    from dacode.harness.models import HarnessVariant


@dataclass
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    command: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@runtime_checkable
class Executor(Protocol):
    """Runs one harness variant inside a workspace and reports the outcome."""

    def run(self, variant: "HarnessVariant", workspace: str | Path) -> ExecResult:
        ...
