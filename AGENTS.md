# Working in this repository (for any agent)

DaCode is a coding-agent rig: it proposes several *harness* variants, runs each in
its own git worktree, and accepts one only if a real test command passes. This
file is the tool-agnostic summary — it applies whether you drive the rig through
its CLI or write code inside the repo by hand. `ARCHITECTURE.md` maps the
blueprint layers to modules; `README.md` documents the CLI.

## The gate decides, nothing else does

A variant passes when the test command exits 0 **and** the parser sees at least
one test. A judge (optional) may pick among already-passing variants; it never
overrules the gate. Treat a green run as evidence about the assertions that ran —
not about the code in general.

## Tests are the contract

- Write the failing test first, then ask for "make `tests/<file>.py` pass … do
  NOT modify the test file".
- The critic fails a trial that edits, deletes or silences tests
  (`tests_modified`, `tests_lost`, `tests_skipped`), and a trial that touches gate
  infrastructure (`tests_infra_modified`: `conftest.py`, `pytest.ini`, `tox.ini`,
  `setup.cfg`, `pyproject.toml`) — a conftest can print a fake summary and exit 0.
  A pass also requires `failed == 0`; counts are parsed from stdout, so exit code 0
  alone proves nothing.
- The suite must stay hermetic: `conftest.py` sets `DACODE_RUNLOG=off` and a
  temporary `DACODE_MEMORY_DB`; no test may reach an embedder or the network.

## Running the rig here

```bash
.venv/bin/python -m pytest -q -o addopts=     # the full suite (no test count: it drifts)
```

`-o addopts=` is required because `pyproject.toml` sets `addopts = "-q"`.

For a rig run, see `.dacode.md` — it holds the canonical gate command. Two rules
that have burned real runs:

- **Interpreter:** trial worktrees do not carry `.venv` (gitignored), so
  `${VIRTUAL_ENV}/bin/python` or an absolute path — never `.venv/bin/python`.
- **Isolation:** `--isolate bwrap` is the default and sandboxes trials and the gate (read-only host,
  empty home, no network by default). An agent executor needs
  `--isolate-network`; a test suite should not.
- **Scope:** one module per run (`dacode/discipline/*`, `dacode/harness/*`,
  `dacode/memory/*`, `dacode/mcp/*`, …). A task spanning layers cannot be gated by
  one test file.

## After a run

The rig never applies its own diff. The winner stays in
`<repo>/../.dacode/worktrees/<task-slug>-rN-vM`; copy the changed files in, run
the suite, read the diff for values and units — not just shape — then commit.
Long runs belong in the background; a foreground timeout leaves orphan worktrees
(`dacode sandbox clean`).

## Before starting

- `dacode retro --days 14` — pass rate, rounds, slow variants, tampering events.
- `dacode state failures --task <substr>` — which approaches already lost.
- `dacode layers` — health of the five layers.

## Conventions

- Conventional commits (`feat:`, `fix:`, `docs:`, `chore(release):`); README is
  English.
- Annotated tags, lowercase-hyphen names; semver tags (`v0.2.0`, `v0.3.0`) mark
  milestones. Push tags explicitly.
- No secrets in the repo: keys live in a gitignored `.env`, read only from the
  real process environment or `<repo>/.env`.
- No new runtime dependencies without a reason — the rig is stdlib-only except
  for what the executor needs.
- Docs use portable paths (`<repo>`, `<vault>`, "the DaCode checkout"), never a
  machine-specific absolute path.
- This repo stays domain-agnostic: applications live in their own repositories
  and carry their own `.dacode.md`.
