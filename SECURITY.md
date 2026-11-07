# Security model

DaCode runs model-written code. This file states what the rig guarantees, what it
does not, and what to do about it. It is written from external audits
(Gemini 4 Argon via `agy`, Oct & Nov 2026) plus the fixes applied in response, and it
deliberately keeps the open items visible.

## Threat model

A *trial* is code produced by an agent from a task description. Treat it as
hostile. A *repository* can also be hostile: `dacode --repo <path>` reads its
`.env` and its tests.

The host secrets worth protecting: `~/.ssh`, `~/.hermes/.env`, `~/.pi/agent/auth.json`,
`~/.gemini` credentials (`oauth_creds.json`, `google_accounts.json`, `antigravity/mcp_config.json`),
provider API keys in the environment, personal vaults under `~/Documents`, and anything reachable over the network.

## Guaranteed today

| Area | Guarantee | Enforced by |
|---|---|---|
| Gate verdict | exit 0 **and** `failed == 0` **and** a non-zero test count | `PstackCritic.review_workspace` |
| Gate counts | for a pytest command the numbers come from a JUnit report written outside the workspace (`--junitxml` directly or via `PYTEST_ADDOPTS` for `bash -c` scripts) and parsed on the host with `O_NOFOLLOW` + `stat.S_ISREG` (rejecting symlinks and non-regular files); counts are taken from `<testcase>` elements **and** cross-checked against declared totals, stdout must agree, and a green run with no usable report fails | `_run_once`, `_junit_counts`, `counts_disagree`, `counts_unavailable` |
| Test integrity | a trial may not change, add, rename or delete `test_*.py`, `*_test.py`, `conftest*.py`, `pytest.ini`, `.pytest.ini`, `tox.ini`, `setup.cfg`, `setup.py`, `pyproject.toml`, `.coveragerc`, `.gitattributes`, `.gitmodules`, `.pth` files, compiled `.so`/`.pyd` shadows, `pytest.py`, startup dependencies (`iniconfig`, `packaging`, `tomllib`, `configparser`, `importlib`), `sitecustomize.py`, `usercustomize.py`, packaging metadata (`*.dist-info`, `entry_points.txt`), any file or nested subdirectory in a dedicated test directory, or any path with a shadowing component | `tests_modified`, `tests_infra_modified` |
| Integrity vs. a commit | the suite and `.git` pointer/config state are hashed before the trial runs, so an edit, a removal, a rename or a `.git` swap fails even if the trial commits it | `snapshot_contract()` + `_check_contract()` + `_git_contract_digest()` |
| Suite size | the collected count may not fall below the baseline (dynamic, or the static `def test_*` count across `test_*.py` and `*_test.py` when collection fails), skips may not rise | `tests_lost`, `tests_skipped` |
| Gate authority | only gate-passing variants are candidates for composition; a judge may pick among passes, never over one | `compose()`, `_variant_score()` |
| Gate network & child env | with isolation on, the gate never gets a network namespace or provider keys; all executor and gate `subprocess.run` calls scrub host secrets (`AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN`, `LD_PRELOAD`, …) via `allowed_env()` even under `--isolate none` | `gate_isolation`, `allowed_env`, `_gate_env` |
| Sandbox (`--isolate bwrap`) | read-only host, empty home tmpfs, private `/proc`, `/dev`, `/tmp`, `/run`, `/var/tmp`, workspace-only writes (`<workspace>/.git` re-bound read-only) plus the gate's own report directory, allow-listed environment; trial-writable workspace paths/symlinks/`pyvenv.cfg` never add host mounts; `protected_paths` entries are re-bound read-only after writable parents | `dacode/sandbox/bwrap.py` |
| Credentials in the sandbox | `$HOME`, its ancestors, vaults (`~/Documents`) and credential/state paths under `$HOME` are never bound; `<repo>/.env` (allow-listed strictly to `*_API_KEY`), `~/.pi/agent/auth.json` and `~/.gemini` auth/MCP files are masked; plugin autoloading is off inside and outside `bwrap` | `_bind_candidates`, `ENV_ALLOW_LIST`, `hidden_files`, `_gate_env` |
| Secrets in state & prompts | state directories are `0700` when created and `runlog.jsonl`, `memory.db` (plus `-wal`/`-shm`) and `embeddings.db` are enforced `0600`; runlog events, vault lessons/hits, and trial `ProbeResult` / `_failure_digest()` outputs are redacted (PEM keys, `sk-`, Stripe, `gsk_`, `AIza`, `hf_`, GitHub/GitLab/PyPI/npm, `AKIA`/`ASIA`, JWTs, `Bearer`/`Basic`, and secret env values) before persistence or LLM proposal | `dacode/redact.py`, `runlog.record`, `HarnessOptimizer.probe`, `_build_lesson` |
| Host-side git | `_verify_worktree_pointer()` guards `checkpoint()`, `rollback()` and `head_sha()`, and `_unsafe_git_workspace()` blocks host `git status` on redirected `.git` pointers or filter/fsmonitor directives; git runs with hooks and fsmonitor disabled | `GitSandbox`, `PstackCritic` |
| Terminal & MCP bounds | ECMA-48 CSI/OSC/DCS/APC/PM and 8-bit C1 control sequences are stripped across variant labels, `dacode watch`, and CLI output; `dacode mcp` caps JSON-RPC lines at 1 MiB (`MAX_REQUEST_CHARS`) | `sanitize_terminal`, `MemoryServer.serve` |
| Fail closed | no bwrap, or namespaces unavailable → `RuntimeError`; an unsandboxable executor returns 126, the gate 125 | `available()` probe, orchestrator, critic |
| Concurrency | worktree creation, checkpoint and removal are serialised; the JSONL append and the SQLite mirror are locked | `_sandbox_lock`, `_WRITE_LOCK`, `_INGEST_LOCK` |
| Cleanup | `sandbox clean` never touches the main checkout, and a superseded round's best worktree is removed | `dacode/cli.py`, `_cleanup_losers` |

## Known open items (do not assume these are handled)

1. **Non-Python runners still count from stdout.** A `make test` or `npm test`
   command gets no JUnit report, so a printed summary is again the only signal.
   For Python suites this part is enforced, not advice: when the workspace has
   Python test files, a green run whose counts were parsed only from stdout is
   an error (`counts_from_stdout`) — make the command name pytest (the gate
   attaches `--junitxml` itself, also inside `bash -c` scripts) or wrap the
   runner so pytest writes one. Suites in other languages have no report to
   attach and keep the stdout count, with the test-integrity and infrastructure
   guards still applying; treat their results as unproven and read the diff.
2. **`/sys` stays mounted read-only.** No secrets live there, but host topology,
   device names and some CPU information are visible to a trial.
3. **Runtime state subdirectories of `~/.pi` and `~/.gemini` remain writable** into
   their respective executor sandboxes (agent CLIs need lock and session state;
   `~/.pi/agent/auth.json` and `~/.gemini` auth/MCP configs are masked, and
   binaries, hooks, skills, plugins, rules and settings are re-bound read-only on
   top of the writable mount via `protected_paths`, so a trial cannot replace
   executables or plant persistent hooks). Logs and session files under those
   directories remain writable by the trial.
4. **`DACODE_ENV_TRUST=1` is a real escape hatch.** It restores the old behaviour of
   importing every key from a repository's `.env`. It prints a warning on stderr;
   never set it for a repository you do not own.
5. **A test directory at the repository root is not covered.** The "any file in a
   test directory is contract" rule applies to dedicated directories (`tests/`,
   `spec/`); at the root a test-support module cannot be told apart from
   application source by path, so only `test_*.py`, `conftest*.py` and the
   gate-infrastructure names are protected there.
6. **The static baseline is a heuristic.** `def test_*` counting does not see
   parametrisation, so a badly under-counted baseline can still let a test be
   removed; it only ever raises the baseline, never lowers it.
7. **A trial that executes during the suite can forge a consistent result.** Any
   module the suite imports runs inside the pytest process: it can read
   `--junitxml` from `sys.argv`, rewrite the report to match a summary it prints,
   and end the process with status 0. Deriving the counts from `<testcase>` elements
   and requiring the report to agree with itself defeats the naive rewrite (there is
   a regression test for exactly that), but a fully fabricated report is
   indistinguishable from a real one. This is inherent to gating on a repository's
   own tests — CI has the same property. The gate is a filter, not a proof: test
   files and gate infrastructure are contract-checked, and the diff still gets read.
8. **Vault lessons are a cross-run influence channel.** A run whose trial passes
   the gate writes a lesson into the shared vault — including the *system prompt
   that won* (`DaCodeRig._build_lesson`). The next run seeds its executor with
   retrieved lessons (`run_task` collects `memory.retrieve` hits into
   `memory_snippets`; the pi executor passes each one as
   `--append-system-prompt`). Secrets are redacted on write and on display, but
   *instructions* are not filtered: a hostile repository whose trial passes the
   gate can plant a lesson that shapes later runs on any repository sharing that
   vault — the sandbox contains a trial's process, not its prose. Keep one vault
   per trust domain, or read the lessons (`dacode memory search`) before pointing
   a new repository at a vault that hostile work has written to.

   *Applied (Nov 2026):* the lesson vault is a dedicated machine vault
   (`~/Documents/dacode_vault`), never a personal one, and retrieval is
   **scoped per project**: a run on repo X reads only
   `Projects/X/Lessons` plus the vault-wide `shared/Lessons` (rig-level
   lessons), with the project line derived from the repository name.
   Scoped retrieval enforces four guards: leaf and intermediate directory
   symlinks inside the vault are never followed by `VaultMemory` or
   `VectorStore.index()` (`_is_safe_vault_file`), semantic hits are filtered to
   the scope *after* path resolution and redacted even on stopword/symbol-only
   queries, and a scoped run's `ingest` writes only into `Projects/<scope>`
   (never `shared/` or outside the vault). `DACODE_VAULT` and `DACODE_EMBED_*`
   (except `DACODE_EMBED_API_KEY`) are deliberately **not** allow-listable
   through a repository's `.env` — a repo that could redirect the vault or swap
   the embedding model could plant lessons or poison shared vector state — so
   those settings stay in the operator's hands (`--vault`, shell environment).

A sandbox hides `$HOME` by design, so a suite importing a **pip --user**
package fails with `No module named X`. The gate turns that into a named
`hidden_home_packages` finding (cause + the workspace-venv / system-runner
way out) instead of leaving the riddle; the home stays closed — there is
deliberately no flag that binds user-site packages in.

## Running safely today

```bash
# repositories you own
dacode run "<task>" --executor pi --isolate bwrap --isolate-network \
  --test-command "${VIRTUAL_ENV}/bin/python -m pytest -q -o addopts="

# a repository you do not trust: no isolation shortcut, no env trust
# (and read the open items above before pointing it at anything valuable)
```

`--isolate` defaults to `bwrap`: isolation is the default, not an opt-in. A host
without bubblewrap or unprivileged user namespaces fails closed (exit 126/125, with
an explanation) instead of quietly running the trial on the bare machine. Pass
`--isolate none` (or `DACODE_ISOLATE=none`) when you deliberately want the host.

## Reporting

Open an issue with the exact command and the smallest reproducing repository. A
finding that produces a green gate, host code execution, or a secret leak is
treated as critical and gets a regression test before the fix.
