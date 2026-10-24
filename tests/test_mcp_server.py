"""dacode mcp — the memory store over stdio JSON-RPC, testable without a socket."""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import pytest

from dacode.mcp import PROTOCOL_VERSION, TOOLS, MemoryServer


def _call(server: MemoryServer, name: str, arguments: dict | None = None, request_id: int = 2):
    response = server.handle({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })
    assert response is not None
    return response


def _payload(response: dict) -> dict:
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


@pytest.fixture()
def vault(tmp_path: Path) -> Path:
    note = tmp_path / "Projects" / "DaCode" / "Lessons" / "lesson.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        "---\ntitle: Baseline guard\n---\n\n"
        "A trial that deletes tests must fail the gate. Measure the baseline first.\n"
    )
    return tmp_path


def test_initialize_reports_the_protocol_and_tool_capability():
    server = MemoryServer()
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert response["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert response["result"]["serverInfo"]["name"] == "dacode-memory"


def test_tools_list_carries_schemas_for_every_tool():
    server = MemoryServer()
    response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = response["result"]["tools"]
    assert {t["name"] for t in tools} == {t["name"] for t in TOOLS}
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


def test_initialized_notification_gets_no_response():
    server = MemoryServer()
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_is_a_jsonrpc_error():
    server = MemoryServer()
    response = server.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert response["error"]["code"] == -32601


def test_unknown_tool_is_an_invalid_params_error():
    server = MemoryServer()
    response = _call(server, "delete_everything")
    assert response["error"]["code"] == -32602


def test_ping_answers():
    server = MemoryServer()
    assert server.handle({"jsonrpc": "2.0", "id": 4, "method": "ping"})["result"] == {}


def test_stats_tool_returns_the_store_counts(monkeypatch, tmp_path):
    monkeypatch.setenv("DACODE_MEMORY_DB", str(tmp_path / "memory.db"))
    from dacode import state

    state.ingest({
        "type": "run", "task": "t", "rounds": 1, "passed": True,
        "best_id": "v1", "best_score": 1.0, "elapsed_s": 3.0,
    })
    server = MemoryServer()
    payload = _payload(_call(server, "stats"))
    assert payload["runs"] == 1
    assert payload["runs_passed"] == 1


def test_memory_search_finds_a_lesson_without_an_embedder(vault):
    server = MemoryServer(vault=vault, semantic=False)
    payload = _payload(_call(server, "memory_search", {"query": "baseline tests deleted"}))
    titles = [hit["title"] for hit in payload["hits"]]
    assert titles == ["Baseline guard"]


def test_memory_search_without_a_vault_explains_itself():
    server = MemoryServer()
    payload = _payload(_call(server, "memory_search", {"query": "anything"}))
    assert payload["hits"] == []
    assert "--vault" in payload["note"]


def test_memory_search_rejects_an_empty_query():
    server = MemoryServer()
    response = _call(server, "memory_search", {"query": "   "})
    assert response["result"]["isError"] is True
    assert "query is required" in response["result"]["content"][0]["text"]


def test_run_history_reads_the_state_store(monkeypatch, tmp_path):
    monkeypatch.setenv("DACODE_MEMORY_DB", str(tmp_path / "memory.db"))
    from dacode import state

    state.ingest({
        "type": "run", "task": "make scoring anchors pass", "rounds": 1,
        "passed": True, "best_id": "v1", "best_score": 1.0,
    })
    server = MemoryServer()
    payload = _payload(_call(server, "run_history", {"query": "scoring"}))
    assert payload["results"], "the FTS index should find the run"


def test_failures_tool_returns_failed_variants(monkeypatch, tmp_path):
    monkeypatch.setenv("DACODE_MEMORY_DB", str(tmp_path / "memory.db"))
    from dacode import state

    state.ingest({
        "type": "probe", "task": "hard task", "variant_id": "v9", "label": "x",
        "score": 0.0, "tests_passed": 0, "tests_total": 3, "critique_passed": False,
        "exit_code": 1,
    })
    server = MemoryServer()
    payload = _payload(_call(server, "failures", {"task": "hard"}))
    assert payload["failures"][0]["variant_id"] == "v9"


def test_retro_tool_returns_the_report_shape(monkeypatch, tmp_path):
    log = tmp_path / "runlog.jsonl"
    log.write_text(json.dumps({
        "ts": time.time(), "type": "run", "task": "some task", "rounds": 2, "passed": False,
    }) + "\n")
    monkeypatch.setenv("DACODE_RUNLOG", str(log))
    server = MemoryServer()
    payload = _payload(_call(server, "retro", {"days": 7}))
    assert payload["since_days"] == 7
    assert payload["tasks"][0]["task"] == "some task"
    assert payload["suggestions"]


def test_serve_loops_over_stdio_and_reports_parse_errors(vault):
    server = MemoryServer(vault=vault, semantic=False)
    stdin = io.StringIO(
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        "not json at all\n"
        "\n"
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )
    stdout = io.StringIO()
    server.serve(stdin=stdin, stdout=stdout)

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert [line.get("id") for line in lines] == [1, None, 2]
    assert lines[1]["error"]["code"] == -32700
    assert lines[2]["result"]["tools"]


def test_serve_writes_one_json_object_per_line(tmp_path):
    server = MemoryServer()
    stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n')
    stdout = io.StringIO()
    server.serve(stdin=stdin, stdout=stdout)
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["jsonrpc"] == "2.0" for line in lines)
