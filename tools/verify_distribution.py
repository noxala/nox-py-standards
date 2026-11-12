# tools/verify_distribution.py
from __future__ import annotations

from email.parser import BytesParser
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


def run(arguments: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(arguments, cwd=cwd, env=env, check=True)


def verify_docs_cli(environment: Path, consumer: Path, env: dict[str, str]) -> None:
    consumer.mkdir()
    run(["git", "init", "--quiet"], cwd=consumer, env=env)
    (consumer / "docs").mkdir()
    (consumer / "pyproject.toml").write_text(
        "[tool.nox-python-standards.docs]\n"
        'include = ["AGENTS.md", "docs/GUIDE.md"]\nrequired = ["AGENTS.md"]\n'
        "[[tool.nox-python-standards.docs.budgets]]\n"
        'include = ["AGENTS.md"]\nmax-words = 450\n'
        "[[tool.nox-python-standards.docs.catalogs]]\n"
        'path = "docs/README.md"\ninclude = ["docs/**/*.md"]\n'
        "require-content-check = true\n"
        "[[tool.nox-python-standards.docs.catalogs.tables]]\n"
        'columns = ["Document", "Status", "Read when", "Authority"]\n'
        'document-column = "Document"\npath-columns = ["Authority"]\n'
        'accepted-values = { Status = ["Current"] }\n'
        "[[tool.nox-python-standards.docs.navigation]]\n"
        'path = "AGENTS.md"\ntargets = ["docs/GUIDE.md#details"]\n'
        "[[tool.nox-python-standards.docs.routers]]\n"
        'path = "AGENTS.md"\nsection = "Routes"\ncolumns = ["Task", "Read", "Source"]\n'
        'link-columns = ["Read"]\npath-columns = ["Source"]\n'
        "[[tool.nox-python-standards.docs.metadata]]\n"
        'include = ["docs/GUIDE.md"]\naccepted-values = { Status = ["Current"] }\n'
        "[[tool.nox-python-standards.docs.metadata.path-groups]]\n"
        'name = "implementation"\nsection = "Details"\ninclude = ["__init__.py"]\n'
        "[[tool.nox-python-standards.docs.metadata.path-groups]]\n"
        'name = "tests"\nsection = "Details"\ninclude = ["checks/**/*.py"]\n'
    )
    (consumer / "AGENTS.md").write_text(
        "# Guide\n[Details][guide]\n[guide]: docs/GUIDE.md#details\n"
        "`[Example](absent.md)`\n"
        "## Routes\n| Task | Read | Source |\n| --- | --- | --- |\n"
        "| Example | [guide][] | `__init__.py` |\n"
    )
    workflow = consumer / "docs/GUIDE.md"
    workflow.write_text(
        "# Guide\n- Status: Current\n## Details\n"
        "- `__init__.py::handler`\n- `checks/test_consumer.py::case`\n"
    )
    (consumer / "checks").mkdir()
    (consumer / "checks/test_consumer.py").write_text(
        'raise RuntimeError("test imported")\n'
    )
    catalog = consumer / "docs/README.md"
    catalog.write_text(
        "# Catalog\n| Document | Status | Read when | Authority |\n"
        "| --- | --- | --- | --- |\n"
        "| [guide][] | Current | Implementation | `__init__.py` |\n"
        "\n[guide]: GUIDE.md#details\n"
    )
    (consumer / "__init__.py").write_text('raise RuntimeError("consumer imported")\n')
    cli = str(environment / "bin/nox-docs-check")
    # Neither standards configuration nor consumer Ruff/Pyright is installed here.
    before = {
        path: path.read_bytes()
        for path in consumer.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    run([cli], cwd=consumer / "docs", env=env)
    run([cli, "--root", str(consumer)], cwd=consumer.parent, env=env)
    if any(path.read_bytes() != contents for path, contents in before.items()):
        raise RuntimeError("Documentation check modified consumer files")
    for invalid, diagnostic in (
        (
            before[workflow].decode().replace("Status: Current", "Status: TBD"),
            "docs/GUIDE.md Status has unsupported value 'TBD'",
        ),
        (
            before[workflow]
            .decode()
            .replace("checks/test_consumer.py::case", "./__init__.py::other"),
            "path group 'tests' must declare an existing file matching:",
        ),
    ):
        workflow.write_text(invalid)
        metadata_failure = subprocess.run(
            [cli], cwd=consumer, env=env, text=True, capture_output=True, check=False
        )
        if (
            metadata_failure.returncode != 1
            or diagnostic not in metadata_failure.stderr
        ):
            raise RuntimeError(
                f"Installed workflow rules did not fail: {metadata_failure}"
            )
        if workflow.read_text() != invalid:
            raise RuntimeError("Failed workflow check modified consumer files")
    workflow.write_bytes(before[workflow])
    catalog.write_text("# Catalog\n[unused]: GUIDE.md#details\n")
    discovery_failure = subprocess.run(
        [cli], cwd=consumer, env=env, text=True, capture_output=True, check=False
    )
    if (
        discovery_failure.returncode != 1
        or "docs/GUIDE.md is not represented" not in discovery_failure.stderr
    ):
        raise RuntimeError(f"Unused definition satisfied catalog: {discovery_failure}")
    if catalog.read_text() != "# Catalog\n[unused]: GUIDE.md#details\n":
        raise RuntimeError("Failed documentation check modified catalog")
    catalog.write_bytes(before[catalog])
    invalid_table = before[catalog].decode().replace("| Current |", "| TBD |")
    catalog.write_text(invalid_table)
    table_failure = subprocess.run(
        [cli], cwd=consumer, env=env, text=True, capture_output=True, check=False
    )
    if (
        table_failure.returncode != 1
        or "column 'Status' has unsupported value 'TBD'" not in table_failure.stderr
    ):
        raise RuntimeError(
            f"Installed catalog table rule did not fail: {table_failure}"
        )
    if catalog.read_text() != invalid_table:
        raise RuntimeError("Failed catalog table check modified consumer files")
    catalog.write_bytes(before[catalog])
    guide = consumer / "AGENTS.md"
    guide.write_text(
        before[guide]
        .decode()
        .replace("[Details][guide]", "Guide pending")
        .replace("[guide][]", "Guide pending")
    )
    navigation_failure = subprocess.run(
        [cli], cwd=consumer, env=env, text=True, capture_output=True, check=False
    )
    if (
        navigation_failure.returncode != 1
        or "requires a navigation link to docs/GUIDE.md#details"
        not in navigation_failure.stderr
        or "row 1 column 'Read'" not in navigation_failure.stderr
    ):
        raise RuntimeError(
            f"Installed navigation rules did not fail: {navigation_failure}"
        )
    guide.write_bytes(before[guide])
    config = consumer / "pyproject.toml"
    config.write_text(before[config].decode().replace(', "docs/GUIDE.md"', ""))
    coverage_failure = subprocess.run(
        [cli], cwd=consumer, env=env, text=True, capture_output=True, check=False
    )
    if (
        coverage_failure.returncode != 1
        or "has no content check" not in coverage_failure.stderr
    ):
        raise RuntimeError(f"Installed coverage rule did not fail: {coverage_failure}")
    config.write_bytes(before[config])
    guide.write_text("# Guide\n[Broken](absent.md)\n")
    failure = subprocess.run(
        [str(environment / "bin/python"), "-m", "nox_python_standards.docs_cli"],
        cwd=consumer,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if failure.returncode != 1 or "broken link: absent.md" not in failure.stderr:
        raise RuntimeError(f"Installed documentation check did not fail: {failure}")
    if guide.read_text() != "# Guide\n[Broken](absent.md)\n":
        raise RuntimeError("Failed documentation check modified guide")


def verify(root: Path, temporary: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv must be on PATH")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    # No dependency cache or sibling checkout may supply a missing package resource.
    env["UV_CACHE_DIR"] = str(temporary / "cache")
    artifacts = temporary / "artifacts"
    run([uv, "build", "--out-dir", str(artifacts)], cwd=root, env=env)
    sdist = next(artifacts.glob("*.tar.gz"))
    wheel = next(artifacts.glob("*.whl"))
    required = {
        "policy.json",
        "ownership.json",
        "versions.json",
        "PYTHON_CONVENTIONS.md",
    }
    with zipfile.ZipFile(wheel) as archive:
        if not required <= {Path(name).name for name in archive.namelist()}:
            raise RuntimeError("Wheel missing policy resources")
        metadata = BytesParser().parsebytes(
            archive.read(
                next(name for name in archive.namelist() if name.endswith("/METADATA"))
            )
        )
        license_path = next(
            name
            for name in archive.namelist()
            if name.endswith(".dist-info/licenses/LICENSE")
        )
        if (
            metadata["Name"] != "nox-py-standards"
            or metadata["License-Expression"] != "0BSD"
            or metadata.get_all("License-File") != ["LICENSE"]
            or archive.read(license_path) != (root / "LICENSE").read_bytes()
        ):
            raise RuntimeError("Wheel distribution name or 0BSD license differs")
    extracted = temporary / "extracted"
    with tarfile.open(sdist) as archive:
        if not required <= {Path(member.name).name for member in archive.getmembers()}:
            raise RuntimeError("Sdist missing policy resources")
        documentation = {
            "docs/DOCUMENTATION_CHECKS.md",
            "docs/examples/compact.toml",
            "docs/examples/progressive.toml",
        }
        if not documentation <= {
            member.name.partition("/")[2] for member in archive.getmembers()
        }:
            raise RuntimeError("Sdist missing documentation policy examples")
        archive.extractall(extracted, filter="data")
    if (next(extracted.iterdir()) / "LICENSE").read_bytes() != (
        root / "LICENSE"
    ).read_bytes():
        raise RuntimeError("Sdist license text differs from 0BSD")
    rebuilt = temporary / "rebuilt"
    run(
        [uv, "build", "--wheel", "--out-dir", str(rebuilt)],
        cwd=next(extracted.iterdir()),
        env=env,
    )
    for index, distribution in enumerate((wheel, next(rebuilt.glob("*.whl")))):
        environment = temporary / f"environment-{index}"
        run(
            [uv, "venv", "--python", sys.executable, str(environment)],
            cwd=temporary,
            env=env,
        )
        run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(environment / "bin/python"),
                str(distribution),
            ],
            cwd=temporary,
            env=env,
        )
        verify_docs_cli(environment, temporary / f"docs-consumer-{index}", env)
    # Continue standards checks using the wheel rebuilt from the sdist.
    environment = temporary / "environment-1"
    python = environment / "bin/python"
    consumer = temporary / "consumer"
    consumer.mkdir()
    run(["git", "init", "--quiet"], cwd=consumer, env=env)
    (consumer / "src").mkdir()
    (consumer / "src/example.py").write_text(
        "# src/example.py\nfrom __future__ import annotations\n\nVALUE = 1\n"
    )
    (consumer / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = ["ruff==0.15.14", "pyright==1.1.411"]\n'
        '[tool.nox-python-standards]\nsources = ["src"]\ndependency-group = "dev"\n'
        '[tool.nox-python-standards.ruff]\nauthorized_version = "v0.15.14"\n'
        '[tool.pyright]\ninclude = ["src"]\n'
    )
    # Exclude developer environments so they cannot supply consumer-owned tools.
    system_paths = [
        entry
        for entry in env["PATH"].split(os.pathsep)
        if not any((Path(entry) / name).exists() for name in ("ruff", "pyright"))
    ]
    env["PATH"] = os.pathsep.join([str(environment / "bin"), *system_paths])
    cli = str(environment / "bin/nox-py-standards")
    run([cli, "sync"], cwd=consumer, env=env)
    run(
        [
            str(python),
            "-c",
            "from importlib import metadata, util; "
            "assert util.find_spec('ruff') is None; "
            "assert util.find_spec('pyright') is None; "
            "assert util.find_spec('nox_python_standards.headers') is None; "
            "assert util.find_spec('nox_python_standards.hooks') is None; "
            "assert metadata.requires('nox-py-standards') == ['tomlkit==0.15.0']",
        ],
        cwd=consumer,
        env=env,
    )
    before = (consumer / "pyproject.toml").read_bytes()
    missing = subprocess.run(
        [cli, "check"],
        cwd=consumer,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if missing.returncode != 1 or "Could not find 'ruff'" not in missing.stderr:
        raise RuntimeError(
            f"Check did not report missing consumer tool: {missing.stderr}"
        )
    if (consumer / "pyproject.toml").read_bytes() != before:
        raise RuntimeError("Check modified consumer settings")
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            "ruff==0.15.14",
            "pyright==1.1.411",
        ],
        cwd=consumer,
        env=env,
    )
    run([cli, "check"], cwd=consumer, env=env)
    run(
        [str(python), "-m", "nox_python_standards", "check"],
        cwd=consumer / "src",
        env=env,
    )
    run(
        [
            str(python),
            "-c",
            "from pathlib import Path; import nox_python_standards as package; "
            f"assert Path(package.__file__).is_relative_to({str(environment)!r})",
        ],
        cwd=consumer,
        env=env,
    )
    sys.stdout.write(
        "Wheel/sdist resources and clean non-editable installation passed.\n"
    )


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="nox-standards-distribution-") as directory:
        verify(Path(__file__).resolve().parents[1], Path(directory))
