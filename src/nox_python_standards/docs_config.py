# src/nox_python_standards/docs_config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import cast

from nox_python_standards.repository import StandardsError, require_regular

_PREFIX = "tool.nox-python-standards.docs"


def _table(value: object, label: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise StandardsError(f"{label}: expected a TOML table")
    result = cast(dict[str, object], value)
    if unknown := result.keys() - keys:
        raise StandardsError(f"{label}: unknown settings: {', '.join(sorted(unknown))}")
    return result


def _strings(value: object, label: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise StandardsError(f"{label}: expected a list of nonempty strings")
    values = cast(list[object], value)
    if (nonempty and not values) or any(
        not isinstance(item, str) or not item.strip() for item in values
    ):
        raise StandardsError(f"{label}: expected a list of nonempty strings")
    return tuple(cast(list[str], values))


def _path(value: object, label: str, *, glob: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StandardsError(f"{label}: expected a repository-relative path")
    path = Path(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or (not glob and any(character in value for character in "*?[]"))
    ):
        raise StandardsError(f"{label}: invalid repository-relative path: {value!r}")
    return value


def _paths(
    data: dict[str, object], key: str, label: str, *, required: bool = False
) -> tuple[str, ...]:
    values = _strings(data.get(key, []), f"{label}.{key}", nonempty=required)
    return tuple(_path(value, f"{label}.{key}", glob=True) for value in values)


@dataclass(frozen=True, slots=True, kw_only=True)
class Selection:
    include: tuple[str, ...]
    exclude: tuple[str, ...]

    @classmethod
    def create(cls, data: dict[str, object], label: str) -> Selection:
        return cls(
            include=_paths(data, "include", label, required=True),
            exclude=_paths(data, "exclude", label),
        )

    def matches(self, path: Path) -> bool:
        return any(path.full_match(pattern) for pattern in self.include) and not any(
            path.full_match(pattern) for pattern in self.exclude
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Budget:
    selection: Selection
    max_bytes: int | None
    max_words: int | None

    @classmethod
    def create(cls, value: object, label: str) -> Budget:
        data = _table(value, label, {"include", "exclude", "max-bytes", "max-words"})
        limits: dict[str, int | None] = {}
        for key in ("max-bytes", "max-words"):
            limit = data.get(key)
            if limit is not None and (type(limit) is not int or limit <= 0):
                raise StandardsError(f"{label}.{key}: expected a positive integer")
            limits[key] = limit
        if all(limit is None for limit in limits.values()):
            raise StandardsError(f"{label}: require max-bytes or max-words")
        return cls(
            selection=Selection.create(data, label),
            max_bytes=limits["max-bytes"],
            max_words=limits["max-words"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Catalog:
    path: str
    selection: Selection

    @classmethod
    def create(cls, value: object, label: str) -> Catalog:
        data = _table(value, label, {"path", "include", "exclude"})
        return cls(
            path=_path(data.get("path"), f"{label}.path"),
            selection=Selection.create(data, label),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Metadata:
    selection: Selection
    fields: tuple[str, ...]
    path_fields: tuple[str, ...]
    path_sections: tuple[str, ...]

    @classmethod
    def create(cls, value: object, label: str) -> Metadata:
        data = _table(
            value,
            label,
            {"include", "exclude", "fields", "path-fields", "path-sections"},
        )
        fields = _strings(data.get("fields", []), f"{label}.fields", nonempty=False)
        path_fields = _strings(
            data.get("path-fields", []), f"{label}.path-fields", nonempty=False
        )
        sections = _strings(
            data.get("path-sections", []), f"{label}.path-sections", nonempty=False
        )
        if not fields and not path_fields and not sections:
            raise StandardsError(
                f"{label}: require fields, path-fields or path-sections"
            )
        return cls(
            selection=Selection.create(data, label),
            fields=fields,
            path_fields=path_fields,
            path_sections=sections,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Router:
    path: str
    section: str
    columns: tuple[str, ...]

    @classmethod
    def create(cls, value: object, label: str) -> Router:
        data = _table(value, label, {"path", "section", "columns"})
        section = data.get("section")
        if not isinstance(section, str) or not section.strip():
            raise StandardsError(f"{label}.section: expected a nonempty heading")
        return cls(
            path=_path(data.get("path"), f"{label}.path"),
            section=section,
            columns=_strings(data.get("columns"), f"{label}.columns"),
        )


def _rules(data: dict[str, object], key: str) -> list[object]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise StandardsError(f"{_PREFIX}.{key}: expected an array of tables")
    return cast(list[object], value)


@dataclass(frozen=True, slots=True, kw_only=True)
class DocsConfiguration:
    documents: Selection
    required: tuple[str, ...]
    budgets: tuple[Budget, ...]
    catalogs: tuple[Catalog, ...]
    metadata: tuple[Metadata, ...]
    routers: tuple[Router, ...]

    @classmethod
    def read(cls, root: Path) -> DocsConfiguration:
        text = require_regular(root, Path("pyproject.toml")).read_text(encoding="utf-8")
        try:
            value: object = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise StandardsError(f"pyproject.toml: malformed TOML: {exc}") from exc
        for key in ("tool", "nox-python-standards", "docs"):
            if not isinstance(value, dict):
                raise StandardsError(f"{_PREFIX}: expected a TOML table")
            value = cast(dict[str, object], value).get(key)
        return cls.create(value)

    @classmethod
    def create(cls, value: object) -> DocsConfiguration:
        data = _table(
            value,
            _PREFIX,
            {
                "include",
                "exclude",
                "required",
                "budgets",
                "catalogs",
                "metadata",
                "routers",
            },
        )
        return cls(
            documents=Selection.create(data, _PREFIX),
            required=tuple(
                _path(path, f"{_PREFIX}.required")
                for path in _strings(
                    data.get("required", []), f"{_PREFIX}.required", nonempty=False
                )
            ),
            budgets=tuple(
                Budget.create(rule, f"{_PREFIX}.budgets[{index}]")
                for index, rule in enumerate(_rules(data, "budgets"))
            ),
            catalogs=tuple(
                Catalog.create(rule, f"{_PREFIX}.catalogs[{index}]")
                for index, rule in enumerate(_rules(data, "catalogs"))
            ),
            metadata=tuple(
                Metadata.create(rule, f"{_PREFIX}.metadata[{index}]")
                for index, rule in enumerate(_rules(data, "metadata"))
            ),
            routers=tuple(
                Router.create(rule, f"{_PREFIX}.routers[{index}]")
                for index, rule in enumerate(_rules(data, "routers"))
            ),
        )
