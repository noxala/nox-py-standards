# test/test_docs_cli.py
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from nox_python_standards.docs_cli import main

_NOX_TACH_POLICY = """\
[tool.nox-python-standards.docs]
include = ["AGENTS.md", "README.md", "docs/**/*.md", ".noxala/*.md"]
required = ["AGENTS.md"]

[[tool.nox-python-standards.docs.budgets]]
include = ["AGENTS.md"]
max-words = 450
"""


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }


@pytest.fixture
def docs_consumer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    _write(tmp_path, "pyproject.toml", _NOX_TACH_POLICY)
    _write(tmp_path, "AGENTS.md", "# Guide\n[Details](docs/GUIDE.md#details-1)\n")
    _write(tmp_path, "README.md", "# Package\n[Guide](AGENTS.md)\n")
    _write(tmp_path, "docs/GUIDE.md", "# Guide\n## Details\n## Details\n")
    _write(tmp_path, ".noxala/PYTHON_CONVENTIONS.md", "# Conventions\n")
    return tmp_path


def test_nox_tach_policy_runs_without_consumer_tools_or_imports(
    docs_consumer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(docs_consumer, "src/__init__.py", 'raise RuntimeError("do not import me")\n')
    # Keep Git accessible while making Ruff/Pyright unexecutable if invoked.
    directory = docs_consumer / "bin"
    directory.mkdir()
    for name in ("ruff", "pyright"):
        target = directory / name
        target.write_text("#!/bin/sh\nexit 99\n")
        target.chmod(0o755)
    monkeypatch.setenv("PATH", str(directory) + ":/usr/bin:/bin:/usr/local/bin")
    before = _snapshot(docs_consumer)
    monkeypatch.chdir(docs_consumer / "docs")
    assert main([]) == 0
    assert main(["--root", str(docs_consumer)]) == 0
    assert _snapshot(docs_consumer) == before


def test_nox_tach_word_budget_boundary(
    docs_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(docs_consumer, "AGENTS.md", "word " * 450)
    assert main([]) == 0
    _write(docs_consumer, "AGENTS.md", "word " * 451)
    before = _snapshot(docs_consumer)
    assert main([]) == 1
    assert "AGENTS.md is 451 words; limit is 450" in capsys.readouterr().err
    assert _snapshot(docs_consumer) == before


@pytest.mark.parametrize("path", ["docs/GUIDE.md", ".noxala/PYTHON_CONVENTIONS.md"])
def test_all_nox_tach_document_scopes_are_checked(
    docs_consumer: Path, path: str
) -> None:
    _write(docs_consumer, path, "# Guide\n[Missing](missing.md)\n")
    assert main([]) == 1


def test_byte_budget_counts_original_utf8_bytes(
    docs_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (docs_consumer / "pyproject.toml").open("a") as stream:
        stream.write("max-bytes = 4\n")
    _write(docs_consumer, "AGENTS.md", "éé")
    assert main([]) == 0
    _write(docs_consumer, "AGENTS.md", "ééé")
    assert main([]) == 1
    assert "AGENTS.md is 6 bytes; limit is 4" in capsys.readouterr().err


def test_external_urls_and_fenced_examples_are_not_fetched(docs_consumer: Path) -> None:
    _write(
        docs_consumer,
        "AGENTS.md",
        "# Guide\n[External](https://invalid.example/absent#missing)\n"
        "[Mail](mailto:person@example.invalid)\n[Site](/site/path)\n"
        "[Network](//invalid.example/path)\n"
        "```md\n[Example](missing.md)\n```\n"
        "~~~md\n[Example](also-missing.md)\n~~~\n",
    )
    assert main([]) == 0


def test_encoded_paths_reference_links_and_non_markdown_fragments(
    docs_consumer: Path,
) -> None:
    _write(docs_consumer, "docs/with space.md", "# Déjà vu\n")
    _write(docs_consumer, "src/example.py", "VALUE = 1\n")
    _write(
        docs_consumer,
        "AGENTS.md",
        "# Guide\n[Space](docs/with%20space.md#d%C3%A9j%C3%A0-vu)\n"
        "[Code](src/example.py#L1)\n[Guide][Details]\n"
        '[Details]: docs/GUIDE.md#details-1 "Title"\n'
        "[details][]\n",
    )
    assert main([]) == 0


def test_local_image_links_are_checked(docs_consumer: Path) -> None:
    _write(docs_consumer, "README.md", "# Package\n![Missing](missing.png)\n")
    assert main([]) == 1


def test_parent_and_symlink_escapes_are_rejected(
    docs_consumer: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "guide.md"
    outside.write_text("# Outside\n")
    (docs_consumer / "escape.md").symlink_to(outside)
    _write(docs_consumer, "AGENTS.md", "# Guide\n[Escape](escape.md)\n")
    assert main([]) == 1
    _write(docs_consumer, "AGENTS.md", "# Guide\n[Escape](../outside.md)\n")
    assert main([]) == 1


@pytest.mark.parametrize("contents", ["[broken", "[tool.nox-python-standards]\n"])
def test_invalid_toml_or_missing_policy_fails_read_only(
    docs_consumer: Path, contents: str
) -> None:
    _write(docs_consumer, "pyproject.toml", contents)
    before = _snapshot(docs_consumer)
    assert main([]) == 1
    assert _snapshot(docs_consumer) == before


def test_missing_required_guide_and_empty_selection_fail(docs_consumer: Path) -> None:
    (docs_consumer / "AGENTS.md").unlink()
    assert main([]) == 1
    _write(
        docs_consumer,
        "pyproject.toml",
        '[tool.nox-python-standards.docs]\ninclude = ["absent/*.md"]\n',
    )
    assert main([]) == 1


def test_bad_explicit_root_is_actionable(docs_consumer: Path) -> None:
    assert main(["--root", str(docs_consumer / "docs")]) == 1


def test_version_does_not_need_consumer_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert "0.4.2" in capsys.readouterr().out


def test_complete_compact_documentation_example(docs_consumer: Path) -> None:
    policy = Path(__file__).resolve().parents[1] / "docs/examples/compact.toml"
    _write(docs_consumer, "pyproject.toml", policy.read_text())
    before = _snapshot(docs_consumer)
    assert main([]) == 0
    assert _snapshot(docs_consumer) == before
