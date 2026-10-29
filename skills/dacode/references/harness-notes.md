# Harness notes — executor, variants, releases

Small facts that cost a debugging session each time they are forgotten.

## Pi must run non-interactively

`PiExecutor` builds
`pi --print --mode text --provider <p> --model <id> --system-prompt … -- <task>`.
Verify the binary works headless before blaming the rig:

```bash
pi --print --mode text -- "Reply with exactly: PI_OK"
```

`--model` accepts `provider/id` patterns, so the fleet entries are OpenRouter IDs
when `--provider openrouter` is set.

## Variant ids are a module-global counter

The base variant consumes `v1`, so proposals in a run start at `v2`. Do not
assume `v1` is a proposal when reading a runlog or a summary.

## `build_llm("stub")` must drop extra kwargs

The orchestrator calls `build_llm(kind, model=..., base_url=...)`; the stub branch
filters to `responses/default/fail_on` or it raises `TypeError`. A CLI end-to-end
test guards this — keep it.

## `GitSandbox.create()` needs at least one commit

A repo with no commits raises `SandboxError`. Commit the scaffold before the
first run.

## Release tags

Annotated tags, lowercase-hyphen names, one per feature, with a Thai message, cut
at the docs commit that closes the feature. Semver tags (`v0.2.0`, `v0.3.0`) mark
milestones that bundle several features; both styles coexist in the repo.

```bash
git tag -a v0.3.0 -m "<what it contains, in Thai>"
git push origin v0.3.0          # tags are not pushed by a plain push
git ls-remote --tags origin | grep v0.3.0
```

Backfilling a tag onto an older commit is fine when the feature landed earlier.

## Background runs, not timeouts

Long `dacode run` calls belong in a background job with a completion
notification. A foreground call killed by the tool timeout leaves the run without
a verdict and leaves trial worktrees behind.
