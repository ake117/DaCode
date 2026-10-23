"""Append-only run log — the labeled dataset for judge evaluation.

Every probe, compose pick, and run summary lands as one JSON line in
``DACODE_RUNLOG`` (default ``~/.local/state/dacode/runlog.jsonl``; set the
variable to ``off`` to disable). The file feeds ``dacode judge-eval``,
which replays Compose picks through Jev and scores agreement against the
gate-verified winner. Recording never fails a run: errors go to stderr.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

__all__ = ["default_path", "record", "load_events"]


def default_path() -> Path:
    return Path("~/.local/state/dacode/runlog.jsonl").expanduser()


def _path() -> Path | None:
    raw = os.environ.get("DACODE_RUNLOG")
    if raw is not None:
        if raw.lower() == "off":
            return None
        return Path(raw).expanduser()
    return default_path()


def record(event: dict) -> None:
    """Append one JSON line (timestamped); never raises."""
    try:
        path = _path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        event = {"ts": time.time(), **event}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[runlog] record failed: {exc}", file=sys.stderr)


def load_events(path: str | os.PathLike | None = None) -> list[dict]:
    """Read all events; malformed lines are skipped, not fatal."""
    target = Path(path).expanduser() if path else _path()
    if target is None or not target.exists():
        return []
    events = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
