# Security boundaries

Every rule here was paid for by an audit finding. Each one is about a boundary where
something leaves the process: to disk, to a terminal, to a subprocess, or to a verdict.

## State on disk

- Directories DaCode creates for its own data are `0700` **at creation**. `mkdir()`
  inherits the umask, so a machine with `DACODE_RUNLOG=off` got a world-readable state
  directory holding every recorded task. `runlog` chmods on every append; `state`
  chmods once, right after `mkdir`, and only when it created the directory — never a
  shared parent like `/tmp`.
- Check the permission on the path that is actually used, not on the default path.
  `DACODE_MEMORY_DB` and `DACODE_RUNLOG` move the target.

## Redaction is an output rule, not a storage rule

- Redacting at write time (runlog, state ingest, lesson text) is not enough: anything
  that reads the store and prints is another boundary. `dacode memory search` printed
  vault snippets verbatim, so a key someone pasted into a lesson reached the terminal.
  Apply `redact()` at every `print()` of stored content, including titles.
- When a store is described as "already redacted", say which writer did it. `retro`
  reads the runlog (redacted on ingest) — that is a different claim from "the CLI
  redacts its output".

## Integrity checks have two code paths

- The gate runs `snapshot_contract()` before the trial and `_check_contract()` after
  it. There is also a `git status` fallback for callers that pass no contract, and the
  two must cover the same set of paths. The fallback matched only `test_*.py` and the
  gate-infra names, so `tests/helper.py` added by a trial went unnoticed: test
  directory membership has to be checked in both.
- A guarantee written in the docs applies to every code path, or the docs must say
  which path it covers.

## Escape hatches must announce themselves

- `DACODE_ENV_TRUST=1` imports every key from a repository's `.env`. The only warning
  fired for *ignored* keys, and trusted mode ignores none — so the hatch was silent
  while SECURITY.md promised a stderr warning. Print the warning when the hatch is
  open, not when the default path rejects something.

## Auditing with an outside model

- Pack by module, roughly 10–30k tokens per slice. At that size a model cites
  `file:line` accurately; at 120k it starts claiming files are missing and builds
  "not verifiable" verdicts on that. Verify every claim against the source before
  acting, and keep the model in the role of finder, never judge.
- Cross-check vendors. Each of DeepSeek and Gemini found a critical the other missed;
  agreement between them is a much stronger signal than either alone.
