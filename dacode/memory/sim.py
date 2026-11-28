"""SIM — Self-Improvement Memory for the Harness Optimizer (arXiv 2611.18856).

Stores structured optimizer edit history grouped by recurring ``root_cause``:
each edit records its rationale, predicted outcome (captured before probing),
observed outcome (both passing and failing), and provenance (repo, model,
round, task). Kept strictly separate from policy/executor memory snippets so
proposer and selector read it directly as a bounded whole block.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from dacode.redact import redact

__all__ = ["SIMRecord", "SIMStore"]

_SPACE_RE = re.compile(r"\s+")


def _norm_key(root_cause: str) -> str:
    cleaned = _SPACE_RE.sub(" ", (root_cause or "").strip()).lower()
    return cleaned or "general"


def _check_not_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"SIM path must not be a symlink: {path}")
    if path.parent.is_symlink():
        raise ValueError(f"SIM parent must not be a symlink: {path.parent}")


@dataclass
class SIMRecord:
    """One probed harness edit's pre-probe intent and post-probe result."""

    root_cause: str
    label: str
    rationale: str = ""
    predicted_outcome: str = ""
    observed_outcome: str = ""
    passed: bool = False
    score: float = 0.0
    errors: list[str] = field(default_factory=list)
    repo: str = ""
    model: str = ""
    round_no: int = 0
    task: str = ""
    ts: float = field(default_factory=time.time)


class SIMStore:
    """JSON-backed Self-Improvement Memory grouped by normalized root cause."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        _check_not_symlink(self.path)
        self.groups: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        _check_not_symlink(self.path)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        groups = data.get("groups") if isinstance(data, dict) else None
        if isinstance(groups, dict):
            self.groups = groups

    def _save(self) -> None:
        _check_not_symlink(self.path)
        parent = self.path.parent
        created_dir = not parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        if created_dir:
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass
        payload = json.dumps(
            {"version": 1, "groups": self.groups},
            ensure_ascii=False,
            indent=2,
        )
        tmp = parent / f".{self.path.name}.{os.getpid()}.tmp"
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        os.replace(str(tmp), str(self.path))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def record(self, rec: SIMRecord) -> None:
        """Append one edit under its root-cause group and persist."""
        raw_cause = redact((rec.root_cause or "").strip())
        key = _norm_key(raw_cause)
        display = raw_cause or "general"
        group = self.groups.setdefault(key, {"root_cause": display, "edits": []})
        edit = {
            "label": redact(rec.label.strip() or "variant"),
            "rationale": redact(rec.rationale.strip())[:400],
            "predicted_outcome": redact(rec.predicted_outcome.strip())[:300],
            "observed_outcome": redact(rec.observed_outcome.strip())[:400],
            "passed": bool(rec.passed),
            "score": round(float(rec.score), 3),
            "errors": [redact(str(e)) for e in rec.errors[:5]],
            "provenance": {
                "repo": redact(rec.repo.strip()),
                "model": redact(rec.model.strip() or "default"),
                "round": int(rec.round_no),
                "task": redact(rec.task.strip())[:160],
            },
            "ts": float(rec.ts),
        }
        group["edits"].append(edit)
        self._save()

    def render(self, max_chars: int = 4000) -> str:
        """Render the full SIM block (no RAG), bounded to ``max_chars``.

        When the history exceeds ``max_chars``, drops the oldest edits first so
        recent cross-round and cross-model evidence always survives.
        """
        if not self.groups or max_chars <= 0:
            return ""

        header = (
            "Self-Improvement Memory (SIM — optimizer history across rounds/models; "
            "use it to retain, revise, replace, or remove prior harness edits):\n"
        )
        if len(header) >= max_chars:
            return header[:max_chars]

        # Collect all edits with a deterministic chronological key so we can
        # keep the newest edits within the character budget.
        items: list[tuple[tuple[float, int], str, str, str]] = []
        seq = 0
        for key, group in self.groups.items():
            title = str(group.get("root_cause") or key)
            for edit in group.get("edits", []):
                seq += 1
                items.append((
                    (float(edit.get("ts", 0.0)), seq),
                    key,
                    title,
                    _format_edit(edit),
                ))
        if not items:
            return ""

        items.sort(key=lambda x: x[0])

        # Greedily select from newest to oldest while respecting max_chars.
        kept_by_key: dict[str, list[tuple[tuple[float, int], str]]] = {}
        titles: dict[str, str] = {}
        used = len(header)
        for order_key, key, title, line in reversed(items):
            group_hdr_cost = 0 if key in kept_by_key else len(f"### {title}\n")
            line_cost = len(line) + 1
            if used + group_hdr_cost + line_cost > max_chars:
                continue
            kept_by_key.setdefault(key, []).append((order_key, line))
            titles[key] = title
            used += group_hdr_cost + line_cost

        if not kept_by_key:
            # At least fit a truncated copy of the single newest edit.
            _, _, title, line = items[-1]
            return (header + f"### {title}\n" + line)[:max_chars]

        # Render kept groups and edits in chronological order.
        out = [header]
        group_order = sorted(
            kept_by_key.keys(),
            key=lambda k: min(ok for ok, _ in kept_by_key[k]),
        )
        for key in group_order:
            out.append(f"### {titles[key]}\n")
            for _, line in sorted(kept_by_key[key], key=lambda x: x[0]):
                out.append(line + "\n")
        return "".join(out).rstrip()[:max_chars]


def _format_edit(edit: dict) -> str:
    status = "PASS" if edit.get("passed") else "FAIL"
    prov = edit.get("provenance") or {}
    prov_bits = []
    if prov.get("repo"):
        prov_bits.append(f"repo={prov['repo']}")
    if prov.get("model"):
        prov_bits.append(f"model={prov['model']}")
    if prov.get("round"):
        prov_bits.append(f"r{prov['round']}")
    prov_str = f" ({', '.join(prov_bits)})" if prov_bits else ""
    parts = [f"- [{status}] {edit.get('label', 'variant')}{prov_str}"]
    if edit.get("rationale"):
        parts.append(f"rationale: {edit['rationale']}")
    if edit.get("predicted_outcome"):
        parts.append(f"predicted: {edit['predicted_outcome']}")
    if edit.get("observed_outcome"):
        parts.append(f"observed: {edit['observed_outcome']}")
    return " | ".join(parts)
