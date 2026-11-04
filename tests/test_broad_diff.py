"""The surgical-change rule (Karpathy #3) as a soft gate.

`broad_diff` is a warning, never a failure: the gate cannot read intent,
so breadth dents a variant's score and flags every report without
blocking legitimately multi-file tasks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from dacode.discipline import PstackCritic


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo_with_changes(tmp_path: Path, extra_files: int) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.local")
    _git(repo, "config", "user.name", "T")
    (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    for i in range(extra_files):
        (repo / f"module_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    return repo


def test_narrow_diff_stays_silent(tmp_path):
    critic = PstackCritic()
    workspace = _repo_with_changes(tmp_path, extra_files=3)
    assert critic._check_broad_diff(workspace) == []


def test_broad_diff_warns_but_does_not_error(tmp_path):
    critic = PstackCritic(broad_diff_limit=5)
    workspace = _repo_with_changes(tmp_path, extra_files=9)  # 9 > 5
    findings = critic._check_broad_diff(workspace)
    assert len(findings) == 1
    assert findings[0].check == "broad_diff"
    assert findings[0].severity == "warning"
    assert "9 non-test files" in findings[0].message


def test_tests_and_infra_do_not_count_toward_breadth(tmp_path):
    critic = PstackCritic(broad_diff_limit=2)
    workspace = _repo_with_changes(tmp_path, extra_files=0)
    # a trial touching only its own tests + gate infra is judged by the
    # dedicated tampering checks — breadth must stay silent here
    (workspace / "test_new.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (workspace / "conftest.py").write_text("", encoding="utf-8")
    (workspace / "extra.py").write_text("y = 1\n", encoding="utf-8")
    assert critic._check_broad_diff(workspace) == []


def test_non_git_workspace_is_skipped(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x\n", encoding="utf-8")
    assert PstackCritic()._check_broad_diff(plain) == []
