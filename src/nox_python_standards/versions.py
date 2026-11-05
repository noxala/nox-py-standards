# src/nox_python_standards/versions.py
from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import cast

from nox_python_standards.config import Configuration, table
from nox_python_standards.repository import StandardsError

_VERSION = r"([0-9]+\.[0-9]+\.[0-9]+)"


def tool_environment() -> dict[str, str]:
    environment = os.environ.copy()
    # The Python launcher otherwise checks for updates and can download npm/Node.
    environment.update(
        {
            "PYRIGHT_PYTHON_FORCE_VERSION": release_pins()["pyright"],
            "PYRIGHT_PYTHON_USE_BUNDLED_PYRIGHT": "1",
            "PYRIGHT_PYTHON_GLOBAL_NODE": "1",
            "PYRIGHT_PYTHON_NODEJS_WHEEL": "0",
            "PYRIGHT_PYTHON_IGNORE_WARNINGS": "1",
        }
    )
    environment.pop("PYRIGHT_PYTHON_PYLANCE_VERSION", None)
    return environment


def group_values(
    groups: dict[str, object],
    name: str,
    ancestors: frozenset[str] = frozenset(),
) -> list[object]:
    if name in ancestors:
        raise StandardsError(f"Cyclic dependency-group include: {name}")
    values = groups.get(name)
    if not isinstance(values, list):
        raise StandardsError(f"dependency-groups.{name} must be an array")
    flattened: list[object] = []
    for value in cast(list[object], values):
        if isinstance(value, str):
            flattened.append(value)
        else:
            include = table(value, f"dependency-groups.{name}")
            target = include.get("include-group")
            if set(include) != {"include-group"} or not isinstance(target, str):
                raise StandardsError(f"Invalid dependency-group include in {name}")
            flattened.extend(group_values(groups, target, ancestors | {name}))
    return flattened


def release_pins() -> dict[str, str]:
    """Distribution dependencies are the single authority for supported tools."""
    dependencies = metadata.requires("nox-python-standards") or []
    pins: dict[str, str] = {}
    for name in ("ruff", "pyright"):
        matches = [re.fullmatch(rf"{name}=={_VERSION}", dep) for dep in dependencies]
        values = [match.group(1) for match in matches if match is not None]
        if len(values) != 1:
            raise StandardsError(
                f"Installed standards release needs one exact {name} pin"
            )
        pins[name] = values[0]
    return pins


def consumer_pin(dependencies: list[object], name: str) -> str:
    declarations = [
        dependency
        for dependency in dependencies
        if isinstance(dependency, str)
        and re.match(rf"^\s*{name}(?:\s|[<>=!~@;\[]|$)", dependency, re.IGNORECASE)
    ]
    if len(declarations) != 1:
        raise StandardsError(
            f"Development group must contain exactly one {name} dependency"
        )
    match = re.fullmatch(
        rf"\s*{name}\s*==\s*{_VERSION}\s*", declarations[0], re.IGNORECASE
    )
    if match is None:
        raise StandardsError(
            f"Development dependency must use exact '{name}==X.Y.Z' pin"
        )
    return match.group(1)


@dataclass(frozen=True, slots=True, kw_only=True)
class Tools:
    ruff: Path
    pyright: Path

    @classmethod
    def validate(cls, configuration: Configuration) -> Tools:
        if shutil.which("node") is None:
            raise StandardsError(
                "Node.js must be installed on PATH; no downloads are attempted"
            )
        groups = table(configuration.data.get("dependency-groups"), "dependency-groups")
        dependencies = groups.get(configuration.dependency_group)
        if not isinstance(dependencies, list):
            raise StandardsError("Configured dependency group must be an array")
        settings = table(
            configuration.tool["nox-python-standards"], "standards settings"
        )
        approval = table(settings.get("ruff"), "tool.nox-python-standards.ruff")
        authorized = approval.get("authorized_version")
        if set(approval) != {"authorized_version"} or not isinstance(authorized, str):
            raise StandardsError("Ruff authorized_version must use the form 'vX.Y.Z'")
        match = re.fullmatch(rf"v{_VERSION}", authorized)
        if match is None:
            raise StandardsError("Ruff authorized_version must use the form 'vX.Y.Z'")
        supported = release_pins()
        flattened = group_values(groups, configuration.dependency_group)
        executables: dict[str, Path] = {}
        for name in ("ruff", "pyright"):
            declared = consumer_pin(cast(list[object], dependencies), name)
            consumer_pin(
                flattened, name
            )  # Included groups must not hide duplicate pins.
            if declared != supported[name] or (
                name == "ruff" and match.group(1) != declared
            ):
                raise StandardsError(
                    f"{name} version mismatch: release {supported[name]}, "
                    f"dependency {declared}, Ruff approval {authorized}. "
                    "Ruff upgrades require explicit manual review; "
                    "Review tool.nox-python-standards.ruff.authorized_version."
                )
            located = shutil.which(name)
            if located is None:
                raise StandardsError(
                    f"Could not find {name!r} on PATH; install locked dependencies"
                )
            # Keep the launcher path: resolving a venv symlink can change its runtime.
            executable = Path(located).absolute()
            try:
                output = subprocess.check_output(
                    [str(executable), "--version"],
                    cwd=configuration.root,
                    text=True,
                    stderr=subprocess.STDOUT,
                    env=tool_environment(),
                ).strip()
            except (OSError, subprocess.CalledProcessError) as exc:
                raise StandardsError(f"{name} --version failed: {exc}") from exc
            actual = re.fullmatch(
                rf"{name}\s+{_VERSION}(?:[ \t].*)?", output, re.IGNORECASE
            )
            if actual is None or actual.group(1) != supported[name]:
                raise StandardsError(
                    f"{name} executable mismatch: expected {supported[name]}; "
                    f"actual {output!r}"
                )
            executables[name] = executable
        return cls(ruff=executables["ruff"], pyright=executables["pyright"])


def run(root: Path, executable: Path, *arguments: str) -> None:
    result = subprocess.run(
        [str(executable), *arguments],
        cwd=root,
        env=tool_environment(),
        check=False,
    )
    if result.returncode:
        raise StandardsError(
            f"{executable.name} failed with exit code {result.returncode}"
        )


def ruff(configuration: Configuration, tools: Tools, *, fix: bool) -> None:
    paths = [path.as_posix() for path in configuration.sources]
    if fix:
        commands = (
            ["format", *paths],
            ["check", "--select", "PT007", "--fix", "--unsafe-fixes", *paths],
            ["check", "--fix", *paths],
            ["format", *paths],
        )
    else:
        commands = (["format", "--check", *paths], ["check", *paths])
    for command in commands:
        run(configuration.root, tools.ruff, *command)
