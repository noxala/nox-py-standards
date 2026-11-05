# test/test_tools.py
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from test_config import replace

from nox_python_standards.cli import main
from nox_python_standards.config import Configuration
from nox_python_standards.repository import StandardsError
from nox_python_standards.versions import (
    Tools,
    consumer_pin,
    group_values,
    tool_environment,
)


def fake_tools(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = root / "bin"
    directory.mkdir()
    log = root / "commands.jsonl"
    for name, version in (("ruff", "0.15.14"), ("pyright", "1.1.411")):
        executable = directory / name
        variable = f"FAKE_{name.upper()}_VERSION"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "if sys.argv[1:] == ['--version']:\n"
            f"    version = os.environ.get('{variable}', '{version}')\n"
            f"    print('{name} ' + version)\n"
            "else:\n"
            f"    with open({str(log)!r}, 'a') as output:\n"
            f"        output.write(json.dumps(['{name}', *sys.argv[1:]]) + '\\n')\n"
            "    if '--fix' in sys.argv and os.environ.get('FAKE_FAIL'):\n"
            "        sys.exit(7)\n"
        )
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ["PATH"])
    monkeypatch.chdir(root)
    return log


def test_ruff_repair_sequence_and_typecheck_options(
    consumer: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = fake_tools(consumer, monkeypatch)
    assert main(["ruff", "fix"]) == 0
    assert [json.loads(line) for line in log.read_text().splitlines()] == [
        ["ruff", "format", "src"],
        ["ruff", "check", "--select", "PT007", "--fix", "--unsafe-fixes", "src"],
        ["ruff", "check", "--fix", "src"],
        ["ruff", "format", "src"],
    ]
    log.unlink()
    assert main(["typecheck", "--threads", "4", "--watch"]) == 0
    assert json.loads(log.read_text()) == ["pyright", "--threads", "4", "--watch"]


def test_failure_stops_later_steps(
    consumer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = fake_tools(consumer, monkeypatch)
    monkeypatch.setenv("FAKE_FAIL", "1")
    assert main(["ruff", "fix"]) == 1
    assert len(log.read_text().splitlines()) == 2


@pytest.mark.parametrize(
    "change", ["approval", "dependency", "ruff", "pyright", "config"]
)
def test_wrong_tools_or_drift_block_source_mutation(
    consumer: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    log = fake_tools(consumer, monkeypatch)
    source = consumer / "src/example.py"
    original = b"VALUE=1\n"
    source.write_bytes(original)
    if change == "approval":
        replace(
            consumer, 'authorized_version = "v0.15.14"', 'authorized_version = "v0.1.0"'
        )
    elif change == "dependency":
        replace(consumer, '"ruff==0.15.14"', '"ruff>=0.15.14"')
    elif change == "config":
        replace(consumer, "line-length = 88", "line-length = 99")
    else:
        monkeypatch.setenv(f"FAKE_{change.upper()}_VERSION", "1.2.3")
    assert main(["fix"]) == 1
    assert source.read_bytes() == original
    assert not log.exists()


@pytest.mark.parametrize(
    "dependencies",
    [
        [],
        ["ruff>=0.15.14"],
        ["ruff==0.15.14", "ruff==0.15.14"],
        ["ruff @ https://example.test/tool.whl"],
        ["ruff[extra]==0.15.14"],
        ["ruff==0.15.14; python_version > '3'"],
    ],
)
def test_invalid_consumer_pins_are_rejected(dependencies: list[object]) -> None:
    with pytest.raises(StandardsError):
        consumer_pin(dependencies, "ruff")


def test_included_groups_cannot_hide_tool_duplicates() -> None:
    groups: dict[str, object] = {
        "dev": ["ruff==0.15.14", {"include-group": "other"}],
        "other": ["ruff==0.15.14"],
    }
    with pytest.raises(StandardsError, match="exactly one"):
        consumer_pin(group_values(groups, "dev"), "ruff")
    with pytest.raises(StandardsError, match="Cyclic"):
        group_values({"dev": [{"include-group": "dev"}]}, "dev")


def test_pyright_environment_prevents_unpinned_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYRIGHT_PYTHON_FORCE_VERSION", "latest")
    monkeypatch.setenv("PYRIGHT_PYTHON_PYLANCE_VERSION", "latest")
    environment = tool_environment()
    assert environment["PYRIGHT_PYTHON_FORCE_VERSION"] == "1.1.411"
    assert environment["PYRIGHT_PYTHON_IGNORE_WARNINGS"] == "1"
    assert environment["PYRIGHT_PYTHON_GLOBAL_NODE"] == "1"
    assert "PYRIGHT_PYTHON_PYLANCE_VERSION" not in environment


def test_module_entry_and_native_tools_use_local_configuration(consumer: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nox_python_standards", "config", "check"],
        cwd=consumer / "src",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    tools = Tools.validate(Configuration.read(consumer))
    lint = subprocess.run(
        [str(tools.ruff), "check", "--show-settings", "src/example.py"],
        cwd=consumer,
        text=True,
        capture_output=True,
        check=False,
    )
    assert lint.returncode == 0
    assert str(consumer / "pyproject.toml") in lint.stdout
    assert "line_length = 88" in lint.stdout
    source = consumer / "src/example.py"
    source.write_text(
        "# src/example.py\nfrom __future__ import annotations\n\nx: int = 'bad'\n"
    )
    typed = subprocess.run(
        [str(tools.pyright), "--outputjson"],
        cwd=consumer,
        text=True,
        capture_output=True,
        check=False,
    )
    assert typed.returncode == 1
    assert '"filesAnalyzed": 1' in typed.stdout
    assert '"rule": "reportAssignmentType"' in typed.stdout
    assert main(["--root", str(consumer), "typecheck"]) == 1


def test_native_pt007_repair_and_unfixable_error(consumer: Path) -> None:
    tools = Tools.validate(Configuration.read(consumer))
    source = consumer / "src/test_values.py"
    original = (
        "from __future__ import annotations\nimport pytest\n\n"
        '@pytest.mark.parametrize("value", (1, 2))\n'
        "def test_value(value: int) -> None:\n    assert value > 0\n"
    )
    source.write_text(original)
    safe = subprocess.run(
        [str(tools.ruff), "check", "--select", "PT007", "--fix", "src"],
        cwd=consumer,
        capture_output=True,
        check=False,
    )
    assert safe.returncode == 1
    assert source.read_text() == original
    assert main(["--root", str(consumer), "ruff", "fix"]) == 0
    repaired = source.read_bytes()
    assert b'parametrize("value", [1, 2])' in repaired
    assert main(["--root", str(consumer), "ruff", "fix"]) == 0
    assert source.read_bytes() == repaired
    source.write_text("from __future__ import annotations\n\nx = missing_name\n")
    assert main(["--root", str(consumer), "ruff", "fix"]) == 1
