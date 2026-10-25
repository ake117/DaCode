"""End-to-end tests for the DaCode rig (all five layers together)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dacode.config import DaCodeConfig
from dacode.orchestrator import DaCodeRig
from dacode.llm import StubLLM

PROPOSE_JSON = json.dumps(
    [
        {"label": "good", "system_prompt": "implement carefully", "tools": []},
        {"label": "bad", "system_prompt": "do nothing", "tools": []},
    ]
)


class FakeExecutor:
    def __init__(self, good_label: str = "good") -> None:
        self.good_label = good_label

    def run(self, variant, workspace):
        from dacode.executor.base import ExecResult

        if variant.label == self.good_label:
            (Path(workspace) / "calc.py").write_text(
                "def add(a, b):\n    return a + b\n", encoding="utf-8"
            )
        return ExecResult(exit_code=0)


def _rig(repo: Path, vault: Path) -> DaCodeRig:
    # These tests exercise the loop, not the sandbox: opt out explicitly. The
    # product default is bwrap now (it must be asked for, not inherited).
    cfg = DaCodeConfig(repo=repo, vault=vault, budget=1, isolate="none")
    llm = StubLLM(responses={"Propose 2 variants": PROPOSE_JSON}, default="")
    return DaCodeRig(cfg, llm=llm, executor=FakeExecutor("good"))


def test_rig_reports_five_ready_layers(rig_repo, vault):
    rig = _rig(rig_repo, vault)
    layers = rig.layers()
    core = [layer for layer in layers if not layer.name.startswith("5b")]
    assert [layer.name.split(".")[0] for layer in core] == ["1", "2", "3", "4", "5"]
    assert all(layer.ready for layer in core)
    # isolation is reported separately: off by default, and that is not a problem
    isolation = [layer for layer in layers if layer.name.startswith("5b")]
    assert len(isolation) == 1 and isolation[0].detail == "off"


def test_rig_run_passes_and_ingests_a_lesson(rig_repo, vault):
    rig = _rig(rig_repo, vault)
    result = rig.run_task("implement calc.add")

    assert result.passed is True
    assert result.lesson_path is not None
    lesson = Path(result.lesson_path)
    assert lesson.is_file()
    text = lesson.read_text(encoding="utf-8")
    assert "type: lesson" in text
    assert "implement calc.add" in text
    assert "good" in text


def test_rig_seeds_context_from_vault(rig_repo, vault):
    # a note that mentions the task terms should be retrieved into the base harness
    note = vault / "Resources" / "AI Agents" / "Calc Lesson.md"
    note.write_text(
        "---\ntitle: Calc Add Lesson\ntags:\n  - lesson\n---\n\n"
        "Implementing calc.add: always return a + b for integers.\n",
        encoding="utf-8",
    )
    rig = _rig(rig_repo, vault)
    # capture the base harness the optimizer received
    captured = {}
    original_run = rig.optimizer.run

    def spy(task, base=None):
        captured["base"] = base
        return original_run(task, base)

    rig.optimizer.run = spy  # type: ignore[assignment]
    rig.run_task("implement calc.add")

    base = captured["base"]
    assert base is not None
    assert any("Calc Add Lesson" in s for s in base.memory_snippets)


def test_rig_does_not_ingest_when_task_fails(rig_repo, vault):
    cfg = DaCodeConfig(repo=rig_repo, vault=vault, budget=1, isolate="none")
    llm = StubLLM(responses={"Propose 2 variants": PROPOSE_JSON}, default="")
    rig = DaCodeRig(cfg, llm=llm, executor=FakeExecutor("none-match"))
    result = rig.run_task("implement calc.add")
    assert result.passed is False
    assert result.lesson_path is None


def test_gate_isolation_hides_the_repository_dotenv(rig_repo, vault, monkeypatch):
    """Gemini 4 Argon audit (Oct 2026): the gate's policy never hid <repo>/.env.

    The gate runs the tested code's own tests. If the repository's .env stays
    readable inside the gate sandbox, a hostile test can print a provider key into
    the stdout the gate reads back — the executor already masked this file, the gate
    did not.
    """
    import dacode.orchestrator as orch

    monkeypatch.setattr(orch, "bwrap_available", lambda: True)
    (rig_repo / ".env").write_text("OPENROUTER_API_KEY=sk-not-a-real-key\n", encoding="utf-8")

    cfg = DaCodeConfig(repo=rig_repo, vault=vault, budget=1, isolate="bwrap")
    llm = StubLLM(responses={}, default="")
    rig = DaCodeRig(cfg, llm=llm, executor=FakeExecutor("good"))

    policy = rig.gate_isolation
    assert policy is not None and policy.enabled is True
    hidden = {Path(p).resolve() for p in policy.hidden_files}
    assert (rig_repo / ".env").resolve() in hidden
