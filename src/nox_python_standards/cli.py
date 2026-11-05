# src/nox_python_standards/cli.py
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import cast

from nox_python_standards.config import Configuration, release_version
from nox_python_standards.headers import headers
from nox_python_standards.hooks import check_hook
from nox_python_standards.repository import StandardsError, project_root
from nox_python_standards.versions import Tools, ruff, run


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="nox-py-standards")
    result.add_argument("--version", action="version", version=release_version())
    result.add_argument(
        "--root", type=Path, help="Consumer Git root (default: current Git root)"
    )
    commands = result.add_subparsers(dest="command", required=True)
    for name, actions in (
        ("config", ("check", "sync")),
        ("ruff", ("check", "fix")),
        ("headers", ("check", "fix")),
        ("hooks", ("check",)),
    ):
        command = commands.add_parser(name)
        command.add_argument("action", choices=actions)
    for name in ("versions", "check", "fix"):
        commands.add_parser(name)
    typecheck = commands.add_parser("typecheck")
    typecheck.add_argument("--threads", type=int)
    typecheck.add_argument("--watch", action="store_true")
    return result


def main(arguments: list[str] | None = None) -> int:
    options = parser().parse_args(arguments)
    command = cast(str, options.command)
    try:
        root = project_root(cast(Path | None, options.root))
        if command == "hooks":
            check_hook(root)
            return 0
        configuration = Configuration.read(root)
        if command == "config" and options.action == "sync":
            configuration.sync()
        else:
            configuration.check()
            if command == "headers":
                headers(configuration, fix=options.action == "fix")
            elif command != "config":
                tools = Tools.validate(configuration)
                if command in {"check", "fix"}:
                    headers(configuration, fix=command == "fix")
                if command in {"ruff", "check", "fix"}:
                    fix = command == "fix" or (
                        command == "ruff" and options.action == "fix"
                    )
                    ruff(configuration, tools, fix=fix)
                if command in {"typecheck", "check"}:
                    flags: list[str] = []
                    if command == "typecheck":
                        threads = cast(int | None, options.threads)
                        if threads is not None:
                            if threads < 1:
                                raise StandardsError("--threads must be positive")
                            flags.extend(["--threads", str(threads)])
                        if options.watch:
                            flags.append("--watch")
                    run(root, tools.pyright, *flags)
        sys.stdout.write(
            f"nox-python-standards {release_version()}: {command} passed\n"
        )
        return 0
    except (StandardsError, OSError, UnicodeError) as exc:
        sys.stderr.write(f"nox-py-standards: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
