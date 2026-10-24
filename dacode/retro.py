"""dacode retro — read the run recorder and say what to change.

pstack #5: a run that ends is a run that should teach the harness something.
This module never guesses with an LLM: it counts what happened in the JSONL
runlog (and, when available, the SQLite mirror) and turns the counts into
concrete suggestions — split the task, raise the budget, cap the timeout, or
stop retrying a shape of work that keeps failing.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from dacode import runlog

__all__ = ["RetroReport", "TaskRetro", "build_report", "render_text"]

DEFAULTS = {
    "slow_variant_s": 240.0,
    "low_pass_rate": 0.5,
    "high_avg_rounds": 2.0,
}


@dataclass
class TaskRetro:
    task: str
    runs: int = 0
    passes: int = 0
    rounds: list[int] = field(default_factory=list)
    variant_times: list[float] = field(default_factory=list)
    failure_checks: dict[str, int] = field(default_factory=dict)
    models: dict[str, int] = field(default_factory=dict)
    model_passes: dict[str, int] = field(default_factory=dict)
    timeouts: int = 0

    @property
    def pass_rate(self) -> float:
        return self.passes / self.runs if self.runs else 0.0

    @property
    def avg_rounds(self) -> float:
        return statistics.fmean(self.rounds) if self.rounds else 0.0

    @property
    def avg_variant_s(self) -> float:
        return statistics.fmean(self.variant_times) if self.variant_times else 0.0

    @property
    def slowest_variant_s(self) -> float:
        return max(self.variant_times) if self.variant_times else 0.0


@dataclass
class RetroReport:
    since_days: int
    events: int
    tasks: list[TaskRetro]
    suggestions: list[str]

    def to_dict(self) -> dict:
        return {
            "since_days": self.since_days,
            "events": self.events,
            "tasks": [
                {
                    "task": t.task,
                    "runs": t.runs,
                    "pass_rate": round(t.pass_rate, 3),
                    "avg_rounds": round(t.avg_rounds, 2),
                    "avg_variant_s": round(t.avg_variant_s, 1),
                    "slowest_variant_s": round(t.slowest_variant_s, 1),
                    "failure_checks": t.failure_checks,
                    "models": t.models,
                    "model_passes": t.model_passes,
                    "timeouts": t.timeouts,
                }
                for t in self.tasks
            ],
            "suggestions": self.suggestions,
        }


def _events(log_path: Path | None, since_days: int) -> list[dict]:
    path = Path(log_path) if log_path else runlog.current_path()
    if not path.exists():
        return []
    cutoff = time.time() - since_days * 86400
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if float(event.get("ts") or 0) < cutoff:
            continue
        out.append(event)
    return out


def build_report(
    *,
    since_days: int = 14,
    log_path: Path | None = None,
    task_filter: str | None = None,
) -> RetroReport:
    events = _events(log_path, since_days)
    tasks: dict[str, TaskRetro] = {}

    def bucket(task: str) -> TaskRetro:
        key = task or "(untitled)"
        if key not in tasks:
            tasks[key] = TaskRetro(task=key)
        return tasks[key]

    for event in events:
        kind = event.get("type")
        task = str(event.get("task") or "")
        if task_filter and task_filter.lower() not in task.lower():
            continue
        row = bucket(task)
        if kind == "run":
            row.runs += 1
            row.passes += 1 if event.get("passed") else 0
            if isinstance(event.get("rounds"), int):
                row.rounds.append(event["rounds"])
        elif kind == "probe":
            if isinstance(event.get("elapsed_s"), (int, float)):
                row.variant_times.append(float(event["elapsed_s"]))
            for item in event.get("findings") or []:
                severity, _, check = str(item).partition(":")
                if not check:            # older events recorded a bare check name
                    severity, check = "error", severity
                if severity != "error":  # style warnings are not failures
                    continue
                row.failure_checks[check] = row.failure_checks.get(check, 0) + 1
            if event.get("model"):
                model = str(event["model"])
                row.models[model] = row.models.get(model, 0) + 1
                if event.get("critique_passed"):
                    row.model_passes[model] = row.model_passes.get(model, 0) + 1
            if event.get("exit_code") == 124:
                row.timeouts += 1

    ordered = sorted(tasks.values(), key=lambda t: (-t.runs, t.task))
    return RetroReport(
        since_days=since_days,
        events=len(events),
        tasks=ordered,
        suggestions=_suggest(ordered),
    )


def _suggest(tasks: list[TaskRetro]) -> list[str]:
    tips: list[str] = []
    for t in tasks:
        label = t.task if len(t.task) <= 60 else t.task[:57] + "…"
        if t.runs >= 3 and t.pass_rate < DEFAULTS["low_pass_rate"]:
            tips.append(
                f"`{label}`: pass rate {t.pass_rate:.0%} over {t.runs} runs — write the "
                "contract as tests first and hand the rig 'make these tests pass'; prose specs "
                "are where it fails."
            )
        if t.avg_rounds > DEFAULTS["high_avg_rounds"]:
            tips.append(
                f"`{label}`: averages {t.avg_rounds:.1f} rounds — either raise --budget or "
                "split the task; a round-2 rescue means the first proposal is too broad."
            )
        if t.avg_variant_s > DEFAULTS["slow_variant_s"]:
            tips.append(
                f"`{label}`: variants average {t.avg_variant_s:.0f}s (slowest {t.slowest_variant_s:.0f}s) "
                "— set --variant-timeout and try --parallel 2."
            )
        if t.timeouts:
            tips.append(f"`{label}`: {t.timeouts} variant(s) hit the timeout — the task is too big for one run.")
        if t.failure_checks.get("tests_lost") or t.failure_checks.get("tests_skipped"):
            tips.append(
                f"`{label}`: a trial deleted or skipped tests — the baseline guard caught it; "
                "check whether the prompt invites 'fixing' the suite."
            )
        if len(t.models) > 1:
            tips.append(f"`{label}`: {len(t.models)} models probed — fleet/ladder is active.")
        for model, probes in sorted(t.models.items()):
            passes = t.model_passes.get(model, 0)
            if probes >= 3 and passes == 0:
                tips.append(
                    f"`{label}`: {model} went 0/{probes} — drop it from the fleet for this "
                    "kind of task or give it a smaller contract."
                )
    if not tips:
        tips.append("Nothing stands out: no low pass rates, no slow variants, no test tampering.")
    return tips


def render_text(report: RetroReport) -> str:
    lines = [f"dacode retro — last {report.since_days} day(s), {report.events} event(s)"]
    if not report.tasks:
        lines.append("  (no runs recorded)")
        return "\n".join(lines)
    lines.append(f"  {'runs':>4} {'pass':>5} {'rounds':>6} {'avg s':>7} {'slow s':>7}  task")
    for t in report.tasks:
        label = t.task if len(t.task) <= 56 else t.task[:53] + "…"
        lines.append(
            f"  {t.runs:>4} {t.pass_rate:>5.0%} {t.avg_rounds:>6.1f} "
            f"{t.avg_variant_s:>7.0f} {t.slowest_variant_s:>7.0f}  {label}"
        )
    if any(len(t.models) > 1 for t in report.tasks):
        lines.append("\nBy model:")
        for t in report.tasks:
            for model, probes in sorted(t.models.items()):
                lines.append(
                    f"  {model:<44} {t.model_passes.get(model, 0):>2}/{probes:<2} pass"
                )
    lines.append("\nSuggestions:")
    for tip in report.suggestions:
        lines.append(f"  - {tip}")
    return "\n".join(lines)
