"""Tests for the pstack discipline layer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from dacode.discipline import PstackCritic, check_python_test
from dacode.discipline.critic import _parse_test_summary


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_flags_a_test_with_no_assertion(tmp_path):
    path = _write(tmp_path, "test_x.py", "def test_a():\n    value = compute()\n")
    checks = {f.check for f in check_python_test(path)}
    assert "assertion_free" in checks


def test_flags_bare_truthiness_assertion(tmp_path):
    path = _write(tmp_path, "test_y.py", "def test_a():\n    items = [1]\n    assert items\n")
    checks = {f.check for f in check_python_test(path)}
    assert "weak_truthiness" in checks


def test_flags_self_referential_assertion(tmp_path):
    path = _write(tmp_path, "test_z.py", "def test_a():\n    assert f(1) == f(1)\n")
    checks = {f.check for f in check_python_test(path)}
    assert "tautology" in checks


def test_accepts_a_literal_behaviour_assertion(tmp_path):
    path = _write(tmp_path, "test_ok.py", "def test_a():\n    assert add(2, 2) == 4\n")
    assert check_python_test(path) == []


def test_accepts_pytest_raises_as_an_assertion(tmp_path):
    """`with pytest.raises(...):` asserts behaviour without an `assert` statement.

    Regression: the rig's own suite (test_sandbox.py, test_llm.py) was flagged
    `assertion_free`, so every probe of the rig against itself failed the
    critic despite a green test run.
    """
    body = (
        "import pytest\n"
        "def test_a():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError\n"
    )
    path = _write(tmp_path, "test_raises.py", body)
    assert check_python_test(path) == []


def test_critic_passes_a_clean_workspace(tmp_path):
    _write(tmp_path, "test_ok.py", "def test_add():\n    assert 1 + 1 == 2\n")
    report = PstackCritic().review_workspace(tmp_path)
    assert report.passed is True
    assert report.tests_total == 1
    assert report.tests_passed == 1
    assert report.score == 1.0


def test_critic_fails_when_no_tests_are_collected(tmp_path):
    report = PstackCritic().review_workspace(tmp_path)
    assert report.passed is False
    assert "no_tests" in {f.check for f in report.findings}


def test_critic_survives_repo_addopts_minus_q(tmp_path):
    """A repo pyproject with ``addopts = "-q"`` must not blank the summary.

    Regression: the critic's own ``-q`` compounded with the repo's ``-q``
    into ``-qq``, pytest printed dots only, ``_parse_test_summary`` counted
    0/0 and a fully passing suite was judged "no tests collected".
    """
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "-q"\n',
        encoding="utf-8",
    )
    _write(tmp_path, "test_ok.py", "def test_add():\n    assert 1 + 1 == 2\n")
    report = PstackCritic().review_workspace(tmp_path)
    assert report.tests_total == 1
    assert report.tests_passed == 1
    assert report.passed is True


def test_critic_fails_when_a_weak_test_is_present(tmp_path):
    _write(tmp_path, "test_weak.py", "def test_a():\n    assert True\n")
    report = PstackCritic().review_workspace(tmp_path)
    assert report.passed is False
    assert report.errors, "a weak assertion must register as an error-level finding"


# --- generalized test-summary parsing (non-pytest suites) -------------------


@pytest.mark.parametrize(
    ("stdout", "expected"),
    [
        ("3 passed, 1 failed in 0.2s", (4, 1)),
        ("2 passed in 0.15s", (2, 0)),
        ("90 checks, 0 failed", (90, 0)),
        ("OK: 66 checks passed (headless)", (66, 0)),
        ("==== 5 passed, 2 failed in 1.0s ====", (7, 2)),
        ("1 error in 0.1s", (1, 1)),
        ("nothing to see here", (0, 0)),
    ],
)
def test_parse_test_summary_understands_common_runners(stdout, expected):
    assert _parse_test_summary(stdout) == expected


def test_static_scan_ignores_non_python_test_files(tmp_path):
    """A .c file matched by the glob must not be fed to the Python AST parser."""
    _write(tmp_path, "test_native.c", "int main(void) { return 0; }\n")
    report = PstackCritic(test_glob="test_*.c").review_workspace(tmp_path)
    assert "syntax_error" not in {f.check for f in report.findings}


def test_critic_runs_a_custom_non_pytest_command(tmp_path):
    """A custom runner printing 'N checks, M failed' is counted and passes."""
    report = PstackCritic(
        test_command=("bash", "-c", "echo '12 checks, 0 failed'"),
    ).review_workspace(tmp_path)
    assert report.tests_total == 12
    assert report.tests_failed == 0
    assert report.passed is True
    assert report.exit_code == 0


def test_critic_fails_when_custom_command_reports_failures(tmp_path):
    report = PstackCritic(
        test_command=("bash", "-c", "echo '12 checks, 3 failed'; exit 1"),
    ).review_workspace(tmp_path)
    assert report.tests_total == 12
    assert report.tests_failed == 3
    assert report.passed is False


def _git_workspace(tmp_path):
    """A tiny git repo with one committed test file."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    _write(tmp_path, "test_ok.py", "def test_add():\n    assert 1 + 1 == 2\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    return tmp_path


def test_critic_rejects_a_trial_that_edits_a_test(tmp_path):
    from dacode.discipline.critic import PstackCritic

    workspace = _git_workspace(tmp_path)
    # the trial "fixes" the assertion instead of the code
    _write(workspace, "test_ok.py", "def test_add():\n    assert 1 + 1 == 3\n")

    report = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q")).review_workspace(workspace)

    checks = {f.check for f in report.findings}
    assert "tests_modified" in checks
    assert report.passed is False


def test_critic_allows_a_trial_that_only_edits_source(tmp_path):
    from dacode.discipline.critic import PstackCritic

    workspace = _git_workspace(tmp_path)
    _write(workspace, "add.py", "def add(a, b):\n    return a + b\n")

    report = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q")).review_workspace(workspace)
    assert "tests_modified" not in {f.check for f in report.findings}
    assert report.passed is True


def test_critic_ignores_a_non_git_workspace(tmp_path):
    from dacode.discipline.critic import PstackCritic

    _write(tmp_path, "test_ok.py", "def test_add():\n    assert 1 + 1 == 2\n")
    report = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q")).review_workspace(tmp_path)
    assert "tests_modified" not in {f.check for f in report.findings}
