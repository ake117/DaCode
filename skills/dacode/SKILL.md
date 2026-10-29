---
name: dacode
description: "Use when running, extending, or debugging the DaCode rig (the 5-layer autonomous engineering rig) — running a task through it, adding an executor or check, or diagnosing a trial that will not pass. Covers the CLI, the layer→module map, and the rules that keep the gate honest."
author: ake117
license: MIT
metadata:
  version: 2.3.0
  hermes:
    tags: [agents, engineering, harness2, pstack, sandbox, git-worktree, cli]
    related_skills: [pstack-principles, plan, subagent-driven-development, agent-dispatch, hermes-agent, orca-remote-access]
---

# DaCode — the autonomous engineering rig

**What it is.** A 5-layer coding-agent rig built from the blueprint *Ultimate
Autonomous Engineering Rig*: Pi (executor) + Google Harness²
(Propose–Probe–Compose) + pstack (adversarial critic) + an Obsidian vault
(memory) + an isolated git-worktree sandbox, in one CLI. A run proposes several
*harness* variants, probes each in its own worktree, gates them on real tests,
and writes the winning lesson back to the vault.

**Where.** The DaCode checkout (git repo, branch `main`). Runtime needs `git`,
`pi` on PATH, and an OpenRouter key. `dacode` is on PATH via
`~/.local/bin/dacode`; `--repo` defaults to the current directory, so `cd` into
the target repo first. Releases: `v0.2.0` (gate integrity, ledger, parallel,
retro), `v0.3.0` (fleet diversity, MCP memory server), `v0.4.0` (bubblewrap
isolation), `v0.5.x` (audit cycle: JUnit-verified counts, commit-proof suite
hashing, masked credentials, redaction, gate-authoritative composition).

## Layer → module map

| Layer | Module | Responsibility |
|---|---|---|
| 1 Vault memory | `dacode/memory/{__init__,semantic}.py` | `VaultMemory.retrieve()` / `.ingest()`; keyword TF + optional semantic blend |
| 2 Harness² optimizer | `dacode/harness/optimizer.py` | `propose/probe/probe_round/compose/run`, fleet assignment, triage loop |
| 3 Executor | `dacode/executor/{pi,script,base}.py` | `PiExecutor`, `ScriptExecutor`; `run(variant, workspace) -> ExecResult` |
| 4 pstack critic | `dacode/discipline/{critic,checks}.py` | AST scan of tests + real `pytest` gate + baseline/integrity guards |
| 5 Git sandbox | `dacode/sandbox/{__init__,bwrap}.py` | `GitSandbox.create/checkpoint/rollback/remove/list`; `bwrap.py` = isolation policy (`wrap_command`, `allowed_env`, `interpreter_binds`) |
| — Wiring | `dacode/orchestrator.py` | `DaCodeRig` (lifecycle, baseline measurement, lesson ingest) |
| — CLI | `dacode/cli.py` | `run`, `memory`, `sandbox`, `judge-eval`, `retro`, `state`, `mcp`, `layers` |
| — Run log / eval | `dacode/runlog.py`, `dacode/jeval.py` | JSONL recorder; `judge-eval` scores judge agreement |
| — State store | `dacode/state.py` | runlog → SQLite `memory.db` (FTS5 trigram); `state stats/search/failures/rebuild` |
| — Retro | `dacode/retro.py` | runlog → pass rate, rounds, per-model results, concrete advice |
| — MCP | `dacode/mcp/server.py` | 5 tools over stdio JSON-RPC (memory, history, failures, stats, retro) |
| — Judge (optional) | `dacode/judgment.py` | Jev bounded pick for `compose`/triage — `--judge jev` |
| — dotenv | `dacode/env.py` | `.env` loader (stdlib only) |

## Prerequisites: Pi is a separate install

`pip install -e` installs DaCode only. The `pi` executor is a Node program
(`@earendil-works/pi-coding-agent`, bin `pi`, Node >= 22.19) and the rig shells out to
it — no `pi` on `PATH` gives exit 127 with no explanation.

```bash
curl -fsSL https://pi.dev/install.sh | sh    # or npm i -g --ignore-scripts @earendil-works/pi-coding-agent
pi --version && pi auth check --provider openrouter
pi --print --mode text -- "Reply with exactly: PI_OK"
```

**z.ai GLM route (verified e2e):** `--llm zai --executor-provider zai --model
glm-5.3-flash` — the `zai` LLM preset hits the coding endpoint with `GLM_API_KEY`,
which must be in the *target repository's* `.env` (the CLI loads that, not DaCode's
own). Five breaks the first real run exposed: symlinked launcher under the home
tmpfs (resolve the binary), pi 1.4 rejecting `--opt=value` prompts (space form plus
a leading newline for dash-leading prompts), pi 1.4 lock files on a read-only
`~/.pi` (mount it writable; auth.json stays masked via an empty-file bind — a
/dev/null bind denies reads outright), `/etc/resolv.conf` symlink into the /run
tmpfs killing DNS (bind the real resolve dir when network is on), and `--junitxml`
appended after `bash -c` never reaching pytest (put it inside the script).
Bytecode caches (`__pycache__`, `.pytest_cache`) are carved out of contract and
fallback integrity checks — they appear the moment any pytest runs.

Live monitoring: `dacode watch` — a read-only tail of the runlog (in-progress run,
probes, findings, pass history). `q` quits, `--once` renders a single frame. It never
writes anything and never judges — the gate owns verdicts, the watch is a window.

Triage: `127` = Pi not on PATH; `ready` from auth check but `402` on `--print` =
provider credit exhausted — the catalog gives deepseek-v4.1-flash `maxTokens: 943718`,
so cap it in `~/.pi/agent/models.json` under `providers.openrouter.modelOverrides`
(`{"deepseek/deepseek-v4.1-flash": {"maxTokens": 8192}}` — must sit under the provider
key; a top-level `modelOverrides` is silently ignored); `401` = bad key; `PI_OK` yet
the run fails = the gate, not Pi. `--executor script` runs the
whole gate with no Pi at all. Under bwrap the auth file is masked, so the provider key
must arrive through the environment, together with `--isolate-network`.

## Run a task

```bash
cd <repo you want to change>
dacode layers                        # health of all five layers

# full rig — Pi executor, DeepSeek v4.1 Flash, 2 variants in 1 round
dacode run "<task>" --llm openrouter --model deepseek/deepseek-v4.1-flash \
  --executor pi --budget 1 --variants 2

# deterministic (no LLM/Pi) — demos and CI
dacode run "<task>" --llm stub --executor script --script-command '<cmd that fixes the repo>'
```

Canonical gate for this repo (each application repo carries its own
`.dacode.md` with the same shape):

```bash
dacode run "<task>" \
  --test-command "$HOME/<repo>/.venv/bin/python -m pytest -q" \
  --test-glob "test_*.py" \
  --llm openrouter --model deepseek/deepseek-v4.1-flash \
  --executor pi --budget 2 --variants 2
```

Exit code 0 when the winning variant passed, 1 otherwise. Trial worktrees live
in `<repo>/../.dacode/worktrees/<task-slug>-<nonce>-rN-vM` — the per-run nonce is
what stops a second run of the same task from colliding with the winner the first
run kept. Losers are removed, the winner is kept so you can read the diff.
`--parallel 2` overlaps executors (worktree creation stays serialised);
`--variant-timeout` bounds one variant.

## The rules that keep the gate honest

1. **The gate owns pass/fail.** `exit_code == 0`, `failed == 0` and a non-zero
   count — and for a pytest command the count comes from the JUnit report the
   critic writes outside the workspace, not from stdout. Jev and triage pick
   *what to try next*; they never overrule the gate, and composition ranks only
   variants that passed it. That includes *resolving the chooser's answer*: when a
   judge or the compose LLM names a variant id, look it up in the gate-passing
   pool, never in the full `variants` list — a judge that names a failing id
   otherwise hands the run to the variant whose gate just failed.
2. **Write the contract as tests yourself, then hand the rig "make
   tests/<file>.py pass".** Prose specs dense with symbols get mangled by
   flash-tier models; against a committed test file the same task passes on the
   first round. Say "do NOT modify the test file". On a repo with no suite at all,
   build the harness and the first golden test by hand — the rig is not a
   scaffolder, and with no gate there is nothing for it to judge (see
   `references/project-playbook.md`, "Adopting the rig on an existing project").
   The gate is a command, not a language: `--test-command "php tools/phpunit.phar
   -c phpunit.xml" --test-glob "*Test.php"` gates a PHP repo the way pytest gates
   Python, and `--test-glob` has to match the runner's naming or the static count
   sees zero tests.
3. **A trial may not edit, delete, or skip tests — and the contract is wider
   than `test_*.py`.** `tests_modified`, `tests_infra_modified` (conftest,
   `pytest.ini`/`.pytest.ini`, `setup.cfg`/`setup.py`, `pyproject.toml`, packaging
   metadata, runner-shadowing packages), `tests_lost`, `tests_skipped`,
   `counts_disagree`, `counts_unavailable`. The suite is hashed before the executor
   runs, so a trial that commits its edit is caught too. A green gate on edited
   tests is a false PASS — it has happened (`approx(100.0)` → `approx(105.0)`,
   reported 107/107).
4. **Use an absolute interpreter path when the venv is gitignored.** Trial
   worktrees are checkouts: a relative `.venv/bin/python` runs 0 tests and every
   variant fails for a reason that has nothing to do with the code.
5. **Land the winner yourself.** The rig never applies the diff. Copy changed
   files out of the printed workspace, run the suite in the repo, commit, merge.
   Read the diff: a PASS proves only what the assertions check, not units or
   semantics.
6. **Run long tasks in the background** (`background=true, notify=true`). A
   foreground timeout kills the run mid-flight and leaves orphan trials;
   `dacode sandbox clean` before retrying.
7. **One failed round is not a verdict — and a uniform score across every variant is a
   spec defect, not a weak model.** Read the failure text before rewriting the task;
   `--budget 2` exists for exactly this. When every variant (and every model you swap
   in) lands on the same "N of M pass", stop re-running and diagnose: run the suite
   yourself in a scratch worktree, read the failing assertions, and write the reference
   implementation by hand. If the hand-written version reaches M of M, the spec was
   satisfiable and the task text was missing a rule — put that rule in the task, not
   more rounds. If it does not, the spec contradicts the codebase and the test is what
   needs fixing. A trial that reports no edits at all is an executor-auth problem, not a
   task problem; see `references/gate-integrity.md`.
8. **Read `dacode retro --days N` before a new batch**, and `dacode state
   failures --task <slug>` before retrying — the rig already recorded which
   approaches lost the gate.
9. **Give the rig a fleet when one model keeps losing** (`--fleet a,b`), and
   `--parallel 2` when variants are slow. Verify OpenRouter model IDs against the
   API instead of guessing a version suffix.
10. **DaCode stays domain-agnostic.** Applications (etf9, dashboards, scrapers)
    are separate repos that carry their own `.dacode.md`; no domain content,
    fixtures, or published numbers belong in this repo.
11. **DaCode owns its memory.** `local` (OpenAI-compatible embeddings + SQLite
    cosine) is the default; `hermes` is one adapter and `module:factory` lets
    anyone plug their own. Never make the rig depend on another agent.
12. **Verify a push by refs, not exit status** — `git push origin main` reports
    success *without pushing* when HEAD sits on another branch. Never commit
    behind a piped `pytest … | tail` either: the pipeline hides the exit code.
13. **Write docs with portable paths** (`<repo>`, `<vault>`, "the DaCode
    checkout"). Concrete machine paths go stale on the next host.
14. **A public repo gets `AGENTS.md` and `.dacode.md`, never this skill.** This
    file is bound to one machine and one agent's vocabulary (tool flags, vault,
    named incidents) and would drift against the repo copy. `AGENTS.md` carries
    the tool-agnostic half — gate ownership, contract-first tests, one module per
    run, conventions — and `.dacode.md` pins the gate command for that repo.
15. **Sandbox trials when the code is untrusted** (`--isolate bwrap`): read-only
    host, empty home, private `/proc`, `/dev`, `/tmp`, `/run`, `/var/tmp`,
    workspace-only writes, network off unless the executor needs it, environment
    rebuilt from an allow-list. Credentials are masked rather than merely denied:
    `<repo>/.env` and `~/.pi/agent/auth.json` are bound over `/dev/null`, so the
    agent authenticates from the environment (verify with a real run — a masked
    auth file does not break the Pi executor). The gate is sandboxed on its own
    network-free policy and fails closed (exit 125/126); `available()` probes
    namespaces because bwrap on `PATH` is not proof they work.
16. **Treat an audit finding as a claim until it reproduces.** Reproduce with the
    smallest case, fix it with a test that reproduces *the original failure*, then
    re-run the reproduction and quote the new output. Verify the regression test
    by stashing the fix: if it still passes without the fix, it never tested the
    bug. A finding that a file is "missing from the provided source" is usually
    the auditor failing to read its own context — check the file exists in the
    pack before acting on it. When a fix contradicts an
    existing test, decide whether the test encoded the bug (one asserted a judge
    may pick a gate-failing variant) — correct it deliberately, never to make the
    new code go green. Finally, scope the claim in `SECURITY.md` to what is
    actually enforced; a reviewer reads that table as fact.

## Tests

```bash
cd <DaCode> && .venv/bin/python -m pytest -q -o addopts=   # 232 tests
```

`-o addopts=` is required (`pyproject.toml` sets `addopts = "-q"`; a second `-q`
suppresses the summary). Harness/orchestrator tests use a deterministic
`FakeExecutor` + `StubLLM` but exercise real git worktrees and real pytest runs
inside the critic; `conftest.py` sets `DACODE_RUNLOG=off` and a temp
`DACODE_MEMORY_DB` so the suite stays hermetic and never reaches an embedder.

## Extending

- **New executor:** implement `run(variant, workspace) -> ExecResult`, wire it in
  `DaCodeRig._build_executor`. Honour `variant.model` if you call a model.
- **New check:** return a `Finding` from `dacode/discipline/checks.py`; the
  critic runs every test file through the AST visitor.
- **New memory backend:** module under `dacode/memory/backends/` with
  `available()` + `search(query, top=8)`; register in `backends/__init__.py`.
- **New MCP tool:** add a definition to `TOOLS` and a handler in
  `dacode/mcp/server.py`; handlers receive and return plain dicts.
- **Harder isolation:** wrap `executor.run` in bwrap/docker — the optimizer does
  not care.

## References

| File | Read it when |
|---|---|
| `references/gate-integrity.md` | a gate passes but you do not believe it; 0 tests; unit or semantic doubts |
| `references/project-playbook.md` | building a new project with the rig, sizing tasks, calibration, landing winners |
| `references/memory-and-embeddings.md` | memory backends, embedder config, indexing, lesson-note format, FTS search |
| `references/embedding-providers.md` | provider-specific embedder details (Gemini compat endpoint, dimensions) |
| `references/observability-and-fleet.md` | runlog/state/ledger, `retro`, parallel, timeout, fleet, escalation |
| `references/judgment.md` | `--judge jev`, triage actions, `judge-eval` |
| `references/mcp-server.md` | exposing the memory to Hermes/Pi/editors over MCP |
| `references/external-audit.md` | running an outside model (agy: Claude/Gemini/GPT-OSS) over the rig; quota behaviour; how to brief it |
| `templates/audit-brief.md` | copy-and-fill prompt for an outside review: section structure, severities, and the defensive wording that survives a content filter |
| `references/security-boundaries.md` | state permissions, redaction at output boundaries, integrity fallbacks, escape hatches, how to brief an outside auditor |
| `references/isolation.md` | sandboxing trials and the gate with bubblewrap; venv symlink trap; fail-closed behaviour |
| `references/harness-notes.md` | Pi headless check, variant-id counter, stub LLM kwargs, release tags |
| `references/orca-integration.md` | running DaCode under Orca ADE, worktree ownership, web pairing |

The design doc lives in the vault at
`Resources/AI Agents/Blueprint - Ultimate Autonomous Engineering Rig.md`, and
`ARCHITECTURE.md` in the repo maps blueprint elements → code.
