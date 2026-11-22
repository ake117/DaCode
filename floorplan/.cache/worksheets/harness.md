# Worksheet harness: ปรับปรุงคำสั่งให้ดีขึ้น
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: เก็บชุดคำสั่งที่ใช้สอนงานไว้ แล้วลองปรับให้ได้ผลดีขึ้นเรื่อย ๆ จากผลของรอบก่อน
Write to: floorplan/descriptions/harness.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it. Values that might be secret are shown as «hidden».

## dacode/harness/__init__.py  (9 loc, python)
doc: Layer 2 — Harness² Optimizer (Propose–Probe–Compose recursion).
uses: ปรับปรุงคำสั่งให้ดีขึ้น ×2
imported by: nothing (no file imports it, sends it web requests or names it)
  code (the whole file, 13 lines):
```
"""Layer 2 — Harness² Optimizer (Propose–Probe–Compose recursion).

Mirrors the Google Research Harness² idea: instead of hand-tuning the prompt
when a task fails, the rig *proposes* several harness variants, *probes* each in
an isolated sandbox, and *composes* the winner — no ground-truth labels needed.
"""

from __future__ import annotations

from dacode.harness.models import HarnessResult, HarnessVariant, ProbeResult
from dacode.harness.optimizer import HarnessOptimizer

__all__ = ["HarnessOptimizer", "HarnessVariant", "ProbeResult", "HarnessResult"]
```

## dacode/harness/models.py  (65 loc, python)
doc: Data model for the Harness² loop.
defines: HarnessVariant (One candidate configuration of the *harness* (not the model).); ProbeResult (What happened when a variant ran in its sandbox trial.); HarnessResult (The outcome of a full ``HarnessOptimizer.run``.)
used by: ตัวลงมือแก้โค้ด ×4, ปรับปรุงคำสั่งให้ดีขึ้น ×2, ทางเข้าของผู้ใช้, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/executor/agy.py, dacode/executor/base.py, dacode/executor/pi.py, +4 more

## dacode/harness/optimizer.py  (653 loc, python)
doc: The Harness² optimizer: Propose → Probe → Compose.
defines: HarnessOptimizer
uses: ตรวจคุณภาพงาน ×3, ตัวจัดการงาน, ปรับปรุงคำสั่งให้ดีขึ้น, ตัวลงมือแก้โค้ด, ช่องคุยกับโมเดล
used by: ตัวลงมือแก้โค้ด, ปรับปรุงคำสั่งให้ดีขึ้น, ตัวจัดการงาน
imported by: dacode/executor/agy.py, dacode/harness/__init__.py, dacode/orchestrator.py
