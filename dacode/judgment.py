"""Jev (TypeSafe System One) judgments for DaCode.

Jev is a *decision model*: it answers bounded questions with typed answers
and probabilities. DaCode uses it for bounded picks (e.g. which probed
variant should win ``compose``) — never for pass/fail verdicts. The critic
gate (real test run + AST scan) stays the only quality authority.

Auth: ``JEV_API_KEY``, resolved from the process environment. ``cli.load_env``
already merges the repo's ``.env`` and the Hermes dotenv before the rig is
built, so a key stored there works without extra wiring. Docs:
https://docs.typesafe.ai/api — endpoint ``POST /v1/systemone``.

Stdlib only, matching the rest of the rig.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

__all__ = ["SystemOneError", "JevAnswer", "JevJudge", "build_judge"]

DEFAULT_MODEL = "jev-1.13.0"  # pin a versioned id; aliases move (docs: /v1/models)
ENDPOINT = "https://api.typesafe.ai/v1/systemone"


class SystemOneError(Exception):
    """Raised when a System One request cannot be completed or parsed."""


@dataclass
class JevAnswer:
    """A Choice answer: the picked option, its confidence, and the spread."""

    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    model: str = ""


def _http_transport(payload: dict, *, api_key: str, timeout: float) -> dict:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise SystemOneError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemOneError(f"request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemOneError(f"non-JSON response: {exc}") from exc


class JevJudge:
    """Bounded picks via a TypeSafe System One Choice question.

    ``choice()`` returns ``(option_id, confidence)``; the option id is
    ``None`` when the model's answer is unknown or below ``min_confidence``
    — callers keep their deterministic fallback. This class never issues
    pass/fail verdicts.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        timeout: float = 15.0,
        transport=None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._transport = transport

    def choice(
        self,
        *,
        state: str,
        instructions: str,
        criteria: dict[str, str],
        min_confidence: float = 0.5,
    ) -> tuple[str | None, float]:
        """Ask one Choice question; return ``(picked_option, confidence)``.

        ``(None, confidence)`` means "no confident pick" — the caller falls
        back to its own deterministic path. Raises :class:`SystemOneError`
        on transport, auth, or malformed-response failures.
        """
        payload = {
            "model": self.model,
            "state": state,
            "questions": {
                "pick": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
        }
        if self._transport is not None:
            try:
                response = self._transport(payload)
            except SystemOneError:
                raise
            except Exception as exc:
                raise SystemOneError(f"transport failed: {exc}") from exc
        else:
            api_key = self.api_key or os.environ.get("JEV_API_KEY")
            if not api_key:
                raise SystemOneError("no JEV_API_KEY in environment")
            response = _http_transport(payload, api_key=api_key, timeout=self.timeout)
        answer = (response.get("answers") or {}).get("pick") or {}
        if answer.get("type") != "choice":
            raise SystemOneError(f"unexpected answer type: {answer.get('type')!r}")
        pick = answer.get("choice")
        confidence = float(answer.get("confidence") or 0.0)
        if pick not in criteria:
            raise SystemOneError(f"model answered with unknown option {pick!r}")
        if confidence < min_confidence:
            return None, confidence
        return pick, confidence


def build_judge(kind: str | None) -> JevJudge | None:
    """Build the compose judge — ``None`` (off) unless ``kind == "jev"``."""
    if kind == "jev":
        return JevJudge()
    return None
