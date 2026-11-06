# src/nox_python_standards/docs_config.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import cast
from urllib.parse import unquote

from nox_python_standards.repository import StandardsError, require_regular

_PREFIX = "tool.nox-python-standards.docs"


def _table(value: object, label: str, keys: set[str] | None) -> dict[str, object]:
    if not isinstance(value, dict):
        raise StandardsError(f"{label}: expected a TOML table")
    result = cast(dict[str, object], value)
    if keys is not None:
        if unknown := result.keys() - keys:
            raise StandardsError(
                f"{label}: unknown settings: {', '.join(sorted(unknown))}"
            )
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


def _accepted_values(
    data: dict[str, object], label: str, *, keys: set[str] | None = None
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if "accepted-values" not in data:
        return ()
    values = _table(data["accepted-values"], f"{label}.accepted-values", keys)
    if not values or any(not field.strip() for field in values):
        raise StandardsError(f"{label}.accepted-values: require nonempty field names")
    return tuple(
        (field, _strings(choices, f"{label}.accepted-values.{field}"))
        for field, choices in values.items()
    )


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
        return any(path.full_match(pattern) for pattern in self.include) and not (
            self.is_excluded(path)
        )

    def is_excluded(self, path: Path) -> bool:
        return any(path.full_match(pattern) for pattern in self.exclude)


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
class CatalogTable:
    section: str | None
    columns: tuple[str, ...]
    document_column: str
    required_columns: tuple[str, ...]
    path_columns: tuple[str, ...]
    accepted_values: tuple[tuple[str, tuple[str, ...]], ...]

    @classmethod
    def create(cls, value: object, label: str) -> CatalogTable:
        data = _table(
            value,
            label,
            {
                "section",
                "columns",
                "document-column",
                "required-columns",
                "path-columns",
                "accepted-values",
            },
        )
        columns = _strings(data.get("columns"), f"{label}.columns")
        if len(set(columns)) != len(columns):
            raise StandardsError(f"{label}.columns: duplicate column names")
        section = data.get("section")
        if "section" in data and (not isinstance(section, str) or not section.strip()):
            raise StandardsError(f"{label}.section: expected a nonempty heading")
        document_column = data.get("document-column")
        if not isinstance(document_column, str) or document_column not in columns:
            raise StandardsError(
                f"{label}.document-column: expected a name from columns"
            )
        required = (
            _column_names(
                data["required-columns"],
                columns,
                f"{label}.required-columns",
                nonempty=False,
            )
            if "required-columns" in data
            else columns
        )
        paths = (
            _column_names(data["path-columns"], columns, f"{label}.path-columns")
            if "path-columns" in data
            else ()
        )
        return cls(
            section=cast(str | None, section),
            columns=columns,
            document_column=document_column,
            required_columns=required,
            path_columns=paths,
            accepted_values=_accepted_values(data, label, keys=set(columns)),
        )


def _column_names(
    value: object, columns: tuple[str, ...], label: str, *, nonempty: bool = True
) -> tuple[str, ...]:
    names = _strings(value, label, nonempty=nonempty)
    if len(set(names)) != len(names) or any(name not in columns for name in names):
        raise StandardsError(f"{label}: require distinct names from columns")
    return names


@dataclass(frozen=True, slots=True, kw_only=True)
class Catalog:
    path: str
    selection: Selection
    require_content_check: bool
    tables: tuple[CatalogTable, ...]

    @classmethod
    def create(cls, value: object, label: str) -> Catalog:
        data = _table(
            value,
            label,
            {"path", "include", "exclude", "require-content-check", "tables"},
        )
        coverage = data.get("require-content-check", False)
        if type(coverage) is not bool:
            raise StandardsError(f"{label}.require-content-check: expected a boolean")
        table_rules = _rules(data, "tables", label=label)
        if "tables" in data and not table_rules:
            raise StandardsError(f"{label}.tables: require at least one table rule")
        return cls(
            path=_path(data.get("path"), f"{label}.path"),
            selection=Selection.create(data, label),
            require_content_check=coverage,
            tables=tuple(
                CatalogTable.create(rule, f"{label}.tables[{index}]")
                for index, rule in enumerate(table_rules)
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class NavigationTarget:
    path: str
    fragment: str | None

    @classmethod
    def create(cls, value: str, label: str) -> NavigationTarget:
        decoded = unquote(value)
        path, separator, fragment = decoded.partition("#")
        if (
            "?" in decoded
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", decoded)
            or (separator and not fragment.strip())
        ):
            raise StandardsError(
                f"{label}: expected a local Markdown path with optional fragment"
            )
        path = _path(path, label)
        if Path(path).suffix.lower() != ".md":
            raise StandardsError(
                f"{label}: expected a Markdown document (.md): {value!r}"
            )
        return cls(path=path, fragment=fragment if separator else None)


@dataclass(frozen=True, slots=True, kw_only=True)
class Navigation:
    path: str
    targets: tuple[NavigationTarget, ...]

    @classmethod
    def create(cls, value: object, label: str) -> Navigation:
        data = _table(value, label, {"path", "targets"})
        return cls(
            path=_path(data.get("path"), f"{label}.path"),
            targets=tuple(
                NavigationTarget.create(target, f"{label}.targets")
                for target in _strings(data.get("targets"), f"{label}.targets")
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PathGroup:
    name: str
    field: str | None
    section: str | None
    selection: Selection
    directories: bool

    @classmethod
    def create(cls, value: object, label: str) -> PathGroup:
        data = _table(
            value,
            label,
            {"name", "field", "section", "include", "exclude", "directories"},
        )
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            raise StandardsError(f"{label}.name: expected a nonempty group name")
        scopes = [key for key in ("field", "section") if key in data]
        if len(scopes) != 1:
            raise StandardsError(f"{label}: require exactly one of field or section")
        key = scopes[0]
        scope = data[key]
        if not isinstance(scope, str) or not scope.strip():
            raise StandardsError(f"{label}.{key}: expected a nonempty name")
        directories = data.get("directories", False)
        if type(directories) is not bool:
            raise StandardsError(f"{label}.directories: expected a boolean")
        return cls(
            name=name,
            field=scope if key == "field" else None,
            section=scope if key == "section" else None,
            selection=Selection.create(data, label),
            directories=directories,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Metadata:
    selection: Selection
    fields: tuple[str, ...]
    path_fields: tuple[str, ...]
    path_sections: tuple[str, ...]
    accepted_values: tuple[tuple[str, tuple[str, ...]], ...]
    path_groups: tuple[PathGroup, ...]

    @classmethod
    def create(cls, value: object, label: str) -> Metadata:
        data = _table(
            value,
            label,
            {
                "include",
                "exclude",
                "fields",
                "path-fields",
                "path-sections",
                "accepted-values",
                "path-groups",
            },
        )
        fields = _strings(data.get("fields", []), f"{label}.fields", nonempty=False)
        path_fields = _strings(
            data.get("path-fields", []), f"{label}.path-fields", nonempty=False
        )
        sections = _strings(
            data.get("path-sections", []), f"{label}.path-sections", nonempty=False
        )
        values = _accepted_values(data, label)
        rules = _rules(data, "path-groups", label=label)
        if "path-groups" in data and not rules:
            raise StandardsError(f"{label}.path-groups: require at least one group")
        groups = tuple(
            PathGroup.create(rule, f"{label}.path-groups[{index}]")
            for index, rule in enumerate(rules)
        )
        if len({group.name for group in groups}) != len(groups):
            raise StandardsError(f"{label}.path-groups: group names must be distinct")
        if (
            not fields
            and not path_fields
            and not sections
            and not values
            and not groups
        ):
            raise StandardsError(
                f"{label}: require fields, path-fields, path-sections, "
                "accepted-values or path-groups"
            )
        return cls(
            selection=Selection.create(data, label),
            fields=fields,
            path_fields=path_fields,
            path_sections=sections,
            accepted_values=values,
            path_groups=groups,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Router:
    path: str
    section: str
    columns: tuple[str, ...]
    link_columns: tuple[str, ...]
    path_columns: tuple[str, ...]

    @classmethod
    def create(cls, value: object, label: str) -> Router:
        data = _table(
            value, label, {"path", "section", "columns", "link-columns", "path-columns"}
        )
        section = data.get("section")
        if not isinstance(section, str) or not section.strip():
            raise StandardsError(f"{label}.section: expected a nonempty heading")
        columns = _strings(data.get("columns"), f"{label}.columns")
        if len(set(columns)) != len(columns):
            raise StandardsError(f"{label}.columns: duplicate column names")
        required_columns: dict[str, tuple[str, ...]] = {}
        for key in ("link-columns", "path-columns"):
            required_columns[key] = (
                _column_names(data[key], columns, f"{label}.{key}")
                if key in data
                else ()
            )
        return cls(
            path=_path(data.get("path"), f"{label}.path"),
            section=section,
            columns=columns,
            link_columns=required_columns["link-columns"],
            path_columns=required_columns["path-columns"],
        )


def _rules(data: dict[str, object], key: str, *, label: str = _PREFIX) -> list[object]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise StandardsError(f"{label}.{key}: expected an array of tables")
    return cast(list[object], value)


@dataclass(frozen=True, slots=True, kw_only=True)
class DocsConfiguration:
    documents: Selection
    required: tuple[str, ...]
    budgets: tuple[Budget, ...]
    catalogs: tuple[Catalog, ...]
    metadata: tuple[Metadata, ...]
    routers: tuple[Router, ...]
    navigation: tuple[Navigation, ...]

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
                "navigation",
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
            navigation=tuple(
                Navigation.create(rule, f"{_PREFIX}.navigation[{index}]")
                for index, rule in enumerate(_rules(data, "navigation"))
            ),
        )
