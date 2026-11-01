# Stage 2 Review: Comprehension Test (Self-Containment & Missing Background)

- **Target Document:** `docs/design/blueprint-ultimate-autonomous-engineering-rig.md` (86 lines)
- **Reviewer Posture:** Fresh-context, naive first-time reader (cold read of the document alone)
- **Rubric:** Self-containment, undefined terminology, unprovided background assumptions, internal contradictions/ambiguities, and standalone implementability

---

## (a) Undefined Terms and Acronyms Requiring Guessing

1. **`Google Harness²` / `Google Harness2` / `Recursive Agent Harnessing` is completely undefined**
   - **Claim:** The central optimization layer of the architecture is named after a specific framework or paper (`Google Harness²` / `Recursive Agent Harnessing`) without explaining what a "harness" is in this context, what the superscript `²` ("squared" / recursive meta-harnessing) signifies, or citing any paper, URL, or author. A cold reader must guess whether this optimizes prompts, tool wrappers, orchestration code, or candidate patches.
   - **Evidence:** Line 2 (`Harness²`), line 35 (`2. Google Harness² (The Optimizer / Propose-Probe-Compose)`), line 62 (`Harness² สั่งสร้าง Git Branch ย่อย`), line 74 (`แบบ Harness²`), and line 81 (`Google Harness2 — Recursive Agent Harnessing`).
   - **Severity:** `high`

2. **`Propose-Probe-Compose` and `Contrastive Loop` are dropped as opaque buzzwords**
   - **Claim:** Two algorithmic terms describing how Layer 2 works appear once each and are never defined or referenced again. The reader must guess what artifact is "proposed," how "probing" scores or falsifies it, how "composing" merges multiple trials, and what two things are compared in a "Contrastive Loop" (e.g., passing vs. failing traces, baseline vs. candidate branches, or competing variants).
   - **Evidence:** Line 35 (`(The Optimizer / Propose-Probe-Compose)`) and line 74 (`เขียนสคริปต์ Python/Bash ควบคุม Git Branch + Test Runner เพื่อทำ Contrastive Loop ง่าย ๆ แบบ Harness²`).
   - **Severity:** `high`

3. **`Pi` / `Pi Coding Agent` has no identity or provenance**
   - **Claim:** Layer 3 is named `Pi` / `Pi Coding Agent`, leaving a cold reader to guess whether `Pi` refers to an existing third-party CLI coding agent, Inflection AI's conversational assistant, Raspberry Pi hardware, or a bespoke internal tool to be written from scratch.
   - **Evidence:** Line 2 (`Pi`), lines 40–41 (`3. Pi Coding Agent (The Executor / Terminal Interface)` / `ตัวลงมือแก้โค้ด รันไฟล์ และจัดการโปรเจกต์ในเครื่อง`), line 63 (`สั่งให้ Pi ลงมือแก้ไขโค้ด`), and line 75 (`ดึงพลังของ Pi`).
   - **Severity:** `high`

4. **`pstack` / `pstack Principles` collides with a standard Unix utility and is never defined**
   - **Claim:** To a systems or Linux engineer, `pstack(1)` means the standard command-line tool that prints execution stack traces of running processes. Here it clearly refers to an unnamed doctrine of engineering rules ("กฎเหล็กวิศวกรรม"), forcing the reader to guess whether `pstack` stands for "prompt stack," "principle stack," or a private methodology.
   - **Evidence:** Line 2 (`pstack`), lines 45–46 (`4. pstack Principles & Adversarial Critic (The Discipline)` / `กฎเหล็กวิศวกรรม`), line 65 (`ตัว pstack/Critic Agent`), and line 73 (`ใช้กฎระเบียบของ pstack`).
   - **Severity:** `high`

5. **`Test behavior` and `Attack the premise` are undefined parenthetical maxims**
   - **Claim:** Two English phrases appear in parentheses inside Thai prose as examples (or the entirety) of Layer 4's inspection criteria without explaining how an automated pre-commit check operationalizes them—particularly what "Attack the premise" means once code has already been edited for a given task (e.g., rejecting the user's requirements vs. questioning root-cause assumptions).
   - **Evidence:** Line 65 (`ตรวจสอบว่าโค้ดทำตามหลักการที่ถูกต้องหรือไม่ (Test behavior, Attack the premise)`).
   - **Severity:** `med`

6. **`Adversarial Critic`, `Critic Agent`, and `Subagent` lack architectural definitions**
   - **Claim:** The document introduces three overlapping agent terms without defining what makes the critic "adversarial" (separate model, hostile rubric, red-team test authoring, or mutation testing), what parent process hosts or spawns a "Subagent," or how its execution privileges differ from `Pi`'s.
   - **Evidence:** Lines 45–46 (`Adversarial Critic` / `Subagent คอยจับผิดและทดสอบพฤติกรรม`) and line 65 (`ตัว pstack/Critic Agent`).
   - **Severity:** `med`

7. **`Semantic Vault Memory`, `Vault`, `Obsidian`, and `ChromaDB` are named without explaining their roles**
   - **Claim:** The reader must guess from external tool knowledge that `Obsidian` is a local Markdown note-taking app, that a `Vault` is an Obsidian directory of Markdown notes (not HashiCorp Vault for secrets management—a genuine ambiguity in a security/sandbox architecture doc), and that `ChromaDB` is an embedding vector database providing the "Semantic" search layer.
   - **Evidence:** Line 2 (`Vault`), line 30 (`1. Semantic Vault Memory (Obsidian / ChromaDB)`), line 60 (`ค้น Vault`), line 67 (`เป็น Note ใน Obsidian Vault`), and line 73 (`ดึง Context จาก Vault`).
   - **Severity:** `med`

8. **`Isolated Sandbox` and `Git-Native Checkpoints` are defined only by metaphor**
   - **Claim:** Layer 5 translates `Isolated Sandbox` merely as "run in a safe closed box" (`รันในกล่องปิดปลอดภัย`) and `Git-Native Checkpoints` as "separate trial branch, able to rewind time" (`แยก Branch ทดลอง ย้อนเวลาได้`). The reader must guess what OS/container/VM boundary defines the sandbox and what Git primitive (commits, tags, worktrees, stashes, or reflogs) constitutes a "checkpoint."
   - **Evidence:** Lines 50–51 (`5. Isolated Sandbox + Git-Native Checkpoints` / `รันในกล่องปิดปลอดภัย + แยก Branch ทดลอง ย้อนเวลาได้`) and line 63 (`ภายใน **Isolated Sandbox**`).
   - **Severity:** `med`

9. **`Trinity Plus Architecture` is an unexplained alias**
   - **Claim:** The YAML frontmatter aliases a 5-component blueprint as `Trinity Plus Architecture`, forcing the reader to guess which three components constitute the "Trinity" and which two are the "Plus."
   - **Evidence:** Line 16 (`aliases:` -> `- Trinity Plus Architecture`).
   - **Severity:** `low`

10. **Unexpanded acronyms, placeholders, and project names (`AI`, `CLI Wrapper`, `<task-id>`, `Rig`, `DaCode`)**
    - **Claim:** Standard acronyms `AI` and `CLI` appear unexpanded; `Rig` is used in titles while `AI Coding Agent` is used in prose without distinguishing them; `<task-id>` appears in a branch naming pattern without defining its source or format; and `DaCode` appears at the end without explaining what it stands for or where it resides.
    - **Evidence:** Lines 2, 6, 15, 19, 22 (`Rig` vs. `AI Coding Agent`), line 62 (`harness-trial-<task-id>`), line 75 (`CLI Wrapper`), line 82 (`DaCode`), and line 86 (`AI assistant`).
    - **Severity:** `low`

---

## (b) Assumed Knowledge Never Provided by the Document

11. **Core Layer 2 explanation is outsourced to an unlinked, unnamed sibling note**
    - **Claim:** The document explicitly assumes the reader can open "the next note in this folder" (`โน้ตถัดไปในโฟลเดอร์นี้`) to learn what `Google Harness2 — Recursive Agent Harnessing` actually is. Even inside a folder, files have no canonical "next" note without a filename or link, making the document non-self-contained by construction.
    - **Evidence:** Line 81 (`- Google Harness2 — Recursive Agent Harnessing (โน้ตถัดไปในโฟลเดอร์นี้)`).
    - **Severity:** `high`

12. **Sole cited source is an inaccessible private brainstorming conversation**
    - **Claim:** All design rationale, component definitions, and trade-offs rely on a private October 18, 2026 chat session between the author and an AI assistant to which no reader has access.
    - **Evidence:** Lines 84–86 (`## 📚 Sources` / `- การระดมความคิดร่วมกันระหว่างผู้ใช้กับ AI assistant (18 ตุลาคม 2026)`).
    - **Severity:** `high`

13. **Short-term implementation step assumes the reader already possesses the `pstack` rulebook**
    - **Claim:** The very first step of the implementation roadmap tells the reader to start using `pstack`'s rules in daily agent prompts immediately—assuming external familiarity with a rule set that is never enumerated anywhere in the file.
    - **Evidence:** Line 73 (`- **ระยะสั้น:** เริ่มต้นจากการใช้กฎระเบียบของ \`pstack\` และดึง Context จาก \`Vault\` มาใช้กำกับ Prompt ของ Agent ในชีวิตประจำวัน`).
    - **Severity:** `high`

14. **Assumed Thai-English bilingual fluency and Obsidian callout familiarity**
    - **Claim:** The document mixes English technical labels with Thai prose explanations and Obsidian-specific Markdown extensions (`> [!abstract]`), assuming a bilingual Thai-reading engineer working inside Obsidian without providing a glossary or plain-Markdown fallback context.
    - **Evidence:** Line 6 (`สร้าง blueprint...`), lines 21–22 (`> [!abstract] สรุปสั้น` / `สถาปัตยกรรมอุดมคติ...`), and lines 31, 36, 41, 46, 51, 57–76, 81–86.
    - **Severity:** `med`

15. **Assumed existence of a pre-configured, trustworthy `Test Runner` in target repositories**
    - **Claim:** Both the workflow and medium-term roadmap assume target projects already have an executable test suite and `Test Runner` that cleanly defines "when tests pass" (`เมื่อเทสผ่าน`), omitting how test commands are configured or discovered, or how tasks in untested codebases are handled.
    - **Evidence:** Line 63 (`แก้ไขโค้ดและรันเทส`), line 67 (`เมื่อเทสผ่านและโค้ดสะอาดเรียบร้อย`), and line 74 (`ควบคุม Git Branch + Test Runner`).
    - **Severity:** `med`

16. **Assumed prior knowledge of `DaCode` and `Pi`'s operational CLI/API**
    - **Claim:** The document assumes the reader already knows how `Pi` is invoked programmatically inside a sandbox and already knows where and what the `DaCode` project is.
    - **Evidence:** Line 63 (`สั่งให้ Pi ลงมือแก้ไขโค้ด`), line 75 (`ดึงพลังของ Pi มาเชื่อมกับ Sandbox`), and line 82 (`- DaCode — โปรเจกต์ที่ blueprint นี้กลายเป็นจริง`).
    - **Severity:** `med`

---

## (c) Contradictions and Ambiguities

17. **Strict top-down linear stack diagram contradicts cross-layer jumps and cyclic workflow**
    - **Claim:** The architecture diagram draws strictly one-way downward arrows (`1 ▼ 2 ▼ 3 ▼ 4 ▼ 5`), implying control/data flows sequentially from `Pi` (Layer 3) through `pstack / Critic` (Layer 4) into `Sandbox + Git` (Layer 5). The workflow contradicts this topology in three ways: Layer 2 bypasses Layers 3–4 to manipulate Layer 5 directly (creating Git branches); Layer 3 executes inside Layer 5 *before* Layer 4 runs; and Layers 4 and 1 receive upward/backward feedback loops omitted from the diagram.
    - **Evidence:** Lines 28–53 (`1 ▼ 2 ▼ 3 ▼ 4 ▼ 5`) vs. lines 61–63 (`2. Experimentation Loop (Layers 2 & 5)` where `Harness²` creates a branch and `Pi` runs in the sandbox), line 65 (Layer 4 loops backward on failure), and line 67 (Step 4 writes back up to Layer 1).
    - **Severity:** `high`

18. **Contradiction over what `Harness²` optimizes: agent tools/prompts vs. repository source code**
    - **Claim:** The Layer 2 box explicitly states that `Harness²` loops to *"automatically improve tools/Prompts"* (meta-level self-improvement of the agent harness). However, the Workflow Lifecycle and Implementation Steps describe `Harness²` only creating Git branches for `Pi` to edit target project code and run tests—nowhere in Steps 1–4 are tools or prompts ever modified or evolved.
    - **Evidence:** Line 36 (`วนลูปแก้ปัญหาและปรับปรุงเครื่องมือ/Prompt อัตโนมัติ`) vs. lines 61–63 (`Harness² สั่งสร้าง Git Branch ย่อย ... สั่งให้ Pi ลงมือแก้ไขโค้ดและรันเทส`) and line 74 (`ควบคุม Git Branch + Test Runner`).
    - **Severity:** `high`

19. **Multi-candidate `Propose-Probe-Compose` / `Contrastive Loop` contradicts single-branch workflow**
    - **Claim:** `Propose-Probe-Compose` and `Contrastive Loop` imply generating multiple candidate variants, probing them, contrasting their outcomes, and composing a final result. Yet Workflow Step 2 creates only a *single* branch named `harness-trial-<task-id>` (whose naming template lacks any trial/variant index, so parallel or sequential branches for the same `<task-id>` would collide), runs `Pi` once, and includes no composition step anywhere.
    - **Evidence:** Line 35 (`Propose-Probe-Compose`) and line 74 (`Contrastive Loop`) vs. lines 62–65 (`harness-trial-<task-id>` -> `Pi` -> `Critic` -> `ส่งกลับไปให้วนลูปแก้ใหม่`).
    - **Severity:** `high`

20. **Underspecified failure loop target, missing test-failure branch, and infinite-loop hazard**
    - **Claim:** When Layer 4 fails a trial (`หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่` — "if it fails, send back to loop and fix again"), three critical behaviors are ambiguous: (1) whether retry starts fresh on a new branch or mutates `harness-trial-<task-id>` in place; (2) whether Critic feedback goes to `Harness²` or directly to `Pi`; and (3) what happens if tests fail in Step 2 *before* Step 3's Critic runs. Moreover, no retry limit, timeout, or abort condition is specified, creating an unbounded infinite loop.
    - **Evidence:** Lines 61–67 (`2. Experimentation Loop` -> `3. Discipline & Critique ... หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่` -> `4. Memory Ingestion ... เมื่อเทสผ่านและโค้ดสะอาดเรียบร้อย`).
    - **Severity:** `high`

21. **Ambiguous `/` in `Obsidian / ChromaDB` leaves vector synchronization unexplained**
    - **Claim:** Writing `Obsidian / ChromaDB` leaves unclear whether Obsidian and ChromaDB are *interchangeable alternatives* ("or") or a *coupled dual-store* ("and"). Step 4 states that lessons are saved automatically as Notes in the Obsidian Vault, never mentioning ChromaDB—leaving ambiguous how ChromaDB ever ingests new notes if it is used for Step 1 retrieval.
    - **Evidence:** Line 30 (`Semantic Vault Memory (Obsidian / ChromaDB)`) and line 60 (`ค้น Vault`) vs. line 67 (`บันทึกผลลัพธ์และบทเรียนสำคัญกลับลงเป็น Note ใน Obsidian Vault อัตโนมัติ`).
    - **Severity:** `med`

22. **Conflation of `pstack` (static prompt rules) with `Critic Agent` (active post-hoc subagent)**
    - **Claim:** Layer 4 initially separates `pstack Principles` ("ironclad engineering rules") from `Adversarial Critic` ("subagent catching faults"), and the short-term plan treats `pstack` as prompt instructions fed to the coding agent upfront. Workflow Step 3 then merges them into one actor (`ตัว pstack/Critic Agent`), making it ambiguous whether `pstack` guides `Pi` during generation, governs a separate reviewer agent after generation, or both.
    - **Evidence:** Lines 45–46 (`pstack Principles & Adversarial Critic` / `กฎเหล็กวิศวกรรม + Subagent`), line 73 (`ใช้กฎระเบียบของ pstack ... มาใช้กำกับ Prompt`), and line 65 (`ตัว pstack/Critic Agent จะเข้ามาตรวจสอบ`).
    - **Severity:** `med`

23. **Pre-commit inspection contradicts `Git-Native Checkpoints`, and final code delivery is omitted**
    - **Claim:** Layer 5 promises `Git-Native Checkpoints` that allow "rewinding time" (`ย้อนเวลาได้`), which in Git requires commits (or refs). Yet Step 3 places Critic review *"before committing or summarizing"* (`ก่อนจะคอมมิตหรือสรุปผล`), implying no commits have been made yet. Furthermore, after Step 3 passes, Step 4 jumps straight to writing an Obsidian memory note without ever stating whether code is committed, merged to main, opened as a pull request, or left stranded on `harness-trial-<task-id>`.
    - **Evidence:** Lines 50–51 (`Git-Native Checkpoints` / `ย้อนเวลาได้`) vs. line 65 (`ก่อนจะคอมมิตหรือสรุปผล`) and line 67 (`เมื่อเทสผ่านและโค้ดสะอาดเรียบร้อย ระบบจะบันทึกผลลัพธ์...ลงเป็น Note`).
    - **Severity:** `med`

24. **Numerical contradiction between `Trinity Plus Architecture` and `The 5-Layer Stack`**
    - **Claim:** Naming the architecture both "Trinity Plus" (3 + extras) and a "5-part / 5-Layer Stack" creates ambiguity about whether two of the five layers are optional add-ons rather than required peers.
    - **Evidence:** Line 16 (`Trinity Plus Architecture`) vs. line 6 (`สถาปัตยกรรม 5 ประสาน`) and line 26 (`The 5-Layer Stack`).
    - **Severity:** `low`

---

## (d) Missing Specifications & Implement-Alone Verdict

25. **Complete absence of inter-layer interfaces, schemas, and data contracts**
    - **Claim:** None of the five layers have defined input/output schemas, API signatures, CLI arguments, or state formats—leaving unspecified how tasks are submitted, how Vault context is formatted, how `Harness²` invokes `Pi` and captures artifacts, or how the Critic returns structured pass/fail feedback.
    - **Evidence:** Lines 26–68 (diagrams and prose bullets contain zero data structures, function signatures, config formats, or protocol definitions).
    - **Severity:** `high`

26. **Missing Layer 2 optimization algorithm, Git concurrency model, and resource budgets**
    - **Claim:** To build `Harness²`, an engineer needs the exact `Propose-Probe-Compose` / `Contrastive Loop` algorithm: number of parallel variants, how concurrent Git branches avoid working-tree collisions (e.g., separate clones or worktrees vs. `git checkout`), candidate scoring metrics, composition/merge rules, max iterations, and token/cost limits—none of which appear in the text.
    - **Evidence:** Lines 35–36, 61–63, and 74.
    - **Severity:** `high`

27. **Missing Layer 4 verification rules, gating authority, and anti-tampering safeguards**
    - **Claim:** The document omits the `pstack` rule list, fails to specify whether deterministic test execution or the LLM Critic has final veto/acceptance authority, does not specify whether Executor and Critic use independent models/contexts, and ignores reward-hacking defenses (e.g., preventing `Pi` from deleting or weakening tests inside the sandbox so that `"เมื่อเทสผ่าน"` succeeds trivially).
    - **Evidence:** Lines 45–46, 63–67, and 73.
    - **Severity:** `high`

28. **Missing Layer 5 sandbox technology, threat model, and network/credential boundary**
    - **Claim:** Calling for an `Isolated Sandbox` leaves out the isolation mechanism (containers, OS namespaces, microVMs), filesystem mounts, environment/secret injection, and a fundamental architectural tension: an LLM coding agent (`Pi`) typically requires outbound network/API credentials to call its model, whereas untrusted code and test execution inside a sandbox should be network-isolated and stripped of secrets.
    - **Evidence:** Lines 50–51, 63, and 75.
    - **Severity:** `high`

29. **Missing Layer 1 memory schema, indexing pipeline, and anti-poisoning controls**
    - **Claim:** Automatic post-run note ingestion (`บันทึก...อัตโนมัติ`) lacks a note schema, embedding model specification, chunking/retrieval parameters (top-$k$, similarity threshold, context-window budget), Obsidian-to-ChromaDB sync trigger, and quality/deduplication gates to prevent noisy or incorrect lessons from poisoning future tasks.
    - **Evidence:** Lines 30–31, 60, and 67.
    - **Severity:** `med`

30. **Missing CLI specification, error handling, and operational lifecycle**
    - **Claim:** The promised end-state `"CLI Wrapper ตัวเดียว"` ("a single CLI Wrapper") has no command grammar, configuration file spec, logging/observability design, crash cleanup for orphaned trial branches/sandboxes, or human review workflow.
    - **Evidence:** Lines 74–75.
    - **Severity:** `med`

**Implement-Alone Verdict:** Honestly, **no**—a competent engineer could **not** implement the intended system from this document alone. At 86 lines total (roughly two dozen sentences of high-level Thai/English concept notes), the file is an ideation sketch rather than an engineering specification: three of its five named pillars (`Google Harness²`, `Pi Coding Agent`, and `pstack`) are undefined proper nouns whose substance lives in an unlinked sibling note (`โน้ตถัดไปในโฟลเดอร์นี้`) and an inaccessible private chat transcript, while core algorithmic claims (`Propose-Probe-Compose`, `Contrastive Loop`, tool/prompt self-improvement) directly conflict with the single-branch code-retry workflow described a few lines later. Handed only this document, ten senior engineers would build ten mutually incompatible prototypes—having to invent from scratch the executor integration, the `pstack` rule set, the multi-candidate optimization and composition algorithm, the test-tampering and gating rules, the sandbox/network boundary, the Obsidian-to-ChromaDB indexing pipeline, and every inter-layer contract.
