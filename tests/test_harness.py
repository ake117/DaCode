"""Tests for the Harness² optimizer (Propose → Probe → Compose)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dacode.discipline import PstackCritic
from dacode.executor.base import ExecResult
from dacode.harness import HarnessOptimizer, HarnessVariant
from dacode.llm import StubLLM
from dacode.sandbox import GitSandbox

PROPOSE_JSON = json.dumps(
    [
        {"label": "good", "system_prompt": "implement carefully"},
        {"label": "bad", "system_prompt": "do nothing"},
    ]
)


class FakeExecutor:
    """Writes the missing ``calc`` module only when the variant is 'good'."""

    def __init__(self, good_label: str = "good") -> None:
        self.good_label = good_label
        self.seen: list[str] = []

    def run(self, variant: HarnessVariant, workspace: str | Path) -> ExecResult:
        self.seen.append(variant.label)
        if variant.label == self.good_label:
            (Path(workspace) / "calc.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
            return ExecResult(exit_code=0, stdout="wrote calc.py")
        return ExecResult(exit_code=0, stdout="no-op")


def _make_optimizer(rig_repo: Path, executor: FakeExecutor, llm: StubLLM) -> HarnessOptimizer:
    return HarnessOptimizer(
        llm=llm,
        sandbox=GitSandbox(rig_repo),
        executor=executor,
        critic=PstackCritic(),
        budget=1,
        variants_per_round=2,
    )


def test_propose_returns_variants_from_llm_json(rig_repo):
    llm = StubLLM(responses={"Propose 2 variants": PROPOSE_JSON}, default="")
    opt = _make_optimizer(rig_repo, FakeExecutor(), llm)
    base = HarnessVariant(system_prompt="base", label="base")
    variants = opt.propose("implement calc.add", base, 2)
    assert [v.label for v in variants] == ["good", "bad"]
    assert all(v.parent_id == base.id for v in variants)


def test_propose_parses_json_inside_markdown_fences(rig_repo):
    fenced = "```json\n" + PROPOSE_JSON + "\n```"
    llm = StubLLM(responses={"Propose 2 variants": fenced}, default="")
    opt = _make_optimizer(rig_repo, FakeExecutor(), llm)
    variants = opt.propose("implement calc.add", HarnessVariant(label="base"), 2)
    assert [v.label for v in variants] == ["good", "bad"]


def test_propose_falls_back_when_llm_returns_garbage(rig_repo):
    llm = StubLLM(default="this is not json at all")
    opt = _make_optimizer(rig_repo, FakeExecutor(), llm)
    variants = opt.propose("t", HarnessVariant(label="base"), 2)
    assert len(variants) == 1
    assert variants[0].label == "fallback"


def test_probe_creates_its_own_worktree(rig_repo):
    llm = StubLLM(default="")
    opt = _make_optimizer(rig_repo, FakeExecutor("good"), llm)
    variant = HarnessVariant(label="good", payload={"task": "t"})
    probe = opt.probe(variant, "t", "trial-x")
    assert Path(probe.workspace).name == "trial-x"
    assert Path(probe.workspace) != rig_repo
    assert probe.tests_passed == 1
    assert probe.tests_total == 1
    assert probe.critique_passed is True


def test_probe_of_noop_variant_fails_the_gate(rig_repo):
    llm = StubLLM(default="")
    opt = _make_optimizer(rig_repo, FakeExecutor("good"), llm)
    variant = HarnessVariant(label="bad", payload={"task": "t"})
    probe = opt.probe(variant, "t", "trial-bad")
    assert probe.critique_passed is False
    assert variant.score == 0.0


def test_compose_falls_back_to_measured_ranking(rig_repo):
    llm = StubLLM(default="")  # compose reply empty → deterministic fallback
    opt = _make_optimizer(rig_repo, FakeExecutor(), llm)
    a = HarnessVariant(label="a")
    a.score = 0.2
    b = HarnessVariant(label="b")
    b.score = 0.9
    assert opt.compose("t", [a, b]) is b


def test_compose_honours_explicit_llm_choice(rig_repo):
    a = HarnessVariant(label="a")
    a.score = 0.2
    b = HarnessVariant(label="b")
    b.score = 0.9
    llm = StubLLM(responses={"Pick the best": json.dumps({"best_id": a.id})}, default="")
    opt = _make_optimizer(rig_repo, FakeExecutor(), llm)
    assert opt.compose("t", [a, b]) is a


def test_run_picks_the_variant_that_makes_tests_pass(rig_repo):
    llm = StubLLM(responses={"Propose 2 variants": PROPOSE_JSON}, default="")
    executor = FakeExecutor("good")
    opt = _make_optimizer(rig_repo, executor, llm)
    result = opt.run("implement calc.add")

    assert result.passed is True
    assert result.best.label == "good"
    assert result.best.probe.tests_passed == 1
    assert result.best.probe.tests_total == 1

    bad = next(v for v in result.variants if v.label == "bad")
    assert bad.probe.critique_passed is False
    # the loser's worktree was cleaned up, the winner's was kept
    assert not Path(bad.probe.workspace).exists()
    assert Path(result.best.probe.workspace).exists()


def test_gate_evidence_keeps_stderr_when_stdout_is_silent():
    # `python -m unittest` reports on stderr only, and a gate that timed out
    # (124) / was refused (125) / found no command (127) writes only there —
    # gate_output used to fall back to the executor's chatter in both cases.
    from types import SimpleNamespace

    from dacode.harness.optimizer import _gate_evidence

    assert _gate_evidence(
        SimpleNamespace(stdout="", stderr="Ran 4 tests in 0.1s\nOK")
    ) == "Ran 4 tests in 0.1s\nOK"
    assert _gate_evidence(SimpleNamespace(stdout="1 passed", stderr="")) == "1 passed"
    assert _gate_evidence(
        SimpleNamespace(stdout="counts line", stderr="isolation detail")
    ) == "counts line\nisolation detail"
    assert _gate_evidence(SimpleNamespace(stdout=None, stderr=None)) == ""
    assert len(_gate_evidence(SimpleNamespace(stdout="x" * 5000, stderr="y" * 3000))) == 4000


def test_default_prompt_matches_the_gates_tampering_rule():
    # The readiness audit (docs/design/reviews/2026-11-01, finding 15/2) found
    # the default prompt telling trials to "Write or update tests" while
    # PstackCritic._check_contract fails any trial that touches a test file —
    # the prompt invited trials into a guaranteed-fail loop. Pin the contract:
    # the prompt must forbid test-file modification.
    from dacode.harness.optimizer import DEFAULT_SYSTEM_PROMPT

    prompt = DEFAULT_SYSTEM_PROMPT.lower()
    assert "never" in prompt
    assert "test" in prompt
    assert "conftest" in prompt
    assert "fail" in prompt
    assert "write or update tests" not in prompt


def test_failure_digest_is_bounded_and_structured():
    from dacode.harness.models import ProbeResult

    opt = HarnessOptimizer(
        llm=StubLLM(), sandbox=GitSandbox(Path("/tmp/unused-digest-repo")),
        executor=FakeExecutor(), critic=PstackCritic(),
    )
    probe = ProbeResult(
        variant_id="v1", workspace="/tmp/x", exit_code=1,
        tests_total=5, tests_passed=2,
        gate_output="FAILED tests/test_calc.py::test_add",
        errors=["tests_modified", "assertion_free"],
    )
    variant = HarnessVariant(label="bad", system_prompt="p", probe=probe)
    digest = opt._failure_digest([variant])
    assert "tests 2/5" in digest
    assert "gate error: tests_modified" in digest
    assert "FAILED tests/test_calc.py" in digest
    assert "variant 'bad'" in digest
    # passing variants and unprobed ones contribute nothing
    ok = HarnessVariant(
        label="ok", system_prompt="p",
        probe=ProbeResult(variant_id="v2", workspace="/w", critique_passed=True),
    )
    assert opt._failure_digest([ok]) == ""
    # capped
    probe2 = ProbeResult(
        variant_id="v3", workspace="/w", gate_output="x" * 9000, errors=[],
    )
    assert len(opt._failure_digest([HarnessVariant(label="x", system_prompt="p", probe=probe2)])) <= 3000


def test_failed_round_feeds_evidence_into_next_proposal(rig_repo):
    # Round 1: both variants fail (executor is a no-op, no calc.py). Round 2's
    # proposal prompt must carry the gate evidence — blind retries were the
    # readiness audit's finding 18 (docs/design/reviews/2026-11-01).
    llm = StubLLM(default=PROPOSE_JSON)
    executor = FakeExecutor(good_label="never-good")  # every variant fails
    opt = HarnessOptimizer(
        llm=llm,
        sandbox=GitSandbox(rig_repo),
        executor=executor,
        critic=PstackCritic(),
        budget=2,
        variants_per_round=2,
    )
    opt.run("add a calc module", HarnessVariant(system_prompt=opt.base_prompt, label="base"))
    first_users = [user for _, user in llm.calls if "Propose" in user]
    assert len(first_users) >= 2
    assert "The previous round failed" not in first_users[0]
    assert any("The previous round failed" in u for u in first_users[1:])
    evidence_call = next(u for u in first_users[1:] if "The previous round failed" in u)
    # the no-op trial fails on counts (0/0), not error findings — the digest
    # still carries the numbers and the gate's own output tail
    assert "tests 0/" in evidence_call
    assert "evidence tail:" in evidence_call


def test_propose_schema_does_not_request_dead_fields():
    # Readiness audit finding 8 (docs/design/reviews/2026-11-01): the schema
    # asked the LLM for "tools" that no executor ever read — the field was
    # cut, and the proposal prompt must not ask for it again.
    from dacode.harness.optimizer import _PROPOSE_SYSTEM

    assert '"tools"' not in _PROPOSE_SYSTEM
