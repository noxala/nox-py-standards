# src/nox_python_standards/docs.py
from __future__ import annotations

from pathlib import Path
import re

from nox_python_standards.docs_config import Catalog, DocsConfiguration, Router
from nox_python_standards.markdown import (
    heading_anchors,
    markdown_links,
    markdown_section,
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


def _check_catalog(documents: _Documents, rule: Catalog) -> list[str]:
    catalog = Path(rule.path)
    targets = documents.links(catalog)
    errors: list[str] = []
    for path in documents.paths:
        if path == catalog or not rule.selection.matches(path) or path in targets:
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
        cells = tuple(cell.strip() for cell in stripped.strip("|").split("|"))
        if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        rows.append(cells)
    errors: list[str] = []
    if not rows or rows[0] != rule.columns:
        errors.append(f"{label} requires columns: {', '.join(rule.columns)}")
    tasks = rows[1:]
    if not tasks:
        errors.append(f"{label} has no task rows")
    for cells in tasks:
        if len(cells) != len(rule.columns) or any(not cell for cell in cells):
            errors.append(f"{label} contains a row with missing or empty cells")
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
    for path in selected:
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
        errors.extend(_check_catalog(documents, catalog))
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
