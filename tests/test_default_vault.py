"""SECURITY.md item 8: the auto-detected vault is the machine vault, never personal."""

from __future__ import annotations

import dacode.config as config


def test_default_vault_prefers_the_machine_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    machine = tmp_path / "Documents" / "dacode_vault"
    machine.mkdir(parents=True)
    assert config._default_vault() == str(machine)


def test_default_vault_never_probes_personal_vaults(monkeypatch, tmp_path):
    # Personal vaults live beside private notes; the readiness audit
    # (docs/design/reviews/2026-11-01, finding 8 caveat) caught the probe
    # still pointing at them. Only an operator may point the rig elsewhere
    # (DACODE_VAULT env or --vault), never an on-disk coincidence.
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Documents" / "Vault").mkdir(parents=True)
    (tmp_path / "Vault").mkdir()
    assert config._default_vault() is None
