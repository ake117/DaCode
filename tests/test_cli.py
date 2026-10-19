"""Smoke tests for the CLI surface."""

from __future__ import annotations

from pathlib import Path

from dacode.cli import build_parser, main


def test_parser_requires_a_subcommand():
    parser = build_parser()
    try:
        parser.parse_args([])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit for missing subcommand")


def test_layers_command_prints_all_five_layers(rig_repo, vault, capsys):
    rc = main(["--repo", str(rig_repo), "--vault", str(vault), "layers"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Vault Memory" in out
    assert "Harness² Optimizer" in out
    assert "Git Sandbox" in out


def test_memory_search_command(rig_repo, vault, capsys):
    rc = main(["--repo", str(rig_repo), "--vault", str(vault), "memory", "search", "worktree"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Sandbox" in out


def test_sandbox_list_command(rig_repo, vault, capsys):
    rc = main(["--repo", str(rig_repo), "--vault", str(vault), "sandbox", "list"])
    assert rc == 0
    assert str(rig_repo) in capsys.readouterr().out
