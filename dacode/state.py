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
import os
import sqlite3
import threading
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
    exit_code INTEGER,
    elapsed_s REAL,
    tests_skipped INTEGER,
    model TEXT
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
    parent = target.parent
    created = not parent.exists()
    parent.mkdir(parents=True, exist_ok=True)
    if created:
        # The runlog is 0700 on every write; the state database used to inherit the
        # umask here, so a machine with DACODE_RUNLOG=off got a world-readable
        # directory holding every recorded task (audit, Oct 2026). Only chmod a
        # directory we just created — never a shared parent.
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass
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


def _migrate(con) -> None:
    """Add columns introduced after a store was first created."""
    wanted = {
        "variants": {
            "elapsed_s": "REAL",
            "tests_skipped": "INTEGER",
            "model": "TEXT",
        },
        "runs": {"elapsed_s": "REAL"},
    }
    for table, columns in wanted.items():
        existing = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns.items():
            if name not in existing:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")


#: One writer at a time: --parallel probes would otherwise race on executescript
#: and on the ALTER TABLE in _migrate().
_INGEST_LOCK = threading.Lock()


def ingest(event: dict) -> None:
    """Mirror one runlog event into the store; never raises."""
    try:
        with _INGEST_LOCK:
            con = _connect()
            if con is None:
                return
            _do_ingest(con, event)
    except sqlite3.Error as exc:
        print(f"[state] ingest failed: {exc}", file=sys.stderr)


def _do_ingest(con, event: dict) -> None:
    try:
        with con:
            _migrate(con)
            kind = event.get("type")
            ts = float(event.get("ts") or time.time())
            task = str(event.get("task") or "")
            if kind == "run":
                cur = con.execute(
                    "INSERT INTO runs(ts, task, rounds, passed, needs_human_review,"
                    " best_id, best_score, elapsed_s) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        ts, task, event.get("rounds"), _flag(event.get("passed")),
                        _flag(event.get("needs_human_review")),
                        event.get("best_id"), event.get("best_score"),
                        event.get("elapsed_s"),
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
                    " tests_passed, tests_total, critique_passed, exit_code,"
                    " elapsed_s, tests_skipped, model)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        ts, task, event.get("variant_id"), event.get("label"),
                        event.get("score"), event.get("tests_passed"),
                        event.get("tests_total"), _flag(event.get("critique_passed")),
                        event.get("exit_code"), event.get("elapsed_s"),
                        event.get("tests_skipped"), event.get("model"),
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
            like = f"%{query.replace('%', '').replace('_', '')}%"  # no wildcards from input
            rows = con.execute(
                "SELECT kind, task, label, detail, ts FROM ("
                "  SELECT 'run' AS kind, task, '' AS label,"
                "         'passed=' || passed AS detail, ts FROM runs"
                "   WHERE task LIKE ?"
                "  UNION ALL"
                "  SELECT 'variant', task, label,"
                "         'id=' || COALESCE(variant_id,'') || ' score=' || COALESCE(score,''), ts"
                "    FROM variants WHERE task LIKE ? OR label LIKE ? OR variant_id LIKE ?"
                "  UNION ALL"
                "  SELECT 'pick', task, labels,"
                "         'chose=' || COALESCE(chosen_id,'') || ' by=' || COALESCE(chooser,''), ts"
                "    FROM picks WHERE task LIKE ? OR chosen_id LIKE ? OR chooser LIKE ?)"
                " ORDER BY ts DESC LIMIT ?",
                (like, like, like, like, like, like, like, limit),
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
            "avg_variant_s": round(con.execute(
                "SELECT COALESCE(AVG(elapsed_s), 0) FROM variants WHERE elapsed_s IS NOT NULL"
            ).fetchone()[0], 1),
            "slowest_variant_s": round(con.execute(
                "SELECT COALESCE(MAX(elapsed_s), 0) FROM variants"
            ).fetchone()[0], 1),
            "tests_skipped": one("SELECT COALESCE(SUM(tests_skipped), 0) FROM variants"),
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
