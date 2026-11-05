# src/nox_python_standards/headers.py
from __future__ import annotations

import io
from pathlib import Path
import re
import tokenize

from nox_python_standards.config import Configuration, atomic_write
from nox_python_standards.repository import (
    StandardsError,
    files,
    in_scope,
    require_regular,
)

_PATH_HEADER = re.compile(rb"^# [^\r\n]+\.py(?:  # noqa: E501)?$")


def render(relative: Path, contents: bytes) -> bytes:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(contents).readline)
        contents.decode("utf-8")
    except (SyntaxError, UnicodeError) as exc:
        raise StandardsError(f"Unsupported Python encoding: {relative}") from exc
    if encoding != "utf-8" or b"\r" in contents.replace(b"\r\n", b""):
        raise StandardsError(f"Unsupported encoding/line endings: {relative}")
    header = f"# {relative.as_posix()}"
    if len(header) > 88:
        header += "  # noqa: E501"
    expected = header.encode()
    lines = contents.splitlines(keepends=True)
    first = lines[0] if lines else b""
    second = lines[1] if len(lines) > 1 else b""
    first_text, second_text = first.rstrip(b"\r\n"), second.rstrip(b"\r\n")
    if first.startswith(b"#!") and second_text == expected:
        return contents
    if first_text == expected and not second.startswith(b"#!"):
        return contents
    # Moving a coding cookie to line three would silently change Python's encoding.
    if re.search(rb"coding[:=]", first + second):
        raise StandardsError(
            f"Cannot safely insert header around encoding cookie: {relative}"
        )
    newline = b"\r\n" if first.endswith(b"\r\n") else b"\n"
    remainder = b"".join(lines[2:])
    if first.startswith(b"#!"):
        tail = remainder if _PATH_HEADER.fullmatch(second_text) else second + remainder
        return first.rstrip(b"\r\n") + newline + expected + newline + tail
    if _PATH_HEADER.fullmatch(first_text) and second.startswith(b"#!"):
        return second.rstrip(b"\r\n") + newline + expected + newline + remainder
    if _PATH_HEADER.fullmatch(first_text):
        return expected + newline + second + remainder
    return expected + newline + contents


def headers(configuration: Configuration, *, fix: bool) -> None:
    changes: list[tuple[Path, bytes]] = []
    paths = [
        path
        for path in files(configuration.root)
        if path.suffix == ".py"
        and in_scope(path, configuration.sources)
        and (configuration.root / path).exists()  # A tracked deletion is not a source.
    ]
    if not paths:
        raise StandardsError("Expected at least one Python source in configured scope")
    for relative in paths:
        path = require_regular(configuration.root, relative)
        original = path.read_bytes()
        rendered = render(relative, original)
        if rendered != original:
            changes.append((path, rendered))
    if changes and not fix:
        raise StandardsError(
            "Python path headers need repair:\n"
            + "\n".join(
                str(path.relative_to(configuration.root)) for path, _ in changes
            )
        )
    for path, contents in changes:
        atomic_write(path, contents)
