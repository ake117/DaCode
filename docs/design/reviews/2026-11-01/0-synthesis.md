# Goldfish Review — Synthesis (2026-11-01)

Five independent fresh-context reviews (`agy` / gemini-4-argon-high, zero shared
context — each stage saw only its rubric and the files), run per the
Elephant-Goldfish-Model ritual. Source reports: `1-zoom-out.md` …
`5-harness2-role.md` in this folder.

## What was reviewed

| # | Stage | Target |
|---|---|---|
| 1 | Zoom-Out (YAGNI / reuse) | blueprint |
| 2 | Comprehension (naive reader) | blueprint |
| 3 | Design Critic (failure modes / trust) | blueprint |
| 4 | Implementation Readiness (claims vs `HEAD`) | blueprint |
| 5 | Comprehension + Role Check | harness2 digest + design README |

## Cross-cutting conclusions (synthesizer)

1. **The blueprint is correctly framed as a historical origin note, but its
   frontmatter still says `status: active`.** Reality has deliberately diverged:
   ChromaDB → stdlib SQLite vectors, LLM critic subagent → deterministic gate,
   cross-project vault → per-project scoping, sandbox-first → sandbox shipped.
   Four of the blueprint's five layers exist under *different mechanics* than the
   note describes. (Stages 1, 4, 5 agree.)

2. **Five live code gaps surfaced by the readiness audit** (owner decision
   needed — not doc issues):
   - `HarnessVariant.tools` is requested from the LLM and parsed, but never read
     by any executor (`pi.py:91` reads static `self.tools`).
   - Failed-round diagnostics (`findings`, `gate_output`, `errors`) are never
     fed back into `propose()` — multi-round retries are blind to why the gate
     failed. (Also the largest divergence from Harness²'s contrastive loop.)
   - `DEFAULT_SYSTEM_PROMPT` tells trials to "Write or update tests", which
     `PstackCritic._check_contract()` immediately fails as `tests_modified`.
   - `VaultMemory.ingest()` does not index new lessons into `VectorStore`;
     they are invisible to `local` semantic search until `dacode memory index`.
   - `_default_vault()` probes personal vault paths, contradicting
     `SECURITY.md` item 8 (machine vault); `_isolation_policy()` docstring
     contradicts the actual `--isolate-network` default-off behaviour.

3. **Doc drift found** (small, factual):
   - `docs/design/README.md` did not list this `reviews/` folder; claimed
     "verbatim" copies although anonymisation also deleted/rewrote prose.
   - `ARCHITECTURE.md` "Extension points" still lists semantic retrieval and
     `bwrap` isolation as unbuilt — both shipped.
   - `skills/dacode/SKILL.md` says 232 tests (now 370); branch naming in
     `AGENTS.md` / `README.md` omits the nonce/idx segments.
   - harness2 digest: broken `DeepSeek Harness (DSH)` cross-link (target note
     not imported), Obsidian-only `[!abstract]` callout, no in-file
     "this is a paper digest, not shipped DaCode" banner.

4. **Security posture validated by outside eyes.** The critic stage
   independently derived the same invariants the project already enforces
   (gate owns pass/fail, worktree-per-trial, networkless gate, scoped vault,
   redaction, budget caps) as *requirements* — none of its attacks described a
   live hole; every hole it named is closed in code. The residual design
   tension it flags — the executor needs network/credentials while untrusted
   tests must not have them — is solved by the two-policy split
   (`isolation` vs `gate_isolation`) and matches `SECURITY.md`.

## Triage

- **Done with this commit:** design README updated (reviews folder, softened
  verbatim claim); blueprint `status` retired to `historical`.
- **Resolved (Nov 2026, all five code gaps in (2), owner-approved):**
  default prompt no longer invites test edits (`21d2f5d`) · failure evidence
  feeds the next proposal round (`97a4f62`) · dead `variant.tools` cut
  (`9134027`) · default-vault probe is machine-vault-only + network-flag docs
  corrected (`0c975a9`) · ingest auto-indexes the vector store, fail-open
  (`dbd4be0`). Suite: 370 → 379 tests.
- **Optional doc pass:** items in (3).
