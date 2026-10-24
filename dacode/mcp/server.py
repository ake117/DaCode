"""dacode mcp — expose the rig's memory and run history over MCP (stdio).

The rig keeps two things worth sharing: the lessons it has written (vault notes)
and what actually happened in past runs (the runlog/state store). Other agents —
Hermes, Pi, an editor plugin — can read both through the Model Context Protocol
instead of duplicating the filesystem logic.

Deliberately stdlib-only: MCP over stdio is newline-delimited JSON-RPC 2.0, and a
few hundred lines with no dependency is easier to trust than a framework that
needs its own release cadence.

    dacode mcp --vault ~/Documents/ake_obsidian
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, TextIO

from dacode import retro, state

__all__ = ["PROTOCOL_VERSION", "MemoryServer", "TOOLS"]

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "dacode-memory"
SERVER_VERSION = "0.3.0"


def _schema(properties: dict[str, Any], required: Iterable[str] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "memory_search",
        "description": (
            "Search DaCode's lessons (vault notes written after successful runs) for "
            "guidance relevant to a task. Returns title, snippet, path and score."
        ),
        "inputSchema": _schema(
            {
                "query": {"type": "string", "description": "what you are trying to do"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
            required=["query"],
        ),
    },
    {
        "name": "run_history",
        "description": (
            "Full-text search over past runs (task text, variants, picks). Use it to see "
            "whether a similar task has been attempted and how it ended."
        ),
        "inputSchema": _schema(
            {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            required=["query"],
        ),
    },
    {
        "name": "failures",
        "description": "Recent failed variants with their scores, optionally filtered by task text.",
        "inputSchema": _schema(
            {
                "task": {"type": "string", "description": "substring of the task text"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            }
        ),
    },
    {
        "name": "stats",
        "description": "Counts, pass rate, average/slowest variant time and skipped tests for the store.",
        "inputSchema": _schema({}),
    },
    {
        "name": "retro",
        "description": (
            "The rig's own retrospective: pass rate, rounds, per-model results and concrete "
            "suggestions for the last N days."
        ),
        "inputSchema": _schema(
            {
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 14},
                "task": {"type": "string", "description": "substring filter"},
            }
        ),
    },
]


class MemoryServer:
    """JSON-RPC handler for the MCP tools above.

    ``handle`` is pure: give it one request dict, get one response dict (or None
    for notifications). ``serve`` is the stdio loop.
    """

    def __init__(self, *, vault: str | Path | None = None, semantic: bool | str = "auto") -> None:
        self.vault = Path(vault).expanduser() if vault else None
        self.semantic = semantic
        self._memory = None

    # -- dependencies ------------------------------------------------------
    def memory(self):
        if self._memory is None and self.vault is not None:
            from dacode.memory import VaultMemory

            self._memory = VaultMemory(self.vault, semantic=self.semantic)
        return self._memory

    # -- JSON-RPC ----------------------------------------------------------
    def handle(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict):
            return _error(None, -32600, "invalid request: expected a JSON object")

        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or {}

        if not isinstance(method, str):
            return _error(request_id, -32600, "invalid request: missing method")

        if method.startswith("notifications/"):
            return None

        if method == "initialize":
            return _ok(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })
        if method == "ping":
            return _ok(request_id, {})
        if method == "tools/list":
            return _ok(request_id, {"tools": TOOLS})
        if method == "tools/call":
            return self._call_tool(request_id, params)
        return _error(request_id, -32601, f"method not found: {method}")

    def _call_tool(self, request_id: Any, params: Any) -> dict[str, Any]:
        if not isinstance(params, dict):
            return _error(request_id, -32602, "invalid params: expected an object")
        name = params.get("name")
        if not isinstance(name, str):
            return _error(request_id, -32602, "invalid params: tool name must be a string")
        args = params.get("arguments") or {}
        if not isinstance(args, dict):
            return _error(request_id, -32602, "invalid params: arguments must be an object")
        handler = {
            "memory_search": self._tool_memory_search,
            "run_history": self._tool_run_history,
            "failures": self._tool_failures,
            "stats": self._tool_stats,
            "retro": self._tool_retro,
        }.get(name)
        if handler is None:
            return _error(request_id, -32602, f"invalid params: unknown tool {name!r}")
        try:
            payload = handler(args)
        except Exception as exc:  # noqa: BLE001 - report it to the caller, never crash the server
            return _ok(request_id, _content(f"{type(exc).__name__}: {exc}", is_error=True))
        return _ok(request_id, _content(payload))

    # -- tools -------------------------------------------------------------
    def _tool_memory_search(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        memory = self.memory()
        if memory is None:
            return {"hits": [], "note": "no vault configured; start the server with --vault PATH"}
        limit = _int(args.get("limit"), 5, 1, 20)
        hits = memory.retrieve(query, limit=limit)
        return {
            "hits": [
                {
                    "title": hit.title,
                    "snippet": hit.snippet,
                    "path": str(hit.path),
                    "score": round(float(hit.score), 3),
                }
                for hit in hits
            ]
        }

    def _tool_run_history(self, args: dict[str, Any]) -> Any:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = _int(args.get("limit"), 10, 1, 50)
        return {"results": state.search(query, limit=limit)}

    def _tool_failures(self, args: dict[str, Any]) -> Any:
        task = args.get("task")
        limit = _int(args.get("limit"), 20, 1, 100)
        return {"failures": state.failures(task if isinstance(task, str) else None, limit=limit)}

    def _tool_stats(self, args: dict[str, Any]) -> Any:  # noqa: ARG002 - no arguments
        return state.stats()

    def _tool_retro(self, args: dict[str, Any]) -> Any:
        days = _int(args.get("days"), 14, 1, 365)
        task = args.get("task")
        return retro.build_report(
            since_days=days,
            task_filter=task if isinstance(task, str) and task else None,
        ).to_dict()

    # -- stdio loop --------------------------------------------------------
    def serve(self, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
        reader: TextIO = stdin if stdin is not None else sys.stdin
        writer: TextIO = stdout if stdout is not None else sys.stdout
        for line in reader:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                _write(writer, _error(None, -32700, f"parse error: {exc}"))
                continue
            response = self.handle(request)
            if response is not None:
                _write(writer, response)


def _content(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _write(stdout: TextIO, payload: dict[str, Any]) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stdout.flush()


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))
