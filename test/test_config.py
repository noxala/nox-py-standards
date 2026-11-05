# test/test_config.py
from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from nox_python_standards.cli import main
from nox_python_standards.config import SNAPSHOT, Configuration
from nox_python_standards.repository import StandardsError


def replace(root: Path, before: str, after: str) -> None:
    path = root / "pyproject.toml"
    text = path.read_text()
    assert before in text
    path.write_text(text.replace(before, after))


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }


def test_check_and_sync_are_stable_and_preserve_local_values(consumer: Path) -> None:
    replace(consumer, "line-length = 88", "line-length = 88 # review comment")
    replace(
        consumer, 'select = ["A",', 'select = [\n    "A", # preserve rule explanation\n'
    )
    original = snapshot(consumer)
    Configuration.read(consumer).check()
    assert snapshot(consumer) == original
    Configuration.read(consumer).sync()
    Configuration.read(consumer).sync()
    assert snapshot(consumer) == original


@pytest.mark.parametrize(
    ("before", "after", "key"),
    [
        ("line-length = 88", "line-length = 100", "ruff.line-length"),
        ('quote-style = "double"', 'quote-style = "single"', "ruff.format.quote-style"),
        (
            "docstring-code-format = true",
            "docstring-code-format = 1",
            "docstring-code-format",
        ),
        (
            'typeCheckingMode = "strict"',
            'typeCheckingMode = "basic"',
            "typeCheckingMode",
        ),
        (
            'reportMissingImports = "error"',
            "reportMissingImports = false",
            "reportMissingImports",
        ),
        ("ignore = []\n", "", "ruff.lint.ignore"),
        ('"A", "B",', '"B", "A",', "ruff.lint.select"),
    ],
)
def test_drift_fails_read_only_and_explicit_sync_repairs(
    consumer: Path,
    before: str,
    after: str,
    key: str,
) -> None:
    replace(consumer, before, after)
    original = snapshot(consumer)
    with pytest.raises(StandardsError, match=key):
        Configuration.read(consumer).check()
    assert snapshot(consumer) == original
    Configuration.read(consumer).sync()
    Configuration.read(consumer).check()
    repaired = snapshot(consumer)
    Configuration.read(consumer).sync()
    assert snapshot(consumer) == repaired
    before_data = tomlkit.parse(original["pyproject.toml"].decode()).unwrap()
    after_data = tomlkit.parse(repaired["pyproject.toml"].decode()).unwrap()
    assert before_data["project"] == after_data["project"]
    assert before_data["dependency-groups"] == after_data["dependency-groups"]
    assert (
        before_data["tool"]["nox-python-standards"]
        == after_data["tool"]["nox-python-standards"]
    )
    assert before_data["tool"]["ruff"]["lint"]["isort"]["known-first-party"] == [
        "example"
    ]
    assert after_data["tool"]["ruff"]["lint"]["isort"]["known-first-party"] == [
        "example"
    ]
    assert (
        before_data["tool"]["pyright"]["executionEnvironments"]
        == after_data["tool"]["pyright"]["executionEnvironments"]
    )


@pytest.mark.parametrize(
    "extra",
    [
        "\n[tool.ruff.lint.extra]\nfoo = true\n",
        "\n[tool.ruff.lint.flake8-bugbear]\nextend-immutable-calls = []\n",
        '\n[tool.ruff.lint]\nextend-select = ["ALL"]\n',  # duplicate table is malformed
    ],
)
def test_unclassified_or_malformed_config_never_syncs(
    consumer: Path, extra: str
) -> None:
    with (consumer / "pyproject.toml").open("a") as output:
        output.write(extra)
    original = snapshot(consumer)
    with pytest.raises(StandardsError):
        Configuration.read(consumer).sync()
    assert snapshot(consumer) == original


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "reportMissingTypeStubs = false",
            'reportMissingTypeStubs = false\nreportAny = "none"',
        ),
        ('target-version = "py314"', "target-version = 314"),
        ('"SLF001"', '"ALL"'),
        (
            'reportPrivateUsage = "none"',
            'reportPrivateUsage = "none", reportAny = "none"',
        ),
        ('root = "test"', 'root = "."'),
        ("line-length = 88", 'line-length = 88\nextend = "other.toml"'),
        (
            'typeCheckingMode = "strict"',
            'typeCheckingMode = "strict"\nextends = "base.json"',
        ),
    ],
)
def test_ownership_whitelist_is_strict(consumer: Path, before: str, after: str) -> None:
    replace(consumer, before, after)
    original = snapshot(consumer)
    with pytest.raises(StandardsError):
        Configuration.read(consumer).sync()
    assert snapshot(consumer) == original


@pytest.mark.parametrize("name", ["ruff.toml", ".ruff.toml", "pyrightconfig.json"])
def test_competing_root_configuration(consumer: Path, name: str) -> None:
    (consumer / name).write_text("")
    with pytest.raises(StandardsError, match=name):
        Configuration.read(consumer)


@pytest.mark.parametrize("name", ["ruff.toml", ".ruff.toml", "pyproject.toml"])
def test_nested_configuration_affecting_untracked_source_is_rejected(
    consumer: Path,
    name: str,
) -> None:
    path = consumer / "src" / name
    path.write_text(
        "[tool.ruff]\nline-length = 120\n" if name == "pyproject.toml" else ""
    )
    with pytest.raises(StandardsError, match=name):
        Configuration.read(consumer)
    path.unlink()
    outside = consumer / "fixtures"
    outside.mkdir()
    (outside / name).write_text(path.name)
    Configuration.read(consumer).check()


def test_ignored_vendor_configuration_is_not_traversed(consumer: Path) -> None:
    vendor = consumer / "src/vendor"
    vendor.mkdir()
    (vendor / "example.py").write_text("")
    (vendor / "ruff.toml").write_text("invalid TOML")
    Configuration.read(consumer).check()


def test_ignored_nested_config_still_cannot_shadow_source(consumer: Path) -> None:
    (consumer / ".gitignore").write_text("ruff.toml\n")
    (consumer / "src/ruff.toml").write_text("")
    with pytest.raises(StandardsError, match=r"src/ruff\.toml"):
        Configuration.read(consumer)


def test_missing_shared_table_is_repairable(consumer: Path) -> None:
    document = tomlkit.parse((consumer / "pyproject.toml").read_text())
    del document["tool"]["ruff"]["format"]
    (consumer / "pyproject.toml").write_text(tomlkit.dumps(document))
    Configuration.read(consumer).sync()
    Configuration.read(consumer).check()


def test_conventions_drift_is_checked_and_repaired(consumer: Path) -> None:
    (consumer / SNAPSHOT).write_text("changed guidance")
    with pytest.raises(StandardsError, match="conventions"):
        Configuration.read(consumer).check()
    Configuration.read(consumer).sync()
    Configuration.read(consumer).check()


def test_sync_does_not_approve_ruff_or_require_executables(consumer: Path) -> None:
    replace(
        consumer, 'authorized_version = "v0.15.14"', 'authorized_version = "v0.1.0"'
    )
    replace(consumer, "line-length = 88", "line-length = 90")
    Configuration.read(consumer).sync()
    assert 'authorized_version = "v0.1.0"' in (consumer / "pyproject.toml").read_text()


def test_subdirectory_invocation_uses_git_root(
    consumer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(consumer / "src")
    assert main(["config", "check"]) == 0
    assert main(["--root", str(consumer), "config", "check"]) == 0
    assert main(["--root", str(consumer / "src"), "config", "check"]) == 1


def test_symlink_snapshot_fails_before_writes(consumer: Path, tmp_path: Path) -> None:
    target = tmp_path / "outside.md"
    target.write_text("untouched")
    (consumer / SNAPSHOT).unlink()
    (consumer / SNAPSHOT).symlink_to(target)
    replace(consumer, "line-length = 88", "line-length = 99")
    original = (consumer / "pyproject.toml").read_bytes()
    with pytest.raises(StandardsError, match="symlink"):
        Configuration.read(consumer).sync()
    assert (consumer / "pyproject.toml").read_bytes() == original
    assert target.read_text() == "untouched"
