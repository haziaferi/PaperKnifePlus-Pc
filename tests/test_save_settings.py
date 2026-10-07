"""Save settings whose cost grows with the square of the page count are not used.

Measured with PyMuPDF 1.28.2 (docs/performance-2026-10-08.md): garbage=2 and 3
take over 2 minutes at 800 pages and garbage=4 without clean over 2 minutes at
100, while garbage=1, and garbage=4 with deflate and clean, stay near linear
(about 4 s at 800 pages).  A PyMuPDF call holds the GIL, so a slow save freezes
the window even from a background job.
"""
import ast
from pathlib import Path

from conftest import SRC


def _save_calls():
    for path in sorted((Path(SRC) / "paperknife").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("save", "_save_doc", "tobytes", "write")):
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                if "garbage" in kw:
                    yield f"{path.name}:{node.lineno}", kw


def _const(node):
    return node.value if isinstance(node, ast.Constant) else None


def test_no_save_uses_a_quadratic_garbage_setting():
    bad = []
    for where, kw in _save_calls():
        level = _const(kw["garbage"])
        clean = _const(kw.get("clean", ast.Constant(False)))
        if level == 1 or (level == 4 and clean is True):
            continue
        bad.append((where, level, clean))
    assert bad == [], f"use garbage=1, or garbage=4 with clean=True: {bad}"
