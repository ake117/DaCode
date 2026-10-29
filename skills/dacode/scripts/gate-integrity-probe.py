#!/usr/bin/env python3
"""Adversarial check: can code under test make a failing suite look green?

The suite imports a module that reads `--junitxml=<path>` from ``sys.argv``,
rewrites the counts, prints a matching summary and ends the process with status 0.
A gate that trusts the report's declared totals (or stdout) reports PASS here; a gate
that counts ``<testcase>`` elements and requires self-consistency fails the trial.

Run it after touching the critic, the JUnit parsing, or the count/verdict logic:

    cd <DaCode checkout>
    .venv/bin/python skills/.../scripts/gate-integrity-probe.py

Exit 0 = the gate held. Exit 1 = the gate can be fooled (fix it before shipping).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

APP = '''"""Runs inside pytest: rewrite the gate's report and end the process green."""
import atexit
import os
import pathlib
import sys


def _rewrite():
    for arg in sys.argv:
        if arg.startswith("--junitxml="):
            target = pathlib.Path(arg.split("=", 1)[1])
            if target.is_file():
                text = target.read_text()
                text = text.replace('tests="1"', 'tests="999"')
                text = text.replace('failures="1"', 'failures="0"')
                target.write_text(text)
    print("999 passed in 0.01s", flush=True)
    os._exit(0)


atexit.register(_rewrite)
'''

TEST = "import app\n\n\ndef test_that_fails():\n    assert 1 == 2\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ("git", *args), cwd=repo, check=True, capture_output=True, text=True
    )


def main() -> int:
    from dacode.discipline.critic import PstackCritic

    with tempfile.TemporaryDirectory(prefix="gate-probe-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        (repo / "app.py").write_text(APP, encoding="utf-8")
        (repo / "test_probe.py").write_text(TEST, encoding="utf-8")
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "probe@dacode.local")
        _git(repo, "config", "user.name", "DaCode probe")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "probe")

        critic = PstackCritic(test_command=(sys.executable, "-m", "pytest", "-q"))
        report = critic.review_workspace(repo)

    checks = sorted({finding.check for finding in report.findings})
    print(
        f"passed={report.passed} total={report.tests_total} "
        f"failed={report.tests_failed} exit={report.exit_code} checks={checks}"
    )
    if report.passed:
        print("FAIL: the gate accepted a fabricated report", file=sys.stderr)
        return 1
    print("OK: the fabricated report was rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
