"""Deterministic LLM stub — the backbone of the test suite."""

from __future__ import annotations


class StubLLM:
    """Returns canned responses based on markers found in the prompt.

    ``responses`` maps a substring of the user prompt to the reply.  The first
    matching marker wins.  ``default`` is returned when nothing matches.  Every
    call is recorded in ``calls`` so tests can assert on the prompt the rig
    actually sent.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default: str = "",
        *,
        fail_on: str | None = None,
    ) -> None:
        self.responses = responses or {}
        self.default = default
        self.fail_on = fail_on
        self.calls: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return "stub"

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        self.calls.append((system, user))
        if self.fail_on and self.fail_on in user:
            from dacode.llm.base import LLMError

            raise LLMError(f"stub configured to fail on {self.fail_on!r}")
        for marker, reply in self.responses.items():
            if marker in user:
                return reply
        return self.default
