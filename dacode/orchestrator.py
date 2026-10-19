"""The DaCode rig — wires the five layers into the blueprint's lifecycle.

Lifecycle (from the blueprint):

1. **Initialization & Context** — retrieve prior lessons from the vault.
2. **Experimentation Loop**   — Harness² proposes, sandbox isolates, executor runs.
3. **Discipline & Critique**  — pstack critic gates each trial.
4. **Memory Ingestion**       — the winning lesson is written back to the vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dacode.config import DaCodeConfig
from dacode.discipline.critic import PstackCritic
from dacode.executor.pi import PiExecutor
from dacode.executor.script import ScriptExecutor
from dacode.harness.models import HarnessResult, HarnessVariant
from dacode.harness.optimizer import DEFAULT_SYSTEM_PROMPT, HarnessOptimizer
from dacode.llm import build_llm
from dacode.memory import Lesson, VaultMemory
from dacode.sandbox import GitSandbox

__all__ = ["DaCodeRig"]


@dataclass
class LayerStatus:
    name: str
    detail: str
    ready: bool


class DaCodeRig:
    def __init__(
        self,
        config: DaCodeConfig,
        *,
        llm=None,
        sandbox: GitSandbox | None = None,
        executor=None,
        critic: PstackCritic | None = None,
        memory: VaultMemory | None = None,
    ) -> None:
        self.config = config
        self.llm = llm or build_llm(config.llm_kind, model=config.model, base_url=config.base_url)
        self.sandbox = sandbox or GitSandbox(config.repo, config.sandbox_root)
        self.executor = executor or self._build_executor()
        self.critic = critic or PstackCritic(
            test_command=config.test_command,
        )
        self.memory = memory
        if self.memory is None and config.vault is not None and Path(config.vault).is_dir():
            self.memory = VaultMemory(config.vault)
        self.optimizer = HarnessOptimizer(
            llm=self.llm,
            sandbox=self.sandbox,
            executor=self.executor,
            critic=self.critic,
            memory=self.memory,
            budget=config.budget,
            variants_per_round=config.variants_per_round,
            keep_winning_worktree=config.keep_winning_worktree,
        )

    def _build_executor(self):
        if self.config.executor == "script":
            return ScriptExecutor(default_command=self.config.script_command)
        return PiExecutor(model=self.config.model)

    # -- layer introspection ----------------------------------------------

    def layers(self) -> list[LayerStatus]:
        return [
            LayerStatus(
                "1. Vault Memory",
                str(self.config.vault) if self.memory else "disabled (no vault)",
                self.memory is not None,
            ),
            LayerStatus("2. Harness² Optimizer", f"budget={self.config.budget}, n={self.config.variants_per_round}", True),
            LayerStatus("3. Executor", self.config.executor, True),
            LayerStatus("4. pstack Critic", "static checks + real test run", True),
            LayerStatus("5. Git Sandbox", str(self.sandbox.sandbox_root), self.config.repo.is_dir()),
        ]

    # -- the run -----------------------------------------------------------

    def run_task(self, task: str, *, base_prompt: str = DEFAULT_SYSTEM_PROMPT) -> HarnessResult:
        # 1. Initialization & Context
        snippets: list[str] = []
        if self.memory is not None:
            hits = self.memory.retrieve(task, limit=5)
            for hit in hits:
                snippets.append(f"{hit.title}: {hit.snippet}".strip())
        base = HarnessVariant(
            system_prompt=base_prompt,
            memory_snippets=snippets,
            label="seeded-base",
            payload={"task": task},
        )

        # 2 & 3. Experimentation + Discipline (inside optimizer.probe)
        result = self.optimizer.run(task, base)

        # 4. Memory Ingestion
        if result.passed and self.memory is not None:
            lesson = self._build_lesson(result)
            path = self.memory.ingest(lesson)
            result.lesson_path = str(path)
        return result

    @staticmethod
    def _build_lesson(result: HarnessResult) -> Lesson:
        best = result.best
        lines = [
            f"## Task\n\n{result.task}\n",
            "## Winning harness",
            f"\n- variant: `{best.id}` ({best.label})",
            f"- rounds: {result.rounds}",
            f"- score: {best.score}",
        ]
        if best.probe:
            lines += [
                f"- tests: {best.probe.tests_passed}/{best.probe.tests_total} pass",
                f"- critique passed: {best.probe.critique_passed}",
                f"- trial workspace: `{best.probe.workspace}`",
            ]
        lines += ["\n## System prompt that won\n", "```", best.system_prompt.strip(), "```"]
        return Lesson(
            title=f"DaCode lesson: {result.task[:60]}",
            body="\n".join(lines),
            tags=["dacode", "lesson", "harness2"],
            source_task=result.task[:120],
        )
