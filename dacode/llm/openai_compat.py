"""OpenAI-compatible chat-completions client (urllib only, no deps)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from dacode.llm.base import LLMError

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class OpenAICompatClient:
    """Talks to any ``/v1/chat/completions`` endpoint."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        *,
        timeout: float = 120.0,
        max_retries: int = 2,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.extra_headers = extra_headers or {}

    @property
    def name(self) -> str:
        return f"{self.model}@{self.base_url}"

    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)

        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:  # noqa: PERF203
                detail = exc.read().decode("utf-8", "replace")[:500]
                last_error = LLMError(f"HTTP {exc.code} from {url}: {detail}")
                if exc.code not in _RETRYABLE_STATUS:
                    raise last_error from exc
            except urllib.error.URLError as exc:
                last_error = LLMError(f"connection to {url} failed: {exc.reason}")
            except (TimeoutError, OSError) as exc:
                last_error = LLMError(f"request to {url} errored: {exc}")
            if attempt < self.max_retries:
                import time

                time.sleep(0.5 * (attempt + 1))
        else:
            assert last_error is not None
            raise last_error

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape from {url}: {data!r:.500}") from exc
