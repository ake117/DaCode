# Worksheet orchestrator: ตัวจัดการงาน
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: รับงานเข้ามา ไล่ทีละขั้น จำสถานะไว้กลางทาง และบันทึกว่าแต่ละรอบทำอะไรไปบ้าง เพื่อให้รันต่อได้หรือย้อนดูได้
Write to: floorplan/descriptions/orchestrator.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it.

## dacode/kanban.py  (335 loc, python)
doc: Kanban worker — DaCode as one worker on a Hermes Kanban board.
defines: KanbanError (The board refused a verb (non-zero exit) — the caller decides what that means.); parse_gate() (The stripped content of the FIRST fenced block info-tagged exactly ``gate``.); CardOutcome (What one pass of the rig did to a card — the evidence for the board.); HermesKanban (Drive a Hermes Kanban board over a subprocess (injectable for tests).); work() (Claim one card, run it through the rig, report the outcome.); changed_files() (Files a trial workspace changed against ``base``; [] on any doubt.); make_rig_runner() (Turn a :class:`dacode.config.DaCodeConfig` into a ``run_card`` for :func:`work`.)
uses: ตัวจัดการงาน ×2, กรงทรายกันความเสียหาย ×2, ตรวจคุณภาพงาน, ค่าตั้งระบบ
used by: ทางเข้าของผู้ใช้
imported by: dacode/cli.py

## dacode/orchestrator.py  (245 loc, python)
doc: The DaCode rig — wires the five layers into the blueprint's lifecycle.
defines: LayerStatus; DaCodeRig
uses: ตรวจคุณภาพงาน ×3, ตัวลงมือแก้โค้ด ×3, ปรับปรุงคำสั่งให้ดีขึ้น ×2, กรงทรายกันความเสียหาย ×2, ค่าตั้งระบบ
used by: ทางเข้าของผู้ใช้, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/kanban.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 48

## dacode/retro.py  (200 loc, python)
doc: dacode retro — read the run recorder and say what to change.
defines: TaskRetro; RetroReport; build_report(); render_text()
uses: ตัวจัดการงาน
used by: ทางเข้าของผู้ใช้ ×2
imported by: dacode/cli.py, dacode/mcp/server.py

## dacode/runlog.py  (72 loc, python)
doc: Append-only run log — the labeled dataset for judge evaluation.
defines: default_path(); current_path() (The log in force right now (``DACODE_RUNLOG`` wins, else the default).); record() (Append one JSON line (timestamped); never raises.); load_events() (Read all events; malformed lines are skipped, not fatal.)
uses: ตัวจัดการงาน, ตรวจคุณภาพงาน
used by: ตัวจัดการงาน ×4, ทางเข้าของผู้ใช้, ปรับปรุงคำสั่งให้ดีขึ้น, ตรวจคุณภาพงาน
imported by: dacode/cli.py, dacode/harness/optimizer.py, dacode/jeval.py, dacode/kanban.py, +3 more
named in: skills/dacode/scripts/pack_for_web_audit.py line 55

## dacode/state.py  (323 loc, python)
doc: SQLite local state store — a queryable history of runs, variants, and picks.
defines: default_path(); ingest() (Mirror one runlog event into the store; never raises.); search() (Substring/phrase search over recorded runs, variants, and picks.); stats() (Counts and freshness of the local store.); failures() (Approaches that failed the gate — do not retry these blindly.); rebuild() (Recreate the store from the JSONL run log (the source of truth).)
uses: ตัวจัดการงาน
used by: ทางเข้าของผู้ใช้ ×2, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/mcp/server.py, dacode/runlog.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 54

## dacode/watch.py  (158 loc, python)
doc: `dacode watch` — a live, read-only TUI over the run log.
defines: split_runs() (Group the stream into finished run blocks, plus the trailing open block.); render() (The whole dashboard as one string — pure so tests can assert on it.); follow() (Yield between repaints until the file stops growing or 'q'/Ctrl-C.); watch() (Repaint loop; returns the final frame (tests and ``--once`` assert on it).)
uses: ตรวจคุณภาพงาน, ตัวจัดการงาน
used by: ทางเข้าของผู้ใช้
imported by: dacode/cli.py
