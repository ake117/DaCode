# Worksheet settings: ค่าตั้งระบบ
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: อ่านค่าจากไฟล์ตั้งค่าและตัวแปรสภาพแวดล้อม: ผู้ให้บริการโมเดล คีย์ เวลาที่อนุญาต และโฟลเดอร์เก็บงาน
Write to: floorplan/descriptions/settings.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it.

## dacode/config.py  (96 loc, python)
doc: Configuration for a DaCode rig instance.
defines: DaCodeConfig
used by: ทางเข้าของผู้ใช้, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/orchestrator.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 51

## dacode/env.py  (127 loc, python)
doc: Minimal ``.env`` loader — stdlib only, no python-dotenv dependency.
defines: parse_env_file() (Parse a dotenv file into a mapping.); load_env() (Load the first value found for each allowed key, without clobbering the env.)
used by: ทางเข้าของผู้ใช้, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/kanban.py
named in: dacode/redact.py line 48, skills/dacode/scripts/pack_for_web_audit.py line 52

## pyproject.toml  (22 loc, toml)
imported by: nothing (no file imports it, sends it web requests or names it)
