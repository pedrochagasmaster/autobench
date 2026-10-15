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

# Reviewed exceptions: (module, enclosing function) pairs allowed to import at
# call time. Each needs a reason, and only ``importlib.import_module`` calls are
# allowed there; ``import`` statements stay forbidden everywhere.
ALLOWED_DEFERRED_IMPORTS = {
    # tui_app imports core.analysis_run (the whole engine, scipy.stats
    # included, about 0.8 s) on first use instead of at module load, and
    # pre-warms it on a thread worker after the first paint. Phase 2 PR 2,
    # docs/research/tui-redesign-phase1/03-performance-architecture.md §1.4.
    ("tui_app.py", "_analysis_run"),
}


class _InlineImportFinder(ast.NodeVisitor):
    """Find import statements and ``__import__`` calls nested in functions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._in_function = 0
        self._functions: list[str] = []
        self.hits: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._in_function += 1
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()
        self._in_function -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._in_function += 1
        self._functions.append(node.name)
        self.generic_visit(node)
        self._functions.pop()
        self._in_function -= 1

    def _deferred_import_allowed(self) -> bool:
        if not self._functions:
            return False
        return (self.path.name, self._functions[-1]) in ALLOWED_DEFERRED_IMPORTS

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
        if (
            self._in_function
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and not self._deferred_import_allowed()
        ):
            self.hits.append(f"{self.path}:{node.lineno}: inline importlib.import_module")
        self.generic_visit(node)


@pytest.mark.parametrize("path", TASK6_MODULES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_task6_modules_have_no_inline_imports(path: Path) -> None:
    assert path.is_file(), f"missing Task 6 module: {path}"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    finder = _InlineImportFinder(path)
    finder.visit(tree)
    assert finder.hits == [], "inline imports / __import__ found:\n" + "\n".join(finder.hits)


def test_deferred_import_allow_list_entries_exist() -> None:
    """Every allow-list entry names a real function that really defers an import."""
    for module, function in ALLOWED_DEFERRED_IMPORTS:
        tree = ast.parse((REPO_ROOT / module).read_text(encoding="utf-8"))
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function
        ]
        assert matches, f"allow-listed function {module}:{function} not found"
        assert any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "import_module"
            for node in matches
            for call in ast.walk(node)
        ), f"{module}:{function} no longer defers an import; drop it from the allow-list"
