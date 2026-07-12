"""AST regressions for Task 6 telemetry instrumentation modules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Task 6 production + test modules that must keep imports at module top.
TASK6_MODULES = (
    REPO_ROOT / "core" / "analysis_run.py",
    REPO_ROOT / "benchmark.py",
    REPO_ROOT / "tui_app.py",
    REPO_ROOT / "tests" / "conftest.py",
    REPO_ROOT / "tests" / "telemetry" / "test_analysis_integration.py",
    REPO_ROOT / "tests" / "telemetry" / "test_cli_session.py",
    REPO_ROOT / "tests" / "telemetry" / "test_tui_integration.py",
    Path(__file__),
)


class _InlineImportFinder(ast.NodeVisitor):
    """Find import statements and ``__import__`` calls nested in functions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._in_function = 0
        self.hits: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._in_function += 1
        self.generic_visit(node)
        self._in_function -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._in_function += 1
        self.generic_visit(node)
        self._in_function -= 1

    def visit_Import(self, node: ast.Import) -> None:
        if self._in_function:
            self.hits.append(f"{self.path}:{node.lineno}: inline import")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._in_function:
            self.hits.append(f"{self.path}:{node.lineno}: inline import-from")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_function and isinstance(node.func, ast.Name) and node.func.id == "__import__":
            self.hits.append(f"{self.path}:{node.lineno}: inline __import__")
        self.generic_visit(node)


@pytest.mark.parametrize("path", TASK6_MODULES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_task6_modules_have_no_inline_imports(path: Path) -> None:
    assert path.is_file(), f"missing Task 6 module: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    finder = _InlineImportFinder(path)
    finder.visit(tree)
    assert finder.hits == [], "inline imports / __import__ found:\n" + "\n".join(finder.hits)
