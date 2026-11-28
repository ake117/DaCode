"""Contract tests for SIM (Self-Improvement Memory) and CRSI in DaCode.

Verifies the core properties of arXiv 2611.18856 adapted to DaCode:
1. Optimizer memory is separate from policy memory (never injected into executor snippets).
2. Proposer records root_cause, rationale, and predicted_outcome BEFORE probing.
3. Both passing AND failing trials are recorded with observed_outcome and provenance
   (repo, model, round, task), merging repeated root causes without dropping history.
4. Both proposer and selector (compose) read the whole SIM block (no RAG), bounded cleanly.
5. Secrets are redacted before persistence, symlinks are refused, and files are mode 0600.
6. Cross-model / cross-run CRSI preserves history across model switches and runs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from dacode.config import DaCodeConfig
from dacode.discipline import PstackCritic
from dacode.executor.base import ExecResult
from dacode.harness import HarnessOptimizer, HarnessVariant
from dacode.llm import StubLLM
from dacode.memory.sim import SIMRecord, SIMStore
from dacode.orchestrator import DaCodeRig
from dacode.sandbox import GitSandbox


class _RecordingExecutor:
    """Captures the exact HarnessVariant each trial receives."""

    def __init__(self, good_label: str = "good") -> None:
        self.good_label = good_label
        self.seen_variants: list[HarnessVariant] = []

    def run(self, variant: HarnessVariant, workspace: str | Path) -> ExecResult:
        self.seen_variants.append(variant)
        if variant.label == self.good_label:
            (Path(workspace) / "calc.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
            return ExecResult(exit_code=0, stdout="wrote calc.py")
        return ExecResult(exit_code=0, stdout="no-op")


# -- SIMStore unit tests ---------------------------------------------------


def test_sim_store_merges_by_root_cause_and_keeps_both_pass_and_fail(tmp_path: Path):
    path = tmp_path / "sim.json"
    store = SIMStore(path)

    store.record(
        SIMRecord(
            root_cause="Early Completion",
            label="v1-naive",
            rationale="try brief prompt",
            predicted_outcome="pass all tests",
            observed_outcome="FAIL (tests 0/1, score=0.0)",
            passed=False,
            score=0.0,
            errors=["no_tests"],
            repo="demo",
            model="model-a",
            round_no=1,
            task="implement calc.add",
        )
    )
    store.record(
        SIMRecord(
            root_cause="  early completion  ",
            label="v2-verify",
            rationale="require running pytest before exit",
            predicted_outcome="all tests pass on first try",
            observed_outcome="PASS (tests 1/1, score=1.0)",
            passed=True,
            score=1.0,
            errors=[],
            repo="demo",
            model="model-b",
            round_no=2,
            task="implement calc.add",
        )
    )

    # Persisted cleanly and reloads identically
    reloaded = SIMStore(path)
    assert len(reloaded.groups) == 1
    group = next(iter(reloaded.groups.values()))
    assert len(group["edits"]) == 2
    assert group["edits"][0]["passed"] is False
    assert group["edits"][1]["passed"] is True
    assert group["edits"][0]["provenance"]["model"] == "model-a"
    assert group["edits"][1]["provenance"]["model"] == "model-b"

    rendered = reloaded.render()
    assert "Early Completion" in rendered
    assert "v1-naive" in rendered
    assert "v2-verify" in rendered
    assert "predicted" in rendered.lower()
    assert "observed" in rendered.lower()
    assert "model-a" in rendered and "model-b" in rendered


def test_sim_store_redacts_secrets_sets_0600_and_refuses_symlinks(tmp_path: Path, monkeypatch):
    secret = "dummy-value-for-OPENROUTER_API_KEY-0123456789"
    monkeypatch.setenv("OPENROUTER_API_KEY", secret)
    path = tmp_path / "nested" / "sim.json"
    store = SIMStore(path)
    store.record(
        SIMRecord(
            root_cause="auth",
            label="v1",
            rationale=f"use key {secret}",
            predicted_outcome="ok",
            observed_outcome=f"error with {secret}",
            passed=False,
            score=0.0,
            repo="demo",
            model="m",
            round_no=1,
            task="fix auth",
        )
    )

    raw = path.read_text(encoding="utf-8")
    assert secret not in raw
    assert (path.stat().st_mode & 0o777) == 0o600

    # Refusing symlinks prevents cross-project / host file overwrite
    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link-sim.json"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        SIMStore(link)


def test_sim_store_render_is_bounded_to_max_chars(tmp_path: Path):
    store = SIMStore(tmp_path / "sim.json")
    for i in range(40):
        store.record(
            SIMRecord(
                root_cause=f"cause-{i % 5}",
                label=f"variant-{i}",
                rationale="r" * 120,
                predicted_outcome="p" * 120,
                observed_outcome="o" * 120,
                passed=(i % 2 == 0),
                score=1.0 if i % 2 == 0 else 0.0,
                repo="demo",
                model="m",
                round_no=i + 1,
                task=f"task-{i}",
            )
        )
    rendered = store.render(max_chars=1200)
    assert len(rendered) <= 1200
    # Most recent edit survives truncation
    assert "variant-39" in rendered


# -- Optimizer integration tests -------------------------------------------


def test_propose_parses_sim_fields_and_feeds_sim_to_optimizer_only(rig_repo, tmp_path: Path):
    sim = SIMStore(tmp_path / "sim.json")
    sim.record(
        SIMRecord(
            root_cause="missing_module",
            label="seed-prior",
            rationale="create module before running tests",
            predicted_outcome="import succeeds",
            observed_outcome="PASS (tests 1/1, score=1.0)",
            passed=True,
            score=1.0,
            repo="repo",
            model="old-model",
            round_no=1,
            task="prior task",
        )
    )

    propose_reply = json.dumps(
        [
            {
                "label": "good",
                "system_prompt": "implement calc.add minimally",
                "root_cause": "missing_module",
                "rationale": "reuse verified create-then-test flow",
                "predicted_outcome": "calc.add passes 1/1 tests",
            },
            {
                "label": "bad",
                "system_prompt": "do nothing",
                "root_cause": "early_stop",
                "rationale": "control variant",
                "predicted_outcome": "fails import",
            },
        ]
    )
    llm = StubLLM(responses={"Propose 2 variants": propose_reply}, default="")
    executor = _RecordingExecutor("good")
    opt = HarnessOptimizer(
        llm=llm,
        sandbox=GitSandbox(rig_repo),
        executor=executor,
        critic=PstackCritic(),
        sim=sim,
        repo_name="repo",
        budget=1,
        variants_per_round=2,
    )

    result = opt.run("implement calc.add")
    assert result.passed is True

    # 1. Proposer parsed root_cause, rationale, predicted_outcome before probing
    good = next(v for v in result.variants if v.label == "good")
    assert good.root_cause == "missing_module"
    assert good.rationale == "reuse verified create-then-test flow"
    assert good.predicted_outcome == "calc.add passes 1/1 tests"

    # 2. Both proposer AND selector (compose) received the SIM block
    propose_calls = [user for _, user in llm.calls if "Propose 2 variants" in user]
    compose_calls = [user for _, user in llm.calls if "Pick the best" in user]
    assert propose_calls and "seed-prior" in propose_calls[0]
    assert compose_calls and "seed-prior" in compose_calls[0]

    # 3. Policy memory isolation: executor NEVER sees SIM inside memory_snippets
    assert executor.seen_variants
    for seen in executor.seen_variants:
        assert not any("seed-prior" in snippet for snippet in seen.memory_snippets)

    # 4. Both passing AND failing variants were recorded into SIM (merged by root cause)
    reloaded = SIMStore(tmp_path / "sim.json")
    assert "missing_module" in reloaded.groups
    assert "early_stop" in reloaded.groups
    # missing_module merged seed-prior + good without losing prior history
    labels = [e["label"] for e in reloaded.groups["missing_module"]["edits"]]
    assert labels == ["seed-prior", "good"]
    bad_edits = reloaded.groups["early_stop"]["edits"]
    assert len(bad_edits) == 1 and bad_edits[0]["passed"] is False


def test_cross_model_crsi_carries_sim_across_rounds_and_runs(rig_repo, vault):
    propose_reply = json.dumps(
        [
            {
                "label": "attempt",
                "system_prompt": "try solving",
                "root_cause": "incomplete_impl",
                "rationale": "first attempt on fast model",
                "predicted_outcome": "may miss edge case",
            }
        ]
    )

    # Run 1 on model-a fails: vault lesson is NOT created, but SIM records the failure
    cfg1 = DaCodeConfig(
        repo=rig_repo,
        vault=vault,
        model="model-a",
        budget=1,
        variants_per_round=1,
        isolate="none",
    )
    llm1 = StubLLM(default=propose_reply)
    rig1 = DaCodeRig(cfg1, llm=llm1, executor=_RecordingExecutor(good_label="never"))
    res1 = rig1.run_task("implement calc.add")
    assert res1.passed is False
    assert res1.lesson_path is None

    sim_file = vault / "Projects" / rig_repo.name / "sim.json"
    assert sim_file.is_file()

    # Run 2 on model-b inherits SIM from Run 1 automatically (cross-model CRSI)
    cfg2 = DaCodeConfig(
        repo=rig_repo,
        vault=vault,
        model="model-b",
        budget=1,
        variants_per_round=1,
        isolate="none",
    )
    llm2 = StubLLM(default=propose_reply)
    exec2 = _RecordingExecutor(good_label="attempt")
    rig2 = DaCodeRig(cfg2, llm=llm2, executor=exec2)
    res2 = rig2.run_task("implement calc.add")
    assert res2.passed is True

    # Run 2 proposer saw Run 1's failure and model-a provenance
    propose_calls = [user for _, user in llm2.calls if "Propose 1 variants" in user]
    assert propose_calls
    assert "incomplete_impl" in propose_calls[0]
    assert "model-a" in propose_calls[0]
    # And VaultMemory.retrieve() did NOT leak sim.json into policy snippets
    for seen in exec2.seen_variants:
        assert not any("incomplete_impl" in s for s in seen.memory_snippets)

    # Reloaded SIM shows cross-model progression under the same root cause
    final_sim = SIMStore(sim_file)
    edits = final_sim.groups["incomplete_impl"]["edits"]
    assert [(e["provenance"]["model"], e["passed"]) for e in edits] == [
        ("model-a", False),
        ("model-b", True),
    ]


def test_explicit_sim_path_supports_cross_repo_crsi_and_cli_flag(tmp_path: Path, rig_repo):
    from dacode.cli import build_parser

    shared_sim = tmp_path / "portable-sim.json"
    store = SIMStore(shared_sim)
    store.record(
        SIMRecord(
            root_cause="tests_modified",
            label="prior-repo-edit",
            rationale="forbid touching tests",
            predicted_outcome="zero tampering",
            observed_outcome="PASS (tests 3/3, score=1.0)",
            passed=True,
            score=1.0,
            repo="other-repo",
            model="model-x",
            round_no=1,
            task="other task",
        )
    )

    cfg = DaCodeConfig(
        repo=rig_repo,
        vault=None,
        sim_path=shared_sim,
        model="model-y",
        budget=1,
        variants_per_round=1,
        isolate="none",
    )
    llm = StubLLM(
        default=json.dumps([{"label": "good", "system_prompt": "implement calc.add"}])
    )
    rig = DaCodeRig(cfg, llm=llm, executor=_RecordingExecutor("good"))
    res = rig.run_task("implement calc.add")
    assert res.passed is True

    # Proposer saw SIM carried over from other-repo
    propose_calls = [user for _, user in llm.calls if "Propose 1 variants" in user]
    assert propose_calls and "prior-repo-edit" in propose_calls[0]

    # CLI accepts --sim PATH
    parsed = build_parser().parse_args(["run", "some task", "--sim", str(shared_sim)])
    assert parsed.sim == str(shared_sim)

