# Worksheet llm: ช่องคุยกับโมเดล
Audience: everyone. Write in plain language for a non-technical owner: what it does for the business or its users, in everyday words, still specific. No jargon (endpoint, ORM, blueprint, webhook, worker…): the path and method/URL are already shown next to it. See "Plain language" in references/writing-descriptions.md.
Module: คุยกับโมเดลภาษาผ่านรูปแบบคำขอมาตรฐานเดียว จึงสลับผู้ให้บริการได้โดยไม่ต้องแก้โค้ดส่วนอื่น
Write to: floorplan/descriptions/llm.json (a skeleton is already there; fill in every "description", improve every "name").
Entries marked REVIEW already have a description but their code changed: update name/description if the change matters, then delete the "review" field. Entries not listed here are fine; leave them alone.
Say what each thing does today ("Say what it does today" in references/writing-descriptions.md). Code quoted under an entry is what it really does: describe that, not what its name suggests, and say plainly when it is a placeholder. "imported by", "sent web requests by" and "named in" list every file the scan saw using it; don't say who or what runs or uses something beyond that unless its own code shows it.

## dacode/llm/__init__.py  (51 loc, python)
doc: Pluggable LLM backends for DaCode.
defines: build_llm() (Factory used by the CLI / config layer.)
uses: ช่องคุยกับโมเดล ×4
used by: ทางเข้าของผู้ใช้, ตัวจัดการงาน
imported by: dacode/cli.py, dacode/orchestrator.py

## dacode/llm/base.py  (22 loc, python)
doc: LLM client protocol shared by every backend.
defines: LLMError (Raised when a backend cannot produce a completion.); LLMClient (Minimal contract every LLM backend must satisfy.)
used by: ช่องคุยกับโมเดล ×3, ปรับปรุงคำสั่งให้ดีขึ้น
imported by: dacode/harness/optimizer.py, dacode/llm/__init__.py, dacode/llm/openai_compat.py, dacode/llm/stub.py

## dacode/llm/openai_compat.py  (80 loc, python)
doc: OpenAI-compatible chat-completions client (urllib only, no deps).
defines: OpenAICompatClient (Talks to any ``/v1/chat/completions`` endpoint.)
uses: ช่องคุยกับโมเดล
used by: ช่องคุยกับโมเดล
imported by: dacode/llm/__init__.py

## dacode/llm/providers.py  (71 loc, python)
doc: Popular AI provider presets for :func:`dacode.llm.build_llm`.
defines: provider_names() (Provider kinds ``build_llm`` accepts beyond ``stub`` and ``local``.); get_provider() (The preset for ``kind``, or ``None`` when it is not a known provider.)
uses: ผู้ให้บริการโมเดล
used by: ช่องคุยกับโมเดล
imported by: dacode/llm/__init__.py
named in: dacode/executor/pi.py line 29

## dacode/llm/stub.py  (39 loc, python)
doc: Deterministic LLM stub — the backbone of the test suite.
defines: StubLLM (Returns canned responses based on markers found in the prompt.)
uses: ช่องคุยกับโมเดล
used by: ช่องคุยกับโมเดล
imported by: dacode/llm/__init__.py
