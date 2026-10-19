"""Tests for the pstack discipline layer."""

from __future__ import annotations

from pathlib import Path

from dacode.discipline import PstackCritic, check_python_test


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_flags_a_test_with_no_assertion(tmp_path):
    path = _write(tmp_path, "test_x.py", "def test_a():\n    value = compute()\n")
    checks = {f.check for f in check_python_test(path)}
    assert "assertion_free" in checks


def test_flags_bare_truthiness_assertion(tmp_path):
    path = _write(tmp_path, "test_y.py", "def test_a():\n    items = [1]\n    assert items\n")
    checks = {f.check for f in check_python_test(path)}
    assert "weak_truthiness" in checks


def test_flags_self_referential_assertion(tmp_path):
    path = _write(tmp_path, "test_z.py", "def test_a():\n    assert f(1) == f(1)\n")
    checks = {f.check for f in check_python_test(path)}
    assert "tautology" in checks


def test_accepts_a_literal_behaviour_assertion(tmp_path):
    path = _write(tmp_path, "test_ok.py", "def test_a():\n    assert add(2, 2) == 4\n")
    assert check_python_test(path) == []


def test_critic_passes_a_clean_workspace(tmp_path):
    _write(tmp_path, "test_ok.py", "def test_add():\n    assert 1 + 1 == 2\n")
    report = PstackCritic().review_workspace(tmp_path)
    assert report.passed is True
    assert report.tests_total == 1
    assert report.tests_passed == 1
    assert report.score == 1.0


def test_critic_fails_when_no_tests_are_collected(tmp_path):
    report = PstackCritic().review_workspace(tmp_path)
    assert report.passed is False
    assert "no_tests" in {f.check for f in report.findings}


def test_critic_fails_when_a_weak_test_is_present(tmp_path):
    _write(tmp_path, "test_weak.py", "def test_a():\n    assert True\n")
    report = PstackCritic().review_workspace(tmp_path)
    assert report.passed is False
    assert report.errors, "a weak assertion must register as an error-level finding"
