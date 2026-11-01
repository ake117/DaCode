# Design Critique: Blueprint — The Ultimate Autonomous Engineering Rig

**Target Document:** `docs/design/blueprint-ultimate-autonomous-engineering-rig.md` (lines 1–86)  
**Stage:** Design Critic (System Design, Scale Bottlenecks, Failure Modes, Trust Boundaries)

---

## (a) Architectural Weaknesses & Single Points of Failure

### 1. Pipeline-vs-Control-Flow Topology Contradiction and Missing Inter-Layer Contracts
- **Severity:** med
- **Claim:** The architecture diagram models the system as a strict top-down unidirectional pipeline (`Layer 1 → Layer 2 → Layer 3 → Layer 4 → Layer 5`), contradicting the cyclic, nested containment topology described in the workflow lifecycle and leaving all inter-layer interfaces, schemas, and authority boundaries undefined.
- **Evidence:** Lines 28–53 draw strictly downward arrows placing `5. Isolated Sandbox + Git-Native Checkpoints` downstream of `4. pstack Principles & Adversarial Critic`. Conversely, Workflow Step 2 (lines 61–63) pairs Layers 2 and 5 (`Experimentation Loop (Layers 2 & 5)`) as an execution envelope *around* Layer 3 (`สั่งให้ Pi ลงมือแก้ไขโค้ดและรันเทสภายใน Isolated Sandbox`), Step 3 (lines 64–65) introduces an unspecified backward retry edge from Layer 4 (`หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่` — ambiguous whether returning to Layer 2 or Layer 3), and Step 4 (lines 66–67) closes a write-back loop to Layer 1. Zero payload contracts, exit-code protocols, or state handoffs are specified between any two layers.

### 2. Correlated LLM Gatekeeping Without an Independent Deterministic Test-Integrity Oracle
- **Severity:** high
- **Claim:** Code modification, test execution, and behavioral acceptance all rely on agentic components without an immutable external verification gate or test-tampering guard, creating a correlated single point of failure where shared LLM blind spots—or agent edits that weaken/delete tests—pass directly to commit and permanent memory ingestion.
- **Evidence:** Step 2 tasks `Pi` with *both* editing code and running tests inside the same workspace (`สั่งให้ Pi ลงมือแก้ไขโค้ดและรันเทสภายใน Isolated Sandbox`, line 63). Step 3 relies on an LLM subagent (`Subagent คอยจับผิดและทดสอบพฤติกรรม`, line 46; `pstack/Critic Agent จะเข้ามาตรวจสอบ`, line 65) before committing, and Step 4 triggers when "tests pass and code is clean" (`เมื่อเทสผ่านและโค้ดสะอาดเรียบร้อย`, line 67). Nothing in the blueprint isolates test definitions from `Pi`'s write permissions, verifies test execution independently outside `Pi`'s shell, or mandates model/provider diversity between Executor and Critic.

### 3. Closed-Loop Memory Poisoning and Split-Brain Dual Storage (`Obsidian / ChromaDB`)
- **Severity:** high
- **Claim:** Layer 1 combines two distinct storage engines (`Obsidian` Markdown files and `ChromaDB` vector embeddings) into an unvalidated, fully automated read-write feedback loop, creating both a dual-write consistency single point of failure and a positive-feedback hallucination amplifier.
- **Evidence:** Line 30 defines `1. Semantic Vault Memory (Obsidian / ChromaDB)`, Step 1 (lines 59–60) injects retrieved cross-project notes as the initial prompt context (`ค้น Vault หาบทเรียนหรือแพทเทิร์นที่เคยแก้ปัญหาคล้ายกันมาเป็น Context ตั้งต้น`), and Step 4 (lines 66–67) writes lessons back *automatically* into Obsidian (`บันทึกผลลัพธ์และบทเรียนสำคัญกลับลงเป็น Note ใน Obsidian Vault อัตโนมัติ`) without mentioning how ChromaDB embeddings are transactionally indexed, updated, or rolled back. Without human curation, provenance scoring, or quarantine, a single fragile workaround that slips past Step 3 is permanently ingested and injected into future tasks across all projects.

### 4. Monolithic Local CLI Orchestrator Without Durable Execution State
- **Severity:** med
- **Claim:** Consolidating orchestration, memory management, sandboxing, and execution into a single host-bound CLI wrapper with no persistent workflow state machine creates an operational single point of failure where process termination loses in-flight optimization history and orphans branches/sandboxes.
- **Evidence:** Layer 3 explicitly manages local host projects (`จัดการโปรเจกต์ในเครื่อง`, line 41) and the long-term target architecture collapses everything into a single wrapper binary (`ประกอบร่างเป็น CLI Wrapper ตัวเดียวที่ดึงพลังของ Pi มาเชื่อมกับ Sandbox และ Memory อย่างสมบูรณ์`, line 74). No durable run ledger, checkpointed trial cursor, or crash-recovery protocol is specified outside target-repo Git branches.

### 5. Concrete Tool Coupling Instead of Capability Interfaces
- **Severity:** low
- **Claim:** The blueprint binds core architectural layers directly to specific product/tool implementations (`Obsidian`, `ChromaDB`, `Google Harness²`, `Pi`, `pstack`) rather than defining replaceable capability contracts, increasing blast radius when any upstream CLI or storage format changes.
- **Evidence:** Lines 2 and 29–46 hard-code tool identities at every layer except Layer 5 without defining adapter boundaries (e.g., how `Pi`'s terminal interface exposes structured diffs/logs to `Harness²` or `pstack`).

---

## (b) What Breaks at Scale

### 6. Working-Tree Lock Contention and Branch Collisions Under Parallel Probing (`harness-trial-<task-id>`)
- **Severity:** high
- **Claim:** Running multi-variant `Propose-Probe-Compose` searches against a single local Git checkout using the branch template `harness-trial-<task-id>` fails under concurrency due to single-HEAD working-tree contention, branch name collisions across rounds/variants, and unbounded Git ref/object accumulation.
- **Evidence:** Layer 2 adopts `Propose-Probe-Compose` (line 35), which inherently evaluates multiple candidate variants, yet Step 2 creates a branch keyed *only* on `<task-id>` (`Harness² สั่งสร้าง Git Branch ย่อย (harness-trial-<task-id>)`, line 62) in a local project without specifying isolated Git worktrees or separate clones. Two concurrent probes or sequential retries of the same `<task-id>` collide on the branch ref and `.git/index.lock`. Moreover, no branch pruning or garbage-collection lifecycle is defined after trials complete or fail.

### 7. Multiplicative Latency Blowup Across Nested Optimizer × Sandbox × Critic Loops
- **Severity:** med
- **Claim:** Nesting `Harness²`'s outer optimization loop around full sandbox test runs and Layer 4's inner rejection-and-rework loop causes wall-clock latency and compute consumption to scale multiplicatively ($O(\text{variants} \times \text{rounds} \times \text{critic\_retries})$), bottlenecking on non-trivial repositories.
- **Evidence:** Layer 2 loops over problem-solving and prompt/tool tuning (`วนลูปแก้ปัญหาและปรับปรุงเครื่องมือ/Prompt อัตโนมัติ`, line 36), Step 2 executes edits and test suites inside an `Isolated Sandbox` (line 63), and Step 3 routes failures back into the loop (`หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่`, line 65). The blueprint specifies no cached sandbox snapshots, incremental/affected-test selection, concurrency limits, or early-abort heuristics when a repository's test suite takes minutes to hours.

### 8. Cross-Project Semantic Drift, Prompt Bloat, and Vector-Index Contention
- **Severity:** med
- **Claim:** Automatically appending notes from every completed task across unrelated repositories into one global Vault degrades top-$k$ retrieval precision, bloats initial prompt context with contradictory patterns, and introduces write-lock contention on local ChromaDB/filesystem storage under parallel agents.
- **Evidence:** Line 31 specifies cross-project accumulation (`บันทึกบทเรียนสะสมข้ามโปรเจกต์`), line 60 injects matches as starting context (`เป็น Context ตั้งต้น`), and line 67 mandates automatic note creation after every clean run (`อัตโนมัติ`). No metadata namespacing (language, framework, repo), deduplication, memory compaction, confidence decay, or archival TTL is defined.

---

## (c) Unhandled Failure Modes

### 9. Unbounded Feedback Loops and Runaway API/Compute Cost Blowups
- **Severity:** high
- **Claim:** The blueprint introduces recursive optimization and unconditional Critic retry loops with zero termination guarantees—no `max_iterations`, token/cost budgets, wall-clock timeouts, or oscillation circuit breakers—allowing an insoluble task or flawed premise to burn unbounded LLM credits.
- **Evidence:** Line 36 establishes an automated optimization loop; line 65 mandates an unconditional back-edge (`หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่`); line 81 cites `Recursive Agent Harnessing`. Crucially, line 65 explicitly instructs the Critic to `Attack the premise`, yet provides *only* one failure transition ("send back to loop and fix again") rather than an abort/escalate-to-human exit when the task premise itself is invalid.

### 10. Undefined Behavior Under LLM/Embedder Outages, Rate Limits, and Context Overflows
- **Severity:** med
- **Claim:** Every active stage in the lifecycle depends on external or local model inference, yet the design specifies no timeout handling, backoff/failover policy, idempotency, or fail-open vs. fail-closed semantics when an LLM or embedding endpoint becomes unavailable mid-run.
- **Evidence:** Steps 1–4 (lines 59–67) assume uninterrupted availability across Vault semantic search (Step 1), `Harness²` + `Pi` execution (Step 2), `Critic Agent` review (Step 3), and lesson synthesis/embedding (Step 4). An outage during Step 3 or Step 4 leaves dirty branches, live sandboxes, or unindexed Obsidian notes with no defined reconciliation path.

### 11. Unrecoverable Corruption of Self-Modified Prompts/Tools and Persistent Memory
- **Severity:** high
- **Claim:** While target repository code is protected by Git branches, the rig's own evolving control plane—prompts and tools mutated automatically by Layer 2, plus the dual-store Vault in Layer 1—lacks versioning, transactionality, regression gating, or rollback checkpoints.
- **Evidence:** Layer 5 provides `Git-Native Checkpoints` (`แยก Branch ทดลอง ย้อนเวลาได้`, line 51) scoped in Step 2 to target project branches (`harness-trial-<task-id>`, line 62). Meanwhile, Layer 2 mutates tools and prompts automatically (`ปรับปรุงเครื่องมือ/Prompt อัตโนมัติ`, line 36) and Step 4 mutates the Vault automatically (line 67). A degenerate prompt/tool edit or interrupted ChromaDB write corrupts global rig state across all subsequent tasks with no rollback mechanism.

### 12. Adversarial Repositories: Indirect Prompt Injection and Persistent Cross-Project Infection
- **Severity:** high
- **Claim:** Running autonomously on untrusted repositories exposes `Pi`, `Harness²`, and the `Critic` to indirect prompt injection via source files, comments, git history, or crafted test stdout—and Step 4 weaponizes successful injection into a persistent worm by automatically saving attacker-influenced "lessons" into the global cross-project Vault.
- **Evidence:** Step 2 executes untrusted repository test suites (`รันเทส`, line 63), Step 3 inspects code/test results (line 65), and Step 4 automatically writes extracted lessons to the shared Obsidian Vault (`บันทึกผลลัพธ์และบทเรียนสำคัญกลับลงเป็น Note ใน Obsidian Vault อัตโนมัติ`, line 67) to be retrieved across projects (`ข้ามโปรเจกต์`, line 31). No input sanitization, untrusted-data framing, or sandbox CPU/memory/PID limits (against fork bombs or infinite test hangs) are specified.

---

## (d) Trust-Boundary and Security Gaps

### 13. Unspecified Sandbox Isolation Policy and Unsandboxed Host Execution in Early Rollout Phases
- **Severity:** high
- **Claim:** Layer 5 asserts a "safe closed box" without defining a threat model or enforcement boundary (network egress, filesystem mounts, syscalls, environment variables), and the blueprint's own implementation roadmap explicitly runs automated code/test loops *outside* any sandbox during short- and medium-term phases.
- **Evidence:** Lines 50–51 describe Layer 5 solely as `Isolated Sandbox + Git-Native Checkpoints — รันในกล่องปิดปลอดภัย` with zero technical constraints. Worse, `Implementation Steps` defer sandbox integration to the *long-term* milestone (`ระยะยาว: ประกอบร่างเป็น CLI Wrapper ตัวเดียวที่ดึงพลังของ Pi มาเชื่อมกับ Sandbox และ Memory อย่างสมบูรณ์`, line 74), whereas the *medium-term* milestone (`ระยะกลาง: เขียนสคริปต์ Python/Bash ควบคุม Git Branch + Test Runner เพื่อทำ Contrastive Loop`, line 73) runs autonomous multi-branch test execution directly on the bare host.

### 14. Credential and `.git` Privilege Collapse From Running `Pi` Inside the Sandbox
- **Severity:** high
- **Claim:** Placing the LLM-driven executor (`Pi`) inside the same `Isolated Sandbox` as untrusted repository tests collapses the trust boundary between agent control credentials and untrusted code execution, exposing LLM API keys, outbound network channels, and `.git/hooks` to malicious test scripts.
- **Evidence:** Line 63 specifies `สั่งให้ Pi ลงมือแก้ไขโค้ดและรันเทสภายใน Isolated Sandbox` ("instruct Pi to edit code and run tests inside the Isolated Sandbox"). For `Pi` (line 40) to call an LLM API from inside the sandbox, the sandbox must possess both network egress and API credentials—which any malicious `setup.py`, `conftest.py`, or `npm test` script executed in that same sandbox can read and exfiltrate. Furthermore, write access to `.git` inside the sandbox lets untrusted code install malicious Git hooks that execute on the host once the branch is inspected or merged.

### 15. Unconstrained Self-Modification of Control-Plane Tools and Critic Prompts
- **Severity:** high
- **Claim:** Granting Layer 2 (`Harness²`) autonomous authority to modify *tools* and *prompts* blurs the code/control-plane trust boundary, enabling privilege escalation on the host or self-weakening of Layer 4's `pstack` disciplinary prompts without human approval.
- **Evidence:** Line 36 explicitly states `วนลูปแก้ปัญหาและปรับปรุงเครื่องมือ/Prompt อัตโนมัติ` ("loop to solve problems and automatically improve tools/prompts"). No immutability boundary separates target-repository edits (sandboxed in Layer 5) from host-side CLI tools (`เครื่องมือ`) or Layer 4's engineering rules (`กฎเหล็กวิศวกรรม`, line 46). An optimizer rewarded for passing Step 3 has a direct incentive to rewrite prompts or helper tools to relax Critic scrutiny.

### 16. Cross-Project Confidentiality Collapse via Shared Global Semantic Vault
- **Severity:** med
- **Claim:** Pooling automatically generated notes from all projects into a single unpartitioned `Obsidian / ChromaDB` store violates repository confidentiality boundaries, risking leakage of proprietary algorithms, internal URLs, or hardcoded secrets from private codebases into prompts for unrelated or public repositories.
- **Evidence:** Line 31 mandates cross-project memory sharing (`ดึงความจำเก่า / บันทึกบทเรียนสะสมข้ามโปรเจกต์`) and line 67 automates note ingestion (`บันทึก...อัตโนมัติ`) with no tenant ACLs, sensitivity tagging, or secret-redaction filter prior to persistence or retrieval.

---

## Overall Verdict

As written, `blueprint-ultimate-autonomous-engineering-rig.md` is an aspirational 86-line thesis note rather than an implementable or safe systems specification: it identifies five complementary ideas (memory, meta-optimization, terminal execution, adversarial critique, and sandboxing) but wires them together with contradictory topology diagrams, zero inter-layer contracts, and dangerous closed-loop feedback paths. Its most severe flaws are structural and security-critical—specifically, allowing the executor and untrusted tests to share a privilege domain, omitting an independent tamper-proof verification oracle, granting `Harness²` unversioned authority to self-modify tools and prompts without budget or iteration caps, deferring sandboxing until the final rollout phase, and automatically ingesting unverified outputs into a global cross-project `Obsidian / ChromaDB` vault where a single hallucination or prompt-injected repository permanently poisons future runs. Before this blueprint can safely guide engineering implementation, it must establish strict host-versus-sandbox privilege separation (networkless sandboxed test runner separated from API-key-bearing agent controller), immutable external gate enforcement over read-only tests, git-worktree isolation per trial variant, hard cost/iteration circuit breakers with human escalation, and quarantined, schema-scoped, version-controlled memory/prompt mutations.
