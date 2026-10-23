# DaCode — The Ultimate Autonomous Engineering Rig

> A 5-layer coding-agent rig built from the blueprint *Ultimate Autonomous
> Engineering Rig* — combining **Pi**, **Google Harness²**, **pstack**, an
> **Obsidian vault memory**, and an **isolated git sandbox** into one CLI,
> with an optional **Jev** (TypeSafe System One) judgment layer on Compose.

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
| + | **Jev Judge** *(optional)* | `dacode/judgment.py` | a TypeSafe **System One** decision model picks the Compose winner — `--judge jev` |

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

Optional: a TypeSafe key in `JEV_API_KEY` for `--judge jev` — the System One
decision model that picks the Compose winner (fast, typed answers with
probabilities; it never issues pass/fail verdicts).

---

## Usage

```bash
# show layer health
.venv/bin/dacode --repo . layers

# run a task through the full rig (Pi as executor, DeepSeek v4.1 Flash)
OPENROUTER_API_KEY=... .venv/bin/dacode run "add a slugify() helper with tests" --budget 2

# same run, plus a Jev (System One) judge picking the Compose winner
OPENROUTER_API_KEY=... JEV_API_KEY=... .venv/bin/dacode run "..." --budget 2 --judge jev

# deterministic run without an LLM (good for demos / CI)
.venv/bin/dacode run "..." --llm stub --executor script --script-command '...'

# memory: keyword + DaCode's own embeddings (see "Memory backends")
.venv/bin/dacode memory index                       # embed the vault (incremental)
.venv/bin/dacode memory backends                    # which backends are usable
.venv/bin/dacode memory search "harness2 propose probe compose"
.venv/bin/dacode memory search "isolate agent worktrees" --backend local

# score Jev's Compose picks against recorded gate-verified winners
.venv/bin/dacode judge-eval --limit 10

# query the local SQLite history (runs, variants, picks)
.venv/bin/dacode state stats
.venv/bin/dacode state search "docstring sandbox"
.venv/bin/dacode state failures --task slugify   # don't retry these blindly

# inspect / clean trial worktrees
.venv/bin/dacode sandbox list
.venv/bin/dacode sandbox clean
```

### Engine configuration

| Flag | Values | Default |
|------|--------|---------|
| `--llm` | `stub` \| `local` \| any provider preset (table below) | `openrouter` |
| `--model` | any model id | `deepseek/deepseek-v4.1-flash` |
| `--executor` | `pi` \| `script` | `pi` |
| `--judge` | `jev` (unset = off) | off |
| `--escalate-models` | comma-separated model ladder, e.g. `claude-sonnet-4-5,gpt-4o` | none |

Environment overrides: `DACODE_REPO`, `DACODE_VAULT`, `DACODE_LLM`,
`DACODE_MODEL`, `DACODE_EXECUTOR`, `DACODE_BUDGET`, `DACODE_VARIANTS`,
`DACODE_JUDGE`, `DACODE_ESCALATE_MODELS`, `DACODE_RUNLOG` (`off` disables
the recorder; default `~/.local/state/dacode/runlog.jsonl`),
`DACODE_MEMORY_DB` (`off` disables the state store; default
`~/.local/state/dacode/memory.db`), `DACODE_SEMANTIC_BACKEND` (`auto` by
default — see "Memory backends"), `DACODE_EMBED_BASE_URL`, `DACODE_EMBED_MODEL`,
`DACODE_EMBED_API_KEY`, `DACODE_EMBED_BATCH`, `DACODE_EMBED_TIMEOUT`,
`DACODE_EMBED_DB`, and `DACODE_SEMANTIC=off` as the global kill switch.

### AI providers

| `--llm` | Key env var | Default model |
|---------|-------------|---------------|
| `openrouter` | `OPENROUTER_API_KEY` | `deepseek/deepseek-v4.1-flash` |
| `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `mistral` | `MISTRAL_API_KEY` | `mistral-small-latest` |
| `xai` | `XAI_API_KEY` | `grok-4` |

Keys resolve in order: an explicit `--api-key` / `api_key=` kwarg → the
provider's env var, populated from the **target repo's** `.env` by
`cli.load_env`. DaCode deliberately never reads `~/.hermes/.env` or Pi's auth
store (`~/.pi/agent/auth.json`) — secrets stay with the project they belong
to. Every provider speaks the OpenAI-compatible shape, so adding one is a
single entry in `dacode/llm/providers.py`.

---

## Memory backends

Retrieval always runs the keyword/TF pass, then blends in a semantic backend
(60% cosine similarity + 40% normalized keyword score). **DaCode owns its
memory by default** — no other agent, database server, or service required.

| Backend | What it uses | When |
|---------|--------------|------|
| `local` (default) | DaCode's own vector store (`~/.local/state/dacode/embeddings.db`) built from any OpenAI-compatible `/v1/embeddings` endpoint | picked by `auto` as soon as vectors exist |
| `hermes` | an external index queried over a subprocess (Hermes' semantic-vault-search by default) — one bundled example of an adapter | `auto` fallback, or explicitly |
| keyword only | TF over the vault | no backend configured, or `DACODE_SEMANTIC_BACKEND=off` |

```bash
# point DaCode at any embedding endpoint — a local model needs no API key
export DACODE_EMBED_BASE_URL=http://127.0.0.1:11434/v1   # e.g. Ollama
export DACODE_EMBED_MODEL=bge-m3
.venv/bin/dacode memory index         # embed the vault (incremental by mtime)
.venv/bin/dacode memory backends      # what is usable right now
.venv/bin/dacode memory search "isolate agent worktrees" --backend local
```

`memory index` skips unchanged notes and prunes deleted ones; changing the
embedding model requires `--rebuild`, because the store refuses to mix models
(two models in one index produce plausible-looking garbage). Without an
embedder configured nothing breaks — retrieval is simply keyword-only.

### Plugging in another agent's memory

A backend is any object with `available()` and
`search(query, top=8) -> list[SemanticHit]`. No registration needed:

```bash
export DACODE_SEMANTIC_BACKEND="my_package.memory:make_backend"  # called with the vault path
export DACODE_SEMANTIC_BACKEND=hermes                            # the bundled adapter
```

`dacode/memory/backends/hermes.py` is the worked example: it shells out to an
external search script and maps its JSON onto `SemanticHit`.

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
3. **Compose** — the best variant is selected (an optional Jev System One
   judgment, then LLM-assisted, with a deterministic fallback to the measured
   ranking). The judge only picks among variants the gate already scored —
   the pass/fail verdict stays with the critic. When the gate did not pass
   and budget remains, the judge also **triages** the next action: retry the
   same variants, propose fresh ones, escalate the executor up a model ladder
   (`--escalate-models`), or stop and flag the task for human review.
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
- [x] Jev (TypeSafe System One) judge for the Compose pick (`--judge jev`)
- [x] Judge triage after a failed round — retry / new proposal / escalate model / human review
- [x] Run recorder (`dacode/runlog.py`) + `dacode judge-eval` — Jev agreement with the critic gate
- [x] SQLite local state store (`memory.db`) + FTS5 trigram search — `dacode state`
- [x] Semantic retrieval with pluggable backends — DaCode-owned vector store by default (60/40 blend)
- [ ] Parallel probing of variants (multiple worktrees at once)
- [ ] Container/bwrap isolation on top of the worktree
- [ ] `dacode retro` — suggest harness improvements after a run (pstack #5)
