#!/usr/bin/env python3
"""Emit upload-ready audit packs from a DaCode checkout.

A private repository cannot be fetched by a web model (raw URLs 404/403), and a model
that gets the whole repo at once (100k+ tokens) starts claiming files are missing and
builds "not verifiable" verdicts on that. This writes one Markdown file per slice,
each self-contained and small enough (~10-25k tokens) that a model cites lines
accurately. Attach the files in order; the brief sits at the top of each pack.

    python3 pack_for_web_audit.py --repo ~/AI_Projects/DaCode --out ./audit-packs

The slices mirror the module boundaries and map onto the three audit questions that
have actually produced findings: gate integrity, sandbox reach, secrets/state/CLI.
"""

from __future__ import annotations

import argparse
import pathlib

BRIEF = """You are auditing one slice of a small autonomous coding-agent rig (DaCode). It
runs model-written code against a git repository, gates the result on the repository's
own test suite, and keeps a lesson when a trial passes.

The complete contents of this slice are below, with line numbers. Nothing is missing.
You are read-only: no refactors, no rewritten files, no working exploit code. Every
claim ends with file:line. Do not restate the code and do not comment on style, naming,
typing or dependencies. Do not report something that SECURITY.md already lists as an
open item unless the description there is wrong. Rank findings by impact: critical (a
claimed guarantee does not hold, or a failing trial can pass), high (silent wrong
result, credential exposure), medium (edge case), low. If a category has nothing, say
so in one line — never invent a finding to fill space.
"""

SLICES: dict[str, list[str]] = {
    "1-gate": [
        "SECURITY.md",
        "dacode/discipline/critic.py",
        "dacode/discipline/checks.py",
    ],
    "2-sandbox": [
        "AGENTS.md",
        "dacode/sandbox/bwrap.py",
        "dacode/sandbox/__init__.py",
        "dacode/executor/base.py",
        "dacode/executor/pi.py",
        "dacode/executor/script.py",
        "dacode/orchestrator.py",
    ],
    "3-state-cli": [
        "dacode/config.py",
        "dacode/env.py",
        "dacode/cli.py",
        "dacode/state.py",
        "dacode/runlog.py",
        "dacode/redact.py",
        "dacode/memory/__init__.py",
    ],
}

QUESTIONS = {
    "1-gate": """Answer only:
1. Can the code under test make a failing suite look green? Walk every input that
decides `passed` — exit code, stdout counts, the JUnit report, the baseline, the
contract snapshot, the test-integrity checks, findings severity — and name the
weakest link with file:line.
2. Can any check be satisfied by a file the trial writes, or by a configuration the
trial controls (pytest ini, plugin autoload, conftest, a test directory)?
3. Does any row of the SECURITY.md table fail to match what this code does?
4. Anything else here that is a real bug — cite the line.""",
    "2-sandbox": """Answer only:
1. What can a trial still reach inside the sandbox that it should not — mounts, env
vars, inherited descriptors, paths bound for the interpreter, the gate's report
directory, /sys, /dev/shm, /proc? Cite the argv construction line.
2. Is there a path where isolation silently degrades instead of failing closed?
3. Do the executor's policy and the gate's policy hide and allow the same things? List
any divergence with file:line on both sides.
4. Can a trial influence the orchestration's configuration or the paths it binds?
5. Anything else here that is a real bug — cite the line.""",
    "3-state-cli": """Answer only:
1. Can a value from a repository's `.env` still change how DaCode behaves? Name every
name that survives the allow-list and what it can influence.
2. Does anything read or write a path taken from untrusted input without containing it?
3. Can a secret reach disk or a subprocess argument on any path here — including the
CLI's own output? Cite the write and the redaction, or the absence of one.
4. Are the locks and the 0700 permissions applied on every path that needs them, or
only on the first-run creation?
5. Anything else here that is a real bug — cite the line.""",
}


def pack(repo: pathlib.Path, name: str) -> str:
    parts = [f"# DaCode audit slice: {name}\n\n## Brief\n\n{BRIEF}"]
    for rel in SLICES[name]:
        text = (repo / rel).read_text(encoding="utf-8", errors="replace")
        numbered = "\n".join(f"{i:>5}| {line}" for i, line in enumerate(text.splitlines(), 1))
        parts.append(f"## File: {rel}\n\n```\n{numbered}\n```")
    parts.append(f"## Task\n\n{QUESTIONS[name]}")
    return "\n\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(pathlib.Path.home() / "AI_Projects" / "DaCode"))
    parser.add_argument("--out", default="audit-packs")
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).expanduser()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in SLICES:
        target = out / f"dacode-audit-{name}.md"
        body = pack(repo, name)
        target.write_text(body, encoding="utf-8")
        print(f"{target}  {len(body):,} chars (~{len(body) // 4:,} tokens)")


if __name__ == "__main__":
    main()
