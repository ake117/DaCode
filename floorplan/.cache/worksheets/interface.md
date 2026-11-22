# Worksheet interface: ทางเข้าของผู้ใช้
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: จุดที่คนหรือ agent เรียกใช้: คำสั่งบน terminal และช่องทางที่ให้ผู้ช่วย AI ภายนอกส่งงานเข้ามาทำต่อ
Write to: floorplan/descriptions/interface.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it. Values that might be secret are shown as «hidden».

## dacode/__init__.py  (12 loc, python)
doc: DaCode — The Ultimate Autonomous Engineering Rig.
imported by: nothing (no file imports it, sends it web requests or names it)
  code (the whole file, 18 lines):
```
"""DaCode — The Ultimate Autonomous Engineering Rig.

A 5-layer coding-agent rig that combines:

  1. Semantic Vault Memory   (dacode.memory)     — retrieve lessons, ingest new ones
  2. Harness² Optimizer      (dacode.harness)    — Propose-Probe-Compose recursion
  3. Executor                (dacode.executor)   — Pi coding agent / script / stub
  4. pstack Discipline       (dacode.discipline) — adversarial critic + real checks
  5. Isolated Git Sandbox    (dacode.sandbox)    — per-task worktree + checkpoints

The entry point is :class:`dacode.orchestrator.DaCodeRig`.
"""

from __future__ import annotations

__version__ = "0.8.0"

__all__ = ["__version__"]
```

## dacode/cli.py  (429 loc, python)
doc: DaCode command-line interface.
defines: build_parser(); main()
uses: ตัวจัดการงาน ×6, ตรวจคุณภาพงาน ×3, ค่าตั้งระบบ ×2, ความจำของโปรเจกต์ ×2, ช่องคุยกับโมเดล
named in: skills/dacode/scripts/pack_for_web_audit.py line 53

## dacode/mcp/__init__.py  (3 loc, python)
doc: MCP server exposing DaCode memory + run history over stdio.
uses: ทางเข้าของผู้ใช้
used by: ทางเข้าของผู้ใช้
imported by: dacode/cli.py
  code (the whole file, 5 lines):
```
"""MCP server exposing DaCode memory + run history over stdio."""

from dacode.mcp.server import PROTOCOL_VERSION, MemoryServer, TOOLS

__all__ = ["PROTOCOL_VERSION", "MemoryServer", "TOOLS"]
```

## dacode/mcp/server.py  (237 loc, python)
doc: dacode mcp — expose the rig's memory and run history over MCP (stdio).
defines: MemoryServer (JSON-RPC handler for the MCP tools above.)
uses: ตัวจัดการงาน ×2, ความจำของโปรเจกต์
used by: ทางเข้าของผู้ใช้
imported by: dacode/mcp/__init__.py
