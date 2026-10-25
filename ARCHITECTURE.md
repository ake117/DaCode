# DaCode Architecture

This document maps the blueprint *Ultimate Autonomous Engineering Rig* onto the
code in this repository.

## Blueprint → code map

| Blueprint element | Code |
|---|---|
| 1. Semantic Vault Memory | `dacode/memory/__init__.py` — `VaultMemory`, `MemoryHit`, `Lesson` |
| 2. Google Harness² (Propose-Probe-Compose) | `dacode/harness/optimizer.py` — `HarnessOptimizer`; `dacode/harness/models.py` |
| 3. Pi Coding Agent (executor) | `dacode/executor/pi.py` — `PiExecutor`; `dacode/executor/script.py`; `dacode/executor/base.py` |
| 4. pstack Principles + Adversarial Critic | `dacode/discipline/critic.py`, `dacode/discipline/checks.py` |
| 5. Isolated Sandbox + Git Checkpoints | `dacode/sandbox/__init__.py` — `GitSandbox` |
| Workflow lifecycle wiring | `dacode/orchestrator.py` — `DaCodeRig` |
| CLI wrapper (blueprint's long-term goal) | `dacode/cli.py` |

## Workflow lifecycle (blueprint §Workflow)

### 1. Initialization & Context — Layer 1

`DaCodeRig.run_task` calls `VaultMemory.retrieve(task, limit=5)`. Each hit
contributes `"<title>: <snippet>"` to `HarnessVariant.memory_snippets` on the
seeded base variant. Retrieval is TF scoring over markdown notes — title matches
weigh 3× body matches, Thai and Latin tokens both supported, stopword-filtered.

### 2. Experimentation Loop — Layers 2 & 5

`HarnessOptimizer.run` iterates up to `budget` rounds. Each round:

* `propose(task, base, n)` asks the LLM for `n` harness variants as JSON; the
  parser tolerates markdown fences and prose, and falls back to the base variant
  if the reply is unusable — **a bad LLM reply never stalls the loop**.
* `probe(variant, task, trial_id)` is where Layers 5 and 3 meet:
  * `GitSandbox.create(trial_id)` → a new `git worktree` on branch
    `dacode/trial/<slug>` (isolated from the base checkout and sibling trials).
  * `executor.run(variant, workspace)` applies the change.
  * `critic.review_workspace(workspace)` gates it (Layer 4).
  * on success, `GitSandbox.checkpoint(trial_id, msg)` commits inside the trial.

### 3. Discipline & Critique — Layer 4

`PstackCritic.review_workspace` does two things:

* **static scan** — `check_python_test` walks the AST of every `test_*.py` and
  flags the five pstack anti-patterns: assertion-free tests, tautologies,
  weak truthiness (`assert x`), constant assertions (`assert True`), and weak
  unittest methods (`assertIsNotNone`, …).
* **real run** — executes the configured test command and requires a clean exit.
  A workspace with zero collected tests is an automatic failure (pstack #9).

The critic returns a `CritiqueReport` with a score; a trial "passes" only when
the exit code is 0, at least one test ran, there are no error-level findings,
and the score clears `min_score`.

### 4. Memory Ingestion — Layer 1

When the run passes, `DaCodeRig._build_lesson` composes a markdown lesson
(the task, the winning variant, the score, and the winning system prompt) and
`VaultMemory.ingest` writes it under `Projects/DaCode/Lessons/` with a
`type: lesson` frontmatter block — so it is retrievable on the next run.

## The Harness² recursion, precisely

**Task-level recursion** lives in `HarnessOptimizer.run`: propose → probe →
compose, repeated within a budget, keeping the best measured variant across
rounds.

**Harnessing-level recursion** is the ingestion step above: a winning harness
becomes a persistent vault note, which seeds the base variant of future tasks.
This is exactly the two-level structure described in the Harness² paper — the
difference being we encode the persistent-improvement store as an Obsidian vault
rather than a bespoke database.

## Scoring

`_variant_score(result)`:

```
base   = tests_passed / tests_total      (0 if no tests ran)
bonus  = 0.5  if the critique passed
penalty= 0.25 if the executor exited non-zero
score  = base + bonus - penalty
```

`compose` ranks by this score; the LLM may override the choice, but the measured
ranking is always the fallback — so the loop degrades gracefully without a model.

## Isolation model

```
<repo>/                                  # base checkout — never touched
<repo>/../.dacode/worktrees/
    ├── task-a-r1-1-v1/                  # trial worktree, branch dacode/trial/...
    ├── task-a-r1-2-v2/
    └── ...
```

Each trial is a separate working directory sharing the repo's object store. A
trial cannot affect the base checkout or another trial's files. `checkpoint`
commits within the trial; `rollback` hard-resets it. Losing trials are removed
(worktree + branch) after each round; the winner is kept for inspection.

## Extension points

* **Semantic retrieval** — replace `VaultMemory._score` with an embedding
  backend; the rest of the pipeline is agnostic.
* **New executors** — implement `run(variant, workspace) -> ExecResult`.
* **New checks** — add functions returning `Finding` to `discipline/checks.py`.
* **Stronger isolation** — wrap `executor.run` in `bwrap`/docker without
  changing the optimizer.

## Module dependency graph

```
cli → orchestrator → {memory, harness → {sandbox, executor, discipline, llm}}
                          sandbox → git (subprocess)
                          executor → pi (subprocess) | shell
                          discipline → ast, pytest (subprocess)
                          llm → urllib (no third-party deps)
```

No third-party runtime dependencies — everything is stdlib + subprocess.
