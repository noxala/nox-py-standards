# src/nox_python_standards/markdown.py
from __future__ import annotations

from dataclasses import dataclass, replace
from html import unescape
import re
from urllib.parse import unquote

_LINK_RE = re.compile(r"\[([^\[\]]*)\](?:\(([^)]*)\)|\[([^\[\]]*)\])")
_REFERENCE_DEFINITION_RE = re.compile(
    r"^[ \t]{0,3}\[([^\[\]\n]+)\]:[ \t]*(.*)$",
    re.MULTILINE,
)
_BACKTICK_RUN_RE = re.compile(r"`+")
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_ATX_HEADING_RE = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class LocalLink:
    destination: str
    path_text: str
    fragment: str | None
    is_image: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkdownTable:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def _blank(text: str) -> str:
    """Hide syntax without joining lines or changing source offsets."""
    return re.sub(r"[^\r\n]", " ", text)


def without_fenced_code(text: str) -> str:
    rendered: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip(" \t").rstrip("\r\n")
        if fence is None:
            opening = re.fullmatch(r"(`{3,}|~{3,})(.*)", stripped)
            if opening is not None and not (
                opening.group(1).startswith("`") and "`" in opening.group(2)
            ):
                fence = opening.group(1)
                rendered.append(_blank(line))
            else:
                rendered.append(line)
            continue
        rendered.append(_blank(line))
        if re.fullmatch(re.escape(fence[0]) + rf"{{{len(fence)},}}[ \t]*", stripped):
            fence = None
    return "".join(rendered)


def _is_escaped(text: str, index: int) -> bool:
    preceding = text[:index]
    return (len(preceding) - len(preceding.rstrip("\\"))) % 2 == 1


def _without_code_spans(text: str) -> str:
    rendered: list[str] = []
    cursor = 0
    while (opening := _BACKTICK_RUN_RE.search(text, cursor)) is not None:
        rendered.append(text[cursor : opening.start()])
        closing = re.search(
            rf"(?<!`)`{{{len(opening.group())}}}(?!`)", text[opening.end() :]
        )
        if _is_escaped(text, opening.start()) or closing is None:
            rendered.append(opening.group())
            cursor = opening.end()
            continue
        end = opening.end() + closing.end()
        if re.search(r"\n[ \t\r]*\n", text[opening.end() : end]):
            rendered.append(opening.group())
            cursor = opening.end()
            continue
        rendered.append(_blank(text[opening.start() : end]))
        cursor = end
    rendered.append(text[cursor:])
    return "".join(rendered)


def _normalize_reference_label(value: str) -> str:
    return " ".join(value.split()).casefold()


def _parse_link_destination(
    raw_destination: str,
) -> tuple[LocalLink | None, str | None]:
    value = raw_destination.strip()
    if len(value) == 0:
        return None, "empty link destination"

    if value.startswith("<"):
        end = value.find(">")
        if end < 0:
            return None, f"unterminated angle-bracket link destination: {value}"
        target = value[1:end]
    else:
        parts = value.split(maxsplit=1)
        if len(parts) == 0:
            return None, "empty link destination"
        target = parts[0]

    target = unquote(target)
    if len(target) == 0:
        return None, "empty link destination"
    if target.startswith(("http://", "https://", "mailto:")):
        return None, None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None, None
    if target.startswith("/"):
        return None, None

    path_and_query, separator, fragment = target.partition("#")
    path_text = path_and_query.split("?", maxsplit=1)[0]
    if len(path_text) == 0 and not separator:
        return None, f"invalid local link destination: {target}"

    return (
        LocalLink(
            destination=target,
            path_text=path_text,
            fragment=fragment if separator else None,
        ),
        None,
    )


def markdown_links(
    text: str, *, reference_context: str | None = None
) -> tuple[tuple[LocalLink, ...], tuple[str, ...]]:
    """Resolve supported link occurrences; definitions alone are not navigation."""
    text_without_fences = without_fenced_code(text)
    visible = _without_code_spans(text_without_fences)
    links: list[LocalLink] = []
    errors: list[str] = []
    definitions: dict[str, str] = {}

    definition_text = (
        text_without_fences
        if reference_context is None
        else without_fenced_code(reference_context)
    )
    definition_visible = (
        visible if reference_context is None else _without_code_spans(definition_text)
    )
    for match in _REFERENCE_DEFINITION_RE.finditer(definition_visible):
        label = definition_text[match.start(1) : match.end(1)]
        raw_destination = definition_text[match.start(2) : match.end(2)]
        definitions.setdefault(_normalize_reference_label(label), raw_destination)
    visible = _REFERENCE_DEFINITION_RE.sub(lambda match: _blank(match.group()), visible)

    for match in _LINK_RE.finditer(visible):
        if _is_escaped(visible, match.start()) or re.search(
            r"\n[ \t\r]*\n", match.group(1)
        ):
            continue
        prefix = ""
        if match.group(2) is not None:
            raw_destination = text_without_fences[match.start(2) : match.end(2)]
        else:
            group = 3 if match.group(3) else 1
            label = text_without_fences[match.start(group) : match.end(group)]
            destination = definitions.get(_normalize_reference_label(label))
            if destination is None:
                errors.append(f"undefined link reference: [{label}]")
                continue
            raw_destination = destination
            prefix = f"reference [{label}] has "
        link, error = _parse_link_destination(raw_destination)
        if error is not None:
            errors.append(prefix + error)
        elif link is not None:
            if (
                match.start() > 0
                and visible[match.start() - 1] == "!"
                and not _is_escaped(visible, match.start() - 1)
            ):
                link = replace(link, is_image=True)
            links.append(link)

    return tuple(links), tuple(errors)


def _heading_slug(value: str) -> str:
    value = re.sub(r"[ \t]+#+[ \t]*$", "", value.strip())
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = unescape(value)
    slug_characters = [
        character.casefold()
        for character in value
        if character.isalnum() or character in {" ", "\t", "-", "_"}
    ]
    return re.sub(r"\s+", "-", "".join(slug_characters).strip())


def heading_anchors(text: str) -> frozenset[str]:
    anchors: set[str] = set()
    slug_counts: dict[str, int] = {}
    for match in _ATX_HEADING_RE.finditer(without_fenced_code(text)):
        slug = _heading_slug(match.group(1))
        if len(slug) == 0:
            continue
        count = slug_counts.get(slug, 0)
        slug_counts[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return frozenset(anchors)


def metadata_value(text: str, label: str) -> str | None:
    lines = without_fenced_code(text).splitlines()
    prefix = f"- {label}:"
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        values = [line.removeprefix(prefix).strip()]
        for continuation in lines[index + 1 :]:
            if not continuation.startswith(("  ", "\t")):
                break
            values.append(continuation.strip())
        value = " ".join(part for part in values if len(part) > 0)
        return value if len(value) > 0 else None
    return None


def _path_from_code_token(token: str) -> str | None:
    value = token.strip().split("::", maxsplit=1)[0]
    if "/" not in value and not value.endswith((".py", ".md")):
        return None
    if any(character in value for character in "*{}[]"):
        return None
    return value


def repo_paths_from_code_tokens(text: str) -> tuple[str, ...]:
    paths = [
        relative_path
        for match in _BACKTICK_RE.finditer(without_fenced_code(text))
        if (relative_path := _path_from_code_token(match.group(1))) is not None
    ]
    return tuple(paths)


def markdown_section(text: str, heading: str) -> str | None:
    clean_text = without_fenced_code(text)
    match = re.search(
        rf"^##[ \t]+{re.escape(heading)}[ \t]*$", clean_text, re.MULTILINE
    )
    if match is None:
        return None
    remainder = clean_text[match.end() :]
    next_heading = re.search(r"^#{1,2}[ \t]+", remainder, re.MULTILINE)
    return remainder if next_heading is None else remainder[: next_heading.start()]


def _pipe_cells(line: str) -> tuple[str, ...] | None:
    stripped = line.strip()
    if "|" not in stripped:
        return None
    return tuple(
        cell.strip() for cell in stripped.removeprefix("|").removesuffix("|").split("|")
    )


def markdown_tables(text: str) -> tuple[MarkdownTable, ...]:
    """Read pipe tables with delimiter rows; retain code tokens in cell values."""
    clean = without_fenced_code(text)
    lines = clean.splitlines()
    visible = _without_code_spans(clean).splitlines()
    tables: list[MarkdownTable] = []
    index = 0
    while index + 1 < len(lines):
        header = _pipe_cells(visible[index])
        separator = _pipe_cells(visible[index + 1])
        if (
            header is None
            or separator is None
            or len(header) != len(separator)
            or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        ):
            index += 1
            continue
        columns = _pipe_cells(lines[index])
        assert columns is not None
        index += 2
        rows: list[tuple[str, ...]] = []
        while index < len(lines) and _pipe_cells(visible[index]) is not None:
            cells = _pipe_cells(lines[index])
            assert cells is not None
            rows.append(cells)
            index += 1
        tables.append(MarkdownTable(columns=columns, rows=tuple(rows)))
    return tuple(tables)
