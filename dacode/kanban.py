"""Kanban worker — DaCode as one worker on a Hermes Kanban board.

The worker takes one card, claims it atomically (a lost race costs nothing),
reads the gate command from the card body's fenced `````gate` block, runs the
card through the rig, and reports back: ``complete`` with evidence when the
gate passes, ``block`` with a readable reason when it does not.

This is an *optional* integration: the board is any ``hermes`` binary speaking
``hermes kanban``. Defaults are overridable:

* ``DACODE_KANBAN_BIN``   — the CLI binary (default ``hermes``)
* ``DACODE_KANBAN_BOARD`` — the board name (``--board`` is omitted when unset)

Every string that crosses to the board goes through :func:`dacode.redact.redact`
— a card comment is as persistent as a log line.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dacode import runlog
from dacode.redact import redact, redact_event

__all__ = [
    "KanbanError",
    "parse_gate",
    "CardOutcome",
    "HermesKanban",
    "work",
    "changed_files",
    "make_rig_runner",
]


class KanbanError(RuntimeError):
    """The board refused a verb (non-zero exit) — the caller decides what that means."""


DEFAULT_BINARY = "hermes"
DEFAULT_TIMEOUT = 60  # seconds per board call

#: Runner signature: ``runner(argv) -> object with returncode/stdout/stderr``.
Runner = Callable[[list[str]], Any]


def parse_gate(body: str | None) -> str | None:
    """The stripped content of the FIRST fenced block info-tagged exactly ``gate``.

    Multi-line commands survive intact (only the whole block is stripped). A
    plain ```` ```bash ```` block is not a gate; neither is an empty one.
    """
    if not body:
        return None
    lines = body.splitlines()
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped.startswith("```"):
            i += 1
            continue
        info = stripped[3:].strip()
        buf: list[str] = []
        i += 1
        while i < n and not lines[i].strip().startswith("```"):
            buf.append(lines[i])
            i += 1
        if info == "gate":
            content = "\n".join(buf).strip()
            return content or None
        i += 1  # some other fenced block: skip past its closing fence
    return None


@dataclass
class CardOutcome:
    """What one pass of the rig did to a card — the evidence for the board."""

    passed: bool
    tests_passed: int = 0
    tests_total: int = 0
    worktree: str | None = None
    changed_files: list[str] = field(default_factory=list)
    output_tail: str = ""
    reason: str = ""


class HermesKanban:
    """Drive a Hermes Kanban board over a subprocess (injectable for tests)."""

    def __init__(
        self,
        board: str | None = None,
        *,
        binary: str | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.board = board or os.environ.get("DACODE_KANBAN_BOARD") or None
        self.binary = binary or os.environ.get("DACODE_KANBAN_BIN") or DEFAULT_BINARY
        self._runner = runner or self._run

    @staticmethod
    def _run(argv: list[str]) -> Any:
        return subprocess.run(argv, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT)

    def _argv(self, verb_args: list[str]) -> list[str]:
        argv = [self.binary, "kanban"]
        if self.board:
            argv += ["--board", self.board]
        return argv + verb_args

    def _fail(self, action: str, proc: Any) -> KanbanError:
        detail = (proc.stderr or proc.stdout or "").strip()
        return KanbanError(detail or f"{action} failed with exit {proc.returncode}")

    def show(self, task_id: str) -> dict:
        proc = self._runner(self._argv(["show", task_id, "--json"]))
        if proc.returncode != 0:
            raise self._fail(f"show {task_id}", proc)
        return json.loads(proc.stdout or "{}")["task"]

    def claim(self, task_id: str, ttl: int) -> bool:
        proc = self._runner(self._argv(["claim", task_id, "--ttl", str(ttl)]))
        return proc.returncode == 0

    def complete(self, task_id: str, result: str, metadata: dict) -> None:
        proc = self._runner(
            self._argv(
                [
                    "complete", task_id,
                    "--result", result,
                    "--metadata", json.dumps(metadata, ensure_ascii=False),
                ]
            )
        )
        if proc.returncode != 0:
            raise self._fail(f"complete {task_id}", proc)

    def block(self, task_id: str, reason: str, kind: str | None = None) -> None:
        verb_args = ["block", task_id]
        if kind:
            verb_args += ["--kind", kind]
        verb_args.append(reason)
        proc = self._runner(self._argv(verb_args))
        if proc.returncode != 0:
            raise self._fail(f"block {task_id}", proc)


def work(task_id: str, board: HermesKanban, run_card: Callable[..., CardOutcome], *, ttl: int = 3600) -> int:
    """Claim one card, run it through the rig, report the outcome.

    Exit codes: 0 complete, 1 gate failed / rig error, 2 no gate, 3 claim
    refused, 4 the board lost our claim on completion.
    """
    if not board.claim(task_id, ttl):
        print(f"[kanban] {task_id}: claim refused — another worker owns the card", file=sys.stderr)
        return 3

    task = board.show(task_id)
    gate = parse_gate(task.get("body"))
    if not gate:
        reason = redact("card body carries no ```gate block — nothing to gate on; add one and requeue")
        board.block(task_id, reason, kind="needs_input")
        return 2

    text = f"{task.get('title') or ''}\n\n{task.get('body') or ''}"
    try:
        outcome = run_card(text, gate, task.get("workspace_path"))
    except Exception as exc:  # noqa: BLE001 — a dead rig is a blocked card, not a crash
        board.block(task_id, redact(f"rig error: {exc}"))
        return 1

    if outcome.passed:
        result = redact(f"gate passed: {outcome.tests_passed}/{outcome.tests_total} tests")
        metadata = redact_event(
            {
                "gate": gate,
                "tests_passed": outcome.tests_passed,
                "tests_total": outcome.tests_total,
                "changed_files": outcome.changed_files,
                "worktree": outcome.worktree,
                "gate_output": outcome.output_tail,
                "runlog": str(runlog.current_path()),
            }
        )
        try:
            board.complete(task_id, result, metadata)
        except KanbanError as exc:
            print(f"[kanban] {task_id}: complete refused: {exc}", file=sys.stderr)
            return 4
        return 0

    reason = redact(f"gate failed: {outcome.tests_passed}/{outcome.tests_total} — {outcome.reason}")
    board.block(task_id, reason)
    return 1


def changed_files(workspace: str | Path | None, base: str) -> list[str]:
    """Files a trial workspace changed against ``base``; [] on any doubt."""
    if not workspace:
        return []
    ws = Path(workspace)
    if not ws.is_dir():
        return []
    try:
        proc = subprocess.run(
            ["git", "-C", str(ws), "diff", "--name-only", base, "HEAD"],
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def make_rig_runner(cfg: Any, *, rig_factory: Any = None) -> Callable[[str, str, Any], CardOutcome]:
    """Turn a :class:`dacode.config.DaCodeConfig` into a ``run_card`` for :func:`work`.

    The card's gate becomes the rig's test command and the card's git workspace
    becomes the repo — the caller's config is copied, never mutated.
    """
    if rig_factory is None:
        from dacode.orchestrator import DaCodeRig  # lazy: pulls in the llm stack

        rig_factory = DaCodeRig

    def run_card(task: str, gate: str, workspace: Any) -> CardOutcome:
        repo = Path(workspace) if workspace and (Path(workspace) / ".git").exists() else cfg.repo
        new_cfg = dataclasses.replace(
            cfg, test_command=("bash", "-c", gate), isolate="bwrap", repo=repo
        )

        try:
            proc = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT,
            )
            base = proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else "HEAD"
        except (OSError, subprocess.SubprocessError):
            base = "HEAD"

        result = rig_factory(new_cfg).run_task(task)
        probe = result.best.probe
        if probe is not None:
            worktree = probe.workspace or None
            tail = (probe.gate_output or probe.stdout or "")[-2000:]
            diffs = changed_files(probe.workspace, base)
        else:
            worktree, tail, diffs = None, "", []
        if result.passed:
            reason = ""
        elif result.needs_human_review:
            reason = "needs human review"
        elif probe is None:
            reason = f"no variant was probed in {result.rounds} round(s)"
        else:
            why = ", ".join(dict.fromkeys(probe.errors)) or "tests did not pass"
            reason = f"gate failed after {result.rounds} round(s): {why}"
            if probe.stderr.startswith("trial error:"):
                reason += f" ({probe.stderr[:300]})"
        return CardOutcome(
            passed=bool(result.passed),
            tests_passed=probe.tests_passed if probe else 0,
            tests_total=probe.tests_total if probe else 0,
            worktree=worktree,
            changed_files=diffs,
            output_tail=tail,
            reason=reason,
        )

    return run_card
