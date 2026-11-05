# src/nox_python_standards/repository.py
from __future__ import annotations

from pathlib import Path
import subprocess


class StandardsError(RuntimeError):
    """An actionable configuration or tool contract failure."""


IGNORED_DIRS = frozenset(
    {
        ".eggs",
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "lib",
        "libs",
        "node_modules",
        "site-packages",
        "third_party",
        "venv",
        "vendor",
    }
)


def git(root: Path, *arguments: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *arguments], stderr=subprocess.PIPE
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise StandardsError(f"Git failed in {root}: {arguments!r}") from exc


def project_root(explicit: Path | None) -> Path:
    location = Path.cwd() if explicit is None else explicit.resolve()
    root = Path(git(location, "rev-parse", "--show-toplevel").decode().strip())
    if explicit is not None and root.resolve() != location:
        raise StandardsError("--root must name the consumer Git root")
    return root.resolve()


def ignored(path: Path) -> bool:
    return any(
        part in IGNORED_DIRS or part.endswith((".egg-info", ".dist-info"))
        for part in path.parts[:-1]
    )


def files(root: Path) -> list[Path]:
    """Git supplies tracked and relevant untracked files without crawling vendors."""
    output = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted(
        {
            Path(p.decode())
            for p in output.split(b"\0")
            if p and not ignored(Path(p.decode()))
        }
    )


def in_scope(path: Path, sources: tuple[Path, ...]) -> bool:
    return any(path == source or source in path.parents for source in sources)


def require_regular(root: Path, relative: Path) -> Path:
    path = root / relative
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root):
        raise StandardsError(f"Refusing symlink path: {relative}")
    if not path.is_file():
        raise StandardsError(f"Expected regular file: {relative}")
    return path
