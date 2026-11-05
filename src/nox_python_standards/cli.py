# src/nox_python_standards/cli.py
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import cast

from nox_python_standards.config import Configuration, release_version
from nox_python_standards.repository import StandardsError, project_root
from nox_python_standards.versions import check_versions


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="nox-py-standards")
    result.add_argument("--version", action="version", version=release_version())
    result.add_argument(
        "--root", type=Path, help="Consumer Git root (default: current Git root)"
    )
    result.add_argument("command", choices=("check", "sync"))
    return result


def main(arguments: list[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    command = cast(str, options.command)
    try:
        root = project_root(cast(Path | None, options.root))
        configuration = Configuration.read(root)
        if command == "sync":
            configuration.sync()
        else:
            configuration.check()
            check_versions(configuration)
        sys.stdout.write(
            f"nox-python-standards {release_version()}: {command} passed\n"
        )
        return 0
    except (StandardsError, OSError, UnicodeError) as exc:
        sys.stderr.write(f"nox-py-standards: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
