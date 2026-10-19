"""The pstack Critic — combines static checks with a real test run."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dacode.discipline.checks import Finding, check_python_test

__all__ = ["CritiqueReport", "PstackCritic"]


@dataclass
class CritiqueReport:
    passed: bool
    findings: list[Finding] = field(default_factory=list)
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    score: float = 0.0
    ran: bool = False

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    def summary(self) -> str:
        if not self.ran:
            return "not run"
        bits = [f"tests {self.tests_passed}/{self.tests_total} pass"]
        if self.errors:
            bits.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            bits.append(f"{len(self.warnings)} warning(s)")
        return ", ".join(bits)


class PstackCritic:
    """Review a workspace against pstack principles.

    * static scan of every ``test_*.py`` for weak/tautological assertions
    * run the configured test command; a clean exit is required to pass
    """

    def __init__(
        self,
        *,
        test_command: tuple[str, ...] | list[str] | None = None,
        test_glob: str = "test_*.py",
        timeout: float = 300.0,
        min_score: float = 0.6,
    ) -> None:
        self.test_command = tuple(test_command) if test_command else (sys.executable, "-m", "pytest", "-q")
        self.test_glob = test_glob
        self.timeout = timeout
        self.min_score = min_score

    def _scan_tests(self, workspace: Path) -> tuple[list[Finding], int]:
        findings: list[Finding] = []
        count = 0
        for path in sorted(workspace.rglob(self.test_glob)):
            if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            found = check_python_test(path)
            count += 1
            findings.extend(found)
        return findings, count

    def _run_tests(self, workspace: Path) -> tuple[int, str, str, int, int]:
        try:
            proc = subprocess.run(
                list(self.test_command),
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            return 127, "", f"test command not found: {exc}", 0, 0
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", f"timed out after {self.timeout}s", 0, 0
        total, failed = _parse_pytest_summary(proc.stdout)
        return proc.returncode, proc.stdout, proc.stderr, total, failed

    def review_workspace(self, workspace: str | Path) -> CritiqueReport:
        workspace = Path(workspace)
        findings, _files = self._scan_tests(workspace)
        exit_code, stdout, stderr, total, failed = self._run_tests(workspace)
        passed_count = max(0, total - failed)

        # pstack #9 — a report without a run is not a report.
        if total == 0:
            findings.append(
                Finding(
                    check="no_tests",
                    severity="error",
                    message="no tests were collected — the change is unverified",
                    location=str(workspace),
                )
            )

        penalty = 0.25 * len([f for f in findings if f.severity == "error"])
        penalty += 0.05 * len([f for f in findings if f.severity == "warning"])
        if exit_code not in (0, None):
            penalty += 0.35
        score = max(0.0, min(1.0, 1.0 - penalty))

        passed = exit_code == 0 and total > 0 and not [f for f in findings if f.severity == "error"]
        passed = passed and score >= self.min_score

        return CritiqueReport(
            passed=passed,
            findings=findings,
            tests_total=total,
            tests_passed=passed_count,
            tests_failed=failed,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            score=round(score, 3),
            ran=True,
        )


def _parse_pytest_summary(stdout: str) -> tuple[int, int]:
    """Parse pytest's last summary line, e.g. '3 passed, 1 failed in 0.2s'."""
    import re

    total = 0
    failed = 0
    for line in reversed(stdout.splitlines()):
        stripped = line.strip().strip("=").strip()
        if "passed" in stripped or "failed" in stripped or "error" in stripped:
            passed_m = re.search(r"(\d+) passed", stripped)
            failed_m = re.search(r"(\d+) failed", stripped)
            error_m = re.search(r"(\d+) error", stripped)
            if passed_m:
                total += int(passed_m.group(1))
            if failed_m:
                total += int(failed_m.group(1))
                failed += int(failed_m.group(1))
            if error_m:
                total += int(error_m.group(1))
                failed += int(error_m.group(1))
            break
    return total, failed
