# src/nox_python_standards/docs_cli.py
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import cast

from nox_python_standards.config import release_version
from nox_python_standards.docs import documentation_errors
from nox_python_standards.docs_config import DocsConfiguration
from nox_python_standards.repository import StandardsError, project_root


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nox-docs-check")
    parser.add_argument("--version", action="version", version=release_version())
    parser.add_argument("--root", type=Path, help="Consumer Git root")
    options = parser.parse_args(arguments)
    try:
        root = project_root(cast(Path | None, options.root))
        errors = documentation_errors(root, DocsConfiguration.read(root))
        if errors:
            raise StandardsError("\n".join(errors))
    except (StandardsError, OSError, UnicodeError) as exc:
        sys.stderr.write(f"nox-docs-check: {exc}\n")
        return 1
    sys.stdout.write(f"nox-docs-check {release_version()}: passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
