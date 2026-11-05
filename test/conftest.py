# test/conftest.py
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest
import tomlkit

from nox_python_standards.config import Configuration, policy


@pytest.fixture
def consumer(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src/example.py").write_text(
        "# src/example.py\nfrom __future__ import annotations\n\nVALUE = 1\n"
    )
    document = tomlkit.document()
    document["project"] = {"name": "example", "version": "0.1.0"}
    document["dependency-groups"] = {"dev": ["ruff==0.15.14", "pyright==1.1.411"]}
    document["tool"] = {
        "nox-python-standards": {
            "sources": ["src"],
            "dependency-group": "dev",
            "ruff": {"authorized_version": "v0.15.14"},
        },
        "ruff": {
            "target-version": "py314",
            "extend-exclude": [],
            "lint": {
                "isort": {"known-first-party": ["example"], "known-third-party": []},
                "per-file-ignores": {"test/**/*.py": ["SLF001"]},
            },
        },
        "pyright": {
            "include": ["src"],
            "extraPaths": ["src"],
            "pythonVersion": "3.14",
            "executionEnvironments": [{"root": "test", "reportPrivateUsage": "none"}],
        },
    }
    for key, value in policy().items():
        current = document["tool"]
        for part in key.split(".")[:-1]:
            if part not in current:
                current[part] = tomlkit.table()
            current = current[part]
        current[key.split(".")[-1]] = value
    (tmp_path / "pyproject.toml").write_text(tomlkit.dumps(document))
    Configuration.read(tmp_path).sync()
    return tmp_path
