# Judgment — Jev and triage

Two optional layers sit on top of the gate. Neither can change a verdict.

## Compose: the Jev judge picks, it never rules

With `--judge jev`, `compose` asks TypeSafe's System One for a **bounded pick**
among probed variants. A confident pick overrides the measured ranking; any
judge failure or low-confidence answer falls through to the reasoning-model
pick, then to `ranked[0]`.

- `JEV_API_KEY` resolves from the target repo's `.env` via `cli.load_env` (never
  a global agent store).
- Pin the versioned model id (`jev-1.13.0`), not the alias.
- The judge is a tie-breaker, not a pass/fail authority: the gate decides which
  variants are even eligible.

## Triage: what to try after a failed round

When a round fails the gate, triage picks one action. Each action consumes one
budget round; a triage failure or an unconfident answer defaults to
`new_proposal` (the pre-judge behaviour).

| Action | Meaning |
|---|---|
| `retry_same` | re-probe the round's variants unchanged — only for transient failures (network, rate limits), not bad code |
| `new_proposal` | propose fresh variants (default) |
| `escalate_model` | switch the executor to a stronger model, then propose again; with a fleet it prefers an untried family |
| `human_review` | stop early; surfaces as `HarnessResult.needs_human_review` |

`escalate_model` walks `--escalate-models` by mutating `executor.model` (legacy
ladder) or, with `--fleet`, `next_fleet_model()`.

## judge-eval: is the judge worth keeping?

```bash
dacode judge-eval            # replay recorded compose picks through Jev
```

It scores judge agreement against **gate-verified** winners only — an unverified
winner is never ground truth. If agreement is no better than the ranking
baseline, drop the judge and save the tokens.

Recording lives in the runlog; the eval changes nothing about past runs.
