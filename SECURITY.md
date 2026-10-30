# Security model

DaCode runs model-written code. This file states what the rig guarantees, what it
does not, and what to do about it. It is written from an external audit
(Gemini 4 Argon via `agy`, Oct 2026) plus the fixes applied in response, and it
deliberately keeps the open items visible.

## Threat model

A *trial* is code produced by an agent from a task description. Treat it as
hostile. A *repository* can also be hostile: `dacode --repo <path>` reads its
`.env` and its tests.

The host secrets worth protecting: `~/.ssh`, `~/.hermes/.env`, `~/.pi/agent/auth.json`,
provider API keys in the environment, and anything reachable over the network.

## Guaranteed today

| Area | Guarantee | Enforced by |
|---|---|---|
| Gate verdict | exit 0 **and** `failed == 0` **and** a non-zero test count | `PstackCritic.review_workspace` |
| Gate counts | for a pytest command the numbers come from a JUnit report written outside the workspace and parsed on the host; the counts are taken from the report's own `<testcase>` elements **and** cross-checked against the totals it declares, stdout must agree, and a green run with no usable report fails | `_run_once`, `_junit_counts`, `counts_disagree`, `counts_unavailable` |
| Test integrity | a trial may not change, add or delete `test_*.py`, `conftest*.py`, `pytest.ini`, `.pytest.ini`, `tox.ini`, `setup.cfg`, `setup.py`, `pyproject.toml`, `.coveragerc`, `pytest.py`, `sitecustomize.py`, `usercustomize.py`, packaging metadata (`*.dist-info`, `entry_points.txt`), any file in a dedicated test directory, or any path with a shadowing component — enforced by the pre-trial snapshot and, without one, by the git-status fallback which also checks test-directory membership | `tests_modified`, `tests_infra_modified` |
| Integrity vs. a commit | the suite is hashed before the trial runs, so an edit, a removal or a new file fails even if the trial commits it or replaces `.git` | `snapshot_contract()` + `_check_contract()` |
| Suite size | the collected count may not fall below the baseline (dynamic, or the static `def test_*` count when collection fails), skips may not rise | `tests_lost`, `tests_skipped` |
| Gate authority | only gate-passing variants are candidates for composition; a judge may pick among passes, never over one | `compose()`, `_variant_score()` |
| Gate network | with isolation on, the gate never gets a network namespace or provider keys | separate `gate_isolation` policy |
| Sandbox (`--isolate bwrap`) | read-only host, empty home tmpfs, private `/proc`, `/dev`, `/tmp`, `/run`, `/var/tmp`, workspace-only writes plus the gate's own report directory, allow-listed environment; a `protected_paths` entry stays read-only even under a writable parent (later mounts shadow earlier ones, so the re-bind is emitted last) | `dacode/sandbox/bwrap.py` |
| Credentials in the sandbox | `$HOME`, its ancestors and credential paths under it are never bound; `<repo>/.env` and `~/.pi/agent/auth.json` are masked with `/dev/null`; plugin autoloading is off | `_bind_candidates`, `hidden_files`, `_gate_env` |
| Secrets in state | the state directory is created `0700` on first use (not inherited from the umask) and the runlog is `0700` on every write; events and lesson text are redacted (`sk-`, `gsk_`, `AIza`, `hf_`, JWTs, `Bearer`/`Basic`, and the values of known key variables) before they are written | `dacode/redact.py`, `runlog.record`, `_build_lesson` |
| Host-side git | `checkpoint()` refuses a worktree whose `.git` is not a pointer file and runs git with hooks and fsmonitor disabled | `GitSandbox.checkpoint` |
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
3. **The rest of `~/.pi` is bound writable** into the executor sandbox (pi 1.4
   needs a lock file next to its settings; `agent/auth.json` is masked, and the
   agent's binary directory is re-bound read-only on top of the writable mount,
   so a trial cannot replace the executable the host runs). Agent config, logs
   and settings remain writable by the trial; treat what a future pi run loads
   from `~/.pi` as possibly influenced by a trial.
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
