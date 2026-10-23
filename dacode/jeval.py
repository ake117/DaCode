"""Replay recorded Compose picks through Jev and score agreement.

Ground truth = the variant the rig picked after the critic gate verified it
(``passed=True`` on the winning row). Jev sees the same state and criteria
the compose judge sees; the agreement rate tells us whether the judge may
keep its seat. This is measurement, not verdicts.
"""

from __future__ import annotations

from dacode.judgment import JevJudge, SystemOneError
from dacode.runlog import load_events

__all__ = ["collect_cases", "evaluate", "summarize"]


def collect_cases(events: list[dict]) -> list[dict]:
    """Compose events whose recorded winner passed the gate, with ≥2 options."""
    cases = []
    for event in events:
        if event.get("type") != "compose":
            continue
        table = event.get("table") or []
        winner_id = event.get("chosen_id")
        winner = next((row for row in table if row.get("id") == winner_id), None)
        if not winner or not winner.get("passed"):
            continue  # only gate-verified winners are ground truth
        if len(table) < 2:
            continue  # nothing to decide
        cases.append({
            "task": event.get("task", ""),
            "table": table,
            "winner_id": winner_id,
            "ts": event.get("ts"),
        })
    return cases


def _criteria(table: list[dict]) -> dict[str, str]:
    return {
        row["id"]: (
            f"label={row.get('label')!r}; score={row.get('score')}; "
            f"tests={row.get('tests_passed')}/{row.get('tests_total')}; "
            f"passed={row.get('passed')}"
        )
        for row in table
    }


def evaluate(
    cases: list[dict],
    judge: JevJudge | None = None,
    *,
    limit: int | None = None,
) -> dict:
    """Ask Jev each case's Compose question; compare with the gate winner."""
    judge = judge or JevJudge()
    rows = cases[:limit] if limit else cases
    agree = disagree = no_confidence = errors = 0
    details: list[dict] = []
    for case in rows:
        state = (
            f"Task:\n{case['task']}\n\n"
            "Probed harness variants (deterministic score order, best first):\n"
            + "\n".join(
                f"- id={row['id']} label={row.get('label')!r} score={row.get('score')} "
                f"tests={row.get('tests_passed')}/{row.get('tests_total')} "
                f"passed={row.get('passed')}"
                for row in case["table"]
            )
        )
        try:
            pick, confidence = judge.choice(
                state=state,
                instructions=(
                    "Which probed harness variant is the single best implementation "
                    "of the task? Prefer passing tests, then fewer critique errors, "
                    "then higher score. Answer with the variant id."
                ),
                criteria=_criteria(case["table"]),
                min_confidence=0.0,  # evaluation counts every answer
            )
        except SystemOneError as exc:
            errors += 1
            details.append({"task": case["task"], "outcome": "error", "error": str(exc)})
            continue
        if pick is None:
            no_confidence += 1
            outcome = "no_confidence"
        elif pick == case["winner_id"]:
            agree += 1
            outcome = "agree"
        else:
            disagree += 1
            outcome = "disagree"
        details.append({
            "task": case["task"],
            "outcome": outcome,
            "jev": pick,
            "gate_winner": case["winner_id"],
            "confidence": confidence,
        })
    decided = agree + disagree
    rate = (agree / decided) if decided else None
    return {
        "total": len(rows),
        "agree": agree,
        "disagree": disagree,
        "no_confidence": no_confidence,
        "errors": errors,
        "agreement_rate": rate,
        "details": details,
    }


def summarize(report: dict) -> str:
    lines = [
        "=" * 62,
        "  Jev judge evaluation — agreement with the critic gate",
        "=" * 62,
        f"  cases        : {report['total']}",
        f"  agree        : {report['agree']}",
        f"  disagree     : {report['disagree']}",
        f"  no confidence: {report['no_confidence']}",
        f"  errors       : {report['errors']}",
        "  agreement    : "
        + (f"{report['agreement_rate']:.0%}" if report["agreement_rate"] is not None else "n/a"),
    ]
    for d in report["details"]:
        if d.get("outcome") != "agree":
            lines.append(f"  ! {d}")
    lines.append("=" * 62)
    return "\n".join(lines)
