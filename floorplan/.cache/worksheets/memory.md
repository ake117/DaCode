# Worksheet memory: ความจำของโปรเจกต์
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: จำสิ่งที่เรียนรู้จากงานก่อน ๆ แล้วดึงกลับมาใช้เมื่อเจองานคล้ายกัน พร้อมค้นหาด้วยความหมายไม่ใช่แค่คำตรงตัว
Write to: floorplan/descriptions/memory.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it.

## dacode/memory/__init__.py  (409 loc, python)
doc: Layer 1 — Semantic Vault Memory.
defines: MemoryHit; Lesson; VaultMemory (Keyword-retrieval memory backed by a markdown vault.)
uses: ความจำของโปรเจกต์ ×4, ตรวจคุณภาพงาน
used by: ทางเข้าของผู้ใช้ ×2, ปรับปรุงคำสั่งให้ดีขึ้น, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/harness/optimizer.py, dacode/mcp/server.py, dacode/orchestrator.py
named in: skills/dacode/scripts/pack_for_web_audit.py line 57

## dacode/memory/backends/__init__.py  (103 loc, python)
doc: Pluggable memory backends.
defines: SemanticHit (One retrieval hit from a semantic backend.); SemanticBackend; register() (Register a backend factory (called with the vault path).); resolve() (Resolve ``spec`` to a usable backend, or ``None`` (keyword only).); status() (Availability report for every in-tree backend (for the CLI).); available() (True when some semantic backend can serve ``vault``.)
uses: ความจำของโปรเจกต์ ×2
used by: ความจำของโปรเจกต์ ×4
imported by: dacode/memory/__init__.py, dacode/memory/backends/hermes.py, dacode/memory/backends/local.py, dacode/memory/semantic.py

## dacode/memory/backends/hermes.py  (87 loc, python)
doc: Hermes adapter — query another agent's vault index over a subprocess.
defines: HermesIndexBackend (Query an external embedding index (Hermes by default) via subprocess.)
uses: ความจำของโปรเจกต์
used by: ความจำของโปรเจกต์ ×3
imported by: dacode/memory/__init__.py, dacode/memory/backends/__init__.py, dacode/memory/semantic.py

## dacode/memory/backends/local.py  (92 loc, python)
doc: Local backend — DaCode's own embeddings, no other agent required.
defines: LocalStoreBackend (Semantic retrieval from DaCode's own vector store.)
uses: ความจำของโปรเจกต์ ×3
used by: ทางเข้าของผู้ใช้, ความจำของโปรเจกต์
imported by: dacode/cli.py, dacode/memory/backends/__init__.py

## dacode/memory/embedder.py  (123 loc, python)
doc: Embedding client for any OpenAI-compatible ``/v1/embeddings`` endpoint.
defines: EmbedError (Raised when the embedding endpoint rejects a request.); Embedder
used by: ความจำของโปรเจกต์ ×3
imported by: dacode/memory/__init__.py, dacode/memory/backends/local.py, dacode/memory/vectors.py

## dacode/memory/semantic.py  (27 loc, python)
doc: Compatibility shim — the semantic layer is now a backend registry.
defines: available() (True when a semantic backend (local or an adapter) can serve the vault.)
uses: ความจำของโปรเจกต์ ×2
imported by: nothing (no file imports it, sends it web requests or names it)

## dacode/memory/vectors.py  (181 loc, python)
doc: DaCode-owned vector store — SQLite + exact cosine, no external database.
defines: default_path(); VectorHit; VectorStore
uses: ความจำของโปรเจกต์
used by: ความจำของโปรเจกต์ ×2
imported by: dacode/memory/__init__.py, dacode/memory/backends/local.py
