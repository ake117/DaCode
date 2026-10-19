# DaCode — The Ultimate Autonomous Engineering Rig

> A 5-layer coding-agent rig built from the blueprint *Ultimate Autonomous
> Engineering Rig* — combining **Pi**, **Google Harness²**, **pstack**, an
> **Obsidian vault memory**, and an **isolated git sandbox** into one CLI.

DaCode does not just run a prompt once. It **proposes** several ways to run the
task, **probes** each one in its own git worktree, lets an **adversarial critic**
gate the result against real tests, and **writes the lesson back** to the vault
so the next run starts smarter. No ground-truth labels required.

---

## The 5-layer stack

| # | Layer | Module | Job |
|---|-------|--------|-----|
| 1 | **Vault Memory** | `dacode/memory/` | retrieve prior lessons → seed the harness; ingest the winner back as a note |
| 2 | **Harness² Optimizer** | `dacode/harness/` | Propose → Probe → Compose recursion over *harness* variants |
| 3 | **Executor** | `dacode/executor/` | Pi coding agent (or a script / test double) does the change |
| 4 | **pstack Discipline** | `dacode/discipline/` | AST checks for weak tests + a real `pytest` run as the gate |
| 5 | **Git Sandbox** | `dacode/sandbox/` | one isolated `git worktree` per trial, checkpoint + rollback |

```
        ┌───────────────────────────────────────────────┐
        │ 1. Vault Memory   retrieve(task) → snippets    │
        └───────────────────────┬───────────────────────┘
                                ▼
        ┌───────────────────────────────────────────────┐
        │ 2. Harness²   propose(n) → probe → compose     │
        └───────────────────────┬───────────────────────┘
                                ▼
        ┌───────────────────────────────────────────────┐
        │ 5. Git Sandbox  worktree per trial (isolated)  │
        │ 3. Executor     Pi / script applies the change │
        └───────────────────────┬───────────────────────┘
                                ▼
        ┌───────────────────────────────────────────────┐
        │ 4. pstack Critic   static scan + real tests    │
        └───────────────────────┬───────────────────────┘
                                ▼
        ┌───────────────────────────────────────────────┐
        │ 1. Vault Memory   ingest(lesson) if it passed  │
        └───────────────────────────────────────────────┘
```

---

## Install

```bash
# from the repo root
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Runtime needs: `git`, `pi` (Pi coding agent) on `PATH`, and an OpenRouter key in
`OPENROUTER_API_KEY`.

---

## Usage

```bash
# show layer health
.venv/bin/dacode --repo . layers

# run a task through the full rig (Pi as executor, DeepSeek v4.1 Flash)
OPENROUTER_API_KEY=... .venv/bin/dacode run "add a slugify() helper with tests" --budget 2

# deterministic run without an LLM (good for demos / CI)
.venv/bin/dacode run "..." --llm stub --executor script --script-command '...'

# search vault memory
.venv/bin/dacode memory search "harness2 propose probe compose"

# inspect / clean trial worktrees
.venv/bin/dacode sandbox list
.venv/bin/dacode sandbox clean
```

### Engine configuration

| Flag | Values | Default |
|------|--------|---------|
| `--llm` | `stub` \| `local` \| `openrouter` \| `openai` | `openrouter` |
| `--model` | any model id | `deepseek/deepseek-v4.1-flash` |
| `--executor` | `pi` \| `script` | `pi` |

Environment overrides: `DACODE_REPO`, `DACODE_VAULT`, `DACODE_LLM`,
`DACODE_MODEL`, `DACODE_EXECUTOR`, `DACODE_BUDGET`, `DACODE_VARIANTS`.

---

## How a run works

1. **Initialization & Context** — `VaultMemory.retrieve(task)` returns the most
   relevant notes; their titles + snippets become `memory_snippets` on the base
   harness variant.
2. **Experimentation Loop** — for each round, the optimizer asks the LLM for
   `n` genuinely different harness variants, then probes each one:
   * a fresh `git worktree` is created on branch `dacode/trial/<task>-rN-vM`
   * the executor applies the change inside it
   * the critic scans the tests and runs `pytest`
   * passing trials are checkpointed (committed) in their worktree
3. **Compose** — the best variant is selected (LLM-assisted, with a
   deterministic fallback to the measured ranking).
4. **Memory Ingestion** — if the winner passed, a `type: lesson` note is written
   into the vault under `Resources/DaCode/Lessons/`.

Losing trial worktrees are cleaned up automatically; the winner's worktree is
kept so you can inspect the diff.

---

## Tests

```bash
.venv/bin/python -m pytest -q
```

The suite covers every layer plus the end-to-end rig. The harness/orchestrator
tests use a deterministic `FakeExecutor` and a `StubLLM`, so they need neither
Pi nor network — but they exercise **real** git worktrees and **real** pytest
runs inside the critic.

---

## Design principles

Built to the pstack rules:

* **Test behaviour, not implementation** — `discipline/checks.py` flags
  assertion-free tests, tautologies, and weak `assert x` / `assert True` forms.
* **Prove it works** — the critic runs the tests; a report without a run is not
  a report.
* **Build the lever** — the rig itself is the tool; every layer is rerunnable.
* **Sequence verifiable units** — one worktree, one trial, one checkpoint.

---

## Status / roadmap

- [x] Layer 1 Vault Memory (keyword retrieval + ingestion)
- [x] Layer 2 Harness² Optimizer (Propose–Probe–Compose)
- [x] Layer 3 Executor (Pi + script + stub)
- [x] Layer 4 pstack Critic (static checks + real test gate)
- [x] Layer 5 Git Sandbox (worktrees + checkpoints)
- [x] CLI + end-to-end tests
- [ ] Semantic embedding retrieval for the vault layer
- [ ] Parallel probing of variants (multiple worktrees at once)
- [ ] Container/bwrap isolation on top of the worktree
- [ ] `dacode retro` — suggest harness improvements after a run (pstack #5)
