"""Issue #5: ``unittest.subTest`` made the gate permanently red.

pytest folds every passing subtest into the declared ``tests=`` total without
emitting a ``<testcase>`` element for it (measured against pytest 9.1.1: a suite
declaring tests="11" yields 6 elements, while failures and skips still reconcile
exactly through ``<failure>``/``<skipped>`` children). A healthy subTest suite
therefore declared more tests than its report contained and the report was
rejected as tampered — tomli (declared 762, 18 elements) could never pass. The
gate now accepts that shape only when failures and skips still match exactly AND
the summary line the gate captured itself from the run's stdout accounts for the
declared total unit by unit; attribute-only rewrites keep failing both checks.
"""

import subprocess
import sys

from dacode.discipline.critic import PstackCritic, _junit_counts, _pytest_summary_units


def _git_baseline(path):
    for cmd in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "t@test.local"),
        ("git", "config", "user.name", "T"),
        ("git", "add", "-A"),
        ("git", "commit", "-qm", "baseline"),
    ):
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)


def test_a_healthy_subtest_suite_passes_the_gate(tmp_path):
    """tomli-shaped: 10 passing subtests + 1 skipped test declare tests="13"
    while pytest emits only 3 elements. That must be green, not a tamper verdict."""
    (tmp_path / "test_probe.py").write_text(
        "import unittest\n\n\n"
        "class TestUnits(unittest.TestCase):\n"
        "    def test_units(self):\n"
        "        for i in range(5):\n"
        "            with self.subTest(unit=i):\n"
        "                self.assertTrue(True)\n\n"
        "    def test_more_units(self):\n"
        "        for i in range(5):\n"
        "            with self.subTest(unit=i):\n"
        "                self.assertTrue(True)\n\n"
        "    def test_deferred(self):\n"
        "        unit = object()\n"
        "        assert unit is not None  # the static critic wants a real assertion\n"
        "        self.skipTest(\"later\")\n",
        encoding="utf-8",
    )
    _git_baseline(tmp_path)

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)

    assert report.passed is True
    assert report.tests_total == 3  # element reading: 2 subtest parents + 1 skip
    assert report.tests_skipped == 1


def test_failing_subtests_still_fail_the_gate_with_a_real_count(tmp_path):
    (tmp_path / "test_probe.py").write_text(
        "import unittest\n\n\n"
        "class TestUnits(unittest.TestCase):\n"
        "    def test_units(self):\n"
        "        for i in range(3):\n"
        "            with self.subTest(unit=i):\n"
        "                assert i != 1 and i != 2\n",
        encoding="utf-8",
    )
    _git_baseline(tmp_path)

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    # Declared failures count subtest units (2) while the report folds both into
    # one parent element's <failure> children, so the shaped exception — which
    # requires the failed counts to match exactly — declines. A red run's counts
    # then come from pytest's own summary line; the verdict is red either way.
    assert report.tests_failed == 2
    assert report.tests_total == 3


def test_an_attribute_rewrite_without_matching_units_stays_rejected(tmp_path):
    """The audited shape, now through the new door: an honest one-test run whose
    report's tests attribute was bumped at exit. The summary line says 1, the
    attribute says 999 — the subTest exception must not accept that."""
    (tmp_path / "test_probe.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "conftest.py").write_text(
        "import atexit\nimport pathlib\nimport sys\n\n\n"
        "def _rewrite():\n"
        "    for arg in sys.argv:\n"
        "        if arg.startswith(\"--junitxml=\"):\n"
        "            target = pathlib.Path(arg.split(\"=\", 1)[1])\n"
        "            if target.is_file():\n"
        "                text = target.read_text()\n"
        "                text = text.replace('tests=\"1\"', 'tests=\"999\"', 1)\n"
        "                target.write_text(text)\n\n\n"
        "atexit.register(_rewrite)\n",
        encoding="utf-8",
    )
    _git_baseline(tmp_path)

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    assert "counts_unavailable" in {f.check for f in report.findings}


def test_a_shaped_report_without_a_summary_line_is_rejected(tmp_path):
    """The corroboration is gate-captured stdout: silence cannot vouch for a
    declared total larger than the report's own test cases."""
    report = tmp_path / "report.xml"
    report.write_text(
        '<?xml version="1.0"?><testsuites><testsuite tests="13" failures="0" '
        'errors="0" skipped="1">'
        '<testcase name="test_units" classname="t"/>'
        '<testcase name="test_more_units" classname="t"/>'
        '<testcase name="test_deferred" classname="t"><skipped/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    assert _junit_counts(report, stdout="") is None
    assert _junit_counts(report, stdout="12 passed, 1 skipped in 0.1s") == (
        (3, 0, 1),
        True,
    )
    # a stdout that accounts for a different total does not corroborate either
    assert _junit_counts(report, stdout="999 passed in 0.1s") is None


def test_the_units_parser_reads_pytest_outcomes_not_warnings():
    assert _pytest_summary_units("3 passed in 0.2s") == 3
    assert _pytest_summary_units("2 failed, 5 passed, 2 skipped, 2 subtests passed in 0.11s") == 11
    assert _pytest_summary_units("1 failed, 1 error, 4 xfailed in 0.3s") == 6
    assert _pytest_summary_units("1 warning in 0.11s") is None
    assert _pytest_summary_units("no tests ran in 0.01s") is None
    assert _pytest_summary_units("") is None
