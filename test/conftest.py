# test/conftest.py
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

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


@pytest.fixture
def version_tools(consumer: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = consumer / "bin"
    directory.mkdir()
    log = consumer / "versions.log"
    for name, version in (("ruff", "0.15.14"), ("pyright", "1.1.411")):
        executable = directory / name
        executable.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            f"with open({str(log)!r}, 'a') as output:\n"
            f"    output.write({name!r} + ' ' + ' '.join(sys.argv[1:]) + '\\n')\n"
            "if sys.argv[1:] != ['--version']:\n    sys.exit(9)\n"
            f"version = os.environ.get('FAKE_{name.upper()}_VERSION', '{version}')\n"
            f"print('{name} ' + version)\n"
        )
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(consumer)
    return log
