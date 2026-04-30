"""Guards against dead public backend seam exports (tests-only types)."""

from __future__ import annotations

import ast
import re
from pathlib import Path


def _parse_backend_init_exports() -> list[str]:
    init_path = Path("src/backends/__init__.py")
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, ast.List):
                        return [
                            elt.value
                            for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        ]
    raise AssertionError("Could not parse __all__ from src/backends/__init__.py")


def test_backend_package_exports_are_used_outside_init() -> None:
    """Each public export must appear in some production module besides src/backends/__init__.py."""
    exports = _parse_backend_init_exports()
    assert exports, "Failed to extract exports from src/backends/__all__; test is vacuous."
    init_only = Path("src/backends/__init__.py")

    prod_files = [
        p
        for p in Path("src").rglob("*.py")
        if p.is_file()
        and "__pycache__" not in p.parts
        and not p.name.startswith("test_")
        and p != init_only
    ]

    missing: list[str] = []
    for name in exports:
        pattern = re.compile(rf"\b{re.escape(name)}\b")
        found = any(pattern.search(p.read_text(encoding="utf-8")) for p in prod_files)
        if not found:
            missing.append(name)

    assert not missing, (
        "Public backend exports with no production reference outside __init__.py: "
        + ", ".join(missing)
    )
