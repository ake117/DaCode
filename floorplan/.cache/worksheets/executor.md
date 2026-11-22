# Worksheet executor: ตัวลงมือแก้โค้ด
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: เลือกวิธีทำงานตามเครื่องมือที่มีในเครื่อง: เรียก agent ภายนอก หรือเขียนสคริปต์เอง แล้วส่งผลลัพธ์กลับพร้อมหลักฐานว่าแก้อะไรไป
Write to: floorplan/descriptions/executor.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it. Values that might be secret are shown as «hidden».

## dacode/executor/__init__.py  (11 loc, python)
doc: Layer 3 — Executors: the thing that actually changes code in a trial.
uses: ตัวลงมือแก้โค้ด ×3
imported by: nothing (no file imports it, sends it web requests or names it)
  code (the whole file, 15 lines):
```
"""Layer 3 — Executors: the thing that actually changes code in a trial.

An executor receives a :class:`~dacode.harness.models.HarnessVariant` and a
workspace directory, does the work, and returns an :class:`ExecResult`.  The rig
does not care *how* the change happens — Pi, a raw script, or a test double all
satisfy the same protocol, which keeps the optimizer unit-testable.
"""

from __future__ import annotations

from dacode.executor.base import ExecResult, Executor
from dacode.executor.pi import PiExecutor
from dacode.executor.script import ScriptExecutor

__all__ = ["ExecResult", "Executor", "PiExecutor", "ScriptExecutor"]
```

## dacode/executor/agy.py  (225 loc, python)
doc: AgyExecutor — drive the Antigravity CLI (``agy``) non-interactively.
defines: AgyExecutor (Run one harness variant through ``agy -p`` inside the trial worktree.)
uses: ปรับปรุงคำสั่งให้ดีขึ้น ×2, ตัวลงมือแก้โค้ด, กรงทรายกันความเสียหาย
used by: ตัวจัดการงาน
imported by: dacode/orchestrator.py

## dacode/executor/base.py  (22 loc, python)
doc: Executor protocol and the shared result type.
defines: ExecResult; Executor (Runs one harness variant inside a workspace and reports the outcome.)
uses: ปรับปรุงคำสั่งให้ดีขึ้น
used by: ตัวลงมือแก้โค้ด ×4, ปรับปรุงคำสั่งให้ดีขึ้น
imported by: dacode/executor/__init__.py, dacode/executor/agy.py, dacode/executor/pi.py, dacode/executor/script.py, +1 more
named in: skills/dacode/scripts/pack_for_web_audit.py line 45

## dacode/executor/pi.py  (191 loc, python)
doc: PiExecutor — drive the Pi coding agent (``~/bin/pi``) non-interactively.
defines: provider_env() (The child environment, with provider-key aliases applied.); PiExecutor (Invoke the Pi coding agent as the change-making executor.)
uses: ตัวลงมือแก้โค้ด, กรงทรายกันความเสียหาย, ปรับปรุงคำสั่งให้ดีขึ้น
used by: ตัวลงมือแก้โค้ด, ตัวจัดการงาน
imported by: dacode/executor/__init__.py, dacode/orchestrator.py
named in: dacode/env.py line 64, dacode/sandbox/bwrap.py line 51, skills/dacode/scripts/pack_for_web_audit.py line 46, tests/test_env.py line 120

## dacode/executor/script.py  (82 loc, python)
doc: ScriptExecutor — run a fixed command inside the workspace.
defines: ScriptExecutor (Runs ``variant.payload['command']`` (str or list) in the workspace.)
uses: ตัวลงมือแก้โค้ด, กรงทรายกันความเสียหาย, ปรับปรุงคำสั่งให้ดีขึ้น
used by: ตัวลงมือแก้โค้ด, ตัวจัดการงาน
imported by: dacode/executor/__init__.py, dacode/orchestrator.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 47
