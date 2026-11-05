# test/test_headers_hooks.py
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from nox_python_standards.config import Configuration
from nox_python_standards.headers import headers, render
from nox_python_standards.hooks import check_hook
from nox_python_standards.repository import StandardsError


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (b"", b"# src/a.py\n"),
        (b"VALUE = 1\n", b"# src/a.py\nVALUE = 1\n"),
        (b"# old.py\r\nVALUE = 1\r\n", b"# src/a.py\r\nVALUE = 1\r\n"),
        (b"#!/usr/bin/python3\n", b"#!/usr/bin/python3\n# src/a.py\n"),
        (b"#!/usr/bin/python3", b"#!/usr/bin/python3\n# src/a.py\n"),
        (
            b"#!/usr/bin/python3\n# old.py\nx=1\n",
            b"#!/usr/bin/python3\n# src/a.py\nx=1\n",
        ),
        (
            b"# old.py\n#!/usr/bin/python3\nx=1\n",
            b"#!/usr/bin/python3\n# src/a.py\nx=1\n",
        ),
    ],
)
def test_header_rendering_and_idempotence(original: bytes, expected: bytes) -> None:
    assert render(Path("src/a.py"), original) == expected
    assert render(Path("src/a.py"), expected) == expected


def test_long_path() -> None:
    path = Path("src") / ("a" * 90 + ".py")
    result = render(path, b"")
    assert result.endswith(b"  # noqa: E501\n")
    assert render(path, result) == result


def test_header_check_read_only_fix_preserves_mode(consumer: Path) -> None:
    source = consumer / "src/example.py"
    source.write_bytes(b"VALUE = 1\n")
    source.chmod(0o755)
    configuration = Configuration.read(consumer)
    with pytest.raises(StandardsError, match="src/example"):
        headers(configuration, fix=False)
    assert source.read_bytes() == b"VALUE = 1\n"
    headers(configuration, fix=True)
    assert source.read_bytes().startswith(b"# src/example.py\n")
    assert source.stat().st_mode & 0o777 == 0o755
    headers(configuration, fix=False)


def test_unsupported_source_blocks_all_header_writes(consumer: Path) -> None:
    first = consumer / "src/a.py"
    first.write_bytes(b"VALUE = 1\n")
    (consumer / "src/z.py").write_bytes(b"# coding: latin-1\nNAME = '\xe9'\n")
    with pytest.raises(StandardsError, match="encoding"):
        headers(Configuration.read(consumer), fix=True)
    assert first.read_bytes() == b"VALUE = 1\n"


def test_git_ignored_untracked_and_vendor_sources_are_untouched(consumer: Path) -> None:
    (consumer / ".gitignore").write_text("ignored.py\n")
    (consumer / "src/ignored.py").write_text("unchanged")
    (consumer / "src/vendor").mkdir()
    vendor = consumer / "src/vendor/a.py"
    vendor.write_text("unchanged")
    subprocess.run(["git", "-C", str(consumer), "add", "src/vendor/a.py"], check=True)
    headers(Configuration.read(consumer), fix=True)
    assert vendor.read_text() == "unchanged"
    assert (consumer / "src/ignored.py").read_text() == "unchanged"


def test_hook_checks_custom_path_without_installing(consumer: Path) -> None:
    hook_dir = consumer / "custom-hooks"
    hook_dir.mkdir()
    subprocess.run(
        ["git", "-C", str(consumer), "config", "core.hooksPath", str(hook_dir)],
        check=True,
    )
    with pytest.raises(StandardsError, match="missing"):
        check_hook(consumer)
    hook = hook_dir / "pre-push"
    hook.write_text("#!/bin/sh\n# pre_commit --hook-type=pre-push\n")
    with pytest.raises(StandardsError, match="missing"):
        check_hook(consumer)
    hook.chmod(0o755)
    check_hook(consumer)
    hook.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(StandardsError, match="managed"):
        check_hook(consumer)


def test_hook_resolution_in_worktree(consumer: Path, tmp_path: Path) -> None:
    def git_command(*arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(consumer), *arguments], check=True, capture_output=True
        )

    git_command("config", "user.email", "test@example.test")
    git_command("config", "user.name", "Test")
    git_command("add", ".")
    git_command("commit", "-qm", "fixture")
    worktree = tmp_path / "worktree"
    git_command("worktree", "add", "--detach", str(worktree))
    hook = consumer / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\n# pre_commit --hook-type=pre-push\n")
    hook.chmod(0o755)
    check_hook(worktree)
