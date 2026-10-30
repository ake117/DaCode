# FAQ

Real questions from real use. If your answer isn't here, the deeper documents are
[SECURITY.md](../SECURITY.md) (what the gate actually enforces), the
[design notes](design/README.md) (where the idea came from), and the README.

## Using it

### I have requirements for a new project. Can DaCode build it from a description?

No — and that is the point. DaCode takes **one scoped task on an existing repository**
and proves its work against that repository's own tests. The parts around it stay with
you (or your assistant): set up the repo, write the tests that encode the
requirements, break the work into small tasks, review the diff the winning trial
produced, merge it. A trial with nothing to prove against has nothing to gate on.

The flow that works: skeleton repo → tests written from requirements → one
`dacode run` per task → review → merge → next task.

### Where does my code end up? Did it touch my checkout?

Never your checkout. Each variant runs in its own **git worktree**; the winner gets a
checkpoint commit on a `dacode/trial/...` branch and the path is printed at the end.
Merging back is a deliberate human step (`git merge` / `cherry-pick` from the printed
workspace).

### Do I have to use Pi?

`--executor pi` needs the [Pi coding agent](https://github.com/earendil-works/pi) on
`PATH`. `--executor script` runs a deterministic shell command instead and needs no
LLM at all — same worktrees, same gate, useful for demos and CI.

### Is this A/B testing?

No. A/B tests a continuous, noisy metric over user traffic and needs statistics.
DaCode is **best-of-N selection with a deterministic oracle**: candidates meet the
same test suite, the suite gives the same answer every time, losers are discarded.
The closest vocabulary is tournament selection. See
[design/README.md](design/README.md).

## Setup failures

### `exit 127` / `command not found: pi`

The `pip install -e` step installs DaCode only. Install Pi separately
(`curl -fsSL https://pi.dev/install.sh | sh`, Node ≥ 22.19) and check
`pi --version`.

### `pi auth check` says `ready`, but runs fail with **402**

The provider account is out of credit — not a DaCode bug. Pi's model catalog can
request a very large `max_tokens` (943,718 for one DeepSeek model), which fails any
preflight balance check. Cap it in `~/.pi/agent/models.json` — the override must sit
**under the provider key**, a top-level `modelOverrides` is silently ignored:

```json
{
  "$schema": "https://pi.dev/schemas/models.schema.json",
  "providers": {
    "openrouter": {
      "modelOverrides": { "deepseek/deepseek-v4.1-flash": { "maxTokens": 32768 } }
    }
  }
}
```

`z.ai` works too, via the coding endpoint with `GLM_API_KEY`:
`--llm zai --executor-provider zai --model glm-5.3-flash`. Put the key in the
**target repository's** `.env` — that is the file the CLI loads (plus your real
environment), never `~/.hermes/.env` or Pi's auth store.

### `No module named X` — but the package IS installed

If X lives under your home directory (a `pip --user` install), the sandbox
hides it by design — the home is empty inside a trial. The gate names this as
a `hidden_home_packages` finding instead of leaving the riddle. Two clean
ways out: a **workspace-local venv** (the workspace is bound into the trial)
or a **system-installed runner**. There is no flag that opens the home.

## Reading the verdict

### My change works, all tests pass — why did the run say FAIL?

The gate fails a trial on more than red tests, and each finding says which:

| Finding | Meaning |
|---|---|
| `tests_modified` / `tests_infra_modified` | the trial edited a test file or gate infrastructure (a new `conftest.py` counts — that is how a suite gets silenced). Fix the source, not the harness. |
| `tests_lost` / `tests_skipped` | the suite shrank or tests were skipped — a quieter way to fake a pass |
| `counts_unavailable` | a green run that produced no JUnit report — the counts you saw came from stdout, which a trial can print |
| `counts_disagree` | the JUnit report and stdout disagree — something is printing its own summary |

One legitimate trap: if a task can only be solved by adding a `conftest.py` (say, to
make imports work), the task is mis-shaped — fix the repository first (a root
`conftest.py` committed in the base), then run the rig.

### `--budget` and `--variants` — which one adds attempts?

`--budget` is **rounds** of the Harness² recursion; `--variants` is the number of
candidate harnesses **per round**. Worktrees created = `variants × rounds`. Start at
2 × 2; a hard task earns a bigger budget sooner than more variants.

### Where do the lessons go, and do they help?

Each passing run writes a lesson note to the vault (`<vault>/Projects/DaCode/Lessons/`)
and each later run retrieves the relevant ones as seed context. The effect compounds
on repos you work repeatedly — that is the strongest reason to point DaCode at your
own automation repos rather than one-off tasks.

## Safety

### Do I need `--isolate bwrap`?

It is the **default**. A host without bubblewrap fails closed (exit 126/125) rather
than running the trial bare. `--isolate none` is the explicit opt-out for when you
mean it. Pair it with `--isolate-network` whenever the executor must reach a model;
a networked sandbox that needs DNS gets the resolver bound for it.

See [SECURITY.md](../SECURITY.md) for what the sandbox hides — and the honest list of
what it does not.
