"""Layer 4 — pstack Discipline (adversarial critic + real checks).

Implements the blueprint's *Discipline & Critique* stage with automated,
runnable checks rather than vibes:

* **Test Behavior, Not Implementation** (pstack #4) — AST scan for tautological
  or weak assertions in Python tests.
* **Prove It Works** (pstack #9) — actually execute the test command and
  require a clean exit; a report without a run is not a report.
"""

from __future__ import annotations

from dacode.discipline.checks import Finding, check_python_test
from dacode.discipline.critic import CritiqueReport, PstackCritic

__all__ = ["Finding", "check_python_test", "CritiqueReport", "PstackCritic"]
