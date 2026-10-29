# Gate integrity — how a green gate lies, and what stops it

The gate is the only verdict in the rig. Everything here exists because a green
run has been wrong at least once in practice.

## The four ways a trial fakes a pass

| Check | Fires when | Real incident |
|---|---|---|
| `tests_modified` | a changed or added file matches `test_glob` | a trial edited `approx(100.0)` → `approx(105.0)` and the gate reported 107/107 PASS |
| `tests_lost` | the collected test count is below the baseline | a trial deleted the test file that disagreed with its code |
| `tests_skipped` | skip count rose above the baseline | silencing a red test with `@pytest.mark.skip` |
| `tests_infra_modified` | a changed file is `conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml` or `.coveragerc` | a conftest registered an atexit hook printing `999 passed in 0.01s` and called `os._exit(0)` — the gate reported PASS on a failing suite |
| `no_tests` | exit 0 but no parseable count | a runner that printed nothing recognisable |

The baseline is `critic.measure_baseline(repo)`: `(total, skipped)` measured on
the **untouched repo**, once per run, by the orchestrator. When it returns
`None` (no test command, non-git workspace, collection error) the guard is
inactive — a missing baseline must never block a run. Custom critics that
predate the `baseline=` argument still work (the optimizer retries without it).

The verdict also requires **`failed == 0`**, not just `exit_code == 0` and a
non-zero count: the counts are parsed from the runner's stdout, which the code
under test controls, so a green exit code by itself proves nothing. `gate_infra`
can be narrowed per repo when a task legitimately edits `pyproject.toml`, but
never widen it for `conftest.py`.

Keep all of this on. When a contract fails, assume the **contract** may be wrong
before accepting a trial that touched it.

## Quiet configs read as zero tests

A project whose `pytest.ini`/`pyproject.toml` already sets `addopts = "-q"` and a
gate command that also passes `-q` produce `-qq`: pytest prints dots and no
`N passed` line, so the parser sees 0 tests and the run fails as `no_tests`.

The critic retries once with `-o addopts=` appended (neutralising the project's
own addopts) when `exit_code == 0` and no summary was parsed. If a gate reports
`0 tests` on a repo you know is green, that is what happened — check the
project's addopts before blaming the model.

The same trap applies when *you* run the suite by hand in the DaCode repo: use
`.venv/bin/python -m pytest -q -o addopts=`.

## Absolute interpreter path

Trial worktrees are checkouts of the repo, and a gitignored `.venv` is not part
of a checkout. `--test-command ".venv/bin/python -m pytest -q"` therefore exits
immediately inside the trial: the critic reads 0 tests, and every variant fails
for a path reason that looks like a model failure. The first etf9 run burned two
variants and seven minutes on exactly this.

Use `"$HOME/<repo>/.venv/bin/python -m pytest -q"`, or install the package into a
shared interpreter. Put the reason next to the command in the repo's
`.dacode.md` so the next run does not "simplify" it back.

## A pass proves only what the assertions say

On etf9 a `YFinanceSource` passed its contract while returning:

- `yield` as a fraction (0.0324 instead of 3.24%),
- expense ratio from the wrong field,
- `fundInceptionDate` (an epoch timestamp) as `age_years`.

The contract only checked lazy-import behaviour. Read the winning diff and
assert **values and units**, not shape or imports — a numerically wrong data
layer quietly poisons every published number downstream.

Provider data is also allowed to be wrong: yfinance reports `yield` as `0.00%`
for ROC/NEOS funds that distribute 12–16%. Compute `TTM distributions ÷ NAV`
yourself when the number matters.

## Shell traps around the gate

- **Never commit behind a piped test run.** `pytest … | tail -1` returns `tail`'s
  exit status, so a red suite sails through `&& git commit` with a message
  claiming green. Run pytest unpiped or check `${PIPESTATUS[0]}`.
- **A mismatched heredoc delimiter writes nothing** yet the next shell line still
  runs — chain edits and commits with `&&`, and read `git status` before
  committing.
- **No backticks inside `dacode run "…"`.** `` `years` `` is command
  substitution: the shell prints `years: command not found` and the model gets a
  prompt with a hole in it. Same for `$` in formulas — single-quote the task text
  or write it to a file.
- **`--test-command` runs through `bash -c`** inside the trial worktree, so it may
  span several commands (`make -C port/renderer test && make -C port/shim test`).

## Output parsing

The summary parser understands pytest and custom runners:

| stdout line | parsed as |
|---|---|
| `3 passed, 1 failed in 0.2s` | total 4, failed 1 |
| `2 passed in 0.15s` | total 2, failed 0 |
| `90 checks, 0 failed` | total 90, failed 0 |
| `OK: 66 checks passed (headless)` | total 66, failed 0 |

For a non-pytest runner the verdict is `exit_code == 0`, `failed == 0` **and** a
non-zero count. For a pytest command the count must also come from a self-consistent
JUnit report (next section), so a printed summary alone cannot decide it.

## Hostile repository, not just hostile trial

`dacode --repo <path>` reads that repository's `.env` and runs its tests, so the
repo is an attacker too (external audit, Oct 2026):

- **`.env` is allow-listed.** Only provider/embedding keys may be set. Before the
  fix, a checkout could define `DACODE_SEMANTIC_BACKEND=evil:factory` (importlib →
  host code), `DACODE_ISOLATE=none` (sandbox off), `DACODE_TEST_COMMAND`,
  `GIT_EXEC_PATH` or `HTTPS_PROXY` (intercept the keys). `DACODE_ENV_TRUST=1` is
  the explicit opt-out for repositories you own, and it warns on stderr.
- **The skip count comes from the summary line**, not the first match in stdout —
  printing `0 skipped` early used to mask real skips.
- **A workspace-level `pytest.py` shadows the runner** because `cwd` is
  `sys.path[0]`. `pytest.py`, `_pytest.py`, `sitecustomize.py`,
  `usercustomize.py` and `setup.py` are gate infrastructure like `conftest.py`.
- **The verdict needs `failed == 0`**, since every count is derived from text the
  code under test can print.

## JUnit is the ground truth

stdout is text the code under test can print. For a pytest command the gate asks for
`--junitxml=<dir>/report.xml` in a private directory bound read-write into the
sandbox (never into the workspace), parses it on the host, and compares it with what
stdout claimed:

- they disagree → `counts_disagree` fails the trial;
- pytest was asked for a report and a green run produced none →
  `counts_unavailable` fails the trial (something called `os._exit`);
- stdout is silent (project `addopts = -q`) → not a disagreement;
- the command is not pytest (`make test`, `npm test`) → counts still come from
  stdout, and there is no authoritative number. That is a documented residual.

The baseline also counts `def test_*` by parsing the files, because a contract-first
suite that imports a module which does not exist yet fails at collection and would
otherwise disable `tests_lost`/`tests_skipped` for the whole run.

## Derive counts from the report, not its summary attributes

A module imported by the suite runs **inside** the pytest process. It can read
`--junitxml=<path>` straight out of `sys.argv`, rewrite `tests="1"` to `tests="999"`,
print a matching summary and call `os._exit(0)` — the gate then reports a green run
on a suite that fails (reproduced, Oct 2026).

Count the `<testcase>` elements and require the suite's declared `tests`/`failures`/
`skipped` attributes to match that count. A report that disagrees with itself is not
a report: return `None`, which becomes `counts_unavailable` and fails the trial.

What this does **not** buy: a fully fabricated, self-consistent report is
indistinguishable from a real one. Gating on a repository's own suite is a filter,
not a proof — the same is true of CI. Say so plainly in SECURITY.md rather than
claiming the counts are trustworthy in general.

Run `scripts/gate-integrity-probe.py` after touching the verdict path: it builds a
scratch repo whose imported module rewrites the report at exit and asserts the critic
still fails the trial. Unit tests pin the parser; that script pins the verdict.

## Gating a repository that is not Python

The gate only needs a command that exits non-zero and prints a countable summary. Three
things bite when the suite is not pytest:

- **Coloured output breaks the parser.** PHPUnit paints its summary line
  (`\x1b[37;41mTests: 23\x1b[0m…`); the escape ends with a letter, so `\bTests:` never
  matches and a fully reported suite counts as zero tests (`error:no_tests`). Strip ANSI
  before parsing, and add a regression test with a coloured line.
- **Understand the runner's summary shape.** PHPUnit prints
  `Tests: 23, Assertions: 65, Failures: 2, Deprecations: 6.` and, when green,
  `OK (17 tests, 46 assertions)`. Treat `Errors` as failures and read `Skipped: 1`
  (capital S — the skip scan must be case-insensitive).
- **A worktree contains only tracked files.** A gate script that downloads its runner on
  first use cannot work: the sandbox hides `$HOME` and the network is off. Commit the
  wrapper *and* the binary it needs (a 6 MB PHPUnit phar is a fair price for a gate that
  runs anywhere), and never point the wrapper at a cache under `$HOME`.

Executor auth is the other trap: `~/.pi/agent/auth.json` is hidden inside the sandbox by
default, and passing the provider key in the parent environment was not enough for `pi`
to start — `DACODE_PI_AUTH=1` was needed for the trial to run at all. If a trial returns
zero findings, zero tests and no file changes, suspect the executor before the task.
