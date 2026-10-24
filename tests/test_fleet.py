"""Fleet diversity: a round probes different model families, not clones.

If every variant runs on the same model, a spec that only that model's habits
satisfy looks "solved" while the harness never learned anything. Assigning a
fleet spreads a round across families; escalation then prefers a family that has
not failed yet instead of repeating the one that just did.
"""

from __future__ import annotations

import json
from pathlib import Path

from dacode import runlog
from dacode.discipline.critic import PstackCritic
from dacode.executor.base import ExecResult
from dacode.executor.pi import PiExecutor
from dacode.harness.models import HarnessVariant
from dacode.harness.optimizer import HarnessOptimizer, _family
from dacode.llm import StubLLM
from dacode.sandbox import GitSandbox

PROPOSE_JSON = json.dumps({
    "variants": [
        {"label": "a", "system_prompt": "one"},
        {"label": "b", "system_prompt": "two"},
    ]
})

FLEET = ["deepseek/deepseek-v4.1-flash", "anthropic/claude-sonnet-4"]


class _FailingExecutor:
    model = "deepseek/deepseek-v4.1-flash"

    def __init__(self):
        self.models_seen: list[str | None] = []

    def run(self, variant, workspace):
        self.models_seen.append(variant.model)
        return ExecResult(exit_code=1, stdout="", stderr="boom", command="fake")


class _Judge:
    """Triage always escalates; compose declines to pick."""

    def __init__(self):
        self.triage_calls = []

    def choice(self, *, state, instructions, criteria, min_confidence=0.5):
        if "new_proposal" in criteria:
            self.triage_calls.append(dict(criteria))
            return "escalate_model", 0.9
        return None, 0.0


def _make(tmp_path: Path, *, fleet=None, judge=None) -> HarnessOptimizer:
    return HarnessOptimizer(
        llm=StubLLM(responses={"Propose 2 variants": PROPOSE_JSON}, default=""),
        sandbox=GitSandbox(tmp_path),
        executor=_FailingExecutor(),
        critic=PstackCritic(),
        judge=judge,
        budget=2,
        variants_per_round=2,
        fleet=fleet,
    )


def test_family_groups_names_by_provider():
    assert _family("anthropic/claude-sonnet-4") == "anthropic"
    assert _family("claude-sonnet-4") == "claude"
    assert _family("deepseek/deepseek-v4.1-flash") == "deepseek"


def test_a_round_gets_one_model_per_variant(tmp_path):
    opt = _make(tmp_path, fleet=FLEET)
    variants = [HarnessVariant(label="a"), HarnessVariant(label="b")]
    opt._assign_fleet(variants, round_no=1)
    assert [v.model for v in variants] == FLEET


def test_the_second_round_rotates_the_fleet(tmp_path):
    opt = _make(tmp_path, fleet=FLEET)
    variants = [HarnessVariant(label="a"), HarnessVariant(label="b")]
    opt._assign_fleet(variants, round_no=2)
    assert [v.model for v in variants] == [FLEET[1], FLEET[0]]


def test_rotation_keeps_every_round_balanced(tmp_path):
    opt = _make(tmp_path, fleet=FLEET)
    seen = []
    for round_no in (1, 2):
        variants = [HarnessVariant(label="a"), HarnessVariant(label="b")]
        opt._assign_fleet(variants, round_no=round_no)
        seen.append([v.model for v in variants])
    assert seen == [[FLEET[0], FLEET[1]], [FLEET[1], FLEET[0]]]


def test_an_explicit_variant_model_is_never_overwritten(tmp_path):
    opt = _make(tmp_path, fleet=FLEET)
    variant = HarnessVariant(label="a", model="openai/gpt-5")
    opt._assign_fleet([variant], round_no=1)
    assert variant.model == "openai/gpt-5"


def test_no_fleet_leaves_the_executor_default(tmp_path):
    opt = _make(tmp_path, fleet=None)
    variants = [HarnessVariant(label="a"), HarnessVariant(label="b")]
    opt._assign_fleet(variants, round_no=1)
    assert [v.model for v in variants] == [None, None]


def test_the_variant_model_reaches_the_pi_command(tmp_path):
    executor = PiExecutor(model="deepseek/deepseek-v4.1-flash", provider="openrouter")
    variant = HarnessVariant(model="anthropic/claude-sonnet-4")
    cmd = executor.build_command(variant, "do the thing")
    assert cmd[cmd.index("--model") + 1] == "anthropic/claude-sonnet-4"


def test_without_a_variant_model_the_executor_default_is_used():
    executor = PiExecutor(model="deepseek/deepseek-v4.1-flash", provider="openrouter")
    cmd = executor.build_command(HarnessVariant(), "task")
    assert cmd[cmd.index("--model") + 1] == "deepseek/deepseek-v4.1-flash"


def test_next_fleet_model_prefers_an_untried_family(tmp_path):
    opt = _make(tmp_path, fleet=FLEET)
    opt._used_models = {"deepseek/deepseek-v4.1-flash"}
    assert opt.next_fleet_model() == "anthropic/claude-sonnet-4"


def test_next_fleet_model_falls_back_when_every_family_was_tried(tmp_path):
    opt = _make(tmp_path, fleet=FLEET)
    opt._used_models = set(FLEET)
    assert opt.next_fleet_model() == FLEET[0]


def test_escalation_switches_to_an_untried_family(rig_repo, tmp_path, monkeypatch):
    log = tmp_path / "runlog.jsonl"
    monkeypatch.setenv("DACODE_RUNLOG", str(log))
    judge = _Judge()
    opt = _make(rig_repo, fleet=FLEET, judge=judge)

    opt.run("implement calc.add")

    # round 1 probed both families, so escalation must fall back to a fleet member
    assert opt._used_models == set(FLEET)
    assert judge.triage_calls, "triage should have been asked after a failed round"
    # a fleet makes escalation possible even without a legacy ladder
    assert "escalate_model" in judge.triage_calls[0]
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    run_event = [e for e in events if e.get("type") == "run"][0]
    assert sorted(run_event["models"]) == sorted(FLEET)


def test_probe_events_record_the_model_used_per_variant(rig_repo, tmp_path, monkeypatch):
    log = tmp_path / "runlog.jsonl"
    monkeypatch.setenv("DACODE_RUNLOG", str(log))
    opt = _make(rig_repo, fleet=FLEET)
    variants = [HarnessVariant(label="a", model=FLEET[0]), HarnessVariant(label="b", model=FLEET[1])]
    opt.probe_round("task", variants, round_no=1)

    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    models = [e.get("model") for e in events if e.get("type") == "probe"]
    assert sorted(models) == sorted(FLEET)
