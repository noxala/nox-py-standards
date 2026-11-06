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
        'include = ["AGENTS.md", "docs/**/*.md"]\nrequired = ["AGENTS.md"]\n'
        "[[tool.nox-python-standards.docs.budgets]]\n"
        'include = ["AGENTS.md"]\nmax-words = 450\n'
    )
    (consumer / "AGENTS.md").write_text("# Guide\n[Details](docs/GUIDE.md#details)\n")
    (consumer / "docs/GUIDE.md").write_text("# Guide\n## Details\n")
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
    guide = consumer / "AGENTS.md"
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
            metadata["License-Expression"] != "0BSD"
            or metadata.get_all("License-File") != ["LICENSE"]
            or archive.read(license_path) != (root / "LICENSE").read_bytes()
        ):
            raise RuntimeError("Wheel license metadata or text differs from 0BSD")
    extracted = temporary / "extracted"
    with tarfile.open(sdist) as archive:
        if not required <= {Path(member.name).name for member in archive.getmembers()}:
            raise RuntimeError("Sdist missing policy resources")
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
            "assert metadata.requires('nox-python-standards') == ['tomlkit==0.15.0']",
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
