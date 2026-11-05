# src/nox_python_standards/versions.py
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import cast

from nox_python_standards.config import Configuration, resource, table
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
    """Supported tools are policy data, not package runtime dependencies."""
    return cast(dict[str, str], json.loads(resource("versions.json")))


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


def check_versions(configuration: Configuration) -> None:
    groups = table(configuration.data.get("dependency-groups"), "dependency-groups")
    dependencies = group_values(groups, configuration.dependency_group)
    settings = table(configuration.tool["nox-python-standards"], "standards settings")
    approval = table(settings.get("ruff"), "tool.nox-python-standards.ruff")
    authorized = approval.get("authorized_version")
    if (
        set(approval) != {"authorized_version"}
        or not isinstance(authorized, str)
        or re.fullmatch(rf"v{_VERSION}", authorized) is None
    ):
        raise StandardsError("Ruff authorized_version must use the form 'vX.Y.Z'")
    supported = release_pins()
    for name, expected in supported.items():
        declared = consumer_pin(dependencies, name)
        if declared != expected or (name == "ruff" and authorized != f"v{expected}"):
            raise StandardsError(
                f"{name} version mismatch: standards {expected}, "
                f"dependency {declared}, Ruff approval {authorized}. "
                "Update dependencies deliberately; "
                "Ruff approval requires manual review."
            )
    for name, expected in supported.items():
        located = shutil.which(name)
        if located is None:
            raise StandardsError(
                f"Could not find {name!r} on PATH; "
                "install locked development dependencies"
            )
        try:
            # Only probe versions. Never format, lint, typecheck or install tools.
            output = subprocess.check_output(
                [located, "--version"],
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
        if actual is None or actual.group(1) != expected:
            raise StandardsError(
                f"{name} executable mismatch: expected {expected}; actual {output!r}"
            )
