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
| Test integrity | a trial may not edit/add/delete `test_*.py`, `conftest*.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `setup.py`, `pyproject.toml`, `.coveragerc`, `pytest.py`, `sitecustomize.py`, `usercustomize.py`, any file in a dedicated test directory, or any path containing a shadowing component (`pytest/`, `_pytest/`, `pluggy/`, `py/`) | `tests_modified`, `tests_infra_modified` |
| Suite size | the collected count may not fall below the baseline, skips may not rise | `tests_lost`, `tests_skipped` (baseline measured on the untouched repo) |
| Suite integrity vs. a commit | every test file and gate-infrastructure file is hashed before the trial runs; an edit, a removal or a new file fails even if the trial commits it or replaces `.git` | `snapshot_contract()` + `_check_contract()` |
| Gate network (when isolation is on) | the gate never gets a network namespace or provider keys, even when the executor does. With `--isolate none` nothing is sandboxed, so the gate runs on the host like everything else | separate `gate_isolation` policy |
| Sandbox (`--isolate bwrap`) | read-only host, empty home tmpfs, workspace-only writes, `/proc`, `/dev`, `/tmp` private, allow-listed environment. `$HOME`, its ancestors **and credential paths under it** (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.kube`, `~/.docker`, `~/.password-store`, `~/.hermes/.env`, `~/.hermes/config.yaml`, `~/.config/gcloud`, `~/.config/gh`) are refused as binds | `dacode/sandbox/bwrap.py` |
| Secrets in the environment | `<repo>/.env` may only set provider keys and the embedding *model* knobs. Everything else is ignored, including `DACODE_EMBED_BASE_URL` and `DACODE_VAULT` (either would redirect where prompts and memory go), `GIT_*`, `PYTHON*`, `LD_*` and `*_PROXY`. `DACODE_ENV_TRUST=1` is the explicit opt-out for repositories you own | `dacode/env.py` |
| Fail closed | no bwrap → `RuntimeError`; an unsandboxable executor returns 126, the gate 125 — never a silent unsandboxed run | orchestrator + critic |
| Cleanup | `sandbox clean` never touches the main checkout, only worktrees under the sandbox root | `dacode/cli.py` |

## Known open items (do not assume these are handled)

1. **Counts still come from stdout.** A JUnit XML written outside the workspace
   and parsed on the host would be authoritative; today a fake summary line plus
   `os._exit(0)` is caught only by the gate-infrastructure guard, the `failed == 0`
   rule and the snapshot comparison.
2. **`~/.pi` is bound into the executor sandbox** so the agent can authenticate;
   that exposes `~/.pi/agent/auth.json` to trial code. Planned: pass only the
   provider key it needs.
3. **`/run/user/$UID` host sockets** (D-Bus, ssh-agent, gpg-agent) are reachable
   with `--unshare-net` still on. Planned: `--tmpfs /run`.
4. **Secrets can reach the logs.** `ProbeResult.stdout` keeps the last 4,000
   characters and `sandbox.checkpoint()` runs `git add -A`, so an echoed key or a
   stray `.env` can land in `runlog.jsonl`, `memory.db`, or the shared `.git`
   object store. Planned: redact known secret values, never stage untracked
   secret-looking files, `chmod 0700` the state directory.
5. **Compose can pick a failing variant.** With a judge or LLM pick, a variant
   that failed the gate can outrank a passing one and the passing worktree is then
   cleaned up. Planned: filter candidates to gate-passing variants first.
6. **Parallel probing races.** `sandbox.checkpoint()` and the JSONL/SQLite writes
   are not fully serialised under `--parallel N`.
7. **A test directory at the repository root is not covered.** The "any file in a
   test directory is contract" rule applies to dedicated directories (`tests/`,
   `spec/`); at the root a test-support module cannot be told apart from
   application source by path, so only `test_*.py`, `conftest*.py` and the
   gate-infrastructure names are protected there.
8. **Smaller ones:** `escalate_model` is a no-op when a fleet is configured;
   `state.rebuild()` wipes the DB before checking `DACODE_RUNLOG=off`;
   `state.ingest()` drops `findings`/`models`; `memory search` ignores queries
   shorter than 3 characters; `ScriptExecutor(shell=False)` splits a string
   command per character.

## Running safely today

```bash
# repositories you own
dacode run "<task>" --executor pi --isolate bwrap --isolate-network \
  --test-command "${VIRTUAL_ENV}/bin/python -m pytest -q -o addopts="

# a repository you do not trust: no isolation shortcut, no env trust
# (and read the open items above before pointing it at anything valuable)
```

`--isolate` defaults to `none` for compatibility. If you are running tasks you did
not write, set `DACODE_ISOLATE=bwrap` in your own shell, not in the repo's `.env`.

## Reporting

Open an issue with the exact command and the smallest reproducing repository. A
finding that produces a green gate, host code execution, or a secret leak is
treated as critical and gets a regression test before the fix.
