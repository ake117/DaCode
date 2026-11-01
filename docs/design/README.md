# Design docs — where the idea came from

Historical copies of the two Thai notes this repository grew out of (18 Oct
2026 — one day before v0.1.0), with personal names, machine names and
vault-only wikilinks anonymised out. They are preserved as origin artifacts:
the shipped implementation has since diverged from them on purpose (see
`ARCHITECTURE.md` for the blueprint-to-code map, and `reviews/` for a
2026-11-01 fresh-context audit of the drift).

| File | What it is |
|---|---|
| [blueprint-ultimate-autonomous-engineering-rig.md](blueprint-ultimate-autonomous-engineering-rig.md) | The origin idea (18 Oct 2026): the 5-layer stack — semantic vault memory, Harness² optimizer, an executor, a static-critic test gate, and a git sandbox — that DaCode implements. |
| [google-harness2-recursive-agent-harnessing.md](google-harness2-recursive-agent-harnessing.md) | The research note behind layer 2: Google Research's Harness² (arXiv:2610.14224) and its Propose–Probe–Compose recursion, which inspired the optimizer and the trial loop (DaCode keeps the stage names and two-level framing, not the paper's mechanics — DaCode selects a single winner against a deterministic test gate). |
| [reviews/](reviews/2026-11-01/0-synthesis.md) | Goldfish-style fresh-context reviews (2026-11-01, EGM ritual): zoom-out, comprehension, critic, implementation-readiness, and digest role-check, with a synthesis and triage. |
