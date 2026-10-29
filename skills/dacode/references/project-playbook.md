# Playbook — running real projects through the rig

Greenfield work is the rig's best case: every task can carry an observable gate.

## Setting up a new project

- Drop a `.dacode.md` in the repo holding the canonical gate command:

  ```
  dacode run "<task>" --test-command "$HOME/<repo>/.venv/bin/python -m pytest -q" \
    --test-glob "test_*.py" --llm openrouter \
    --model deepseek/deepseek-v4.1-flash --executor pi --budget 2 --variants 2
  ```

  One gate per repo beats ad-hoc flags; it also documents *why* the interpreter
  path is absolute.
- Commit an initial state — `GitSandbox.create()` raises `SandboxError` on a repo
  with no commits.
- Decide the milestone order **before** the first task and gate each milestone on
  its own tests. Aim for one module per run.

## Sizing a task

- One assertion a test can make. "Implement scoring" is too big to gate;
  "weighted score returns 8.35 for these inputs" is not.
- **Write the failing test yourself, then hand the rig "make tests/<file>.py
  pass".** A prose spec dense with symbols gets mangled by flash-tier models —
  one generated module came back with an unterminated string and every variant
  failed on syntax; the same task against a committed test file produced two
  passing variants in round one. The test file is the variant-agnostic contract.
- Keep the test file out of scope in the prompt ("do NOT modify the test file").
- **Never commit a new failing contract while a run is in flight.** The critic
  gates the whole suite inside the trial worktree, so a red test staged for the
  *next* task makes the running task unpassable for reasons unrelated to its
  code. Stage it in the scratch dir and commit after the run returns.

## Calibration and numeric work

- When the target numbers already exist (published tables, a previous notebook),
  make the first real task a **calibration task**: gate = "reproduce the known
  value within ±tolerance". A variant that cannot is rejected without debate.
- If nothing reproduces the published numbers, write the gap into `docs/` and
  **stop**. Never let the rig nudge inputs until a golden test goes green — that
  is how a rubric becomes a fit to itself.
- **Freeze accepted numbers as a fixture, then gate every later change on
  replaying it.** Record the metrics and the expected score per case in a
  committed JSON fixture and assert replay to a tight tolerance (`abs=5e-4`).
  Once the rubric lives in one module, an anchor edit silently moves every
  published number; the fixture turns that into a red test at the moment of the
  edit instead of a stale table nobody notices.
- **Prove a refactor is behaviour-preserving by re-running the probe and diffing
  to four decimals.** Folding duplicated logic into a shared module moved 14
  scores by max 3e-6 — float noise, not behaviour. Save the "before" output
  first; a real change moves a digit.
- A probe script that imports the package needs a path bootstrap when run as
  `python scripts/x.py`:
  `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))`, or
  install the package editable.

## Budget and retries

- 1 round for scaffolding or a mechanical render, 2 for ordinary features, 3 for
  calibration or numeric ambiguity.
- `--judge jev` only where candidate scores land close enough that the ranking
  needs a tie-break.
- **One failed round is not a verdict on the rig.** Even a well-pinned contract
  lost round 1 (both variants died on a syntax error) and round 2 passed the full
  suite.
- Before retrying, run `dacode state failures --task <slug>`: the rig recorded
  which approaches already failed the gate. Do not retry them blindly.

## Running, waiting, landing

- **Start long runs in the background** (`background=true, notify=true`). A
  foreground call that hits the tool timeout kills the run mid-flight: no verdict,
  orphan trial worktrees, and a stale-worktree failure waiting for the next
  attempt. `dacode sandbox clean` (plus `git worktree prune`) before retrying.
- **The rig never applies the diff.** The summary prints
  `workspace: <trial worktree>`; copy the changed files out, run the suite in the
  repo, commit on a feature branch, `merge --no-ff`, push. Treat PASS as a
  proposal.
- Before copying, diff the trial's test files against the base commit
  (`diff <(git show HEAD:tests/<file>) <worktree>/tests/<file>`) and skim the
  source diff for units.
- **Verify the push by refs.** `git push origin main` succeeds silently without
  pushing when HEAD sits on another branch (ten etf9 commits sat on
  `feat/lenses` while `origin/main` looked fine). Always compare
  `git rev-parse main` with `git rev-parse origin/main`.
- After landing, clean up: `git worktree list` should show only the repo, and
  `dacode/trial/*` branches should be gone.

## Adopting the rig on an existing project

The rig is not a scaffolder. It takes three things and nothing else: a repository,
a test command that exits non-zero on failure, and one task with a boundary. It does
not turn a requirements document into an architecture, and **a repo with no runnable
suite is not a rig target yet** — say that before proposing tasks, rather than
starting a run that can only fail for lack of a gate.

Order of work when the repo has no suite:

1. **Find the artifact that ends the process.** Whatever the business calls "done"
   is the gate: a rendered PDF, an exported spreadsheet, a generated report. A gate
   on "the handler returned 200" stays green while the document is empty.
2. **Probe the toolchain before promising a gate.** Convert one real document with
   the same tool the app uses and extract its text:

   ```bash
   soffice --headless --norestore --convert-to pdf --outdir <dir> <file.xlsx>
   pdftotext -layout <file.pdf> out.txt
   ```

   Count characters in the document's own script (Thai: `U+0E00`–`U+0E7F`).
   Extracted text is what an assertion can read; if the script comes back empty or
   mojibake, assert on page count and layout structure instead, and say so — a
   string assertion against an unextractable script is a gate that can never pass.
3. **Build the harness by hand.** Install the runner, bootstrap the framework's
   constants (`BASEPATH`/`APPPATH` for CodeIgniter), write the first tests around
   pure logic. Do it outside the rig: with no suite there is no gate, so there is
   nothing for the rig to judge.
4. **Cut a seam before testing.** Handler methods bound to a request or a database
   cannot be tested. Move the pure part into a class that takes a plain array and
   returns artifact paths, then let the golden test call that instead of the
   controller.
5. **The golden test is fixed real input → artifact → assertion.** One row of real
   input, the real template, the real converter; assert the extracted text holds
   the identifying fields (project, entity, tax id, total) and that totals agree
   with the calculator's own output.
6. **Then hand the rig behaviour-locked tasks.** "Migrate the exporter off the
   abandoned spreadsheet library; the generated PDF text must stay identical" is
   gateable. "Modernise the export path" is not.

Sample business documents belong in the repository (private), with a `README.md` in
that folder saying what each file feeds — a future agent needs the real input shapes,
and a fixture generator that invents them drifts from the actual business. Scan them
for credentials before the first push: `zipfile` plus a regex over the xlsx XML parts
reads shared strings without opening the workbook. Never copy them into a public repo
or a published fixture.

Vendored code inflates gate time — scope `--test-command` to the suite
(`vendor/bin/phpunit -c phpunit.xml`) instead of a repo-wide runner, and keep the
rig's tasks inside first-party directories so a trial never edits `vendor/`.

## Non-Python projects

The AST checks are Python-only; the real gate is language-agnostic. Point
`--test-command` at any command (run via `bash -c` in the trial worktree) and set
`--test-glob` to the language's test naming:

```bash
dacode run "<task>" \
  --test-command "make -C port/renderer test && make -C port/shim test" \
  --test-glob "test_*.c" --executor pi --budget 1 --variants 2
```

Environment equivalents: `DACODE_TEST_COMMAND` (shell-quoted) and
`DACODE_TEST_GLOB`. Parsing rules live in `gate-integrity.md`.

## Where trial worktrees live

`<repo>/../.dacode/worktrees/<task-slug>-rN-vM` — a sibling of the repo, not
inside it. Losers are removed automatically; the winner is kept so you can read
the diff. `--keep-worktree` keeps every trial when you need to compare side by
side. Trial worktree names are derived from the task slug, so a re-run of the same
task needs a clean first (`SandboxError: worktree already exists`).

Winners accumulate: every accepted run leaves a worktree and a `dacode/trial/*`
branch behind. `dacode sandbox clean` handles the ones it knows about; for strays
left by an older sandbox root, purge from inside the repo —

```bash
for wt in $(git worktree list --porcelain | awk '/^worktree /{print $2}' \
             | grep '/.dacode/worktrees/'); do git worktree remove --force "$wt"; done
git worktree prune
git branch -D $(git branch --list 'dacode/trial/*' | tr -d ' ')   # asks nothing
```

— then confirm `git worktree list` shows only the repo. Do this before tagging a
release, so the tag cannot point at a commit whose worktree is still holding an
unmerged trial.
