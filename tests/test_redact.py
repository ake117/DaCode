"""The redact boundary must know every provider key the rig routes.

``redact()`` is the single gate between the rig and everything that persists
(runlog JSONL, the SQLite state mirror the MCP server serves, vault lessons).
Its env-name list used to miss ``GLM_API_KEY``/``ZAI_API_KEY`` — the two names
DaCode itself loads from ``.env`` and passes into networked trials — and a
z.ai key has no ``sk-``-like shape, so the token patterns caught nothing and
the value survived into persisted text verbatim.
"""

from __future__ import annotations

import pytest

from dacode.env import ENV_ALLOW_LIST
from dacode.redact import REDACTED, redact, redact_event

#: A fake key with z.ai's real-world shape: no provider prefix, just an
#: identifier, a dot and an opaque tail. The generic patterns must not be
#: relied on to catch this — the env-name path has to.
ZAI_SHAPED = "a1b2c3d4e5f60718293a4b5c6d7e8f90.QwXzAbCdEfGh1234"


@pytest.mark.parametrize(
    "name",
    [key for key in ENV_ALLOW_LIST if key.upper().endswith("_API_KEY")],
)
def test_every_allow_listed_key_is_redacted_by_name(name, monkeypatch):
    """Any key name the env allow-list routes is treated as secret at the boundary."""
    value = f"dummy-value-for-{name}-0123456789"
    monkeypatch.setenv(name, value)
    text = f"probe failed: settings dump {name}={value}"
    assert value not in redact(text)
    assert REDACTED in redact(text)


def test_a_zai_key_without_a_token_shape_is_redacted(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", ZAI_SHAPED)
    text = f"model echoed: export ZAI_API_KEY={ZAI_SHAPED} before running"
    out = redact(text)
    assert ZAI_SHAPED not in out
    assert "export ZAI_API_KEY=" + REDACTED in out


def test_redact_event_covers_nested_strings(monkeypatch):
    monkeypatch.setenv("GLM_API_KEY", ZAI_SHAPED)
    event = redact_event(
        {
            "type": "probe",
            "nested": {"stderr": [f"trial error: env ZAI_API_KEY={ZAI_SHAPED}"]},
        }
    )
    assert ZAI_SHAPED not in str(event)


def test_an_unset_key_name_leaves_other_text_untouched():
    text = "the variable ZAI_API_KEY is documented in the README"
    assert redact(text) == text
