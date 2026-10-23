"""DaCode command-line interface.

Usage:
  dacode run "<task>" [--budget N] [--llm KIND] [--executor pi|script] ...
  dacode memory search "<query>"
  dacode sandbox list | clean
  dacode layers
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dacode.config import DaCodeConfig
from dacode.llm import provider_names
from dacode.env import DEFAULT_ENV_PATHS, load_env
from dacode.harness.models import HarnessResult
from dacode.memory import VaultMemory
from dacode.orchestrator import DaCodeRig
from dacode.sandbox import GitSandbox

__all__ = ["main", "build_parser"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dacode",
        description="DaCode — The Ultimate Autonomous Engineering Rig",
    )
    parser.add_argument("--repo", default=None, help="target repository (default: cwd)")
    parser.add_argument("--vault", default=None, help="Obsidian vault path for memory")
    parser.add_argument("--sandbox-root", default=None, help="where trial worktrees live")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a task through the full 5-layer rig")
    run.add_argument("task", help="the engineering task, in plain language")
    run.add_argument("--budget", type=int, default=2, help="Harness² recursion rounds")
    run.add_argument("--variants", type=int, default=2, help="variants proposed per round")
    run.add_argument(
        "--llm",
        default=None,
        help="stub | local | " + " | ".join(provider_names()),
    )
    run.add_argument("--model", default=None, help="model id for the chosen backend")
    run.add_argument("--executor", default=None, choices=["pi", "script"])
    run.add_argument("--script-command", default=None, help="command for --executor script")
    run.add_argument(
        "--test-command",
        default=None,
        help="shell command that runs the project's tests "
        "(default: python -m pytest -q); run via bash -c inside the trial worktree",
    )
    run.add_argument(
        "--test-glob",
        default=None,
        help="glob for static test scanning (default: test_*.py)",
    )
    run.add_argument("--keep-worktree", action="store_true", help="keep losing trial worktrees")
    run.add_argument(
        "--escalate-models",
        default=None,
        help="comma-separated model ladder for the judge's escalate_model "
        "triage action (e.g. 'claude-sonnet-4-5,gpt-4o')",
    )
    run.add_argument(
        "--judge",
        default=None,
        help="bounded-decision judge for compose: 'jev' = TypeSafe System One "
        "(unset = off)",
    )

    mem = sub.add_parser("memory", help="query the vault memory layer")
    mem_sub = mem.add_subparsers(dest="mem_command", required=True)
    search = mem_sub.add_parser("search", help="retrieve relevant lessons for a query")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)

    sand = sub.add_parser("sandbox", help="inspect or clean trial worktrees")
    sand_sub = sand.add_subparsers(dest="sand_command", required=True)
    sand_sub.add_parser("list", help="list registered worktrees")
    sand_sub.add_parser("clean", help="remove all dacode trial worktrees")

    jev = sub.add_parser(
        "judge-eval",
        help="score Jev's Compose picks against recorded gate-verified winners",
    )
    jev.add_argument("--limit", type=int, default=None, help="max cases to evaluate")
    jev.add_argument("--model", default=None, help="Jev model id (default: the pinned jev-1.13.0)")
    jev.add_argument(
        "--log",
        default=None,
        help="runlog path (default: DACODE_RUNLOG or ~/.local/state/dacode/runlog.jsonl)",
    )
    sub.add_parser("layers", help="show the status of the five layers")
    return parser


def _make_config(args) -> DaCodeConfig:
    cfg = DaCodeConfig.from_env(args.repo)
    if args.vault:
        cfg.vault = Path(args.vault).expanduser().resolve()
    if args.sandbox_root:
        cfg.sandbox_root = Path(args.sandbox_root).expanduser().resolve()
    for attr in ("budget", "variants"):
        value = getattr(args, attr, None)
        if value is not None:
            setattr(cfg, "variants_per_round" if attr == "variants" else attr, value)
    if getattr(args, "llm", None):
        cfg.llm_kind = args.llm
    if getattr(args, "model", None):
        cfg.model = args.model
    if getattr(args, "executor", None):
        cfg.executor = args.executor
    if getattr(args, "script_command", None):
        cfg.script_command = args.script_command
    if getattr(args, "test_command", None):
        # Run the user's test command through a shell so pipes/`&&` work, and
        # so a non-Python suite (e.g. `make -C port/renderer test`) is one argv.
        cfg.test_command = ("bash", "-c", args.test_command)
    if getattr(args, "test_glob", None):
        cfg.test_glob = args.test_glob
    if getattr(args, "keep_worktree", False):
        cfg.keep_winning_worktree = True
    if getattr(args, "judge", None):
        cfg.judge = args.judge
    if getattr(args, "escalate_models", None):
        cfg.escalate_models = [m.strip() for m in args.escalate_models.split(",") if m.strip()]
    return cfg


def _print_result(result: HarnessResult) -> None:
    best = result.best
    print()
    print("=" * 62)
    print(f"  DaCode result — {'PASS ✅' if result.passed else 'FAIL ❌'}")
    print("=" * 62)
    print(f"  task      : {result.task}")
    print(f"  rounds    : {result.rounds}")
    print(f"  variants  : {len(result.variants)} probed")
    print(f"  best      : {best.id} ({best.label})  score={best.score}")
    if best.probe:
        p = best.probe
        print(f"  tests     : {p.tests_passed}/{p.tests_total} pass  (exit {p.exit_code})")
        print(f"  workspace : {p.workspace}")
    if result.lesson_path:
        print(f"  lesson    : {result.lesson_path}")
    if result.needs_human_review:
        print("  note      : needs human review — the judge stopped the run")
    print("=" * 62)
    for v in sorted(result.variants, key=lambda x: x.score or 0, reverse=True):
        mark = "★" if v is best else " "
        t = f"{v.probe.tests_passed}/{v.probe.tests_total}" if v.probe else "?"
        print(f"  {mark} {v.id:<6} {v.label:<20} score={v.score}  tests={t}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Load secrets from the target repo's own .env before building the rig.
    # DaCode never reads ~/.hermes/.env or ~/.pi/agent/auth.json.
    repo_hint = Path(args.repo).expanduser() if getattr(args, "repo", None) else Path.cwd()
    load_env(*[p.replace("{repo}", str(repo_hint)) for p in DEFAULT_ENV_PATHS])

    if args.command == "judge-eval":
        from dacode.jeval import collect_cases, evaluate, summarize
        from dacode.judgment import JevJudge
        from dacode.runlog import load_events

        cases = collect_cases(load_events(args.log))
        if not cases:
            print(
                "no gate-verified compose cases in the run log yet — run tasks "
                "and let the recorder accumulate (DACODE_RUNLOG, default "
                "~/.local/state/dacode/runlog.jsonl)"
            )
            return 1
        judge = JevJudge(model=args.model) if args.model else JevJudge()
        print(summarize(evaluate(cases, judge, limit=args.limit)))
        return 0

    if args.command == "layers":
        cfg = _make_config(args)
        rig = DaCodeRig(cfg)
        print(f"DaCode rig @ {cfg.repo}")
        for layer in rig.layers():
            icon = "✅" if layer.ready else "⚠️ "
            print(f"  {icon} {layer.name:<22} {layer.detail}")
        return 0

    if args.command == "memory":
        cfg = _make_config(args)
        if cfg.vault is None or not Path(cfg.vault).is_dir():
            print(f"error: vault not found ({cfg.vault}); pass --vault", file=sys.stderr)
            return 2
        mem = VaultMemory(cfg.vault)
        hits = mem.retrieve(args.query, limit=args.limit)
        if not hits:
            print("no matching notes")
            return 1
        for hit in hits:
            print(f"[{hit.score:>6}] {hit.title}")
            print(f"          {hit.path}")
            print(f"          {hit.snippet[:160]}…")
        return 0

    if args.command == "sandbox":
        cfg = _make_config(args)
        sandbox = GitSandbox(cfg.repo, cfg.sandbox_root)
        if args.sand_command == "list":
            for info in sandbox.list():
                print(f"  {info.path}  [{info.branch or 'detached'}]  {info.head or ''}")
            return 0
        if args.sand_command == "clean":
            removed = 0
            for info in sandbox.list():
                name = Path(info.path).name
                if "dacode" in str(info.branch or "") or name.startswith("dacode"):
                    sandbox.remove(name, delete_branch=True)
                    removed += 1
            print(f"removed {removed} trial worktree(s)")
            return 0

    if args.command == "run":
        cfg = _make_config(args)
        rig = DaCodeRig(cfg)
        result = rig.run_task(args.task)
        _print_result(result)
        return 0 if result.passed else 1

    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
