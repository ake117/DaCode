# Auditing the rig with an outside model

Use when the question is "is this thing actually safe / correct?" and the answer
should not come from the agent that wrote it. `agy` (Antigravity CLI,
`~/.local/bin/agy`) fronts several vendors, so one CLI gives a genuine second
opinion.

## Set up so the audit cannot touch anything real

```bash
agy models                      # gemini-4-argon-*, gemini-3.8-flash-*, claude-opus-5-5-*, gpt-oss-120b
rm -rf /tmp/<name>-audit && git clone -q ~/<repo> /tmp/<name>-audit
```

Audit the clone, never the working checkout. `--dangerously-skip-permissions` is
needed for the auditor to read files and run the suite, which also means it can
write; a throwaway clone makes that harmless, and keeps a real `.env` out of the
prompt and out of any reproduction it writes.

```bash
cd /tmp/<name>-audit && agy -p "$(cat brief.md)" --model gemini-4-argon-high \
  --mode plan --dangerously-skip-permissions > /tmp/audit.md 2>/tmp/audit.err
```

Run it with `background=true, notify=true`: a real audit of a few thousand lines
takes 10–20 minutes and prints nothing until it is done (`wc -c` staying at a few
hundred bytes means it is still reading, not stalled).

## Private repositories: pack it, never link it

A brief that says "read `https://raw.githubusercontent.com/owner/repo/<sha>/file.py`"
works only while the repository is public. Once it is private every one of those URLs
returns 404 to the auditor, and a web model asked to review the links produces a
confident report about a codebase it could not open. Two consequences:

- **Emit a self-contained pack instead**: full contents with line numbers, the brief,
  and the task, in one file per slice (~10–15 k tokens each; one module group per
  file). `file:line` citations stay reliable at that size and the model has nothing to
  fetch.
- **Delete stale prompt files** that were built on public raw URLs when you learn the
  repository is private — a leftover brief is worse than none, because a later session
  pastes it and trusts the answer.

`agy` and the OpenRouter path are unaffected: they read a local clone, so a private
repository is still auditable that way. It is only the web-model route that needs the
pack.

## Brief: written like a review request, not an attack plan

Start from `templates/audit-brief.md` — it already has the shape below and the
wording that survives a content filter.

- Name the promise documents to read first (`README`, `AGENTS.md`, `SECURITY.md`)
  and say the job is to judge the code **against what the project claims**.
- List the areas to look at, hardest first, each with the invariant at stake.
- Demand a table: `id | severity | file:line | what breaks | condition | fix`.
- Put the out-of-scope list in writing (style, naming, type hints, new
  dependencies) or the report is 40 pages of "migrate to FastAPI".
- Ask for "what you could not verify" and a one-paragraph yes/no verdict.

Write it in defensive language — "the invariant does not hold", "condition",
"residual gap". Briefs that read like an exploit recipe get the model's answer
**blocked by its content filter mid-run** (exit 3, `blocked by content safety
filters`, retries exhausted), which looks like a quota error and is not. Ask for
descriptions, explicitly not proof-of-concept code.

## Two passes beat one long run

1. **Discovery** — the full brief, strongest model available (`claude-opus-5-5-high`
   for design logic, `gemini-4-argon-high` for breadth across files).
2. **Verification** — a narrow brief: "here are the N fixes and what each was
   supposed to close; verdict `held` / `partial` / `still open` per fix, with the
   residual gap". A cheap model does this well and it is the pass that finds the
   half-closed fixes.

Quota is per pool: the Claude and gpt-oss models share one, the Gemini models have
another. A 429 states the reset time — when it says days rather than hours, switch
model family instead of waiting, and never loop on retries.

**A second model from the same vendor is not a second opinion.** Gemini via `agy`
and Gemini in a browser tab share a family's blind spots; when the goal is
independence, spend the next pass on a different vendor (DeepSeek over OpenRouter,
ChatGPT, Claude) rather than a bigger Gemini.

## Treat every finding as a claim

Reproduce before fixing, every time. A minimal reproduction (a `conftest.py` that
prints a fake summary and calls `os._exit(0)`; a workspace under `/tmp`; a
committed test edit) settles in a minute what a paragraph of prose only suggests.
The loop that works:

1. Reproduce the finding with the smallest possible case; if it does not
   reproduce, it is a question for the user, not a bug to fix.
2. Fix it with a regression test that *reproduces the original failure* — the test
   that would have caught it, not a test of the new helper.
3. Re-run the reproduction against the fixed code and quote the new output.
4. Update the guarantees table in `SECURITY.md` **and** scope the claim to what is
   actually enforced. A reviewer will read that table as documentation of fact;
   "the gate never gets the network" is false under `--isolate none`, and
   saying so is cheaper than being caught.

Keep the raw report in the vault (`Projects/<name>/Audit - … .md`) and correlate
the two auditors: a finding both report is high confidence, a finding only one
reports needs reproduction before it earns a commit.

## DeepSeek over OpenRouter

DeepSeek is a strong second opinion for structural/architectural findings, but
not a trustworthy final judge.

- **Reasoning models return `content: null` when `max_tokens` is too low.** The
  token budget is consumed by internal reasoning first. Set `max_tokens` to
  ~12000 and fall back to `message.reasoning` when `message.content` is null;
  also inspect `finish_reason` — a `length` finish with 4000 tokens looks like a
  silent empty answer.
- **It can hallucinate "files not in the provided source".** In one run it
  claimed seven modules were absent when all 58 files were packed (338 KB). Any
  `not verifiable` verdict built on that claim is void — check the file exists in
  the pack first. Size is the trigger: at ~25 k tokens (one module plus its
  contract) the same model cited `file:line` correctly on every question; the
  whole-repo pack (~120 k) is where the false "absent" claims appeared. Send one
  module per request when you want citations you can act on.
- **Its real strength is configuration ordering.** It found that a repo's `.env`
  is loaded into `os.environ` *before* config is built (`cli.py:235`), so the
  tested repo could in principle choose its own sandbox mode. Use it for this
  class of finding; verify every claim against the code.

## agy model / effort matrix

`agy` rejects contradictory model+effort pairs with a hard error:

| model | valid effort | notes |
|---|---|---|
| `gemini-4-argon-high` | — | the tier is in the name; adding `--effort high` conflicts |
| `gemini-4-argon` | low, medium, high | **no** `xhigh` or `max`; `high` is the ceiling |
| `claude-opus-5-5` | low, medium, high | no `xhigh`/`max` |
| `gemini-3.8-flash-high` | — | tier in name |

Measured on a narrow single-file question: `gemini-4-argon-high` ~46 s,
`gemini-3.8-flash-high` ~28 s. Use Argon for a full audit, Flash for a quick
re-verdict. Picking the tier suffix twice is the most common error — read
`agy models` first.

## Three traps

- **The report describes an older HEAD.** Record the SHA the auditor checked
  (`git log --oneline -1` inside its clone). By the time you read the report you may
  have already fixed some of it, and "critical" items that are already closed waste
  a batch. Re-check each finding against the current tree before touching code.
- **A test can encode the bug.** When a fix contradicts a green test, read what the
  test asserts: one here asserted that a judge may pick a gate-failing variant,
  which is exactly the invariant being fixed. Correct the test deliberately and say
  so in the commit — never relax it to make new code pass.
- **The suggested fix is a suggestion.** Reviewers over-correct: one wanted every
  embedding knob removed from the env allow-list, when only the two that redirect
  traffic (`*_BASE_URL`, vault path) were dangerous. Keep the smallest change that
  closes the stated condition, and write down why the rest was not taken.
