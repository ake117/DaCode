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
    run.add_argument("--llm", default=None, help="stub | local | openrouter | openai")
    run.add_argument("--model", default=None, help="model id for the chosen backend")
    run.add_argument("--executor", default=None, choices=["pi", "script"])
    run.add_argument("--script-command", default=None, help="command for --executor script")
    run.add_argument("--keep-worktree", action="store_true", help="keep losing trial worktrees")

    mem = sub.add_parser("memory", help="query the vault memory layer")
    mem_sub = mem.add_subparsers(dest="mem_command", required=True)
    search = mem_sub.add_parser("search", help="retrieve relevant lessons for a query")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)

    sand = sub.add_parser("sandbox", help="inspect or clean trial worktrees")
    sand_sub = sand.add_subparsers(dest="sand_command", required=True)
    sand_sub.add_parser("list", help="list registered worktrees")
    sand_sub.add_parser("clean", help="remove all dacode trial worktrees")

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
    if getattr(args, "keep_worktree", False):
        cfg.keep_winning_worktree = True
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
    print("=" * 62)
    for v in sorted(result.variants, key=lambda x: x.score or 0, reverse=True):
        mark = "★" if v is best else " "
        t = f"{v.probe.tests_passed}/{v.probe.tests_total}" if v.probe else "?"
        print(f"  {mark} {v.id:<6} {v.label:<20} score={v.score}  tests={t}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Load secrets from .env files before building the rig:
    # the target repo's own .env first, then the canonical ~/.hermes/.env.
    repo_hint = Path(args.repo).expanduser() if getattr(args, "repo", None) else Path.cwd()
    load_env(repo_hint / ".env", *[p.replace("{repo}", str(repo_hint)) for p in DEFAULT_ENV_PATHS])

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
