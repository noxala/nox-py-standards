# test/test_docs.py
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

_COMO_POLICY = """\
[tool.nox-python-standards.docs]
include = ["**/AGENTS.md", "ARCHITECTURE.md", "README.md", "docs/**/*.md"]
exclude = ["docs/generated/**", "docs/adr/[0-9]*.md"]
required = ["AGENTS.md", "ARCHITECTURE.md", "docs/README.md", "docs/workflows"]

[[tool.nox-python-standards.docs.budgets]]
include = ["**/AGENTS.md"]
max-bytes = 8192

[[tool.nox-python-standards.docs.budgets]]
include = ["ARCHITECTURE.md"]
max-bytes = 16384

[[tool.nox-python-standards.docs.catalogs]]
path = "docs/README.md"
include = ["docs/**/*.md", "*.md"]
exclude = ["AGENTS.md", "ARCHITECTURE.md", "README.md", "docs/generated/**"]

[[tool.nox-python-standards.docs.metadata]]
include = ["docs/workflows/**/*.md"]
exclude = ["**/README.md"]
fields = ["Status", "Read when", "Authority"]
path-fields = ["Authority"]
path-sections = ["Code and tests"]

[[tool.nox-python-standards.docs.routers]]
path = "ARCHITECTURE.md"
section = "Task router"
columns = ["Task", "Read", "Implementation authority"]
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_checker(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "nox_python_standards.docs_cli",
            "--root",
            str(repo_root),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_valid_repository(repo_root: Path) -> None:
    subprocess.run(["git", "init", "--quiet", str(repo_root)], check=True)
    _write(repo_root / "pyproject.toml", _COMO_POLICY)
    _write(
        repo_root / "AGENTS.md",
        "# Instructions\n\nSee [architecture](ARCHITECTURE.md).\n",
    )
    _write(repo_root / "README.md", "# Repository\n\nSee [catalog](docs/README.md).\n")
    _write(
        repo_root / "db_models/AGENTS.md",
        "# DB instructions\n\nSee "
        "[persistence](../docs/architecture/persistence.md).\n",
    )
    _write(
        repo_root / "ARCHITECTURE.md",
        """\
# Architecture

See [catalog](docs/README.md).

## Task router

| Task | Read | Implementation authority |
| --- | --- | --- |
| Example | [workflow](docs/workflows/example.md) | `application/example.py` |
| Persistence | [guide](docs/architecture/persistence.md) | `db_models/` |

## System
""",
    )
    _write(
        repo_root / "docs/README.md",
        """\
# Catalog

- [Persistence](architecture/persistence.md)
- [Example workflow](workflows/example.md)
- [Domain](DOMAIN.md)
- [ADRs](adr/README.md)
- [Design](design-docs/current-design.md)
""",
    )
    _write(
        repo_root / "docs/architecture/persistence.md",
        "# Persistence\n\nSee [domain](../DOMAIN.md#domain).\n",
    )
    _write(
        repo_root / "docs/workflows/example.md",
        """\
# Example workflow

- Status: Current
- Read when: Changing the example workflow
- Authority: `application/example.py` and mirrored tests
- Related: [`../architecture/persistence.md`](../architecture/persistence.md)

## Responsibility

## Code and tests

- `application/example.py`
- `test/example_test/`
""",
    )
    _write(repo_root / "docs/DOMAIN.md", "# Domain\n")
    _write(
        repo_root / "docs/design-docs/current-design.md",
        "# Design\n\nSee [domain](../DOMAIN.md).\n",
    )
    _write(
        repo_root / "docs/adr/README.md", "# ADRs\n\n- [0001](0001-old-decision.md)\n"
    )
    _write(
        repo_root / "docs/adr/0001-old-decision.md",
        "# Historical decision\n\n[Historical broken link](missing-history.md)\n",
    )
    _write(
        repo_root / "docs/generated/MODULE_MAP.md",
        "# Generated\n\n[Generated broken link](missing-generated.md)\n",
    )
    _write(repo_root / "application/example.py", "# application/example.py\n")
    _write(repo_root / "db_models/__init__.py", "# db_models/__init__.py\n")
    _write(
        repo_root / "test/example_test/__init__.py", "# test/example_test/__init__.py\n"
    )


def test_como_policy_passes(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nox-docs-check" in result.stdout
    assert "passed" in result.stdout


def test_size_ceiling_failure_is_actionable(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(tmp_path / "AGENTS.md", "x" * (8 * 1024 + 1))
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "AGENTS.md is 8193 bytes; limit is 8192" in result.stderr


def test_broken_repository_relative_markdown_link_fails(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/architecture/persistence.md"
    path.write_text(path.read_text() + "\n[Missing](missing.md)\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert (
        "docs/architecture/persistence.md has broken link: missing.md" in result.stderr
    )


def test_root_readme_links_are_checked(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(tmp_path / "README.md", "# Repository\n\n[Missing](missing.md)\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "README.md has broken link: missing.md" in result.stderr


def test_reference_style_local_links_are_checked(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/architecture/persistence.md"
    path.write_text(path.read_text() + "\nSee [missing][ref].\n\n[ref]: missing.md\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "has broken link: missing.md" in result.stderr


def test_undefined_reference_style_link_fails(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/architecture/persistence.md"
    path.write_text(path.read_text() + "\nSee [missing][ref].\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "undefined link reference: [ref]" in result.stderr


def test_existing_markdown_heading_fragment_passes(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/architecture/persistence.md"
    path.write_text(path.read_text() + "\nSee [domain](../DOMAIN.md#domain).\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_missing_markdown_heading_fragment_fails(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/architecture/persistence.md"
    path.write_text(
        path.read_text() + "\nSee [missing](../DOMAIN.md#missing-section).\n"
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "missing heading fragment: ../DOMAIN.md#missing-section" in result.stderr


def test_same_document_heading_fragment_is_checked(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "docs/architecture/persistence.md",
        "# Persistence\n\nSee [details](#details).\n\n## Details\n",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_empty_link_destination_is_actionable_and_other_errors_continue(
    tmp_path: Path,
) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/architecture/persistence.md"
    path.write_text(path.read_text() + "\n[Empty](   )\n[Missing](missing.md)\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "malformed link: empty link destination" in result.stderr
    assert "broken link: missing.md" in result.stderr
    assert "Traceback" not in result.stderr


def test_catalog_requires_focused_documents_to_be_discoverable(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    catalog_path = tmp_path / "docs/README.md"
    catalog_path.write_text(
        catalog_path.read_text().replace(
            "- [Design](design-docs/current-design.md)\n", ""
        )
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "docs/design-docs/current-design.md is not represented" in result.stderr


def test_maintained_root_guidance_must_be_cataloged(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(tmp_path / "CONTRIBUTING.md", "# Contributing\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "CONTRIBUTING.md is not represented" in result.stderr


def test_cataloged_subtree_readme_must_index_its_documents(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(tmp_path / "docs/adr/README.md", "# ADRs\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "docs/adr/0001-old-decision.md is not represented" in result.stderr


def test_cataloged_subtree_accepts_multiline_markdown_link_label(
    tmp_path: Path,
) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "docs/adr/README.md",
        "# ADRs\n\n- [0001: Historical\n  decision](0001-old-decision.md)\n",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_requires_metadata_and_existing_authority_path(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "docs/workflows/example.md",
        """\
# Example workflow

- Status: Current
- Authority: `application/missing.py`

## Code and tests

- `application/example.py`
- `test/example_test/`
""",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "missing '- Read when: ...' metadata" in result.stderr
    assert "Authority references missing path: application/missing.py" in result.stderr


def test_workflow_metadata_inside_fence_does_not_count(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "docs/workflows/example.md",
        """\
# Example workflow

```
- Status: Current
- Read when: Changing the example workflow
- Authority: `application/example.py`
```

## Code and tests

- `application/example.py`
- `test/example_test/`
""",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "missing '- Status: ...' metadata" in result.stderr
    assert "missing '- Read when: ...' metadata" in result.stderr
    assert "missing '- Authority: ...' metadata" in result.stderr


def test_nested_workflow_documents_require_metadata(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "docs/workflows/nested/other.md",
        "# Other workflow\n\n## Code and tests\n\n- `application/example.py`\n",
    )
    catalog_path = tmp_path / "docs/README.md"
    catalog_path.write_text(
        catalog_path.read_text() + "\n- [Other](workflows/nested/other.md)\n"
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert (
        "docs/workflows/nested/other.md is missing '- Status: ...' metadata"
        in result.stderr
    )


def test_workflow_code_and_tests_paths_must_exist(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/workflows/example.md"
    path.write_text(
        path.read_text().replace("`test/example_test/`", "`test/missing_test/`")
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "Code and tests references missing path: test/missing_test/" in result.stderr


def test_workflow_requires_code_and_tests_section(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "docs/workflows/example.md"
    code_and_tests = (
        "\n## Code and tests\n\n- `application/example.py`\n- `test/example_test/`\n"
    )
    path.write_text(path.read_text().replace(code_and_tests, ""))
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "is missing '## Code and tests'" in result.stderr


def test_task_router_rejects_missing_source_path(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    path = tmp_path / "ARCHITECTURE.md"
    path.write_text(
        path.read_text().replace("`application/example.py`", "`application/missing.py`")
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert (
        "Task router references missing path: application/missing.py" in result.stderr
    )


def test_task_router_requires_at_least_one_task_row(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "ARCHITECTURE.md",
        "# Architecture\n\n## Task router\n\nNo routed tasks yet.\n\n## System\n",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "ARCHITECTURE.md Task router has no task rows" in result.stderr


def test_generated_docs_and_historical_adr_bodies_are_not_content_checked(
    tmp_path: Path,
) -> None:
    _write_valid_repository(tmp_path)
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "missing-generated.md" not in result.stderr
    assert "missing-history.md" not in result.stderr
