# tools/verify_distribution.py
from __future__ import annotations

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
    required = {"policy.json", "ownership.json", "PYTHON_CONVENTIONS.md"}
    with zipfile.ZipFile(wheel) as archive:
        if not required <= {Path(name).name for name in archive.namelist()}:
            raise RuntimeError("Wheel missing policy resources")
    extracted = temporary / "extracted"
    with tarfile.open(sdist) as archive:
        if not required <= {Path(member.name).name for member in archive.getmembers()}:
            raise RuntimeError("Sdist missing policy resources")
        archive.extractall(extracted, filter="data")
    rebuilt = temporary / "rebuilt"
    run(
        [uv, "build", "--wheel", "--out-dir", str(rebuilt)],
        cwd=next(extracted.iterdir()),
        env=env,
    )
    environment = temporary / "environment"
    run(
        [uv, "venv", "--python", sys.executable, str(environment)],
        cwd=temporary,
        env=env,
    )
    python = environment / "bin/python"
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            str(next(rebuilt.glob("*.whl"))),
        ],
        cwd=temporary,
        env=env,
    )
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
    env["PATH"] = str(environment / "bin") + os.pathsep + env["PATH"]
    cli = str(environment / "bin/nox-py-standards")
    for arguments in (["config", "sync"], ["config", "check"], ["check"]):
        run([cli, *arguments], cwd=consumer, env=env)
    run(
        [str(python), "-m", "nox_python_standards", "config", "check"],
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
