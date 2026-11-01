# Stage 4 Review — Implementation Readiness (`blueprint-ultimate-autonomous-engineering-rig.md`)

- **Reviewed document:** `docs/design/blueprint-ultimate-autonomous-engineering-rig.md` (86 lines; YAML `created: 2026-10-18`, `updated: 2026-10-18`)
- **Repository snapshot audited:** `HEAD` (`ee826b1`, `2026-11-01`, package `dacode` `v0.7.0` + 5 post-release commits; 94 total commits since `6e34fdc` on `2026-10-19`; 39 Python modules under `dacode/`; 28 `tests/test_*.py` modules collecting **370 tests**)
- **Audit mode:** Fresh-context, read-only empirical verification of every blueprint claim against repository files, CLI parser definitions, AST/runtime control flow, test collection, and git history.

## Verdict Summary

| Verdict | Count | Findings |
|---|---:|---|
| **VERIFIED** | 8 | #1, #4, #8, #11, #13, #16, #19, #21 |
| **WRONG** | 7 | #7, #9, #12, #14, #15, #17, #18 |
| **STALE** | 6 | #2, #3, #5, #6, #10, #20 |
| **UNVERIFIABLE** | 1 | #22 |

---

## Numbered Findings

1. **[VERIFIED] Five-component rig composition (`title`, L2; `The 5-Layer Stack`, L26–53)**
   - **Blueprint claim:** Combines five named components — `Pi + Harness² + pstack + Vault + Sandbox` — into a single autonomous engineering rig.
   - **Repository fact:** `pyproject.toml:6-8` declares `name = "dacode"`, `version = "0.7.0"`, and `description = "DaCode — The Ultimate Autonomous Engineering Rig (Pi + Harness² + pstack + Vault + Sandbox)"`. All five layers exist as dedicated packages (`dacode/memory/`, `dacode/harness/`, `dacode/executor/`, `dacode/discipline/`, `dacode/sandbox/`), wired by `DaCodeRig` (`dacode/orchestrator.py:40-215`) and reported by `dacode layers` (`dacode/orchestrator.py:161-180`, which adds a sixth status row, `5b. Isolation`).

2. **[STALE] Frontmatter revision history (`created` / `updated` / `update_history`, L3–6)**
   - **Blueprint claim:** `created: 2026-10-18`, `updated: 2026-10-18`, with a single `update_history` entry from `2026-10-18`.
   - **Repository fact:** The file was imported into git on `2026-10-30` (`24abe07`) and edited in `6f0e5f7` (`2026-10-30`, rewriting L81–86 to anonymise personal names and vault wikilinks) without updating `updated:` or `update_history` (unlike sibling `docs/design/google-harness2-recursive-agent-harnessing.md:6-8`, which records `updated: 2026-10-24`). Across the 14 days from `2026-10-18` to `2026-11-01`, the codebase evolved through 94 commits and 8 semver tags (`v0.2.0`–`v0.7.0`) without any corresponding blueprint revision.

3. **[STALE] Active architecture status (`status: active`, L13)**
   - **Blueprint claim:** Frontmatter declares `type: architecture` and `status: active`.
   - **Repository fact:** `docs/design/README.md:3-8` frames this document as a historical, verbatim copy of *"The origin idea (18 Oct 2026)"*, while `ARCHITECTURE.md` serves as the repo's blueprint-to-code map. Retaining `status: active` misrepresents a frozen pre-`v0.1.0` brainstorm note whose storage engine, branch naming, critic architecture, and vault-sharing model no longer match the live codebase.

4. **[VERIFIED] Primary project alias `"Ultimate Autonomous Engineering Rig"` (`aliases`, L15; H1, L19)**
   - **Blueprint claim:** Named `Ultimate Autonomous Engineering Rig`.
   - **Repository fact:** Used consistently across `pyproject.toml:8`, `README.md:1`, `ARCHITECTURE.md:3`, `dacode/__init__.py:1`, and `dacode/cli.py:117` (`argparse.ArgumentParser(description=...)`).

5. **[STALE] Secondary alias `"Trinity Plus Architecture"` (`aliases`, L16)**
   - **Blueprint claim:** Lists `Trinity Plus Architecture` as an alternate architecture name.
   - **Repository fact:** `git grep -i trinity` returns zero matches anywhere in `dacode/`, `tests/`, `docs/`, `skills/`, or root documentation outside L16 of this file.

6. **[STALE] Abstract positioning as a general "AI Coding Agent" (`[!abstract]`, L21–22)**
   - **Blueprint claim:** Describes an architecture for building a full *"AI Coding Agent ระดับโปร"* (pro-grade AI coding agent).
   - **Repository fact:** DaCode is explicitly **not** a standalone greenfield coding agent; it is a best-of-N harness tournament runner over an external executor (`pi` or `script`) for **one scoped task on an existing git repository with pre-committed tests**, and it never merges its own diff back into the working checkout (`docs/FAQ.md:9-25`, `AGENTS.md:21-31, 52-55`). Repository scaffolding, contract-test authoring, and landing the winning worktree diff remain mandatory human/operator steps.

7. **[WRONG] Top-down 5-layer stack control-flow ordering (`1 → 2 → 3 → 4 → 5`, L28–53)**
   - **Blueprint claim:** The stack diagram connects `1. Vault Memory ▼ 2. Harness² ▼ 3. Pi Coding Agent ▼ 4. pstack Critic ▼ 5. Isolated Sandbox + Git-Native Checkpoints`, placing Layer 5 at the bottom after Layer 4.
   - **Repository fact:** In `DaCodeRig.run_task()` (`dacode/orchestrator.py:184-214`) and `HarnessOptimizer.probe()` (`dacode/harness/optimizer.py:153-190`), **Layer 5 executes before and around Layers 3 and 4, not after Layer 4**: (a) Layer 1 `memory.retrieve()` seeds snippets; (b) Layer 2 `propose()` generates variants; (c) Layer 5 `sandbox.create()` provisions the `git worktree` and `critic.snapshot_contract()` hashes test files *before* Layer 3 runs; (d) Layer 3 `executor.run()` executes inside Layer 5's worktree and `bwrap` sandbox; (e) Layer 4 `critic.review_workspace()` gates the worktree inside a separate offline `bwrap` sandbox; (f) Layer 5 `sandbox.checkpoint()` commits *only if* `report.passed`; and (g) Layer 1 `memory.ingest()` writes the lesson (`README.md:36-57` redraws the diagram accordingly).

8. **[VERIFIED] Layer 1 storage medium: Obsidian Markdown vault (`Obsidian`, L30, L60, L67)**
   - **Blueprint claim:** Stores and retrieves lessons as notes in an Obsidian Vault.
   - **Repository fact:** `VaultMemory` (`dacode/memory/__init__.py:90-389`) scans `.md` files with YAML frontmatter, excludes `.obsidian`, `.git`, `.trash`, and `templates` (`L99`), and is configured via `--vault` (`dacode/cli.py:120`) or `DACODE_VAULT` (`dacode/config.py:46`).
   - **Readiness caveat (internal repo drift):** When no vault path exists on disk, `DaCodeRig.__init__` leaves `self.memory = None` (`dacode/orchestrator.py:67-75`) and silently skips Layer 1. Furthermore, `SECURITY.md:87-88` (updated `2026-11-01`) states *"the lesson vault is a dedicated machine vault (`~/Documents/dacode_vault`), never a personal one"*, whereas `_default_vault()` in `dacode/config.py:84-91` still auto-probes personal vault paths (`~/Documents/Vault` and `~/Vault`) and never checks `~/Documents/dacode_vault`.

9. **[WRONG] Layer 1 vector database: `ChromaDB` (`Obsidian / ChromaDB`, L30)**
   - **Blueprint claim:** Names `ChromaDB` as the vector store for Semantic Vault Memory.
   - **Repository fact:** `ChromaDB` is not used anywhere in the repository (`pyproject.toml:14` has `dependencies = []`, keeping runtime dependencies strictly zero/stdlib; `skills/dacode/references/memory-and-embeddings.md:8` explicitly notes *"exact cosine in SQLite, no ChromaDB, no vector service"*). Instead, DaCode ships:
     - `VectorStore` (`dacode/memory/vectors.py:53-180`), a stdlib `sqlite3` + normalized `float32` (`array('f')`) exact-cosine store at `~/.local/state/dacode/embeddings.db` (`DACODE_EMBED_DB`), populated via any OpenAI-compatible `/v1/embeddings` endpoint (`Embedder` in `dacode/memory/embedder.py`) through `dacode memory index` (`dacode/cli.py:168-169, 344-359`);
     - `VaultMemory._blend()` (`dacode/memory/__init__.py:241-283`), combining `0.6 * cosine_similarity + 0.4 * normalized_keyword_TF` (with Thai + Latin regex tokenization `_WORD_RE` at `L42` and 3× title weighting at `L185`);
     - `HermesIndexBackend` (`dacode/memory/backends/hermes.py`) and `module:factory` (`DACODE_SEMANTIC_BACKEND`) as optional pluggable adapters (`dacode/memory/backends/__init__.py:58-106`).

10. **[STALE] Layer 1 cross-project lesson accumulation & vault-wide retrieval (`บันทึกบทเรียนสะสมข้ามโปรเจกต์`, L31; L60)**
    - **Blueprint claim:** Accumulates and retrieves lessons **across projects** (`ข้ามโปรเจกต์`) and searches the Vault broadly for prior patterns (`ค้น Vault หาบทเรียนหรือแพทเทิร์น`).
    - **Repository fact:** Deliberately **reversed on `2026-11-01`** (commit `e069a45`, documented in `SECURITY.md:75-100` item 8) because cross-project lesson injection (`--append-system-prompt`) creates a cross-repository prompt-injection channel. `DaCodeRig.__init__` now passes `scope=config.repo.name` (`dacode/orchestrator.py:73-75`), restricting `VaultMemory` (`dacode/memory/__init__.py:106-156, 259-261, 355-368`) to read **only** `Projects/<repo.name>/Lessons/**/*.md` plus manually curated `shared/Lessons/**/*.md`, refusing symlinks, filtering semantic hits after `Path.resolve()`, and raising `ValueError` if `ingest()` targets another project folder. Automatic runs on repo A can no longer read lessons ingested by repo B, nor general vault notes outside `Projects/<repo>/Lessons` and `shared/Lessons`.

11. **[VERIFIED] Layer 2 Google Harness² `Propose-Probe-Compose` & prompt optimization (`L35–36`)**
    - **Blueprint claim:** Implements Google Harness²'s `Propose-Probe-Compose` loop and automatically optimizes prompts across rounds.
    - **Repository fact:** `HarnessOptimizer` (`dacode/harness/optimizer.py:62-479`) implements `propose()` (`L103-141`), `probe()` / `probe_round()` (`L153-294`), `compose()` (`L298-386`), and `run()` (`L390-479`) controlled by `--budget` (default `2`) and `--variants` (default `2`, `dacode/cli.py:43-44`). `propose()` varies `HarnessVariant.system_prompt`, `PiExecutor.build_command()` forwards it via `--system-prompt` (`dacode/executor/pi.py:78-84`), `compose()` selects only among gate-passing variants when any pass (`dacode/harness/optimizer.py:304-305`), and the winning `system_prompt` seeds subsequent rounds and vault ingestion.

12. **[WRONG] Layer 2 automatic tool optimization (`ปรับปรุงเครื่องมือ/Prompt อัตโนมัติ`, L36)**
    - **Blueprint claim:** Layer 2 automatically optimizes **tools** alongside prompts (`ปรับปรุงเครื่องมือ/Prompt อัตโนมัติ`).
    - **Repository fact:** **Dead / unwired code.** `_PROPOSE_SYSTEM` instructs the LLM to return `{"label": "...", "system_prompt": "...", "tools": ["..."]}` (`dacode/harness/optimizer.py:51`), and `HarnessOptimizer.propose()` parses and stores `HarnessVariant.tools` (`dacode/harness/optimizer.py:123`, `dacode/harness/models.py:18`). However, **no code anywhere in the repository ever reads `variant.tools`**:
      - `PiExecutor.build_command()` (`dacode/executor/pi.py:91-92`) checks `if self.tools:` (the static constructor tuple `PiExecutor.tools`, defaulting to `()` at `L50` and never passed by `DaCodeRig._build_executor()` at `dacode/orchestrator.py:99-104`), completely ignoring `variant.tools`;
      - `ScriptExecutor.run()` (`dacode/executor/script.py:37-76`) ignores `variant.tools`;
      - `DaCodeRig._build_lesson()` (`dacode/orchestrator.py:217-246`) omits `best.tools` when persisting winning harnesses.

13. **[VERIFIED] Layer 3 Pi Coding Agent executor (`Pi Coding Agent (The Executor / Terminal Interface)`, L40–41, L63)**
    - **Blueprint claim:** Uses the Pi Coding Agent as the executor to edit files and run commands in the project workspace.
    - **Repository fact:** `PiExecutor` (`dacode/executor/pi.py:40-179`) is the default executor (`DaCodeConfig.executor = "pi"`, `dacode/config.py:23`), running `pi --print --mode text --provider <p> --model <m> --system-prompt ... --append-system-prompt ... --no-session -- <task>` with `cwd=str(workspace)`. Layer 3 is abstracted behind the `Executor` protocol (`dacode/executor/base.py:27-31`) and also supports `--executor script` (`ScriptExecutor` in `dacode/executor/script.py`). Note that `pi` is an external Node.js (`>= 22.19`) binary not installed by `pip install -e .` (`docs/installing-pi.md:3-14`), returning exit code `127` when absent from `PATH` (`dacode/executor/pi.py:135-140`).

14. **[WRONG] Layer 4 `Subagent` / `Critic Agent` architecture (`Subagent คอยจับผิด`, L46; `ตัว pstack/Critic Agent`, L65)**
    - **Blueprint claim:** Layer 4 uses an adversarial **`Subagent` / `Critic Agent`** to inspect code and behaviour.
    - **Repository fact:** `PstackCritic` (`dacode/discipline/critic.py:59-692`) and `dacode/discipline/checks.py` make **zero LLM calls and spawn zero subagents** (`ARCHITECTURE.md:122`: `discipline → ast, pytest (subprocess)`; `docs/design/README.md:8` re-labels Layer 4 `"a static-critic test gate"`). Layer 4 is 100% deterministic Python: AST inspection (`_TestVisitor`), pre-trial SHA-256 contract hashing (`snapshot_contract` / `_check_contract`), baseline test/skip counting (`measure_baseline`), and subprocess test execution with out-of-workspace `--junitxml` report verification (`_run_once`, `_junit_counts`). Even the optional `JevJudge` (`--judge jev`, `dacode/judgment.py`) only participates in Layer 2 `compose()` and failed-round `_triage()`, and is explicitly barred from issuing pass/fail verdicts (`dacode/judgment.py:5-6`, `dacode/harness/optimizer.py:303-305, 351-356`).

15. **[WRONG] Layer 4 enforcement of `(Test behavior, Attack the premise)` (L65)**
    - **Blueprint claim:** The critic checks whether code follows `(Test behavior, Attack the premise)`.
    - **Repository fact:** Only the first half exists, and with an internal prompt contradiction:
      - `Test behavior` (pstack #4) is enforced statically on Python `test_*.py` files via `_TestVisitor` (`dacode/discipline/checks.py:58-202`), flagging `assertion_free`, `constant_assertion`, and `tautology` as errors plus `weak_truthiness`, `none_check`, `weak_length`, and `weak_method` as warnings (skipped for non-`.py` suites at `dacode/discipline/critic.py:101`).
      - **`Attack the premise` is completely unimplemented** (`git grep -i premise` matches only L65 of the blueprint).
      - **Internal code contradiction:** `DEFAULT_SYSTEM_PROMPT` (`dacode/harness/optimizer.py:39-43`) still instructs the executor to *"Write or update tests that assert literal behaviour"*, whereas `PstackCritic._check_contract()` and `_check_test_integrity()` (`dacode/discipline/critic.py:397-518`) fail any trial that edits, deletes, or adds a test file with `severity="error"` (`tests_modified`).

16. **[VERIFIED] Layer 5 isolated sandbox, git branches, checkpoints, and rollback (`L50–51, L63, L65`)**
    - **Blueprint claim:** Executes inside a secure closed sandbox (`กล่องปิดปลอดภัย`), isolates experimental branches, commits checkpoints after critique (`ก่อนจะคอมมิต`), and supports rollback (`ย้อนเวลาได้`).
    - **Repository fact:**
      - **OS sandbox (`dacode/sandbox/bwrap.py`):** `--isolate bwrap` is the default (`DaCodeConfig.isolate = "bwrap"`, `dacode/config.py:41`), mounting `/` read-only, replacing `$HOME`, `/tmp`, `/run`, and `/var/tmp` with `tmpfs`, clearing env vars to `BASE_ENV` / `NETWORK_ENV`, masking `<repo>/.env` and `~/.pi/agent/auth.json`, and failing closed (`RuntimeError`, exit `126` executor, exit `125` gate) if `bwrap` or user namespaces are unavailable. The test gate always runs under a separate `gate_isolation` policy with `network=False` (`dacode/orchestrator.py:58, 106-126`).
      - **Git isolation & checkpoints (`dacode/sandbox/__init__.py`):** `GitSandbox.create()` creates an isolated `git worktree` per trial; `HarnessOptimizer.probe()` calls `self.sandbox.checkpoint()` **only** when `report.passed` is `True` (`dacode/harness/optimizer.py:183-190`), with hardened git flags (`core.hooksPath=/dev/null`, `core.fsmonitor=false`, `.git` pointer validation at `dacode/sandbox/__init__.py:70-76, 139-165`); `GitSandbox.rollback()` (`L172-177`) implements `git reset --hard <ref>` + `git clean -fd`.
      - **Readiness caveats:** (a) `GitSandbox.rollback()` has **zero production callers** (`git grep rollback` hits only `dacode/sandbox/__init__.py:172`, docs, and `tests/test_sandbox.py:37` — losing trials are deleted via `sandbox.remove()`); (b) `DaCodeConfig.isolate_network` defaults to `False` (`dacode/config.py:42`), so default `dacode run` with `--executor pi` unshares network and strips provider API keys unless `--isolate-network` is passed — directly contradicting the stale docstring in `DaCodeRig._isolation_policy()` (`dacode/orchestrator.py:131-132`: *"The executor always sees the network when isolation is on"*).

17. **[WRONG] Step 2 git trial branch naming (`harness-trial-<task-id>`, L62)**
    - **Blueprint claim:** Harness² creates a sub-branch named `harness-trial-<task-id>`.
    - **Repository fact:** `git grep harness-trial` matches only L62 of the blueprint. `GitSandbox.__init__` sets `branch_prefix: str = "dacode/trial"` (`dacode/sandbox/__init__.py:55`), `_branch_for()` builds `f"{self.branch_prefix}/{_safe_slug(task_id)}"` (`L95-96`), and `HarnessOptimizer.probe_round()` (`dacode/harness/optimizer.py:277-279`) formats `trial_id = f"{_slug(task)}-{self._trial_nonce()}-r{round_no}-{idx}-{variant.id}"`. Actual branches are named **`dacode/trial/<task-slug>-<5hex-nonce>-r<round>-<idx>-<variant-id>`** inside external worktrees at `<repo>/../.dacode/worktrees/<trial-id>` (`dacode/sandbox/__init__.py:59-63`). *(Secondary repo doc drift: `AGENTS.md:54`, `README.md:232`, and `ARCHITECTURE.md:97-98` still write `<task-slug>-rN-vM`, omitting `<nonce>` and `<idx>`.)*

18. **[WRONG] Step 3 critique-to-loop error feedback (`หากไม่ผ่าน ส่งกลับไปให้วนลูปแก้ใหม่`, L65)**
    - **Blueprint claim:** If a trial fails Layer 4 critique, the critic sends it back to loop and fix the problem (`ส่งกลับไปให้วนลูปแก้ใหม่`).
    - **Repository fact:** While `HarnessOptimizer.run()` (`dacode/harness/optimizer.py:414-460`) does advance to `round_no + 1` when `best` has not passed (unless `--judge jev` `_triage()` returns `human_review`), **no critique feedback or code state is sent back**:
      1. Failed worktrees and branches are deleted by `_cleanup_losers()` (`L438, 543-563`), and every next-round trial branches fresh from untouched `HEAD` (`sandbox.create(trial_id)` at `L159`).
      2. `HarnessOptimizer.propose()` (`dacode/harness/optimizer.py:103-111`) sends the LLM **only** `task`, `base.system_prompt`, and `base.seed_context()` — it **never includes** the previous round's critic `findings`, `probe.errors`, `probe.gate_output`, or test counts. (`ProbeResult.gate_output` and `ProbeResult.errors` at `dacode/harness/models.py:54-55` are read only by `dacode/kanban.py:360, 373` when closing/blocking Kanban cards.) Even `retry_same` triage (`L417-419, 458-459`) re-probes the identical variants from scratch for transient network/rate-limit errors.

19. **[VERIFIED] Step 4 automatic Obsidian lesson ingestion (`Memory Ingestion`, L66–67)**
    - **Blueprint claim:** When tests pass and critique succeeds, the system automatically writes the result and winning lesson back as an Obsidian Vault note so future runs start smarter.
    - **Repository fact:** In `DaCodeRig.run_task()` (`dacode/orchestrator.py:210-213`), when `result.passed and self.memory is not None`, `_build_lesson()` (`L217-246`) formats a redacted Markdown note containing the task, winning variant ID/label, rounds, score, test pass ratio, worktree basename, and winning `system_prompt`, and `VaultMemory.ingest()` (`dacode/memory/__init__.py:361-389`) writes `<vault>/Projects/<repo-name>/Lessons/<YYYYMMDD-HHMMSS>-<slug>.md` with JSON-quoted YAML frontmatter (`type: lesson`, `source: dacode`).
    - **Readiness caveat:** `VaultMemory.ingest()` writes the `.md` file on disk **without updating `VectorStore` (`embeddings.db`)**. Until `dacode memory index` is executed manually, newly ingested lessons are missing from `local` semantic vector search and can only surface through the 40%-weighted keyword/TF pass.

20. **[STALE] Phased implementation roadmap (`ระยะสั้น / ระยะกลาง / ระยะยาว`, L71–75)**
    - **Blueprint claim:** Proposes three future stages: short-term (manual `pstack` + Vault prompt context), medium-term (Python/Bash Git-branch + test-runner contrastive script), and long-term (single unified CLI wrapper connecting Pi, Sandbox, and Memory).
    - **Repository fact:** All three stages — including the "long-term" unified CLI (`dacode = "dacode.cli:main"` in `pyproject.toml:20`) — shipped in `v0.1.0` (`6e34fdc`, `2026-10-19`) and have since expanded into **10 CLI subcommands** (`dacode/cli.py:124-198`: `run`, `kanban work`, `mcp`, `watch`, `retro`, `memory {search,backends,index}`, `sandbox {list,clean}`, `judge-eval`, `state {search,stats,failures,rebuild}`, `layers`) and major subsystems absent from the blueprint:
      - 9 OpenAI-compatible LLM provider presets + `local` + `stub` (`dacode/llm/providers.py`), `--executor-provider`, multi-model `--fleet`, `--parallel N`, and `--variant-timeout`;
      - Optional TypeSafe System One judge (`--judge jev`, `--escalate-models`, `dacode judge-eval` in `dacode/judgment.py`, `dacode/jeval.py`);
      - Redacted `0700` JSONL run recorder (`dacode/runlog.py`, `dacode/redact.py`), SQLite FTS5-trigram state mirror (`dacode/state.py`), deterministic harness retrospective (`dacode/retro.py`), and live TUI log viewer (`dacode/watch.py`);
      - Stdlib stdio JSON-RPC MCP server exposing 5 tools (`dacode/mcp/server.py`) and atomic Hermes Kanban worker (`dacode/kanban.py`).
      *(Note: `ARCHITECTURE.md:107-124` has also drifted behind the code, still listing semantic retrieval and `bwrap` isolation as unbuilt "Extension points".)*

21. **[VERIFIED] Related companion note & DaCode realization (`## 🔗 Related`, L81–82; historical test-count drift)**
    - **Blueprint claim:** Points to `Google Harness2 — Recursive Agent Harnessing (โน้ตถัดไปในโฟลเดอร์นี้)` ("next note in this folder") and `DaCode — โปรเจกต์ที่ blueprint นี้กลายเป็นจริง` (which, in commit `24abe07` before `6f0e5f7` anonymisation, asserted `5 layer ครบ + 50 tests`).
    - **Repository fact:** `docs/design/google-harness2-recursive-agent-harnessing.md` sits directly alongside this file in `docs/design/`, and `dacode` implements the 5-layer stack. Test count has grown more than 7× since the October note: from `50 tests` (pre-anonymised blueprint note, Oct 20) and `# 232 tests` (stale comment still present in `skills/dacode/SKILL.md:213`) to **370 collected pytest tests** across 28 `tests/test_*.py` files at `HEAD`.

22. **[UNVERIFIABLE] Pre-repository brainstorming attribution (`## 📚 Sources`, L86)**
    - **Blueprint claim:** Originates from a joint brainstorming session between the user and an AI assistant on `18 ตุลาคม 2026`.
    - **Repository fact:** Predates the repository's initial commit (`6e34fdc`, `2026-10-19`); corroborated only by commit messages (`24abe07`, `6f0e5f7`) and `docs/design/README.md:3-8`, with no primary transcript in the repository.

---

## Drift Verdict

Since `blueprint-ultimate-autonomous-engineering-rig.md` was written on 18 October 2026 (one day before `v0.1.0`), DaCode has undergone substantial, mostly deliberate architectural drift across 94 commits, 8 releases (`v0.2.0`–`v0.7.0`), and a 7.4× expansion in test coverage (50 → 370 tests): the rig abandoned `ChromaDB` for a zero-dependency SQLite float32 vector store (`embeddings.db`) blended 60/40 with keyword TF, replaced the envisioned LLM "Critic Subagent / Attack-the-premise" reviewer with a deterministic AST + SHA-256 contract-hash + JUnit-XML test gate, wrapped both executor and gate in fail-closed `bubblewrap` namespaces (`--isolate bwrap`), reversed cross-project vault lesson sharing into strict per-repository scoping (`Projects/<repo>/Lessons/`) to close a prompt-injection channel, and grew far past its "long-term CLI wrapper" milestone with `--fleet`, `--parallel`, Jev System One compose/triage, a redacted JSONL/SQLite FTS5 ledger (`state`, `retro`, `watch`), an MCP server, and a Hermes Kanban worker. Because `docs/design/README.md` preserves the blueprint as an historical origin artifact, its divergence on superseded choices is expected — though its frontmatter `status: active` (`L13`) should be retired to `historical`/`superseded` (and `ARCHITECTURE.md:107-124` + `skills/dacode/SKILL.md:213` refreshed where they lag `v0.7.0`). More critically, verifying the blueprint line-by-line against `HEAD` exposes **five live implementation-readiness gaps in the code itself**: (1) `HarnessVariant.tools` is requested from the LLM and parsed in `HarnessOptimizer.propose()` (`dacode/harness/optimizer.py:51, 123`) but completely ignored by `PiExecutor.build_command()` (`dacode/executor/pi.py:91`, which reads static `self.tools`); (2) failed-round critic diagnostics (`findings`, `probe.errors`, `probe.gate_output`) are never fed back into `HarnessOptimizer.propose()` (`dacode/harness/optimizer.py:103-111`), leaving multi-round retries blind to why the gate failed; (3) `DEFAULT_SYSTEM_PROMPT` (`dacode/harness/optimizer.py:41`) still tells trials to *"Write or update tests"*, which `PstackCritic` immediately fails as `tests_modified`; (4) `VaultMemory.ingest()` writes lesson notes without indexing them into `VectorStore`, leaving new lessons invisible to `local` vector search until `dacode memory index` is run manually; and (5) `dacode/config.py:84-91` (`_default_vault()`) and `dacode/orchestrator.py:131-132` (`_isolation_policy` docstring) contradict `SECURITY.md:88` (`~/Documents/dacode_vault`) and actual `--isolate-network` default-off behaviour.
