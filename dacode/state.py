"""SQLite local state store — a queryable history of runs, variants, and picks.

The JSONL run log (:mod:`dacode.runlog`) is the source of truth; every event is
mirrored into ``memory.db`` so history can be *queried*: which approaches
failed for a task, what scored best, who picked the winner. FTS5 with the
trigram tokenizer makes substring search work for Thai and English alike; when
FTS5 is unavailable, search degrades to ``LIKE``.

``DACODE_MEMORY_DB`` overrides the path (``off`` disables the store). Ingestion
never raises — history must not be able to fail a run. The database is derived
state: :func:`rebuild` recreates it from the run log at any time.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

__all__ = ["default_path", "ingest", "search", "stats", "failures", "rebuild"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    task TEXT NOT NULL,
    rounds INTEGER,
    passed INTEGER,
    needs_human_review INTEGER,
    best_id TEXT,
    best_score REAL
);
CREATE TABLE IF NOT EXISTS variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    task TEXT NOT NULL,
    variant_id TEXT,
    label TEXT,
    score REAL,
    tests_passed INTEGER,
    tests_total INTEGER,
    critique_passed INTEGER,
    exit_code INTEGER
);
CREATE TABLE IF NOT EXISTS picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    task TEXT NOT NULL,
    chosen_id TEXT,
    chooser TEXT,
    table_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task);
CREATE INDEX IF NOT EXISTS idx_variants_task ON variants(task);
CREATE INDEX IF NOT EXISTS idx_variants_passed ON variants(critique_passed);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS search_fts
USING fts5(kind, task, label, detail, ref_id UNINDEXED, ts UNINDEXED,
           tokenize='trigram');
"""


def default_path() -> Path:
    return Path("~/.local/state/dacode/memory.db").expanduser()


def _path() -> Path | None:
    raw = os.environ.get("DACODE_MEMORY_DB")
    if raw is not None:
        if raw.lower() == "off":
            return None
        return Path(raw).expanduser()
    return default_path()


def _connect() -> sqlite3.Connection | None:
    target = _path()
    if target is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(target), timeout=5.0)
    con.executescript(_SCHEMA)
    try:
        con.executescript(_FTS_SCHEMA)
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass  # no FTS5 in this build — search() falls back to LIKE
    return con


def _fts_ready(con: sqlite3.Connection) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='search_fts'"
    ).fetchone()
    return row is not None


def _flag(value) -> int:
    return 1 if value else 0


def _index(con, kind: str, task: str, label: str, detail: str, ref_id, ts: float) -> None:
    if not _fts_ready(con):
        return
    try:
        con.execute(
            "INSERT INTO search_fts(kind, task, label, detail, ref_id, ts)"
            " VALUES(?,?,?,?,?,?)",
            (kind, task, label, detail, str(ref_id), ts),
        )
    except sqlite3.OperationalError:
        pass


def ingest(event: dict) -> None:
    """Mirror one runlog event into the store; never raises."""
    try:
        con = _connect()
        if con is None:
            return
        with con:
            kind = event.get("type")
            ts = float(event.get("ts") or time.time())
            task = str(event.get("task") or "")
            if kind == "run":
                cur = con.execute(
                    "INSERT INTO runs(ts, task, rounds, passed, needs_human_review,"
                    " best_id, best_score) VALUES(?,?,?,?,?,?,?)",
                    (
                        ts, task, event.get("rounds"), _flag(event.get("passed")),
                        _flag(event.get("needs_human_review")),
                        event.get("best_id"), event.get("best_score"),
                    ),
                )
                _index(
                    con, "run", task, "",
                    f"passed={event.get('passed')} rounds={event.get('rounds')} "
                    f"best={event.get('best_id')} score={event.get('best_score')}",
                    cur.lastrowid, ts,
                )
            elif kind == "probe":
                cur = con.execute(
                    "INSERT INTO variants(ts, task, variant_id, label, score,"
                    " tests_passed, tests_total, critique_passed, exit_code)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        ts, task, event.get("variant_id"), event.get("label"),
                        event.get("score"), event.get("tests_passed"),
                        event.get("tests_total"), _flag(event.get("critique_passed")),
                        event.get("exit_code"),
                    ),
                )
                _index(
                    con, "variant", task, str(event.get("label") or ""),
                    f"score={event.get('score')} "
                    f"tests={event.get('tests_passed')}/{event.get('tests_total')} "
                    f"passed={event.get('critique_passed')}",
                    cur.lastrowid, ts,
                )
            elif kind == "compose":
                table = event.get("table") or []
                cur = con.execute(
                    "INSERT INTO picks(ts, task, chosen_id, chooser, table_json)"
                    " VALUES(?,?,?,?,?)",
                    (
                        ts, task, event.get("chosen_id"), event.get("chooser"),
                        json.dumps(table, ensure_ascii=False),
                    ),
                )
                labels = ", ".join(str(row.get("label")) for row in table)
                _index(
                    con, "pick", task, labels,
                    f"chose={event.get('chosen_id')} by={event.get('chooser')} "
                    f"options={labels}",
                    cur.lastrowid, ts,
                )
        con.close()
    except (sqlite3.Error, OSError, ValueError) as exc:
        print(f"[state] ingest failed: {exc}", file=sys.stderr)


def _fts_query(query: str) -> str:
    """Tokenize a user query into a safe FTS5 OR-expression."""
    tokens = [t for t in re.split(r"[^\w\u0E00-\u0E7F]+", query or "") if len(t) >= 3]
    return " OR ".join(f'"{t}"' for t in tokens)


def search(query: str, limit: int = 10) -> list[dict]:
    """Substring/phrase search over recorded runs, variants, and picks."""
    con = _connect()
    if con is None:
        return []
    try:
        expr = _fts_query(query)
        if expr and _fts_ready(con):
            rows = con.execute(
                "SELECT kind, task, label, detail, ts FROM search_fts"
                " WHERE search_fts MATCH ? ORDER BY ts DESC LIMIT ?",
                (expr, limit),
            ).fetchall()
        else:
            like = f"%{query}%"
            rows = con.execute(
                "SELECT 'row', task, '', '', ts FROM ("
                "  SELECT task, ts FROM runs WHERE task LIKE ?"
                "  UNION ALL SELECT task, ts FROM variants WHERE task LIKE ? OR label LIKE ?"
                "  UNION ALL SELECT task, ts FROM picks WHERE task LIKE ?)"
                " ORDER BY ts DESC LIMIT ?",
                (like, like, like, like, limit),
            ).fetchall()
        return [
            {"kind": k, "task": t, "label": lab, "detail": d, "ts": ts}
            for k, t, lab, d, ts in rows
        ]
    finally:
        con.close()


def stats() -> dict:
    """Counts and freshness of the local store."""
    con = _connect()
    if con is None:
        return {"enabled": False}
    try:
        one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "enabled": True,
            "path": str(_path()),
            "runs": one("SELECT COUNT(*) FROM runs"),
            "runs_passed": one("SELECT COUNT(*) FROM runs WHERE passed=1"),
            "tasks": one("SELECT COUNT(DISTINCT task) FROM runs"),
            "variants": one("SELECT COUNT(*) FROM variants"),
            "variants_failed": one("SELECT COUNT(*) FROM variants WHERE critique_passed=0"),
            "picks": one("SELECT COUNT(*) FROM picks"),
            "last_run_ts": one("SELECT MAX(ts) FROM runs"),
            "fts": _fts_ready(con),
        }
    finally:
        con.close()


def failures(task: str | None = None, limit: int = 20) -> list[dict]:
    """Approaches that failed the gate — do not retry these blindly."""
    con = _connect()
    if con is None:
        return []
    try:
        sql = (
            "SELECT ts, task, variant_id, label, score, tests_passed, tests_total"
            " FROM variants WHERE critique_passed=0"
        )
        args: list = []
        if task:
            sql += " AND task LIKE ?"
            args.append(f"%{task}%")
        sql += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        cols = ["ts", "task", "variant_id", "label", "score", "tests_passed", "tests_total"]
        return [dict(zip(cols, row)) for row in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def rebuild(events: list[dict] | None = None) -> int:
    """Recreate the store from the JSONL run log (the source of truth)."""
    from dacode.runlog import load_events

    events = load_events() if events is None else list(events)
    target = _path()
    if target is None:
        return 0
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(target) + suffix)
        if candidate.exists():
            candidate.unlink()
    for event in events:
        ingest(event)
    return len(events)
