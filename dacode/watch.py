"""`dacode watch` — a live, read-only TUI over the run log.

The rig is silent while it works: a run takes minutes and the terminal shows
nothing until the final banner. This viewer tails the run log (the same JSONL
the run recorder writes) and repaints a small dashboard — the in-progress run,
its probes and findings, the finished runs below it.

It is a window, not a control surface. It reads one file and never writes
anything: the gate owns verdicts, the orchestrator owns state, and a monitor
that could reach back into either would be a second place to disagree.
"""

from __future__ import annotations

import select
import sys
import termios
import time
import tty
from pathlib import Path

from .runlog import current_path, default_path, load_events

MAX_EVENTS = 5000  # render budget; a log beyond this outgrew the TUI
WIDTH = 78


def split_runs(events: list[dict]) -> tuple[list[list[dict]], list[dict]]:
    """Group the stream into finished run blocks, plus the trailing open block.

    A ``run`` event closes its block; everything after the last closed block is
    the run in progress (possibly empty).
    """
    blocks: list[list[dict]] = []
    current: list[dict] = []
    for event in events:
        current.append(event)
        if event.get("type") == "run":
            blocks.append(current)
            current = []
    return blocks, current


def _hhmmss(ts: float | None) -> str:
    if not ts:
        return "--:--:--"
    return time.strftime("%H:%M:%S", time.localtime(ts))


def _short_task(task: str | None, width: int = 52) -> str:
    if not task:
        return "(untitled)"
    return task if len(task) <= width else task[: width - 1] + "…"


def render(events: list[dict], history: int = 10,
           log_name: str | None = None) -> str:
    """The whole dashboard as one string — pure so tests can assert on it."""
    events = events[-MAX_EVENTS:]
    blocks, current = split_runs(events)
    runs = [b for b in blocks if b and b[-1].get("type") == "run"]

    total_runs = len(runs)
    passed = sum(1 for b in runs if b[-1].get("passed"))
    probes = sum(1 for e in events if e.get("type") == "probe")
    rate = f"{(100 * passed / total_runs):.0f}%" if total_runs else "—"

    lines: list[str] = []
    lines.append(f"DaCode watch · {log_name or 'runlog.jsonl'} · "
                 f"{total_runs} runs · {passed} passed ({rate}) · "
                 f"{probes} probes · [q] quit")
    lines.append("─" * WIDTH)

    if current:
        started = current[0].get("ts")
        task = next((e.get("task") for e in current if e.get("task")), None)
        lines.append(f"▶ RUN IN PROGRESS  {_hhmmss(started)}  "
                     f"{_short_task(task)}")
        for event in current:
            if event.get("type") == "probe":
                findings = event.get("findings") or []
                ok = event.get("exit_code") == 0 and not findings
                mark = "✓" if ok else "✗"
                detail = ", ".join(map(str, findings)) if findings else "clean"
                total = event.get("tests_total")
                count = (f"tests {event.get('tests_passed')}/{total}"
                         if total is not None else "tests ?")
                lines.append(
                    f"   {mark} {event.get('variant_id', '?'):<4} "
                    f"{(event.get('label') or ''):<26} {count:<8} "
                    f"exit {event.get('exit_code')} "
                    f"{event.get('elapsed_s', 0):.1f}s  {detail}")
            elif event.get("type") == "compose":
                lines.append(f"   · compose  chooser={event.get('chooser')} "
                             f"picked {event.get('chosen_id')}")
        lines.append("─" * WIDTH)

    for block in reversed(runs[-history:]):
        done = block[-1]
        if done.get("passed"):
            mark = "✓"
        elif done.get("needs_human_review"):
            mark = "⚑"
        else:
            mark = "✗"
        best = done.get("best_id") or "—"
        label = next((e.get("label") for e in block
                      if e.get("type") == "probe" and e.get("variant_id") == best
                      and e.get("label")), "")
        score = done.get("best_score")
        score_s = f" (score {score:g})" if isinstance(score, (int, float)) else ""
        flag = "  needs-human" if done.get("needs_human_review") else ""
        lines.append(
            f"{mark} {_hhmmss(done.get('ts'))}  "
            f"{'PASS' if done.get('passed') else 'FAIL'}  "
            f"rounds {done.get('rounds', '?')}  best {best}"
            f"{f' [{label}]' if label else ''}{score_s}"
            f"  {_short_task(done.get('task'))}{flag}")

    if not runs and not current:
        lines.append("(no runs recorded yet — the log is empty or missing)")
    return "\n".join(lines)


def follow(path: Path, interval: float = 2.0):
    """Yield between repaints until the file stops growing or 'q'/Ctrl-C.

    Read-only on the watched file; the only input consumed is the quit key.
    """
    last_size = -1
    while True:
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        yield size != last_size
        fd = sys.stdin.fileno()
        try:
            ready, _, _ = select.select([fd], [], [], interval)
            if not ready:
                continue
            old = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                key = sys.stdin.read(1)
                if key in {"q", "Q", "\x03"} or key == "":
                    return  # a keypress quits; a closed stdin (EOF) ends too
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except (OSError, ValueError, termios.error):
            # no interactive tty (piped, CI) — poll without the quit key
            time.sleep(interval)


def watch(path: Path | None = None, interval: float = 2.0, history: int = 10,
          once: bool = False) -> str:
    """Repaint loop; returns the final frame (tests and ``--once`` assert on it)."""
    path = path or current_path()
    frame = render(load_events(path), history=history)
    if once:
        return frame
    out = sys.stdout
    try:
        for _ in follow(path, interval=interval):
            frame = render(load_events(path), history=history)
            out.write("\033[2J\033[H" + frame + "\n")
            out.flush()
    except KeyboardInterrupt:
        pass
    return frame


__all__ = ["render", "split_runs", "watch", "follow", "default_path"]
