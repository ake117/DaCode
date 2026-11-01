# Stage 1: Zoom-Out Review — Blueprint: The Ultimate Autonomous Engineering Rig

- **Target Document:** `docs/design/blueprint-ultimate-autonomous-engineering-rig.md`
- **Review Date:** 2026-11-01
- **Rubric:** Simplicity, YAGNI, Reuse — (a) cuttable components, (b) reinvented existing tools, (c) speculative complexity

## Assumptions

- **Core goal:** Because the abstract (`สรุปสั้น`, lines 21–22) bundles carelessness (`ความสะเพร่า`), disorganization (`ความไร้ระเบียบ`), and forgetting lessons (`การลืมบทเรียน`), this review assumes the core operational goal is reliably producing verified, disciplined code changes on real repositories without damaging the host environment, while cross-project memory and prompt self-modification are proposed means rather than required end-user deliverables.
- **Build-versus-reuse boundary:** Because `Pi Coding Agent`, `Google Harness²`, and `pstack` are named without interface specifications (referencing an external note at line 81), this review assumes `Pi` is an existing terminal coding agent and `pstack` is an existing prompt/principle set, whereas the `Obsidian / ChromaDB` memory pipeline, `Harness²` Python/Bash loop scripts, runtime `Adversarial Critic` subagent gate, sandbox integration, and unified `CLI Wrapper` represent proposed custom build work.
- **Target scale:** Based on local project execution (`จัดการโปรเจกต์ในเครื่อง`, line 41), personal Obsidian Vault storage (lines 30, 67), and single-developer scripting stages (lines 73–75), this review assumes a single developer or small local engineering setup rather than a multi-tenant cloud service.

## Findings

1. **Claim:** [Cut — (a)] Automatic tool and prompt self-optimization in Layer 2 can be cut with no loss to the core goal of shipping verified code changes, because solving an individual engineering task only requires iterating on repository code against tests rather than mutating the agent's own prompts or tools mid-run.
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)`, lines 35–36 (`"2. Google Harness² (The Optimizer / Propose-Probe-Compose) - วนลูปแก้ปัญหาและปรับปรุงเครื่องมือ/Prompt อัตโนมัติ"`), contrasted with `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Step 2, lines 61–63, which only creates a trial branch and runs code edits plus tests.
   - **Severity:** high

2. **Claim:** [Cut — (a)] Automatic post-run note ingestion into an Obsidian Vault after every passing task can be cut with no loss to engineering quality, because uncurated LLM-generated summaries accumulate noisy, task-overfitted advice while static versioned repository rules prevent repeat mistakes deterministically.
   - **Evidence:** `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Step 4 (`Memory Ingestion (Layer 1)`), lines 66–67 (`"เมื่อเทสผ่านและโค้ดสะอาดเรียบร้อย ระบบจะบันทึกผลลัพธ์และบทเรียนสำคัญกลับลงเป็น Note ใน Obsidian Vault อัตโนมัติ เพื่อให้สมองกลเก่งขึ้นในรอบถัดไป"`).
   - **Severity:** high

3. **Claim:** [Cut — (a)] The separate pre-commit Adversarial Critic Subagent can be cut with no loss to behavioral correctness, because attacking the premise after code and tests are already written causes unbounded retry churn whereas upfront `pstack` prompt rules plus deterministic test and lint gates enforce discipline objectively.
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 4, lines 45–46 (`"4. pstack Principles & Adversarial Critic (The Discipline) - กฎเหล็กวิศวกรรม + Subagent คอยจับผิดและทดสอบพฤติกรรม"`) and `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Step 3, lines 64–65 (`"ก่อนจะคอมมิตหรือสรุปผล ตัว pstack/Critic Agent จะเข้ามาตรวจสอบว่าโค้ดทำตามหลักการที่ถูกต้องหรือไม่ (Test behavior, Attack the premise) หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่"`), contrasted with `## 💡 แนวทางการนำไปปฏิบัติ` (`ระยะสั้น`), line 73.
   - **Severity:** high

4. **Claim:** [Cut — (a)] The long-term unified CLI wrapper around `Pi Coding Agent` can be cut with no loss to capability, because `Pi` is already designated as the terminal interface and local project executor and can invoke sandboxes, Git hooks, and memory tools directly without an outer wrapper CLI.
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 3, lines 40–41 (`"3. Pi Coding Agent (The Executor / Terminal Interface) - ตัวลงมือแก้โค้ด รันไฟล์ และจัดการโปรเจกต์ในเครื่อง"`) versus `## 💡 แนวทางการนำไปปฏิบัติ (Implementation Steps)` (`ระยะยาว`), line 75 (`"ประกอบร่างเป็น CLI Wrapper ตัวเดียวที่ดึงพลังของ Pi มาเชื่อมกับ Sandbox และ Memory อย่างสมบูรณ์"`).
   - **Severity:** low

5. **Claim:** [Reuse — (b)] Writing custom Python or Bash scripts to create trial Git branches (`harness-trial-<task-id>`), manage rollback checkpoints, and run test-driven retry loops reinvents capabilities already provided natively by `git worktree`, Aider (`--test-cmd`, auto-commits, and `/undo`), Claude Code worktree sessions, SWE-agent, and OpenHands.
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 5, lines 50–51 (`"แยก Branch ทดลอง ย้อนเวลาได้"`), `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Step 2, line 62 (`"Harness² สั่งสร้าง Git Branch ย่อย (harness-trial-<task-id>)"`), and `## 💡 แนวทางการนำไปปฏิบัติ (Implementation Steps)` (`ระยะกลาง`), line 74 (`"เขียนสคริปต์ Python/Bash ควบคุม Git Branch + Test Runner"`).
   - **Severity:** med

6. **Claim:** [Reuse — (b)] Treating sandboxed execution and pre-commit discipline checks as custom layers to integrate into a bespoke wrapper reinvents mature isolation and gating tools including Docker Devcontainers (`@devcontainers/cli`), Bubblewrap (`bwrap`), OpenAI Codex CLI's built-in OS sandboxing, `pre-commit`, `lefthook`, Semgrep, and Claude Code Hooks.
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 5, lines 50–51 (`"5. Isolated Sandbox + Git-Native Checkpoints - รันในกล่องปิดปลอดภัย"`), `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Steps 2–3, lines 63–65 (`"ภายใน **Isolated Sandbox**"`, `"ก่อนจะคอมมิตหรือสรุปผล"`), and `## 💡 แนวทางการนำไปปฏิบัติ (Implementation Steps)` (`ระยะยาว`), line 75 (`"ดึงพลังของ Pi มาเชื่อมกับ Sandbox"`).
   - **Severity:** med

7. **Claim:** [Reuse — (b)] Building a custom Obsidian-and-ChromaDB semantic memory pipeline reinvents persistent context and retrieval mechanisms already provided by native coding-agent instruction files (`AGENTS.md`, `CLAUDE.md`, Cursor Rules), Obsidian plugins (`Smart Connections`, `mcp-obsidian`), fast local Markdown search (`ripgrep`, `qmd`), and turnkey MCP memory servers (`Mem0`, `Letta`).
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 1, lines 30–31 (`"1. Semantic Vault Memory (Obsidian / ChromaDB) - ดึงความจำเก่า / บันทึกบทเรียนสะสมข้ามโปรเจกต์"`) and `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Steps 1 & 4, lines 59–60, 66–67.
   - **Severity:** med

8. **Claim:** [Reuse — (b)] Implementing a custom `Harness²` Propose-Probe-Compose optimizer and contrastive evaluation loop in Python or Bash reinvents established prompt-optimization and multi-variant evaluation frameworks such as DSPy (MIPROv2 and GEPA), Promptfoo, and Inspect AI.
   - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 2, lines 35–36 (`"2. Google Harness² (The Optimizer / Propose-Probe-Compose) - วนลูปแก้ปัญหาและปรับปรุงเครื่องมือ/Prompt อัตโนมัติ"`), `## 💡 แนวทางการนำไปปฏิบัติ (Implementation Steps)` (`ระยะกลาง`), line 74 (`"เพื่อทำ Contrastive Loop ง่าย ๆ แบบ Harness²"`), and `## 🔗 Related`, line 81.
   - **Severity:** med

9. **Claim:** [Speculative / YAGNI — (c)] Proposing a five-layer "ideal" architecture upfront without any baseline failure metrics, evaluation tasks, or measurable exit criteria gating progression from short-term prompt rules (`ระยะสั้น`) to custom infrastructure (`ระยะกลาง` and `ระยะยาว`) is speculative complexity driven by brainstorming ideals rather than observed bottlenecks.
   - **Evidence:** `> [!abstract] สรุปสั้น`, lines 21–22 (`"สถาปัตยกรรมอุดมคติสำหรับการสร้าง **AI Coding Agent ระดับโปร** ที่ผสานจุดเด่นของ 5 องค์ประกอบเข้าด้วยกัน"`), `## 💡 แนวทางการนำไปปฏิบัติ (Implementation Steps)`, lines 73–75 (defining three build stages with no validation gates), and `## 📚 Sources`, line 86 (`"การระดมความคิดร่วมกันระหว่างผู้ใช้กับ AI assistant (18 ตุลาคม 2026)"`).
   - **Severity:** high

10. **Claim:** [Speculative / YAGNI — (c)] Deploying ChromaDB vector indexing to accumulate cross-project lessons so the agent automatically "gets smarter in subsequent rounds" is speculative complexity that presupposes both a note corpus too large for plain text search and high cross-project transferability of local bug fixes, without defining any schema, retrieval precision bar, or staleness eviction policy.
    - **Evidence:** `## 🏛️ สถาปัตยกรรม 5 ประสาน (The 5-Layer Stack)` Layer 1, lines 30–31 (`"1. Semantic Vault Memory (Obsidian / ChromaDB) - ดึงความจำเก่า / บันทึกบทเรียนสะสมข้ามโปรเจกต์"`) and `## ⚙️ ขั้นตอนการทำงาน (Workflow Lifecycle)` Step 4, lines 66–67 (`"บันทึกผลลัพธ์และบทเรียนสำคัญกลับลงเป็น Note ใน Obsidian Vault อัตโนมัติ เพื่อให้สมองกลเก่งขึ้นในรอบถัดไป"`).
    - **Severity:** high

## Overall Verdict

As a whole, the blueprint over-architects a tractable engineering discipline problem into a speculative five-layer meta-system whose custom components largely reinvent mature, off-the-shelf developer tooling. At least half of the proposed stack—automatic per-task prompt/tool mutation (`Layer 2`), uncurated post-run Obsidian/ChromaDB write-back (`Layer 1` / Step 4), the pre-commit LLM Adversarial Critic veto loop (`Layer 4` / Step 3), and the outer unified CLI wrapper (`ระยะยาว`)—can be cut without losing the core ability to ship verified, disciplined code safely, and in several cases cutting them actively removes failure modes such as memory poisoning and unbounded critic-executor oscillation. What remains essential—upfront engineering rules, isolated execution, clean trial checkouts, and objective test/lint verification—is already solved by composing existing tools (`Pi` or Aider/Claude Code, a versioned `AGENTS.md` containing `pstack` rules, `git worktree`, `devcontainer` or `bwrap` sandboxing, and `pre-commit` test/lint gates) with near-zero custom framework code; the project should stop after its `ระยะสั้น` baseline plus a deterministic container/worktree test gate, measure real failure modes on real tasks, and earn every additional layer empirically before building bespoke orchestration or semantic memory infrastructure.
