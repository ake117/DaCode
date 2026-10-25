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

1. **Counts still come from stdout.** Everything the gate knows about pass/fail is
   parsed from text the code under test can print. A fake summary line is caught by
   the gate-infrastructure contract, by `failed == 0` and by the snapshot, but the
   ground truth is not authoritative. The durable fix is a JUnit XML written outside
   the workspace and parsed on the host.
2. **`~/.pi` is bound into the executor sandbox** so the agent can authenticate;
   that exposes `~/.pi/agent/auth.json` to trial code. Planned: pass only the
   provider key the run needs.
3. **Host paths still visible inside the sandbox.** `/run`, `/sys` and `/var/tmp`
   are mounted read-only, so `/run/user/$UID` sockets (D-Bus, ssh-agent,
   gpg-agent), `/run/docker.sock` and `/run/dbus/system_bus_socket` are reachable;
   with `--ro-bind / /` a repository that does not live under `$HOME` or `/tmp`
   (say `/srv/app`) is readable inside the sandbox, including its `.env` and
   `.git`. Planned: `--tmpfs /run`, and binding the workspace rather than `/`.
4. **Nothing is redacted before it is persisted.** The state directory and the
   runlog are now `0700`, but `_build_lesson()` writes the task text, the winning
   label and its system prompt verbatim into the vault, and the runlog records
   whatever the harness emits. A key echoed into a task string, or an injected
   instruction, survives into future runs. Planned: redact `sk-`, `gsk_`, `AIza`
   and known env values on the way to the log, the store and the lesson.
5. **The baseline runs the suite on the repository itself**, read-write under the
   gate sandbox, and a repository whose untouched tests fail to import reports
   `total == 0` → baseline `None`, which switches `tests_lost`/`tests_skipped` off
   for the whole run. A collection `ImportError` also makes `base_total = 1` even
   if the file declares dozens of tests.
6. **Worktrees leak across rounds.** `retry_same` re-probes the same variant
   objects, and a new best in round 2 never removes round 1's former best.
7. **A test directory at the repository root is not covered.** The "any file in a
   test directory is contract" rule applies to dedicated directories (`tests/`,
   `spec/`); at the root a test-support module cannot be told apart from
   application source by path, so only `test_*.py`, `conftest*.py` and the
   gate-infrastructure names are protected there.
8. **Smaller ones:** `escalate_model` is a no-op when a fleet is configured;
   `state.search()`'s `LIKE` fallback returns placeholder columns and ignores
   `variant_id`/`best_id`/`chosen_id`; `memory search` ignores queries shorter than
   three characters; `ScriptExecutor(shell=False)` splits a string command per
   character.

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
