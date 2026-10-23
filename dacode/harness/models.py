"""Data model for the Harness² loop."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

__all__ = ["HarnessVariant", "ProbeResult", "HarnessResult"]

_counter = itertools.count(1)


@dataclass
class HarnessVariant:
    """One candidate configuration of the *harness* (not the model)."""

    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    memory_snippets: list[str] = field(default_factory=list)
    parent_id: str | None = None
    label: str = ""
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"v{next(_counter)}")

    # filled in after probing
    score: float | None = None
    probe: "ProbeResult | None" = None

    def seed_context(self) -> str:
        """The memory + task context injected into the executor prompt."""
        if not self.memory_snippets:
            return ""
        joined = "\n".join(f"- {s}" for s in self.memory_snippets)
        return f"Relevant prior lessons:\n{joined}"


@dataclass
class ProbeResult:
    """What happened when a variant ran in its sandbox trial."""

    variant_id: str
    workspace: str
    exit_code: int = 0
    tests_total: int = 0
    tests_passed: int = 0
    critique_passed: bool = False
    critique_score: float = 0.0
    stdout: str = ""
    stderr: str = ""

    def as_dict(self) -> dict:
        return {
            "variant_id": self.variant_id,
            "workspace": self.workspace,
            "exit_code": self.exit_code,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "critique_passed": self.critique_passed,
            "critique_score": self.critique_score,
        }


@dataclass
class HarnessResult:
    """The outcome of a full ``HarnessOptimizer.run``."""

    task: str
    rounds: int
    best: HarnessVariant
    variants: list[HarnessVariant] = field(default_factory=list)
    passed: bool = False
    lesson_path: str | None = None
    needs_human_review: bool = False

    @property
    def best_score(self) -> float:
        return self.best.score or 0.0
