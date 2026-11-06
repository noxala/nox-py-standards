# src/nox_python_standards/docs.py
from __future__ import annotations

from pathlib import Path
import re

from nox_python_standards.docs_config import (
    Catalog,
    CatalogTable,
    DocsConfiguration,
    Navigation,
    Router,
    Selection,
)
from nox_python_standards.markdown import (
    heading_anchors,
    markdown_links,
    markdown_section,
    markdown_tables,
    metadata_value,
    repo_paths_from_code_tokens,
)
from nox_python_standards.repository import StandardsError, files, require_regular


class _Documents:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.paths = tuple(files(root))
        self._texts: dict[Path, str] = {}
        self._anchors: dict[Path, frozenset[str]] = {}

    def text(self, relative: Path) -> str:
        if relative not in self._texts:
            self._texts[relative] = require_regular(self.root, relative).read_text(
                encoding="utf-8"
            )
        return self._texts[relative]

    def anchors(self, relative: Path) -> frozenset[str]:
        if relative not in self._anchors:
            self._anchors[relative] = heading_anchors(self.text(relative))
        return self._anchors[relative]

    def target(self, source: Path, path_text: str) -> Path:
        path = (
            (self.root / source.parent / path_text).resolve()
            if path_text
            else (self.root / source).resolve()
        )
        if not path.is_relative_to(self.root):
            raise StandardsError(f"{source}: path leaves repository: {path_text}")
        return path.relative_to(self.root)

    def links(self, source: Path) -> set[Path]:
        result: set[Path] = set()
        links, _errors = markdown_links(self.text(source))
        for link in links:
            if link.path_text:
                result.add(self.target(source, link.path_text))
        return result

    def document_links(
        self, source: Path, text: str | None = None
    ) -> set[tuple[Path, str | None]]:
        context = self.text(source)
        links, _errors = markdown_links(
            context if text is None else text,
            reference_context=context if text is not None else None,
        )
        result: set[tuple[Path, str | None]] = set()
        for link in links:
            if link.is_image:
                continue
            try:
                target = self.target(source, link.path_text)
            except StandardsError:
                continue
            if target.suffix.lower() != ".md" or not (self.root / target).is_file():
                continue
            if link.fragment and link.fragment not in self.anchors(target):
                continue
            result.add((target, link.fragment))
        return result


def _check_links(documents: _Documents, source: Path) -> list[str]:
    links, parse_errors = markdown_links(documents.text(source))
    errors = [f"{source} has malformed link: {error}" for error in parse_errors]
    for link in links:
        try:
            target = documents.target(source, link.path_text)
        except StandardsError:
            errors.append(f"{source} links outside the repository: {link.destination}")
            continue
        absolute = documents.root / target
        if not absolute.exists():
            errors.append(f"{source} has broken link: {link.destination}")
        elif (
            link.fragment
            and absolute.is_file()
            and target.suffix.lower() == ".md"
            and link.fragment not in documents.anchors(target)
        ):
            errors.append(f"{source} has missing heading fragment: {link.destination}")
    return errors


def _check_catalog(
    documents: _Documents,
    rule: Catalog,
    checked: set[Path],
    content_selection: Selection,
) -> list[str]:
    catalog = Path(rule.path)
    targets: set[Path] = set()
    errors: list[str] = []
    if rule.tables:
        for table_rule in rule.tables:
            table_targets, table_errors = _check_catalog_tables(
                documents, catalog, table_rule
            )
            targets.update(table_targets)
            errors.extend(table_errors)
    else:
        targets = documents.links(catalog)
    selected = [path for path in documents.paths if rule.selection.matches(path)]
    if rule.require_content_check and not any(path != catalog for path in selected):
        errors.append(
            f"{catalog} catalog include patterns matched no files "
            "other than the catalog"
        )
    for path in selected:
        if (
            rule.require_content_check
            and path not in checked
            and not content_selection.is_excluded(path)
        ):
            errors.append(
                f"{path} selected by {catalog} has no content check; "
                "add it to docs.include or explicitly exempt it in docs.exclude"
            )
        if path == catalog or path in targets:
            continue
        index = path.parent / "README.md"
        if (
            path != index
            and index in targets
            and (documents.root / index).is_file()
            and path in documents.links(index)
        ):
            continue
        errors.append(
            f"{path} is not represented by {catalog} directly or through a "
            "cataloged subtree README.md"
        )
    return errors


def _check_catalog_tables(
    documents: _Documents, source: Path, rule: CatalogTable
) -> tuple[set[Path], list[str]]:
    text = documents.text(source)
    label = str(source)
    if rule.section is not None:
        label += f" section '{rule.section}'"
        section = markdown_section(text, rule.section)
        if section is None:
            return set(), [f"{source} is missing '## {rule.section}'"]
        text = section
    tables = markdown_tables(text)
    if not tables:
        return set(), [
            f"{label} has no catalog tables; requires columns: "
            f"{', '.join(rule.columns)}"
        ]
    targets: set[Path] = set()
    errors: list[str] = []
    for number, table in enumerate(tables, start=1):
        table_label = f"{label} table {number}"
        if table.columns != rule.columns:
            errors.append(f"{table_label} requires columns: {', '.join(rule.columns)}")
            continue
        if not table.rows:
            errors.append(f"{table_label} has no document rows")
        for row, cells in enumerate(table.rows, start=1):
            row_label = f"{table_label} row {row}"
            if len(cells) != len(rule.columns):
                errors.append(f"{row_label} contains missing or extra cells")
                continue
            for column, cell in zip(rule.columns, cells, strict=True):
                cell_label = f"{row_label} column '{column}'"
                if column in rule.required_columns and not cell:
                    errors.append(f"{cell_label} must be nonempty")
                if column == rule.document_column:
                    links = documents.document_links(source, cell)
                    if not links:
                        errors.append(
                            f"{cell_label} must contain a local Markdown document link"
                        )
                    targets.update(target for target, _fragment in links)
                if column in rule.path_columns:
                    errors.extend(_check_paths(documents.root, cell_label, cell))
                for name, choices in rule.accepted_values:
                    if column == name and cell not in choices:
                        errors.append(
                            f"{cell_label} has unsupported value {cell!r}; "
                            f"expected one of: {', '.join(choices)}"
                        )
    return targets, errors


def _check_navigation(documents: _Documents, rule: Navigation) -> list[str]:
    source = Path(rule.path)
    links = documents.document_links(source)
    errors: list[str] = []
    for expected in rule.targets:
        path = documents.root / expected.path
        destination = expected.path + (
            f"#{expected.fragment}" if expected.fragment else ""
        )
        if not path.resolve().is_relative_to(documents.root) or not path.is_file():
            errors.append(
                f"{source} navigation target must be an existing local document: "
                f"{destination}"
            )
            continue
        target = path.resolve().relative_to(documents.root)
        if expected.fragment and expected.fragment not in documents.anchors(target):
            errors.append(
                f"{source} navigation target has missing heading fragment: "
                f"{destination}"
            )
        if not any(
            actual == target
            and (expected.fragment is None or fragment == expected.fragment)
            for actual, fragment in links
        ):
            errors.append(f"{source} requires a navigation link to {destination}")
    return errors


def _check_paths(root: Path, source_label: str, text: str) -> list[str]:
    paths = repo_paths_from_code_tokens(text)
    errors: list[str] = []
    if not paths:
        errors.append(f"{source_label} must declare at least one repository path")
    for path in paths:
        absolute = (root / path).resolve()
        if not absolute.is_relative_to(root):
            errors.append(f"{source_label} references path outside repository: {path}")
        elif not absolute.exists():
            errors.append(f"{source_label} references missing path: {path}")
    return errors


def _check_router(documents: _Documents, rule: Router) -> list[str]:
    source = Path(rule.path)
    label = f"{source} {rule.section}"
    section = markdown_section(documents.text(source), rule.section)
    if section is None:
        return [f"{source} is missing '## {rule.section}'"]
    rows: list[tuple[str, ...]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = tuple(cell.strip() for cell in stripped[1:-1].split("|"))
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        rows.append(cells)
    errors: list[str] = []
    if not rows or rows[0] != rule.columns:
        errors.append(f"{label} requires columns: {', '.join(rule.columns)}")
    tasks = rows[1:]
    if not tasks:
        errors.append(f"{label} has no task rows")
    for row, cells in enumerate(tasks, start=1):
        if len(cells) != len(rule.columns) or any(not cell for cell in cells):
            errors.append(f"{label} contains a row with missing or empty cells")
            continue
        for column, cell in zip(rule.columns, cells, strict=True):
            cell_label = f"{label} row {row} column '{column}'"
            if column in rule.link_columns and not documents.document_links(
                source, cell
            ):
                errors.append(
                    f"{cell_label} must contain a local Markdown document link"
                )
            if column in rule.path_columns:
                errors.extend(_check_paths(documents.root, cell_label, cell))
    # Router cells may contain prose and links without a literal source path.
    if repo_paths_from_code_tokens(section):
        errors.extend(_check_paths(documents.root, label, section))
    return errors


def documentation_errors(
    root: Path, configuration: DocsConfiguration
) -> tuple[str, ...]:
    """Check repository data only; do not import consumer code or invoke its tools."""
    root = root.resolve()
    documents = _Documents(root)
    errors: list[str] = []
    for path in configuration.required:
        absolute = root / path
        if not absolute.resolve().is_relative_to(root):
            errors.append(f"Required path leaves repository: {path}")
        elif not absolute.exists():
            errors.append(f"Missing required path: {path}")
    selected = [
        path for path in documents.paths if configuration.documents.matches(path)
    ]
    if not selected:
        errors.append("Documentation include patterns matched no files")
    checked = set(selected)
    checked.update(Path(rule.path) for rule in configuration.catalogs)
    checked.update(Path(rule.path) for rule in configuration.routers)
    checked.update(Path(rule.path) for rule in configuration.navigation)
    for path in sorted(checked):
        errors.extend(_check_links(documents, path))
    for rule in configuration.budgets:
        matches = [path for path in documents.paths if rule.selection.matches(path)]
        if not matches:
            errors.append(
                f"Budget include patterns matched no files: {rule.selection.include}"
            )
        for path in matches:
            text = documents.text(path)
            for size, limit, unit in (
                (len((root / path).read_bytes()), rule.max_bytes, "bytes"),
                (len(text.split()), rule.max_words, "words"),
            ):
                if limit is not None and size > limit:
                    errors.append(
                        f"{path} is {size} {unit}; limit is {limit}. "
                        "Move detail into a focused guide or explicitly revise "
                        "the local budget."
                    )
    for catalog in configuration.catalogs:
        errors.extend(
            _check_catalog(documents, catalog, checked, configuration.documents)
        )
    for navigation in configuration.navigation:
        errors.extend(_check_navigation(documents, navigation))
    for metadata in configuration.metadata:
        matches = [path for path in documents.paths if metadata.selection.matches(path)]
        if not matches:
            errors.append(
                "Metadata include patterns matched no files: "
                f"{metadata.selection.include}"
            )
        for path in matches:
            text = documents.text(path)
            for field in dict.fromkeys((*metadata.fields, *metadata.path_fields)):
                value = metadata_value(text, field)
                if value is None:
                    errors.append(f"{path} is missing '- {field}: ...' metadata")
                elif field in metadata.path_fields:
                    errors.extend(_check_paths(root, f"{path} {field}", value))
            for heading in metadata.path_sections:
                section = markdown_section(text, heading)
                if section is None:
                    errors.append(f"{path} is missing '## {heading}'")
                else:
                    errors.extend(_check_paths(root, f"{path} {heading}", section))
    for router in configuration.routers:
        errors.extend(_check_router(documents, router))
    return tuple(errors)
