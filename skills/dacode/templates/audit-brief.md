# <project> — external robustness review

Copy this file, fill the brackets, and hand it to the auditor as one prompt
(`agy -p "$(cat brief.md)" --model <model> --mode plan --dangerously-skip-permissions`).
Keep the defensive wording: a brief written like an attack plan gets the answer
blocked by the model's content filter mid-run, which surfaces as `exit 3`.

---

# <project> — robustness review of the current revision

This is a defensive engineering review of <one-line description, LOC>. You are
read-only: do not refactor or rewrite files, and do not produce proof-of-concept
code. The output needed is a list of places where an invariant the project states
does not actually hold.

Read `<README>`, `<AGENTS.md>`, `<SECURITY.md>` and `<ARCHITECTURE>` first. They
state what the project promises. Judge the implementation against those promises.

## 1. Check whether `<SECURITY.md>` is accurate

It lists <N> items under "Known open items" and a table of guarantees. For each
open item say whether the description is accurate, understated, overstated, or
already fixed. For each guarantee row say whether the claim is enforced and
covered by a test.

## 2. Invariants that may not be upheld

Rank by what you find. Describe the *condition*, not a recipe.

1. **<Area 1>** (`<path>`). <What the code enforces today.> Which path still lets
the invariant fail? Consider <specific mechanisms>.
2. **<Area 2>** ...
3. **<Area 3>** ...

## 3. The one question

Is this ready for <the real use case>? Answer yes/no, name the single change that
would move it furthest, and say what you still would not rely on afterwards.

Out of scope: style, naming, type hints, new dependencies, framework suggestions,
and code samples that demonstrate a problem. Describe, do not demonstrate.

## Output format

| id | severity | file:line | invariant at risk | condition | suggested fix |

Severities: critical (a claimed guarantee does not hold), high (silent wrong
result or data loss), medium (edge case), low (worth knowing).

Then: (1) the row-by-row `SECURITY.md` assessment, (2) what you could not verify
without running the system and what you would run first, (3) one paragraph verdict.

Do not pad. Do not restate an open item unless the description is wrong.
