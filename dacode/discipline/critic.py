"""The pstack Critic — combines static checks with a real test run."""

from __future__ import annotations

import fnmatch
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
    tests_skipped: int = 0
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
        # The gate must own its output contract: a repo pyproject that sets
        # `addopts = "-q"` compounds with our own `-q` into `-qq` (verbosity −2),
        # which suppresses the `N passed` summary line _parse_test_summary needs —
        # a fully passing suite then reads as 0/0 collected ("no tests"). Clearing
        # ini addopts keeps the gate's summary deterministic regardless of repo
        # config; plugins still autoload, only addopts flags are cleared.
        self.test_command = tuple(test_command) if test_command else (sys.executable, "-m", "pytest", "-q", "-o", "addopts=")
        self.test_glob = test_glob
        self.timeout = timeout
        self.min_score = min_score

    def _scan_tests(self, workspace: Path) -> tuple[list[Finding], int]:
        findings: list[Finding] = []
        count = 0
        for path in sorted(workspace.rglob(self.test_glob)):
            if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
                continue
            # The static checks are AST-based and Python-only.  A non-Python
            # suite (C, JS, …) still gets the real test gate below, but must
            # not be fed to the Python parser.
            if path.suffix != ".py":
                continue
            found = check_python_test(path)
            count += 1
            findings.extend(found)
        return findings, count

    def measure_baseline(self, repo: Path) -> tuple[int, int] | None:
        """Count (total, skipped) on the untouched repo, once per run.

        A trial that deletes tests or silences them with skips keeps the suite
        green without proving anything; the baseline is what makes that visible.
        """
        try:
            exit_code, stdout, _stderr, total, _failed, skipped = self._run_tests(Path(repo))
        except Exception:  # noqa: BLE001 - a missing baseline must never block a run
            return None
        if total <= 0:
            return None
        return (total, skipped)

    def _run_tests(self, workspace: Path) -> tuple[int, str, str, int, int, int]:
        try:
            proc = subprocess.run(
                list(self.test_command),
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            return 127, "", f"test command not found: {exc}", 0, 0, 0
        except subprocess.TimeoutExpired as exc:
            return 124, exc.stdout or "", f"timed out after {self.timeout}s", 0, 0, 0
        total, failed, skipped = _parse_test_counts(proc.stdout)
        if total == 0 and proc.returncode == 0:
            # A green run with no summary usually means the project's own addopts
            # already contain -q ("-qq" prints nothing). Re-run with the project
            # addopts neutralised so the gate can count what actually ran.
            retried = self._neutralised_run(workspace)
            if retried is not None:
                return retried
        return proc.returncode, proc.stdout, proc.stderr, total, failed, skipped

    def _neutralised_run(self, workspace: Path) -> tuple[int, str, str, int, int, int] | None:
        """Re-run with ``-o addopts=`` so a quiet project config cannot look like 0 tests."""
        if not self.test_command:
            return None
        cmd = [*self.test_command, "-o", "addopts="]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        total, failed, skipped = _parse_test_counts(proc.stdout)
        if total == 0:
            return None
        return proc.returncode, proc.stdout, proc.stderr, total, failed, skipped

    def _check_test_integrity(self, workspace: Path) -> list[Finding]:
        """A trial may not edit, add or delete a test file.

        The gate's ground truth is the test suite it was handed. A trial that
        rewrites an assertion can turn a red gate green without changing
        behaviour — that is a false PASS, and it happened once (a trial changed
        ``approx(100.0)`` to ``approx(105.0)``). Only git workspaces can be
        checked; elsewhere this is a no-op.
        """
        try:
            proc = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=all"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        if proc.returncode != 0:
            return []  # not a git workspace in this trial

        findings: list[Finding] = []
        for line in proc.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip().strip('"')
            name = Path(path).name
            if fnmatch.fnmatch(name, self.test_glob):
                findings.append(
                    Finding(
                        check="tests_modified",
                        severity="error",
                        message=f"trial modified a test file ({path}) — the gate must judge unedited tests",
                        location=str(workspace / path),
                    )
                )
        return findings

    def review_workspace(
        self,
        workspace: str | Path,
        *,
        baseline: tuple[int, int] | None = None,
    ) -> CritiqueReport:
        workspace = Path(workspace)
        findings, _files = self._scan_tests(workspace)
        findings.extend(self._check_test_integrity(workspace))
        exit_code, stdout, stderr, total, failed, skipped = self._run_tests(workspace)

        if baseline is not None:
            base_total, base_skipped = baseline
            if total < base_total:
                findings.append(
                    Finding(
                        check="tests_lost",
                        severity="error",
                        message=(
                            f"the suite shrank: {total} test(s) now vs {base_total} at baseline "
                            "— deleting or disabling tests is not a fix"
                        ),
                        location=str(workspace),
                    )
                )
            if skipped > base_skipped:
                findings.append(
                    Finding(
                        check="tests_skipped",
                        severity="error",
                        message=(
                            f"{skipped} test(s) skipped vs {base_skipped} at baseline "
                            "— a skipped test proves nothing"
                        ),
                        location=str(workspace),
                    )
                )
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
            tests_skipped=skipped,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            score=round(score, 3),
            ran=True,
        )


def _parse_test_counts(stdout: str) -> tuple[int, int, int]:
    """``(total, failed, skipped)`` — see :func:`_parse_test_summary`."""
    import re

    total, failed = _parse_test_summary(stdout)
    skipped = 0
    match = re.search(r"(\d+)\s+skipped", stdout)
    if match:
        skipped = int(match.group(1))
    return total, failed, skipped


def _parse_test_summary(stdout: str) -> tuple[int, int]:
    """Extract ``(total, failed)`` from a test run's stdout.

    Understands pytest's summary line *and* the common custom-runner shapes, so
    a non-Python suite (Makefile/C, JS, …) is counted correctly too::

        "3 passed, 1 failed in 0.2s"        pytest
        "2 passed in 0.15s"                 pytest, all green
        "90 checks, 0 failed"               Makefile / C suite
        "OK: 66 checks passed (headless)"   Makefile / C suite

    Returns ``(0, 0)`` when nothing recognisable is found; the caller treats a
    zero total as "no tests were collected".
    """
    import re

    for line in reversed(stdout.splitlines()):
        stripped = line.strip().strip("=").strip()
        if not stripped:
            continue
        # "N checks, M failed"
        m = re.search(r"(\d+)\s+checks?\s*,\s*(\d+)\s+failed", stripped)
        if m:
            return int(m.group(1)), int(m.group(2))
        # "N checks passed" / "OK: N checks passed (headless)"
        m = re.search(r"(\d+)\s+checks?\s+passed", stripped)
        if m:
            return int(m.group(1)), 0
        # pytest: "3 passed, 1 failed in 0.2s"
        passed_m = re.search(r"(\d+)\s+passed", stripped)
        failed_m = re.search(r"(\d+)\s+failed", stripped)
        error_m = re.search(r"(\d+)\s+errors?", stripped)
        if passed_m or failed_m or error_m:
            total = 0
            failed = 0
            if passed_m:
                total += int(passed_m.group(1))
            if failed_m:
                total += int(failed_m.group(1))
                failed += int(failed_m.group(1))
            if error_m:
                total += int(error_m.group(1))
                failed += int(error_m.group(1))
            return total, failed
    return 0, 0


# Backwards-compatible alias — the old name was pytest-specific.
_parse_pytest_summary = _parse_test_summary
