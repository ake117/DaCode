"""The pstack Critic — combines static checks with a real test run."""

from __future__ import annotations

import fnmatch
import subprocess
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dacode.discipline.checks import Finding, check_python_test
from dacode.sandbox.bwrap import (
    IsolationPolicy,
    IsolationUnavailable,
    interpreter_binds,
    wrap_command,
)

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
        isolation: IsolationPolicy | None = None,
        gate_infra: tuple[str, ...] | None = None,
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
        self.isolation = isolation
        # Files that decide what the gate sees and what it reports. A trial that
        # touches them can pass without doing the work (verified: a conftest that
        # prints a fake summary and calls os._exit(0)).
        self.gate_infra = tuple(gate_infra or DEFAULT_GATE_INFRA)

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

    def _wrap(self, cmd: list[str], workspace: Path) -> list[str]:
        """Run the gate under bwrap when isolation is on.

        A suite is model-written code too: it must not reach the network, the
        user's home, or anything outside its own worktree.
        """
        if self.isolation is None or not self.isolation.enabled:
            return cmd
        policy = self.isolation.with_paths(
            *interpreter_binds(self.test_command),
            os.environ.get("VIRTUAL_ENV"),
        )
        # Fail closed: an isolated run that silently fell back to the host would be
        # worse than a failed gate. The exception is re-raised as a failed probe by
        # _run_tests (exit 125) so the caller sees a verdict, not a traceback.
        return wrap_command(cmd, workspace=workspace, policy=policy)

    def _run_tests(self, workspace: Path) -> tuple[int, str, str, int, int, int]:
        try:
            proc = subprocess.run(
                self._wrap(list(self.test_command), workspace),
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except IsolationUnavailable as exc:
            return 125, "", f"isolation unavailable: {exc}", 0, 0, 0
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
                self._wrap(cmd, workspace),
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

    def _is_contract_path(self, relative: Path, *, test_dirs: set[str]) -> bool:
        """Is this path part of what decides the gate's answer?

        Basenames alone were not enough (verification audit, Oct 2026): a trial can
        add ``pytest/__init__.py`` to shadow the runner, or rewrite
        ``tests/helpers.py`` to make every assertion trivially true. So: gate-infra
        basenames, a shadowing path component, a conftest anywhere, and *any* file
        inside a directory that holds tests.
        """
        name = relative.name
        if name in self.gate_infra:
            return True
        if name.startswith("conftest") or name.startswith("test_") or name.startswith("_test"):
            return True
        if fnmatch.fnmatch(name, self.test_glob):
            return True
        if any(part in SHADOW_NAMES for part in relative.parts[:-1]):
            return True
        if name.endswith(".py") and str(relative.parent) in test_dirs:
            return True
        return False

    def _test_dirs(self, root: Path) -> set[str]:
        dirs: set[str] = set()
        for path in root.rglob("*"):
            if not path.is_file() or not fnmatch.fnmatch(path.name, self.test_glob):
                continue
            relative = path.parent.relative_to(root)
            # A dedicated test directory is contract; the repository root is not,
            # or every source file a trial writes there would look like a test
            # helper (it cannot be told apart from one by path alone).
            if str(relative) != ".":
                dirs.add(str(relative))
        return dirs

    def snapshot_contract(self, workspace: str | Path) -> dict[str, str]:
        """Hash the test files and gate infrastructure as they are *now*.

        Taken before the executor runs, on the untouched worktree. Comparing hashes
        afterwards is the only check a trial cannot reach around by committing: the
        git-status route compares against the worktree's own index, which the trial
        can move.
        """
        import hashlib

        root = Path(workspace)
        contract: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if ".git" in relative.parts:
                continue
            if not self._is_contract_path(relative, test_dirs=self._test_dirs(root)):
                continue
            try:
                contract[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
        return contract

    def _check_contract(
        self, workspace: Path, contract: dict[str, str]
    ) -> list[Finding]:
        """Compare the workspace against a snapshot taken before the trial ran."""
        import hashlib

        findings: list[Finding] = []
        current = self.snapshot_contract(workspace)
        test_dirs = self._test_dirs(workspace)

        def _check_for(relative: str) -> str:
            path = Path(relative)
            # a file inside a test directory, or a test module, is the suite itself
            if fnmatch.fnmatch(path.name, self.test_glob) or str(path.parent) in test_dirs:
                return "tests_modified"
            return "tests_infra_modified"

        for path, digest in contract.items():
            check = _check_for(path)
            if path not in current:
                findings.append(
                    Finding(
                        check=check,
                        severity="error",
                        message=f"trial removed {path} — the gate must judge the suite it was given",
                        location=str(workspace / path),
                    )
                )
            elif current[path] != digest:
                findings.append(
                    Finding(
                        check=check,
                        severity="error",
                        message=f"trial changed {path} — the gate must judge unedited tests",
                        location=str(workspace / path),
                    )
                )

        for path in sorted(set(current) - set(contract)):
            check = _check_for(path)
            findings.append(
                Finding(
                    check=check,
                    severity="error",
                    message=(
                        f"trial added {path} — a new test or config file changes what the gate "
                        "sees; a human must review it"
                    ),
                    location=str(workspace / path),
                )
            )
        return findings

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
            return [
                Finding(
                    check="integrity_unavailable",
                    severity="error",
                    message="could not read the worktree's git status — refusing to certify unedited tests",
                    location=str(workspace),
                )
            ]
        if proc.returncode != 0:
            if "not a git repository" in (proc.stderr or "").lower():
                return []  # standalone use on a plain directory: nothing to compare
            return [
                Finding(
                    check="integrity_unavailable",
                    severity="error",
                    message="git status failed in the worktree — refusing to certify unedited tests",
                    location=str(workspace),
                )
            ]

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
            elif name in self.gate_infra:
                findings.append(
                    Finding(
                        check="tests_infra_modified",
                        severity="error",
                        message=(
                            f"trial modified gate infrastructure ({path}) — a conftest or a "
                            "pytest config can silence or spoof the gate itself; a human must "
                            "review that change, not a trial"
                        ),
                        location=str(workspace / path),
                    )
                )
        return findings

    def review_workspace(
        self,
        workspace: str | Path,
        *,
        baseline: tuple[int, int] | None = None,
        contract: dict[str, str] | None = None,
    ) -> CritiqueReport:
        workspace = Path(workspace)
        findings, _files = self._scan_tests(workspace)
        if contract is not None:
            findings.extend(self._check_contract(workspace, contract))
        else:
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

        # `failed == 0` matters: counts come from the runner's stdout, so an exit
        # code of 0 is not enough on its own (see _check_test_integrity).
        passed = (
            exit_code == 0
            and total > 0
            and failed == 0
            and not [f for f in findings if f.severity == "error"]
        )
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


#: Path components that shadow or hook the runner when the workspace is `sys.path[0]`.
SHADOW_NAMES: tuple[str, ...] = ("pytest", "_pytest", "pluggy", "py", "sitecustomize", "usercustomize")

DEFAULT_GATE_INFRA: tuple[str, ...] = (
    "conftest.py",
    "pytest.ini",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    "setup.py",
    ".coveragerc",
    # modules that shadow or hook the runner inside the workspace
    "pytest.py",
    "_pytest.py",
    "sitecustomize.py",
    "usercustomize.py",
)


def _parse_test_counts(stdout: str) -> tuple[int, int, int]:
    """``(total, failed, skipped)`` — see :func:`_parse_test_summary`.

    The skip count must come from the *same* summary line as the pass/fail counts.
    Searching the whole stdout let a trial print ``0 skipped`` early and mask real
    skips (external audit, verified).
    """
    import re

    total, failed = _parse_test_summary(stdout)
    skipped = 0
    for line in reversed(stdout.splitlines()):
        stripped = line.strip().strip("=").strip()
        if not stripped:
            continue
        if re.search(r"\d+\s+(passed|failed|checks?\b)", stripped) or "skipped" in stripped:
            match = re.search(r"(\d+)\s+skipped", stripped)
            if match:
                skipped = int(match.group(1))
            break
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
