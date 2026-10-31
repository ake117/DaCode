"""`dacode kanban work` — DaCode as a Kanban worker (README roadmap).

The worker takes one card from a Hermes Kanban board, claims it atomically,
reads the gate command from the card body, runs the card through the rig, and
reports back: ``complete`` with evidence when the gate passes, ``block`` with a
readable reason when it does not. Everything here is hermetic — the board is a
fake ``runner`` and the rig is a fake factory; no ``hermes`` binary, no model.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from dacode.config import DaCodeConfig
from dacode.harness.models import HarnessResult, HarnessVariant, ProbeResult
from dacode.kanban import (
    CardOutcome,
    HermesKanban,
    KanbanError,
    changed_files,
    make_rig_runner,
    parse_gate,
    work,
)

ZAI_SHAPED = "a1b2c3d4e5f60718293a4b5c6d7e8f90.QwXzAbCdEfGh1234"


# -- parse_gate ---------------------------------------------------------------


def test_parse_gate_reads_the_first_fenced_gate_block():
    body = (
        "Make the slug tests pass.\n\n"
        "```gate\n"
        "python3 -m pytest -q tests/test_slug.py\n"
        "```\n\n"
        "```gate\nsecond block is ignored\n```\n"
    )
    assert parse_gate(body) == "python3 -m pytest -q tests/test_slug.py"


def test_parse_gate_keeps_a_multi_line_command_intact():
    body = "```gate\ncd sub &&\n  make test\n```"
    assert parse_gate(body) == "cd sub &&\n  make test"


@pytest.mark.parametrize(
    "body",
    [
        "",
        "no gate here",
        "```bash\npython3 -m pytest\n```",  # a plain code block is not a gate
        "```gate\n   \n```",  # an empty gate is no gate
    ],
)
def test_parse_gate_returns_none_without_a_usable_gate(body):
    assert parse_gate(body) is None


def test_parse_gate_tolerates_none():
    assert parse_gate(None) is None


# -- HermesKanban (the subprocess adapter) ------------------------------------


class FakeBoard:
    """Records every argv and answers like `hermes kanban` would."""

    def __init__(self, task: dict | None = None, *, claim_rc: int = 0, complete_rc: int = 0):
        self.calls: list[list[str]] = []
        self.task = task or {"id": "t_1", "title": "card", "body": "", "status": "ready"}
        self.claim_rc = claim_rc
        self.complete_rc = complete_rc

    def __call__(self, argv: list[str]):
        self.calls.append(list(argv))
        sub = argv[argv.index("kanban") + 1:]
        if sub and sub[0] == "--board":
            sub = sub[2:]
        verb = sub[0]
        if verb == "show":
            out = json.dumps({"task": self.task, "comments": [], "runs": []})
            return SimpleNamespace(returncode=0, stdout=out, stderr="")
        if verb == "claim":
            if self.claim_rc:
                return SimpleNamespace(
                    returncode=self.claim_rc, stdout="",
                    stderr="cannot claim t_1: status=running lock=host:1",
                )
            return SimpleNamespace(returncode=0, stdout="Claimed t_1\n", stderr="")
        if verb == "complete":
            return SimpleNamespace(returncode=self.complete_rc, stdout="", stderr="claim lost")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def verbs(self) -> list[str]:
        out = []
        for argv in self.calls:
            sub = argv[argv.index("kanban") + 1:]
            if sub and sub[0] == "--board":
                sub = sub[2:]
            out.append(sub[0])
        return out

    def call(self, verb: str) -> list[str]:
        for argv, v in zip(self.calls, self.verbs()):
            if v == verb:
                return argv
        raise AssertionError(f"no {verb!r} call in {self.verbs()}")


def test_adapter_builds_argv_with_board_and_binary():
    fake = FakeBoard()
    board = HermesKanban("myboard", binary="/opt/hermes", runner=fake)
    board.show("t_1")
    assert fake.calls[0] == ["/opt/hermes", "kanban", "--board", "myboard", "show", "t_1", "--json"]


def test_adapter_reads_binary_and_board_from_env(monkeypatch):
    monkeypatch.setenv("DACODE_KANBAN_BIN", "/env/hermes")
    monkeypatch.setenv("DACODE_KANBAN_BOARD", "envboard")
    fake = FakeBoard()
    HermesKanban(runner=fake).show("t_1")
    assert fake.calls[0][:4] == ["/env/hermes", "kanban", "--board", "envboard"]


def test_adapter_omits_board_flag_when_unset(monkeypatch):
    monkeypatch.delenv("DACODE_KANBAN_BIN", raising=False)
    monkeypatch.delenv("DACODE_KANBAN_BOARD", raising=False)
    fake = FakeBoard()
    HermesKanban(runner=fake).show("t_1")
    assert fake.calls[0] == ["hermes", "kanban", "show", "t_1", "--json"]


def test_adapter_show_returns_the_task_dict():
    fake = FakeBoard({"id": "t_9", "title": "x", "body": "b", "status": "ready"})
    assert HermesKanban("b", runner=fake).show("t_9")["id"] == "t_9"


def test_adapter_claim_passes_ttl_and_reports_refusal():
    ok = FakeBoard()
    assert HermesKanban("b", runner=ok).claim("t_1", ttl=1234) is True
    assert ok.calls[0][-3:] == ["t_1", "--ttl", "1234"]
    refused = FakeBoard(claim_rc=1)
    assert HermesKanban("b", runner=refused).claim("t_1", ttl=60) is False


def test_adapter_complete_sends_result_and_json_metadata():
    fake = FakeBoard()
    HermesKanban("b", runner=fake).complete("t_1", "gate ok", {"changed_files": ["a.py"]})
    argv = fake.call("complete")
    assert argv[argv.index("--result") + 1] == "gate ok"
    assert json.loads(argv[argv.index("--metadata") + 1]) == {"changed_files": ["a.py"]}


def test_adapter_complete_raises_when_the_board_refuses():
    fake = FakeBoard(complete_rc=1)
    with pytest.raises(KanbanError):
        HermesKanban("b", runner=fake).complete("t_1", "r", {})


def test_adapter_block_puts_reason_last_and_kind_before_it():
    fake = FakeBoard()
    HermesKanban("b", runner=fake).block("t_1", "no gate", kind="needs_input")
    argv = fake.call("block")
    assert argv[-1] == "no gate"
    assert argv[argv.index("--kind") + 1] == "needs_input"
    plain = FakeBoard()
    HermesKanban("b", runner=plain).block("t_1", "gate failed")
    assert "--kind" not in plain.call("block")


def test_adapter_show_raises_on_unknown_card():
    def runner(argv):
        return SimpleNamespace(returncode=1, stdout="", stderr="no such task")

    with pytest.raises(KanbanError):
        HermesKanban("b", runner=runner).show("t_missing")


# -- work(): claim → gate → rig → complete | block -----------------------------


GATED = {
    "id": "t_1",
    "title": "slugify",
    "body": "Make tests/test_slug.py pass.\n\n```gate\npython3 -m pytest -q\n```",
    "status": "ready",
    "workspace_path": None,
}


def _outcome(**kw) -> CardOutcome:
    base = dict(
        passed=True, tests_passed=4, tests_total=4, worktree="/w/t", changed_files=["slug.py"],
        output_tail="4 passed", reason="",
    )
    base.update(kw)
    return CardOutcome(**base)


def test_work_refuses_a_card_someone_else_claimed():
    fake = FakeBoard(dict(GATED), claim_rc=1)
    calls = []
    rc = work("t_1", HermesKanban("b", runner=fake), lambda *a: calls.append(a))
    assert rc == 3
    assert calls == []  # the rig never ran
    assert "complete" not in fake.verbs() and "block" not in fake.verbs()


def test_work_claims_before_anything_else():
    fake = FakeBoard(dict(GATED))
    work("t_1", HermesKanban("b", runner=fake), lambda *a: _outcome())
    assert fake.verbs()[0] == "claim"


def test_work_blocks_a_card_without_a_gate_and_does_not_run():
    fake = FakeBoard({**GATED, "body": "just do it"})
    calls = []
    rc = work("t_1", HermesKanban("b", runner=fake), lambda *a: calls.append(a))
    assert rc == 2
    assert calls == []
    argv = fake.call("block")
    assert argv[argv.index("--kind") + 1] == "needs_input"
    assert "gate" in argv[-1]


def test_work_hands_title_body_gate_and_workspace_to_the_runner():
    fake = FakeBoard({**GATED, "workspace_path": "/some/repo"})
    seen = []

    def run_card(task, gate, workspace):
        seen.append((task, gate, workspace))
        return _outcome()

    work("t_1", HermesKanban("b", runner=fake), run_card)
    task, gate, workspace = seen[0]
    assert "slugify" in task and "Make tests/test_slug.py pass." in task
    assert gate == "python3 -m pytest -q"
    assert workspace == "/some/repo"


def test_work_completes_with_evidence_when_the_gate_passes():
    fake = FakeBoard(dict(GATED))
    rc = work("t_1", HermesKanban("b", runner=fake), lambda *a: _outcome())
    assert rc == 0
    argv = fake.call("complete")
    assert "4/4" in argv[argv.index("--result") + 1]
    meta = json.loads(argv[argv.index("--metadata") + 1])
    assert meta["changed_files"] == ["slug.py"]
    assert meta["tests_passed"] == 4 and meta["tests_total"] == 4
    assert meta["worktree"] == "/w/t"
    assert meta["gate"] == "python3 -m pytest -q"
    assert meta["gate_output"] == "4 passed"
    assert meta["runlog"]  # the run log path is part of the evidence
    assert "block" not in fake.verbs()


def test_work_blocks_with_a_readable_reason_when_the_gate_fails():
    fake = FakeBoard(dict(GATED))
    out = _outcome(passed=False, tests_passed=1, tests_total=4, reason="tests_modified")
    rc = work("t_1", HermesKanban("b", runner=fake), lambda *a: out)
    assert rc == 1
    reason = fake.call("block")[-1]
    assert "1/4" in reason and "tests_modified" in reason
    assert "complete" not in fake.verbs()


def test_work_blocks_when_the_rig_crashes():
    fake = FakeBoard(dict(GATED))

    def boom(*a):
        raise RuntimeError("--isolate bwrap requested but bubblewrap is not installed")

    rc = work("t_1", HermesKanban("b", runner=fake), boom)
    assert rc == 1
    assert "bubblewrap" in fake.call("block")[-1]


def test_work_reports_a_lost_claim_instead_of_claiming_success():
    fake = FakeBoard(dict(GATED), complete_rc=1)
    rc = work("t_1", HermesKanban("b", runner=fake), lambda *a: _outcome())
    assert rc == 4


def test_work_redacts_secrets_before_they_reach_the_board(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", ZAI_SHAPED)
    fake = FakeBoard(dict(GATED))
    out = _outcome(passed=False, tests_passed=0, tests_total=1,
                   reason=f"key={ZAI_SHAPED}", output_tail=f"leak {ZAI_SHAPED}")
    work("t_1", HermesKanban("b", runner=fake), lambda *a: out)
    assert ZAI_SHAPED not in json.dumps(fake.calls)


# -- changed_files + make_rig_runner (the real rig glue) -----------------------


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()


def test_changed_files_lists_what_the_trial_committed(git_repo: Path, tmp_path: Path):
    base = _git(git_repo, "rev-parse", "HEAD")
    wt = tmp_path / "trial"
    _git(git_repo, "worktree", "add", "-b", "dacode/trial/x", str(wt))
    (wt / "slug.py").write_text("def slugify(s):\n    return s\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "trial")
    assert changed_files(wt, base) == ["slug.py"]


def test_changed_files_is_empty_for_a_missing_workspace(tmp_path: Path):
    assert changed_files(tmp_path / "gone", "HEAD") == []


def _fake_rig_factory(record: list, workspace: str, passed: bool):
    class FakeRig:
        def __init__(self, cfg):
            record.append(cfg)

        def run_task(self, task):
            probe = ProbeResult(
                variant_id="v1", workspace=workspace, exit_code=0 if passed else 1,
                tests_total=2, tests_passed=2 if passed else 0, critique_passed=passed,
                stdout="== 2 passed in 0.01s ==\n",
            )
            best = HarnessVariant(label="seeded-base", probe=probe, score=1.5 if passed else 0.0)
            return HarnessResult(task=task, rounds=1, best=best, variants=[best], passed=passed)

    return FakeRig


def test_rig_runner_gates_on_the_card_command_and_uses_the_card_repo(git_repo: Path, tmp_path: Path):
    record: list = []
    cfg = DaCodeConfig(repo=tmp_path / "elsewhere")
    run_card = make_rig_runner(cfg, rig_factory=_fake_rig_factory(record, str(git_repo), True))
    out = run_card("task text", "python3 -m pytest -q", str(git_repo))
    used = record[0]
    assert used.test_command == ("bash", "-c", "python3 -m pytest -q")
    assert Path(used.repo).resolve() == git_repo.resolve()  # the card's git workspace wins
    assert used.isolate == "bwrap"
    assert out.passed is True
    assert (out.tests_passed, out.tests_total) == (2, 2)
    assert out.worktree == str(git_repo)
    assert "2 passed" in out.output_tail
    assert cfg.test_command is None  # the caller's config is not mutated


def test_rig_runner_falls_back_to_repo_when_the_card_workspace_is_not_git(git_repo: Path, tmp_path: Path):
    record: list = []
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    cfg = DaCodeConfig(repo=git_repo)
    run_card = make_rig_runner(cfg, rig_factory=_fake_rig_factory(record, str(git_repo), True))
    run_card("t", "true", str(scratch))
    assert Path(record[0].repo).resolve() == git_repo.resolve()


def test_rig_runner_explains_a_failure(git_repo: Path):
    record: list = []
    cfg = DaCodeConfig(repo=git_repo)
    run_card = make_rig_runner(cfg, rig_factory=_fake_rig_factory(record, str(git_repo), False))
    out = run_card("t", "true", None)
    assert out.passed is False
    assert out.reason  # never an empty block reason


def test_rig_runner_explains_a_run_that_probed_nothing(git_repo: Path):
    class EmptyRig:
        def __init__(self, cfg):
            pass

        def run_task(self, task):
            return HarnessResult(task=task, rounds=2, best=HarnessVariant(), passed=False)

    out = make_rig_runner(DaCodeConfig(repo=git_repo), rig_factory=EmptyRig)("t", "true", None)
    assert out.passed is False and out.worktree is None
    assert "2 round" in out.reason


def test_rig_runner_reports_the_gate_run_and_the_critic_errors(git_repo: Path):
    class TamperRig:
        def __init__(self, cfg):
            pass

        def run_task(self, task):
            probe = ProbeResult(
                variant_id="v1", workspace=str(git_repo), exit_code=0, tests_total=4,
                tests_passed=1, stdout="agent chatter", gate_output="== 3 failed, 1 passed ==",
                errors=["tests_modified", "tests_modified"],
            )
            best = HarnessVariant(probe=probe)
            return HarnessResult(task=task, rounds=1, best=best, variants=[best], passed=False)

    out = make_rig_runner(DaCodeConfig(repo=git_repo), rig_factory=TamperRig)("t", "true", None)
    assert "3 failed" in out.output_tail and "agent chatter" not in out.output_tail
    assert out.reason.count("tests_modified") == 1
