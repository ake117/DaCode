"""SECURITY.md open item 1, enforced: stdout-only counts on a green run.

A printed summary is the suite grading its own homework — nothing verifies it.
For a Python suite that is never necessary (pytest can always emit the JUnit
report the gate attaches itself), so a green run whose counts were parsed from
the suite's own stdout is refused when the workspace has Python test files.
Non-Python suites (C/JS/PHPUnit) have no report to attach and keep the stdout
count — SECURITY.md keeps documenting that residual risk.
"""

import sys

from dacode.discipline.critic import PstackCritic


def test_a_python_suite_that_only_prints_its_counts_is_refused(tmp_path):
    """`make test` over a Python repo prints '3 passed'; nothing verified it."""
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(test_command=("/bin/echo", "3 passed, 0 failed in 0.1s"))

    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    assert "counts_from_stdout" in {f.check for f in report.findings}


def test_a_wrapper_that_hides_the_runner_is_refused_too(tmp_path):
    """A `bash -c` wrapper swallows the real runner and prints its own summary:
    the tokens do not name pytest, so the gate cannot attach a report — refused,
    with the fix named in the message."""
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(
        test_command=(
            "bash",
            "-c",
            f"{sys.executable} -m not_a_real_module 2>/dev/null; "
            "printf '3 passed, 0 failed in 0.1s\\n'; exit 0",
        )
    )

    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    assert "counts_from_stdout" in {f.check for f in report.findings}
    assert any("pytest" in f.message for f in report.findings)


def test_a_report_backed_python_run_still_passes(tmp_path):
    """Naming pytest lets the gate attach --junitxml: the normal path is intact."""
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))

    report = critic.review_workspace(tmp_path)

    assert report.passed is True
    assert "counts_from_stdout" not in {f.check for f in report.findings}
    assert (report.tests_total, report.tests_failed) == (1, 0)


def test_a_red_run_is_not_affected(tmp_path):
    """The guard targets green runs claiming counts; failures stay failures."""
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(
        test_command=("bash", "-c", "printf '1 passed, 1 failed in 0.1s\\n'; exit 1")
    )

    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    assert report.exit_code == 1
    assert "counts_from_stdout" not in {f.check for f in report.findings}


def test_a_non_python_suite_keeps_its_stdout_count(tmp_path):
    """C/JS/PHPUnit repos have no Python test files and no report to attach."""
    (tmp_path / "check.sh").write_text("echo done\n")
    critic = PstackCritic(test_command=("/bin/echo", "3 passed in 0.1s"))

    report = critic.review_workspace(tmp_path)

    assert report.passed is True
    assert "counts_from_stdout" not in {f.check for f in report.findings}


def test_a_stdlib_unittest_suite_is_exempt_the_refusal_targets_stdout_only(tmp_path):
    """unittest has no report to attach: its deterministic two-line stderr
    summary is the only count that exists, so the refusal must not fire on it
    (the guard is about *printed* summaries, not about reports)."""
    (tmp_path / "test_math.py").write_text(
        "import unittest\n"
        "\n"
        "class MathTest(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(1 + 1, 2)\n"
    )
    critic = PstackCritic(
        isolation=None,
        test_command=("bash", "-c", "python3 -m unittest test_math -v"),
    )
    report = critic.review_workspace(tmp_path)
    checks = [f.check for f in report.findings]
    assert "counts_from_stdout" not in checks
    assert report.passed
