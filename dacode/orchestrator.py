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
from dacode.judgment import build_judge
from dacode.llm import build_llm
from dacode.memory import Lesson, VaultMemory
from dacode.sandbox import GitSandbox
from dacode.sandbox.bwrap import IsolationPolicy, available as bwrap_available, describe as describe_isolation

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
        self.isolation = self._isolation_policy()
        # The gate gets its own policy: an agent needs the network to reach a model,
        # a test suite never does. Sharing one object gave the gate sockets (and the
        # provider keys that come with them) whenever --isolate-network was on.
        self.gate_isolation = self._gate_isolation()
        self.executor = executor or self._build_executor()
        self.judge = build_judge(config.judge)
        self.critic = critic or PstackCritic(
            test_command=config.test_command,
            test_glob=config.test_glob,
            timeout=config.variant_timeout,
            isolation=self.gate_isolation,
        )
        self.memory = memory
        if self.memory is None and config.vault is not None and Path(config.vault).is_dir():
            self.memory = VaultMemory(config.vault, semantic=config.semantic)
        self.optimizer = HarnessOptimizer(
            llm=self.llm,
            sandbox=self.sandbox,
            executor=self.executor,
            critic=self.critic,
            memory=self.memory,
            judge=self.judge,
            escalation_models=config.escalate_models,
            baseline=config.baseline,
            parallel=config.parallel,
            fleet=config.fleet,
            budget=config.budget,
            variants_per_round=config.variants_per_round,
            keep_winning_worktree=config.keep_winning_worktree,
        )

    def _build_executor(self):
        if self.config.executor == "script":
            return ScriptExecutor(
                default_command=self.config.script_command,
                timeout=self.config.variant_timeout,
                isolation=self.isolation,
            )
        return PiExecutor(
            model=self.config.model,
            timeout=self.config.variant_timeout,
            isolation=self.isolation,
        )

    def _gate_isolation(self) -> IsolationPolicy | None:
        """Isolation for the test gate: always offline, always key-free."""
        if self.isolation is None:
            return None
        return IsolationPolicy(enabled=True, network=False, read_only_paths=(), env_allow=())

    def _isolation_policy(self) -> IsolationPolicy | None:
        """Turn `--isolate` into a policy, refusing to pretend when bwrap is missing.

        The executor always sees the network when isolation is on (it has to reach a
        model); the gate never does.
        """
        setting = (self.config.isolate or "none").strip().lower()
        if setting in {"none", "off", "false", "0", "no", ""}:
            return None
        if setting != "bwrap":
            raise RuntimeError(
                f"unknown --isolate value {self.config.isolate!r} — use 'bwrap' or 'none'"
            )
        if not bwrap_available():
            raise RuntimeError(
                "--isolate bwrap requested but bubblewrap is not installed "
                "(install bubblewrap, or run with --isolate none)"
            )
        return IsolationPolicy(
            enabled=True,
            network=bool(self.config.isolate_network),
            env_allow=(),
        )

    # -- layer introspection ----------------------------------------------

    def layers(self) -> list[LayerStatus]:
        report = [
            LayerStatus(
                "5b. Isolation",
                (describe_isolation(self.isolation) if self.isolation else "off")
                + ("" if self.isolation is None else " · gate: net:off"),
                self.isolation is None or bwrap_available(),
            ),
        ]
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
        ] + report

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
        # The gate needs to know how many tests the untouched repo has, so a
        # trial cannot "fix" a red suite by deleting or skipping tests.
        baseline = None
        try:
            baseline = self.critic.measure_baseline(self.config.repo)
        except Exception:  # noqa: BLE001 - a missing baseline must not block the run
            baseline = None
        self.optimizer.baseline = baseline
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
                # worktree name only — absolute scratch paths are machine-specific and ephemeral
                f"- trial worktree: `{Path(best.probe.workspace).name}`",
            ]
        lines += ["\n## System prompt that won\n", "```", best.system_prompt.strip(), "```"]
        return Lesson(
            title=f"DaCode lesson: {result.task[:60]}",
            body="\n".join(lines),
            tags=["dacode", "lesson", "harness2"],
            source_task=result.task[:120],
        )
