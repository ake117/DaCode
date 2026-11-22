# Worksheet discipline: ตรวจคุณภาพงาน
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: ตรวจงานที่ได้ว่าตรงตามที่ขอหรือไม่ ด้วยการให้โมเดลอีกตัววิจารณ์และให้คะแนนตามเกณฑ์ แล้วตัดสินว่าผ่านหรือต้องแก้
Write to: floorplan/descriptions/discipline.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it. Values that might be secret are shown as «hidden».

## dacode/discipline/__init__.py  (12 loc, python)
doc: Layer 4 — pstack Discipline (adversarial critic + real checks).
uses: ตรวจคุณภาพงาน ×2
imported by: nothing (no file imports it, sends it web requests or names it)
  code (the whole file, 17 lines):
```
"""Layer 4 — pstack Discipline (adversarial critic + real checks).

Implements the blueprint's *Discipline & Critique* stage with automated,
runnable checks rather than vibes:

* **Test Behavior, Not Implementation** (pstack #4) — AST scan for tautological
  or weak assertions in Python tests.
* **Prove It Works** (pstack #9) — actually execute the test command and
  require a clean exit; a report without a run is not a report.
"""

from __future__ import annotations

from dacode.discipline.checks import Finding, check_python_test
from dacode.discipline.critic import CritiqueReport, PstackCritic

__all__ = ["Finding", "check_python_test", "CritiqueReport", "PstackCritic"]
```

## dacode/discipline/checks.py  (205 loc, python)
doc: AST-based test-quality checks — pstack principle #4.
defines: Finding; check_test_source() (Check a single test file's *source text* and return findings.); check_python_test() (Check a test *file* on disk and return findings.)
used by: ตรวจคุณภาพงาน ×2
imported by: dacode/discipline/__init__.py, dacode/discipline/critic.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 39

## dacode/discipline/critic.py  (1.2k loc, python)
doc: The pstack Critic — combines static checks with a real test run.
defines: CritiqueReport; PstackCritic (Review a workspace against pstack principles.)
uses: ตรวจคุณภาพงาน, กรงทรายกันความเสียหาย
used by: ตรวจคุณภาพงาน, ปรับปรุงคำสั่งให้ดีขึ้น, ตัวจัดการงาน, ชุดคำสั่งสอน agent
imported by: dacode/discipline/__init__.py, dacode/harness/optimizer.py, dacode/orchestrator.py, skills/dacode/scripts/gate-integrity-probe.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 38

## dacode/jeval.py  (121 loc, python)
doc: Replay recorded Compose picks through Jev and score agreement.
defines: collect_cases() (Compose events whose recorded winner passed the gate, with ≥2 options.); evaluate() (Ask Jev each case's Compose question; compare with the gate winner.); summarize()
uses: ตรวจคุณภาพงาน, ตัวจัดการงาน
used by: ทางเข้าของผู้ใช้
imported by: dacode/cli.py

## dacode/judgment.py  (119 loc, python)
doc: Jev (TypeSafe System One) judgments for DaCode.
defines: SystemOneError (Raised when a System One request cannot be completed or parsed.); JevAnswer (A Choice answer: the picked option, its confidence, and the spread.); JevJudge (Bounded picks via a TypeSafe System One Choice question.); build_judge() (Build the compose judge — ``None`` (off) unless ``kind == "jev"``.)
used by: ทางเข้าของผู้ใช้, ปรับปรุงคำสั่งให้ดีขึ้น, ตรวจคุณภาพงาน, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/harness/optimizer.py, dacode/jeval.py, dacode/orchestrator.py

## dacode/redact.py  (105 loc, python)
doc: Redaction of credentials on their way into anything that persists.
defines: redact() (Replace credentials in ``text`` with :data:`REDACTED`.); redact_event() (Redact every string in an event, recursively.); sanitize_terminal() (Strip terminal escape and control sequences from single-line UI text.)
used by: ตัวจัดการงาน ×4, ทางเข้าของผู้ใช้, ปรับปรุงคำสั่งให้ดีขึ้น, ความจำของโปรเจกต์
imported by: dacode/cli.py, dacode/harness/optimizer.py, dacode/kanban.py, dacode/memory/__init__.py, +3 more
named in: skills/dacode/scripts/pack_for_web_audit.py line 56
