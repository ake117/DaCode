"""The Harness² optimizer: Propose → Probe → Compose.

Two levels of recursion, exactly as the blueprint describes:

* **Task-level** (``run``): for a single task, propose variants, probe each in
  an isolated worktree, compose the best, and iterate within a budget.
* **Harnessing-level** (``memory.ingest`` via the orchestrator): the winning
  variant's lesson is written back to the vault so future runs start smarter.

All LLM interaction is funneled through the injected ``llm`` client, so the loop
is deterministic and testable with a stub.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from dacode.harness.models import HarnessResult, HarnessVariant, ProbeResult

if TYPE_CHECKING:
    from dacode.discipline.critic import PstackCritic
    from dacode.executor.base import Executor
    from dacode.llm.base import LLMClient
    from dacode.memory import VaultMemory
    from dacode.sandbox import GitSandbox

__all__ = ["HarnessOptimizer"]

DEFAULT_SYSTEM_PROMPT = (
    "You are a meticulous coding agent. Implement the task with the smallest "
    "correct change. Write or update tests that assert literal behaviour. "
    "Run the tests and do not stop until they pass."
)

_PROPOSE_SYSTEM = """You are the Harness Optimizer (layer 2 of DaCode).
A "harness" is everything around the model: the system prompt, the tools
enabled, and the memory snippets injected. Your job is to propose DIFFERENT
harness variants for the task below, so the rig can contrast them.

Return ONLY a JSON array. Each element:
{"label": "<short>", "system_prompt": "<full prompt>", "tools": ["..."]}
Propose {n} genuinely different variants (vary the prompt strategy, not wording).
No prose, no markdown fences — JSON only."""

_COMPOSE_SYSTEM = """You are the Harness Optimizer (layer 2 of DaCode).
You are given several probed harness variants and their measured results.
Pick the single best variant for the task. Prefer passing tests, then fewer
critique errors, then higher score. Return ONLY JSON:
{"best_id": "<variant id>", "rationale": "<one sentence>"}"""


class HarnessOptimizer:
    def __init__(
        self,
        llm: "LLMClient",
        sandbox: "GitSandbox",
        executor: "Executor",
        critic: "PstackCritic",
        memory: "VaultMemory | None" = None,
        *,
        budget: int = 2,
        variants_per_round: int = 2,
        base_prompt: str = DEFAULT_SYSTEM_PROMPT,
        keep_winning_worktree: bool = False,
    ) -> None:
        self.llm = llm
        self.sandbox = sandbox
        self.executor = executor
        self.critic = critic
        self.memory = memory
        self.budget = max(1, budget)
        self.variants_per_round = max(1, variants_per_round)
        self.base_prompt = base_prompt
        self.keep_winning_worktree = keep_winning_worktree

    # -- propose -----------------------------------------------------------

    def propose(self, task: str, base: HarnessVariant, n: int) -> list[HarnessVariant]:
        """Ask the LLM for ``n`` candidate harness variants."""
        user = (
            f"Task:\n{task}\n\n"
            f"Current best harness system_prompt:\n{base.system_prompt}\n\n"
            f"Seeded memory snippets:\n{base.seed_context() or '(none)'}\n\n"
            f"Propose {n} variants."
        )
        raw = self.llm.complete(_PROPOSE_SYSTEM, user)
        specs = _parse_json_array(raw)
        variants: list[HarnessVariant] = []
        for i, spec in enumerate(specs[:n]):
            if not isinstance(spec, dict):
                continue
            variants.append(
                HarnessVariant(
                    label=str(spec.get("label", f"proposal-{i + 1}")),
                    system_prompt=str(spec.get("system_prompt") or base.system_prompt),
                    tools=[str(t) for t in spec.get("tools", [])] or list(base.tools),
                    memory_snippets=list(base.memory_snippets),
                    parent_id=base.id,
                    payload=dict(base.payload),
                )
            )
        if not variants:
            # Robustness: never let a bad LLM response stall the loop.
            variants.append(
                HarnessVariant(
                    label="fallback",
                    system_prompt=base.system_prompt,
                    tools=list(base.tools),
                    memory_snippets=list(base.memory_snippets),
                    parent_id=base.id,
                    payload=dict(base.payload),
                )
            )
        return variants

    # -- probe -------------------------------------------------------------

    def probe(self, variant: HarnessVariant, task: str, trial_id: str) -> ProbeResult:
        """Run one variant end-to-end in a fresh isolated worktree."""
        variant.payload.setdefault("task", task)
        workspace = self.sandbox.create(trial_id)
        try:
            exec_result = self.executor.run(variant, workspace)
            report = self.critic.review_workspace(workspace)
            if report.passed:
                self.sandbox.checkpoint(trial_id, f"dacode: {variant.label} passed ({trial_id})")
            result = ProbeResult(
                variant_id=variant.id,
                workspace=str(workspace),
                exit_code=exec_result.exit_code,
                tests_total=report.tests_total,
                tests_passed=report.tests_passed,
                critique_passed=report.passed,
                critique_score=report.score,
                stdout=exec_result.stdout[-4000:],
                stderr=exec_result.stderr[-2000:],
            )
        except Exception as exc:  # noqa: BLE001 - a failed trial must not kill the run
            result = ProbeResult(
                variant_id=variant.id,
                workspace=str(workspace),
                exit_code=1,
                critique_passed=False,
                critique_score=0.0,
                stderr=f"trial error: {exc!r}",
            )
        variant.score = _variant_score(result)
        variant.probe = result
        return result

    # -- compose -----------------------------------------------------------

    def compose(self, task: str, variants: list[HarnessVariant]) -> HarnessVariant:
        """Pick the best variant — LLM-assisted, with a deterministic fallback."""
        if not variants:
            raise ValueError("compose() called with no variants")
        ranked = sorted(variants, key=lambda v: v.score or 0.0, reverse=True)
        fallback = ranked[0]
        table = "\n".join(
            f"- id={v.id} label={v.label!r} score={v.score} "
            f"tests={v.probe.tests_passed if v.probe else '?'}/"
            f"{v.probe.tests_total if v.probe else '?'} "
            f"passed={v.probe.critique_passed if v.probe else '?'}"
            for v in ranked
        )
        user = f"Task:\n{task}\n\nProbed variants (best first):\n{table}\n\nPick the best."
        try:
            raw = self.llm.complete(_COMPOSE_SYSTEM, user)
            data = _parse_json_object(raw)
            chosen = next((v for v in variants if v.id == str(data.get("best_id", ""))), None)
            if chosen is not None:
                return chosen
        except Exception:  # noqa: BLE001 - fall back to the measured ranking
            pass
        return fallback

    # -- full loop ---------------------------------------------------------

    def run(self, task: str, base: HarnessVariant | None = None) -> HarnessResult:
        """Execute the Propose–Probe–Compose loop for ``task``."""
        if base is None:
            base = HarnessVariant(system_prompt=self.base_prompt, label="base")

        all_variants: list[HarnessVariant] = []
        best = base
        best.score = 0.0
        rounds_run = 0

        for round_no in range(1, self.budget + 1):
            rounds_run = round_no
            variants = self.propose(task, best, self.variants_per_round)
            for idx, variant in enumerate(variants, start=1):
                trial_id = f"{_slug(task)}-r{round_no}-{idx}-{variant.id}"
                variant.payload.setdefault("task", task)
                self.probe(variant, task, trial_id)
                all_variants.append(variant)
            round_best = self.compose(task, variants)
            if (round_best.score or 0.0) >= (best.score or 0.0):
                best = round_best
            # cleanup losing trials to keep the repo tidy
            self._cleanup_losers(variants, keep=best)
            if best.score is not None and best.score >= 1.0 and best.probe and best.probe.critique_passed:
                break

        return HarnessResult(
            task=task,
            rounds=rounds_run,
            best=best,
            variants=all_variants,
            passed=bool(best.probe and best.probe.critique_passed),
        )

    def _cleanup_losers(self, variants: list[HarnessVariant], *, keep: HarnessVariant) -> None:
        if self.keep_winning_worktree:
            return
        for variant in variants:
            if variant is keep:
                continue
            trial_dir = variant.probe.workspace if variant.probe else None
            if not trial_dir:
                continue
            task_id = _trial_id_from_path(trial_dir)
            if task_id:
                try:
                    self.sandbox.remove(task_id, delete_branch=True)
                except Exception:  # noqa: BLE001 - cleanup is best-effort
                    pass


# -- helpers ---------------------------------------------------------------


def _variant_score(result: ProbeResult) -> float:
    """Rank a trial: passing tests dominate, critique score breaks ties."""
    if result.tests_total == 0:
        base = 0.0
    else:
        base = result.tests_passed / result.tests_total
    bonus = 0.5 if result.critique_passed else 0.0
    exit_penalty = 0.0 if result.exit_code == 0 else 0.25
    return round(max(0.0, base + bonus - exit_penalty), 3)


def _slug(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug or "task")[:40]


def _trial_id_from_path(path: str) -> str | None:
    from pathlib import Path

    name = Path(path).name
    return name or None


def _parse_json_array(raw: str) -> list:
    data = _extract_json(raw, expect="[")
    return data if isinstance(data, list) else []


def _parse_json_object(raw: str) -> dict:
    data = _extract_json(raw, expect="{")
    return data if isinstance(data, dict) else {}


def _extract_json(raw: str, *, expect: str):
    """Pull a JSON value out of an LLM reply that may include prose/fences."""
    if not raw:
        return [] if expect == "[" else {}
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    closer = "]" if expect == "[" else "}"
    start = text.find(expect)
    end = text.rfind(closer)
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return [] if expect == "[" else {}
    return [] if expect == "[" else {}
