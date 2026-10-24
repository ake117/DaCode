"""P1 guards: the gate cannot be fooled by shrinking tests, and probes are timed.

A trial that deletes tests or silences them with skips used to keep the suite
green. The baseline makes that a failure. Timing/parallel probing are covered
here too so the ledger cannot regress silently.
"""

from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest

from dacode.discipline.critic import CritiqueReport, PstackCritic
from dacode.executor.base import ExecResult
from dacode.harness.models import HarnessVariant
from dacode.harness.optimizer import HarnessOptimizer

GREEN = "def test_a():\n    assert 1 + 1 == 2\n"


def _git_init(path: Path) -> None:
    """The integrity check compares against git; a bare dir is a no-op."""
    import subprocess

    for cmd in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "t@test.local"),
        ("git", "config", "user.name", "T"),
        ("git", "add", "-A"),
        ("git", "commit", "-qm", "baseline"),
    ):
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)


def _workspace(tmp_path: Path, *, tests: dict[str, str]) -> Path:
    for name, body in tests.items():
        (tmp_path / name).write_text(textwrap.dedent(body))
    return tmp_path


def test_deleting_a_test_file_is_caught_by_the_baseline(tmp_path):
    ws = _workspace(tmp_path, tests={"test_a.py": GREEN, "test_b.py": "def test_b():\n    assert True\n"})
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    assert critic.measure_baseline(ws) == (2, 0)

    (ws / "test_b.py").unlink()
    report = critic.review_workspace(ws, baseline=(2, 0))

    assert "tests_lost" in {f.check for f in report.findings}
    assert report.passed is False


def test_skipping_a_test_is_caught_by_the_baseline(tmp_path):
    ws = _workspace(tmp_path, tests={"test_a.py": GREEN})
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))

    (ws / "test_a.py").write_text("import pytest\n\n@pytest.mark.skip\ndef test_a():\n    assert 1 + 1 == 2\n")
    report = critic.review_workspace(ws, baseline=(1, 0))

    assert "tests_skipped" in {f.check for f in report.findings}
    assert report.passed is False


def test_baseline_does_not_block_a_clean_run(tmp_path):
    ws = _workspace(tmp_path, tests={"test_a.py": GREEN})
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(ws, baseline=(1, 0))
    assert report.passed is True
    assert report.tests_skipped == 0


def test_no_baseline_means_no_guard(tmp_path):
    ws = _workspace(tmp_path, tests={"test_a.py": GREEN})
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(ws, baseline=None)
    assert report.passed is True


# --- timing + parallel probing ---------------------------------------------

class _Sandbox:
    def __init__(self, root: Path):
        self.root = root
        self.created = 0

    def create(self, trial_id: str) -> Path:
        path = self.root / trial_id
        path.mkdir(parents=True, exist_ok=True)
        self.created += 1
        return path

    def checkpoint(self, *args, **kwargs):
        return None


class _SlowExecutor:
    model = "test-model"

    def __init__(self, delay: float):
        self.delay = delay

    def run(self, variant, workspace):
        time.sleep(self.delay)
        return ExecResult(exit_code=0, stdout="", stderr="", command="fake")


class _PassingCritic:
    def __init__(self):
        self.calls = []

    def review_workspace(self, workspace, baseline=None):
        self.calls.append((str(workspace), baseline))
        return CritiqueReport(passed=True, tests_total=4, tests_passed=4, score=1.0, ran=True)


def _optimizer(tmp_path: Path, *, delay: float, parallel: int) -> HarnessOptimizer:
    return HarnessOptimizer(
        llm=None,
        sandbox=_Sandbox(tmp_path / "wt"),
        executor=_SlowExecutor(delay),
        critic=_PassingCritic(),
        budget=1,
        variants_per_round=2,
        parallel=parallel,
        baseline=(4, 0),
    )


def test_probe_records_elapsed_time_and_the_baseline_reaches_the_critic(tmp_path):
    opt = _optimizer(tmp_path, delay=0.05, parallel=1)
    variants = [HarnessVariant(label="a"), HarnessVariant(label="b")]
    opt.probe_round("task", variants, round_no=1)

    for variant in variants:
        assert variant.probe.elapsed_s >= 0.05
        assert variant.probe.model == "test-model"
    critic_calls = opt.critic.calls
    assert all(baseline == (4, 0) for _ws, baseline in critic_calls)


def test_parallel_probing_is_faster_than_sequential(tmp_path):
    variants = [HarnessVariant(label="a"), HarnessVariant(label="b"), HarnessVariant(label="c")]

    seq = _optimizer(tmp_path / "seq", delay=0.2, parallel=1)
    started = time.perf_counter()
    seq.probe_round("task", [HarnessVariant(label=v.label) for v in variants], round_no=1)
    sequential = time.perf_counter() - started

    par = _optimizer(tmp_path / "par", delay=0.2, parallel=3)
    started = time.perf_counter()
    par.probe_round("task", [HarnessVariant(label=v.label) for v in variants], round_no=1)
    concurrent = time.perf_counter() - started

    assert sequential > 0.55
    assert concurrent < sequential * 0.75


def test_parallel_probing_still_records_every_variant(tmp_path):
    opt = _optimizer(tmp_path, delay=0.05, parallel=2)
    variants = [HarnessVariant(label="a"), HarnessVariant(label="b")]
    opt.probe_round("task", variants, round_no=1)
    assert [v.probe.critique_passed for v in variants] == [True, True]
    assert sorted(v.score for v in variants) == [1.0, 1.0]


def test_a_quiet_project_config_does_not_look_like_zero_tests(tmp_path):
    """`addopts = "-q"` plus our `-q` prints no summary; the gate must still count."""
    ws = _workspace(tmp_path, tests={"test_a.py": GREEN})
    (ws / "pytest.ini").write_text("[pytest]\naddopts = -q\n")
    critic = PstackCritic(
        test_command=(sys.executable, "-m", "pytest", "-q"),
        test_glob="test_*.py",
    )
    report = critic.review_workspace(ws)
    assert report.tests_total == 1
    assert report.tests_passed == 1
    assert report.passed is True


def test_a_conftest_that_spoofs_the_summary_and_exits_zero_is_rejected(tmp_path):
    """Found by an external audit: counts come from the runner's stdout."""
    ws = _workspace(tmp_path, tests={"test_bad.py": "def test_fails():\n    assert 1 == 2\n"})
    _git_init(ws)
    (ws / "conftest.py").write_text(
        "import atexit\nimport os\n\n\n"
        "def _spoof():\n"
        '    print("999 passed in 0.01s")\n'
        "    os._exit(0)\n\n\n"
        "atexit.register(_spoof)\n"
    )
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(ws)

    assert report.passed is False
    assert "tests_infra_modified" in {f.check for f in report.findings}


def test_a_failing_test_cannot_pass_on_exit_code_alone(tmp_path):
    ws = _workspace(tmp_path, tests={"test_bad.py": "def test_fails():\n    assert 1 == 2\n"})
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(ws)
    assert (report.tests_total, report.tests_failed) == (1, 1)
    assert report.passed is False


def test_gate_infrastructure_can_be_relaxed_explicitly(tmp_path):
    """A repo that must edit pyproject.toml can opt out of that one guard."""
    ws = _workspace(tmp_path, tests={"test_a.py": GREEN})
    (ws / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    critic = PstackCritic(
        test_command=(sys.executable, "-m", "pytest", "-q"),
        gate_infra=("conftest.py",),
    )
    report = critic.review_workspace(ws)
    assert "tests_infra_modified" not in {f.check for f in report.findings}
