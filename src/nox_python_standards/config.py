# src/nox_python_standards/config.py
from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata, resources
import json
import os
from pathlib import Path
import tempfile
import tomllib
from typing import cast

import tomlkit
from tomlkit.items import Table

from nox_python_standards.repository import (
    StandardsError,
    files,
    in_scope,
    require_regular,
)

SNAPSHOT = Path(".noxala/PYTHON_CONVENTIONS.md")
_RESOURCE_ROOT = resources.files("nox_python_standards").joinpath("resources")


def resource(name: str) -> str:
    return _RESOURCE_ROOT.joinpath(name).read_text(encoding="utf-8")


def release_version() -> str:
    return metadata.version("nox-python-standards")


def policy() -> dict[str, object]:
    return cast(dict[str, object], json.loads(resource("policy.json")))


def ownership() -> dict[str, str]:
    return cast(dict[str, str], json.loads(resource("ownership.json")))


def table(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise StandardsError(f"{name}: expected a TOML table")
    return cast(dict[str, object], value)


def strings(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) for item in cast(list[object], value)
    )


def same(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        a, b = cast(list[object], left), cast(list[object], right)
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    return left == right


def local_valid(value: object, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str) and bool(value)
    if kind == "strings":
        return strings(value)
    if kind == "private-test-rules":
        return isinstance(value, dict) and all(
            key == "test/**/*.py" and same(rules, ["SLF001"])
            for key, rules in cast(dict[str, object], value).items()
        )
    if kind == "test-environments":
        return isinstance(value, list) and all(
            same(environment, {"root": "test", "reportPrivateUsage": "none"})
            for environment in cast(list[object], value)
        )
    raise StandardsError(f"Unknown installed ownership schema: {kind}")


def validate_boundary(tool: dict[str, object]) -> None:
    shared, local = policy(), ownership()
    keys = set(shared) | set(local)

    def visit(value: object, prefix: str) -> None:
        if prefix in shared:
            return  # Missing/wrong shared values are checked separately and repairable.
        if prefix in local:
            if not local_valid(value, local[prefix]):
                raise StandardsError(
                    f"pyproject.toml: tool.{prefix}: invalid consumer value {value!r}; "
                    f"expected {local[prefix]} (see installed ownership.json)"
                )
            return
        if not any(key.startswith(prefix + ".") for key in keys):
            raise StandardsError(
                f"pyproject.toml: tool.{prefix}: unclassified override"
            )
        for key, item in sorted(table(value, f"tool.{prefix}").items()):
            visit(item, f"{prefix}.{key}")

    for name in ("ruff", "pyright"):
        if name in tool:
            visit(tool[name], name)


def shared_diagnostics(tool: dict[str, object]) -> list[str]:
    problems: list[str] = []
    for key, expected in sorted(policy().items()):
        actual: object = tool
        missing = False
        for part in key.split("."):
            current = table(actual, f"tool.{key}")
            if part not in current:
                missing = True
                break
            actual = current[part]
        if missing or not same(actual, expected):
            shown = "<missing>" if missing else repr(actual)
            problems.append(
                f"pyproject.toml: tool.{key}: expected {expected!r}; actual {shown}"
            )
    return problems


@dataclass(frozen=True, slots=True, kw_only=True)
class Configuration:
    root: Path
    text: str
    data: dict[str, object]
    tool: dict[str, object]
    sources: tuple[Path, ...]
    dependency_group: str

    @classmethod
    def read(cls, root: Path) -> Configuration:
        path = require_regular(root, Path("pyproject.toml"))
        text = path.read_text(encoding="utf-8")
        try:
            data = cast(dict[str, object], tomllib.loads(text))
        except tomllib.TOMLDecodeError as exc:
            raise StandardsError(f"pyproject.toml: malformed TOML: {exc}") from exc
        tool = table(data.get("tool", {}), "tool")
        settings = table(
            tool.get("nox-python-standards", {}), "tool.nox-python-standards"
        )
        if set(settings) - {"sources", "dependency-group", "ruff", "docs"}:
            raise StandardsError("Unclassified tool.nox-python-standards setting")
        source_values = settings.get("sources")
        if not strings(source_values) or not source_values:
            raise StandardsError(
                "tool.nox-python-standards.sources: expected nonempty paths"
            )
        sources: list[Path] = []
        for source in cast(list[str], source_values):
            candidate = Path(source)
            if (
                candidate.is_absolute()
                or ".." in candidate.parts
                or not (root / candidate).exists()
                or not (root / candidate).resolve().is_relative_to(root)
                or (root / candidate).is_symlink()
            ):
                raise StandardsError(f"Invalid consumer source path: {source!r}")
            sources.append(candidate)
        group = settings.get("dependency-group")
        if not isinstance(group, str) or not group:
            raise StandardsError(
                "tool.nox-python-standards.dependency-group is required"
            )
        validate_boundary(tool)
        result = cls(
            root=root,
            text=text,
            data=data,
            tool=tool,
            sources=tuple(sources),
            dependency_group=group,
        )
        result.check_discovery()
        return result

    def check_discovery(self) -> None:
        for name in ("ruff.toml", ".ruff.toml", "pyrightconfig.json"):
            if (self.root / name).exists() or (self.root / name).is_symlink():
                raise StandardsError(f"Conflicting native configuration: {name}")
        discovered = files(self.root)
        python_files = [
            path
            for path in discovered
            if path.suffix in {".py", ".pyi"} and in_scope(path, self.sources)
        ]
        # Check ancestors too: an ignored config can still shadow a tracked source.
        directories = {parent for path in python_files for parent in path.parents}
        for directory in sorted(directories - {Path(".")}):
            for name in ("ruff.toml", ".ruff.toml", "pyproject.toml"):
                relative = directory / name
                path = self.root / relative
                if not path.exists() and not path.is_symlink():
                    continue
                require_regular(self.root, relative)
                if name == "pyproject.toml":
                    try:
                        nested = cast(
                            dict[str, object], tomllib.loads(path.read_text())
                        )
                    except tomllib.TOMLDecodeError as exc:
                        raise StandardsError(
                            f"Cannot inspect {relative}: {exc}"
                        ) from exc
                    if "ruff" not in table(nested.get("tool", {}), str(relative)):
                        continue
                raise StandardsError(
                    f"Conflicting nested Ruff configuration: {relative}"
                )

    def check(self) -> None:
        problems = shared_diagnostics(self.tool)
        path = self.root / SNAPSHOT
        if (
            not path.is_file()
            or require_regular(self.root, SNAPSHOT).read_bytes()
            != resource("PYTHON_CONVENTIONS.md").encode()
        ):
            problems.append(
                f"{SNAPSHOT}: expected installed conventions; actual missing/drifted"
            )
        if problems:
            raise StandardsError(
                f"nox-python-standards {release_version()} in {self.root}:\n"
                + "\n".join(problems)
                + "\nReview drift, then explicitly run nox-py-standards sync."
            )

    def sync(self) -> None:
        document = tomlkit.parse(self.text)
        for key, value in policy().items():
            existing: object = self.tool
            for part in key.split("."):
                existing = table(existing, f"tool.{key}").get(part)
                if existing is None:
                    break
            if same(existing, value):
                continue  # Keep existing array layout and comments byte-for-byte.
            current = document
            for part in ["tool", *key.split(".")[:-1]]:
                if part not in current:
                    current[part] = tomlkit.table()
                child = current[part]
                if not isinstance(child, Table):
                    raise StandardsError(f"Cannot repair non-table tool.{key}")
                current = child
            current[key.split(".")[-1]] = value
        rendered = tomlkit.dumps(document)
        proposed = cast(dict[str, object], tomllib.loads(rendered))
        proposed_tool = table(proposed["tool"], "tool")
        validate_boundary(proposed_tool)
        if shared_diagnostics(proposed_tool):
            raise StandardsError("Rendered shared configuration failed validation")
        # Preflight both destinations before writing either file.
        for relative in (Path("pyproject.toml"), SNAPSHOT):
            destination = self.root / relative
            if destination.exists() or destination.is_symlink():
                require_regular(self.root, relative)
            if any(parent.is_symlink() for parent in destination.parents):
                raise StandardsError(f"Refusing symlink path: {relative}")
        atomic_write(self.root / "pyproject.toml", rendered.encode())
        atomic_write(self.root / SNAPSHOT, resource("PYTHON_CONVENTIONS.md").encode())


def atomic_write(path: Path, contents: bytes) -> None:
    if path.is_file() and path.read_bytes() == contents:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
