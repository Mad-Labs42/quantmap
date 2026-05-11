from __future__ import annotations

import tomllib
from pathlib import Path


def test_pyproject_packages_include_src_subpackages() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    declared_packages = set(pyproject["tool"]["setuptools"]["packages"])

    import_packages = {
        ".".join(path.parent.parts) for path in Path("src").rglob("__init__.py")
    }
    missing_packages = sorted(import_packages - declared_packages)

    assert not missing_packages
