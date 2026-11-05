# src/nox_python_standards/hooks.py
from __future__ import annotations

import os
from pathlib import Path

from nox_python_standards.repository import StandardsError, git


def check_hook(root: Path) -> None:
    value = git(root, "rev-parse", "--git-path", "hooks/pre-push").decode().strip()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not path.is_file() or not os.access(path, os.X_OK):
        raise StandardsError(
            "Executable Git pre-push hook missing. "
            "Run: pre-commit install --hook-type pre-push"
        )
    contents = path.read_text()
    if "--hook-type=pre-push" not in contents or "pre_commit" not in contents:
        raise StandardsError(
            f"{path}: expected pre-commit-managed pre-push hook. "
            "Run: pre-commit install --hook-type pre-push"
        )
