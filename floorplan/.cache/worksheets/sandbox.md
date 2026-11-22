# Worksheet sandbox: กรงทรายกันความเสียหาย
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: ล้อมการแก้โค้ดให้อยู่ในวงจำกัด: จำกัดการเข้าถึงไฟล์ เครือข่าย และเวลาทำงาน เพื่อไม่ให้คำสั่งที่ผิดลามออกไปนอกโปรเจกต์
Write to: floorplan/descriptions/sandbox.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it.

## dacode/sandbox/__init__.py  (196 loc, python)
doc: Layer 5 — Isolated Git sandbox (worktrees + checkpoints).
defines: GitError (A git command exited non-zero.); SandboxError (The sandbox could not perform the requested operation.); WorktreeInfo; GitSandbox (Manage per-task git worktrees for isolated experiments.)
used by: ตัวจัดการงาน ×2, ทางเข้าของผู้ใช้, ปรับปรุงคำสั่งให้ดีขึ้น
imported by: dacode/cli.py, dacode/harness/optimizer.py, dacode/kanban.py, dacode/orchestrator.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 44

## dacode/sandbox/bwrap.py  (490 loc, python)
doc: bwrap isolation for trials — the worktree protects the repo, this protects the host.
defines: IsolationUnavailable (bwrap is not installed (or cannot create namespaces) on this host.); IsolationPolicy (How much of the host a trial may see.); available() (True when bwrap is present *and* can actually create namespaces.); bwrap_version(); allowed_env() (The environment a trial may see: base + allow-list, and network keys only if permitted.); exposes_home() (Would mounting ``path`` re-expose the home directory?); wrap_command() (Prefix ``command`` with a bwrap invocation implementing ``policy``.); describe() (One line for `dacode layers` and run summaries.); interpreter_binds() (Everything the sandbox needs to start the test interpreter.); interpreter_root() (The directory holding the interpreter in a test command, if it is an absolute path.)
used by: ตัวลงมือแก้โค้ด ×3, ตัวจัดการงาน ×2, ตรวจคุณภาพงาน
imported by: dacode/discipline/critic.py, dacode/executor/agy.py, dacode/executor/pi.py, dacode/executor/script.py, +2 more
named in: dacode/redact.py line 48, skills/dacode/scripts/pack_for_web_audit.py line 43
