# Observability and fleet — runlog, ledger, retro, parallelism

## The run recorder is eval fuel, not a verdict source

Every probe, compose pick (with chooser: judge/llm/ranking) and run summary
appends to `DACODE_RUNLOG` (default `~/.local/state/dacode/runlog.jsonl`; `off`
disables it; `dacode retro` and the MCP server honour the variable via
`runlog.current_path()`).

`runlog.record` is the single funnel: it appends the JSONL line and then calls
`state.ingest`. So `DACODE_RUNLOG=off` stops both.

Recording never changes a verdict.

## Event fields worth knowing

| Event | Fields |
|---|---|
| `probe` | `variant_id`, `label`, `score`, `tests_passed/total`, `critique_passed`, `exit_code`, `elapsed_s`, `tests_skipped`, `model`, `findings` (`severity:check`), `stdout`/`stderr` tails |
| `compose` | pick + chooser (`judge`/`llm`/`ranking`) |
| `run` | `rounds`, `passed`, `needs_human_review`, `best_id`, `best_score`, `elapsed_s`, `models` |

`findings` carries severity so the retro counts real errors, not style warnings
(`none_check`, `weak_truthiness` are warnings and cost only score).

## The ledger

`elapsed_s`, `tests_skipped` and `model` are mirrored into SQLite; `state.py`
migrates older stores in place.

```bash
dacode state stats        # runs, pass rate, variants, avg_variant_s, slowest_variant_s, tests_skipped
dacode state search <q>   # FTS over tasks/labels
dacode state failures --task <substr>
dacode state rebuild      # drop the DB, replay the JSONL
```

`avg_variant_s` stays 0 for runs recorded before the ledger existed — it is not a
symptom of anything.

## `dacode retro` — rules, not vibes

```bash
dacode retro --days 14 [--task <substr>] [--json]
```

It prints per-task runs, pass rate, average rounds, average/slowest variant
seconds, a per-model pass rate, and suggestions:

| Signal | Suggestion |
|---|---|
| pass rate < 50% over ≥3 runs | write the contract as tests first; the prose spec is the problem |
| average rounds > 2 | split the task or raise `--budget` |
| average variant > 240 s | set `--variant-timeout`, try `--parallel 2` |
| variants hit exit 124 | the task is too big for one run |
| `tests_lost` / `tests_skipped` | the baseline guard fired; check whether the prompt invites "fixing" the suite |
| one model at 0/N probes | drop that model from the fleet for this kind of task |

Read it before starting a new batch — it is the cheapest source of course
correction the rig has.

## Parallel probing

`--parallel N` (default 1) probes a round's variants concurrently.

- **Worktree creation stays serialised** (`threading.Lock` around
  `sandbox.create`): `git worktree add` is not concurrency-safe on one repo.
- Executors overlap, which is where the wall time goes. Three variants at 0.2 s
  finish in well under the sequential time (test-locked).
- `DACODE_PARALLEL` sets the default.

## Per-variant timeout

`--variant-timeout` (default 900 s, `DACODE_VARIANT_TIMEOUT`) reaches both
`PiExecutor` and the critic, so a hung variant returns exit 124 instead of
holding the run. A 124 in the runlog is what `retro` reports as "too big for one
run".

## Fleet diversity

```bash
dacode run "<task>" --executor pi --llm openrouter \
  --fleet "deepseek/deepseek-v4.1-flash,anthropic/claude-sonnet-5.5" \
  --parallel 2 --variants 2
```

- `HarnessVariant.model` is honoured by `PiExecutor.build_command`; unset means
  the executor's default model.
- Round 1 gives variant 1 the first model and variant 2 the second; later rounds
  rotate (`offset = round_no - 1`), so every round stays balanced.
- `next_fleet_model()` prefers a family that has **not** been tried
  (`_family()` = provider segment), so escalation stops repeating the family that
  just failed. With every family tried it falls back to the first fleet member,
  then to the legacy `--escalate-models` ladder.
- A fleet alone enables `escalate_model` in triage (`can_escalate`), no ladder
  needed.
- Model IDs must be real OpenRouter IDs:

  ```bash
  curl -s https://openrouter.ai/api/v1/models -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    | python -c "import sys,json; print([m['id'] for m in json.load(sys.stdin)['data']][:20])"
  ```

  Verified live (Oct 2026): `deepseek/deepseek-v4.1-flash`,
  `anthropic/claude-sonnet-5.5`, `openai/gpt-5.6-luna`, `google/gemini-2.5-pro`.
