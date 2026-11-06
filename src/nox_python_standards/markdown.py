# src/nox_python_standards/markdown.py
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from urllib.parse import unquote

_INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]*)\)")
_REFERENCE_DEFINITION_RE = re.compile(
    r"^[ \t]{0,3}\[([^\]]+)\]:[ \t]*(.*)$",
    re.MULTILINE,
)
_REFERENCE_USAGE_RE = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
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


def without_fenced_code(text: str) -> str:
    rendered: list[str] = []
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if fence is None:
            if stripped.startswith("```"):
                fence = "```"
                continue
            if stripped.startswith("~~~"):
                fence = "~~~"
                continue
            rendered.append(line)
            continue
        if stripped.startswith(fence):
            fence = None
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


def markdown_links(text: str) -> tuple[tuple[LocalLink, ...], tuple[str, ...]]:
    text_without_fences = without_fenced_code(text)
    links: list[LocalLink] = []
    errors: list[str] = []
    definitions: dict[str, str] = {}

    for match in _REFERENCE_DEFINITION_RE.finditer(text_without_fences):
        label = _normalize_reference_label(match.group(1))
        raw_destination = match.group(2)
        if len(raw_destination.strip()) == 0:
            errors.append(f"reference [{match.group(1)}] has empty link destination")
            continue
        definitions[label] = raw_destination
        link, error = _parse_link_destination(raw_destination)
        if error is not None:
            errors.append(f"reference [{match.group(1)}] has {error}")
        elif link is not None:
            links.append(link)

    for match in _REFERENCE_USAGE_RE.finditer(text_without_fences):
        label = match.group(2) if len(match.group(2)) > 0 else match.group(1)
        normalized_label = _normalize_reference_label(label)
        if normalized_label not in definitions:
            errors.append(f"undefined link reference: [{label}]")

    for match in _INLINE_LINK_RE.finditer(text_without_fences):
        link, error = _parse_link_destination(match.group(1))
        if error is not None:
            errors.append(error)
        elif link is not None:
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
