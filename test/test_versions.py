# test/test_versions.py
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from test_config import replace

from nox_python_standards.cli import main
from nox_python_standards.config import Configuration, policy
from nox_python_standards.repository import StandardsError
from nox_python_standards.versions import (
    consumer_pin,
    group_values,
    release_pins,
    tool_environment,
)


def test_check_only_probes_versions_and_never_repairs_source(
    consumer: Path, version_tools: Path
) -> None:
    source = consumer / "src/example.py"
    original = b"x=undefined_name\n"
    source.write_bytes(original)
    config = (consumer / "pyproject.toml").read_bytes()
    assert main(["check"]) == 0
    assert version_tools.read_text().splitlines() == [
        "ruff --version",
        "pyright --version",
    ]
    assert source.read_bytes() == original
    assert (consumer / "pyproject.toml").read_bytes() == config


@pytest.mark.parametrize(
    "change", ["approval", "dependency", "ruff", "pyright", "config"]
)
def test_check_rejects_drift_and_wrong_versions(
    consumer: Path,
    version_tools: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
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
    before = (consumer / "pyproject.toml").read_bytes()
    assert main(["check"]) == 1
    assert (consumer / "pyproject.toml").read_bytes() == before
    if change in {"approval", "dependency", "config"}:
        assert not version_tools.exists()


def test_missing_or_broken_tool_is_reported(
    consumer: Path,
    version_tools: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    git = shutil.which("git")
    assert git is not None
    (consumer / "bin/git").symlink_to(git)
    monkeypatch.setenv("PATH", str(consumer / "bin"))
    (consumer / "bin/ruff").unlink()
    assert main(["--root", str(consumer), "check"]) == 1
    assert "Could not find 'ruff'" in capsys.readouterr().err
    executable = consumer / "bin/ruff"
    executable.write_text(f"#!{sys.executable}\nraise SystemExit(7)\n")
    executable.chmod(0o755)
    assert main(["--root", str(consumer), "check"]) == 1
    assert "ruff --version failed" in capsys.readouterr().err


def test_sync_preserves_pins_and_approval_without_tool_probes(
    consumer: Path, version_tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace(consumer, '"ruff==0.15.14"', '"ruff==0.1.0"')
    replace(
        consumer, 'authorized_version = "v0.15.14"', 'authorized_version = "v0.1.0"'
    )
    replace(consumer, "line-length = 88", "line-length = 99")
    # Keep Git available for repository discovery, but remove both tool executables.
    for name in ("ruff", "pyright"):
        (consumer / "bin" / name).unlink()
    assert main(["sync"]) == 0
    text = (consumer / "pyproject.toml").read_text()
    assert '"ruff==0.1.0"' in text
    assert 'authorized_version = "v0.1.0"' in text
    Configuration.read(consumer).check()
    assert not version_tools.exists()
    assert main(["check"]) == 1


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


def test_version_probe_prevents_pyright_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYRIGHT_PYTHON_FORCE_VERSION", "latest")
    monkeypatch.setenv("PYRIGHT_PYTHON_PYLANCE_VERSION", "latest")
    environment = tool_environment()
    assert environment["PYRIGHT_PYTHON_FORCE_VERSION"] == "1.1.411"
    assert environment["PYRIGHT_PYTHON_USE_BUNDLED_PYRIGHT"] == "1"
    assert environment["PYRIGHT_PYTHON_GLOBAL_NODE"] == "1"
    assert environment["PYRIGHT_PYTHON_NODEJS_WHEEL"] == "0"
    assert "PYRIGHT_PYTHON_PYLANCE_VERSION" not in environment


def test_ruff_runtime_requirement_matches_version_policy() -> None:
    assert policy()["ruff.required-version"] == f"=={release_pins()['ruff']}"


@pytest.mark.parametrize(
    "arguments",
    [
        ["config", "check"],
        ["config", "sync"],
        ["ruff", "fix"],
        ["headers", "fix"],
        ["hooks", "check"],
        ["versions"],
        ["fix"],
        ["typecheck"],
    ],
)
def test_removed_commands_are_rejected(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2


def test_module_entry_uses_consumer_root(consumer: Path, version_tools: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "nox_python_standards", "check"],
        cwd=consumer / "src",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_subdirectory_version_probe_preserves_relative_path_lookup(
    consumer: Path, version_tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(consumer / "src")
    monkeypatch.setenv("PATH", "../bin" + os.pathsep + os.environ["PATH"])
    assert main(["check"]) == 0


def native(root: Path, tool: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [tool, *arguments],
        cwd=root,
        env=tool_environment(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_native_tools_read_checked_local_configuration(consumer: Path) -> None:
    lint = native(consumer, "ruff", "check", "--show-settings", "src/example.py")
    assert lint.returncode == 0, lint.stderr
    assert str(consumer / "pyproject.toml") in lint.stdout
    assert "line_length = 88" in lint.stdout
    (consumer / "src/example.py").write_text("x: int = 'bad'\n")
    typed = native(consumer, "pyright", "--outputjson")
    assert typed.returncode == 1, typed.stderr
    assert '"filesAnalyzed": 1' in typed.stdout
    assert '"rule": "reportAssignmentType"' in typed.stdout


def test_native_fix_approves_pt007_only_and_remains_idempotent(consumer: Path) -> None:
    source = consumer / "src/test_values.py"
    source.write_text(
        "from __future__ import annotations\nimport pytest\n\n"
        '@pytest.mark.parametrize("value", (1, 2))\n'
        "def test_value(value: int) -> None:\n    assert value > 0\n"
    )
    assert native(consumer, "ruff", "check", "--fix", "src").returncode == 0
    repaired = source.read_bytes()
    assert b'parametrize("value", [1, 2])' in repaired
    assert native(consumer, "ruff", "check", "--fix", "src").returncode == 0
    assert source.read_bytes() == repaired
    # RUF015's next(iter(...)) conversion changes empty-input behavior: keep it unsafe.
    source.write_text(
        "from __future__ import annotations\n\n"
        "def first(xs: list[int]) -> int:\n    return list(xs)[0]\n"
    )
    original = source.read_bytes()
    unsafe = native(consumer, "ruff", "check", "--select", "RUF015", "--fix", "src")
    assert unsafe.returncode == 1
    assert "RUF015" in unsafe.stdout
    assert source.read_bytes() == original
    source.write_text("from __future__ import annotations\n\nx = missing_name\n")
    assert native(consumer, "ruff", "check", "--fix", "src").returncode == 1


def test_native_ruff_version_requirement_blocks_edits(consumer: Path) -> None:
    replace(consumer, 'required-version = "==0.15.14"', 'required-version = "==0.1.0"')
    source = consumer / "src/example.py"
    original = b"x=undefined_name\n"
    source.write_bytes(original)
    for arguments in (("format", "src"), ("check", "--fix", "src")):
        result = native(consumer, "ruff", *arguments)
        assert result.returncode != 0
        assert "Required version" in result.stderr
        assert source.read_bytes() == original
