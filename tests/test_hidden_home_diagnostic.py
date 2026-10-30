"""Issue #9: a pip --user package under $HOME is invisible to the sandbox.

The sandbox hides $HOME by design, so a suite importing a user-site package
dies with an opaque "No module named X". The gate must name the cause and the
way out instead of leaving a riddle in the log. Reproduced end to end with a
fake home: the package exists only under <fake-home>/.local, the sandboxed
run cannot see it, and the finding says exactly that.
"""

from __future__ import annotations

from pathlib import Path

from dacode.config import DaCodeConfig
from dacode.orchestrator import DaCodeRig


def test_a_user_site_import_failure_names_the_home_hidden_cause(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    site = fake_home / ".local" / "lib" / "python3.14" / "site-packages"
    (site / "fakepkg").mkdir(parents=True)
    (site / "fakepkg" / "__init__.py").write_text("")

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "test_calc.py").write_text(
        "import fakepkg\n\ndef test_import():\n    assert hasattr(fakepkg, '__name__')\n"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    cfg = DaCodeConfig(repo=workspace, isolate="bwrap",
                       test_command=("/usr/bin/python3", "-m", "pytest", "-q"))
    rig = DaCodeRig(cfg)
    report = rig.critic.review_workspace(workspace)

    checks = [f.check for f in report.findings]
    assert "hidden_home_packages" in checks
    message = next(f.message for f in report.findings if f.check == "hidden_home_packages")
    assert "pip --user" in message and "workspace-local venv" in message


def test_a_genuinely_missing_module_gets_no_false_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "absent-home"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "test_calc.py").write_text(
        "import module_that_nowhere_exists\n\ndef test_x():\n    assert True\n"
    )
    cfg = DaCodeConfig(repo=workspace, isolate="bwrap",
                       test_command=("/usr/bin/python3", "-m", "pytest", "-q"))
    rig = DaCodeRig(cfg)
    report = rig.critic.review_workspace(workspace)
    assert "hidden_home_packages" not in [f.check for f in report.findings]
