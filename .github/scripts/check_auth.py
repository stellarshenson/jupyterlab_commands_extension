"""Fail when a request handler in the package lacks authentication.

The Makefile's ``test`` target runs this before a release. A handler method
that Tornado can route (get, post, put, delete, patch, head, options) must
carry ``@tornado.web.authenticated``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDLERS = ROOT / "jupyterlab_commands_extension" / "handlers.py"
ROUTES = {"get", "post", "put", "delete", "patch", "head", "options"}


def _is_authenticated(decorator: ast.expr) -> bool:
    for node in ast.walk(decorator):
        if isinstance(node, ast.Attribute) and node.attr == "authenticated":
            return True
        if isinstance(node, ast.Name) and node.id == "authenticated":
            return True
    return False


def main() -> int:
    tree = ast.parse(HANDLERS.read_text(encoding="utf-8"), filename=str(HANDLERS))
    missing: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name not in ROUTES:
                continue
            if not any(_is_authenticated(d) for d in item.decorator_list):
                missing.append(f"{node.name}.{item.name}")
    if missing:
        print(
            "handlers missing @tornado.web.authenticated: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    print("every request handler requires authentication")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
