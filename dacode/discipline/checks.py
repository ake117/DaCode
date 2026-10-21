"""AST-based test-quality checks — pstack principle #4.

The guiding question (from pstack): *would this test still pass if every
imported function returned ``None``?*  If yes, the assertion is weak and the
test proves nothing.  These checks find the mechanical cases of that pattern in
Python test files without running anything.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Finding", "check_python_test", "check_test_source"]

# unittest-style assertion methods that are weak on their own.
_WEAK_METHODS = {
    "asserttrue": "assertTrue() only checks truthiness — assert the literal value",
    "assertfalse": "assertFalse() only checks falsiness — assert the literal value",
    "assertisnotnone": "assertIsNotNone() passes when every call returns None",
    "assertisnone": "assertIsNone() — is that really the behaviour under test?",
    "assertisinstance": "assertIsInstance() pins a type, not the behaviour",
    "assertgreater": "assertGreater()/assertLess() with 0 is a weak 'is non-empty' check",
    "assertless": "assertGreater()/assertLess() with 0 is a weak 'is non-empty' check",
    "assert": "bare assert() helper — prefer explicit assertion",
}


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str  # "error" | "warning" | "info"
    message: str
    location: str

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"[{self.severity}] {self.check}: {self.message} ({self.location})"


def _is_none(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_zero(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0


def _is_empty_len_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
        and len(node.args) == 1
    )


class _TestVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[Finding] = []
        self.test_functions: list[str] = []

    def _loc(self, node: ast.AST) -> str:
        return f"{self.filename}:{getattr(node, 'lineno', '?')}"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_test(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_test(node)

    def _visit_test(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if not node.name.startswith("test"):
            self.generic_visit(node)
            return
        self.test_functions.append(node.name)
        asserts = [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Assert)
            or self._is_assert_call(child)
            or self._is_raises_context(child)
        ]
        if not asserts:
            self.findings.append(
                Finding(
                    check="assertion_free",
                    severity="error",
                    message=f"test '{node.name}' has no assertion — it cannot fail",
                    location=self._loc(node),
                )
            )
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                self._check_assert(child)
            elif self._is_assert_call(child):
                self._check_method_call(child)
        # do not descend into nested test functions twice
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.visit(child)

    @staticmethod
    def _is_assert_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr.lower().startswith("assert")
        if isinstance(func, ast.Name):
            return func.id.lower() in {"assert_that", "assertthat", "assertthat"}
        return False

    @staticmethod
    def _is_raises_context(node: ast.AST) -> bool:
        """``with pytest.raises(...):`` asserts behaviour — an exception must fire."""
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            return False
        return any(
            isinstance(item.context_expr, ast.Call)
            and (
                (isinstance(item.context_expr.func, ast.Name) and item.context_expr.func.id == "raises")
                or (isinstance(item.context_expr.func, ast.Attribute) and item.context_expr.func.attr == "raises")
            )
            for item in node.items
        )

    def _check_assert(self, node: ast.Assert) -> None:
        test = node.test
        # assert True / assert False / assert 0  → a literal, always same outcome
        if isinstance(test, ast.Constant):
            self.findings.append(
                Finding(
                    check="constant_assertion",
                    severity="error",
                    message=f"'assert {test.value!r}' is a constant — the test can never fail on behaviour",
                    location=self._loc(node),
                )
            )
        # assert x            → truthiness
        elif isinstance(test, ast.Name):
            self._warn(node, "weak_truthiness", f"'assert {test.id}' only checks truthiness")
        # assert x is not None / is None
        elif isinstance(test, ast.Compare) and any(isinstance(op, (ast.Is, ast.IsNot)) for op in test.ops):
            if any(_is_none(c) for c in test.comparators):
                self._warn(node, "none_check", "assert against None proves nothing about behaviour")
            self._check_tautology(node)
        # assert len(x) > 0  etc.
        elif isinstance(test, ast.Compare):
            self._check_tautology(node)
            left = test.left
            comp = test.comparators[0] if test.comparators else None
            if _is_empty_len_call(left) and isinstance(test.ops[0], (ast.Gt, ast.GtE, ast.NotEq)) and _is_zero(comp):
                self._warn(node, "weak_length", "assert len(x) > 0 only proves non-emptiness")

    def _check_method_call(self, node: ast.Call) -> None:
        attr = node.func.attr.lower()  # type: ignore[union-attr]
        if attr in _WEAK_METHODS:
            self._warn(node, "weak_method", _WEAK_METHODS[attr])

    def _check_tautology(self, node: ast.Assert) -> None:
        test = node.test
        if isinstance(test, ast.Compare) and len(test.comparators) == 1:
            left, right = test.left, test.comparators[0]
            if ast.dump(left) == ast.dump(right):
                self.findings.append(
                    Finding(
                        check="tautology",
                        severity="error",
                        message="self-referential assertion — both sides are the same expression",
                        location=self._loc(node),
                    )
                )

    def _warn(self, node: ast.AST, check: str, message: str) -> None:
        self.findings.append(
            Finding(check=check, severity="warning", message=message, location=self._loc(node))
        )


def check_test_source(source: str, filename: str = "<test>") -> list[Finding]:
    """Check a single test file's *source text* and return findings."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [
            Finding(
                check="syntax_error",
                severity="error",
                message=f"cannot parse: {exc.msg}",
                location=f"{filename}:{exc.lineno}",
            )
        ]
    visitor = _TestVisitor(filename)
    visitor.visit(tree)
    return visitor.findings


def check_python_test(path: str | Path) -> list[Finding]:
    """Check a test *file* on disk and return findings."""
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            Finding(
                check="unreadable",
                severity="error",
                message=f"cannot read test file: {exc}",
                location=str(path),
            )
        ]
    return check_test_source(source, filename=str(path))
