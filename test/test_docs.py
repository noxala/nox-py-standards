# test/test_docs.py
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

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


@pytest.mark.parametrize(
    "replacement",
    [
        "[unused-persistence]: architecture/persistence.md",
        "`[Persistence](architecture/persistence.md)`",
        "``[Persistence](architecture/persistence.md) with ` inside``",
        "`[Persistence][ref]`\n[ref]: architecture/persistence.md",
        "```md\n[Persistence](architecture/persistence.md)\n```",
        "~~~md\n[Persistence](architecture/persistence.md)\n~~~",
    ],
)
def test_catalog_requires_rendered_links(tmp_path: Path, replacement: str) -> None:
    _write_valid_repository(tmp_path)
    catalog = tmp_path / "docs/README.md"
    catalog.write_text(
        catalog.read_text().replace(
            "- [Persistence](architecture/persistence.md)", replacement
        )
    )
    before = catalog.read_bytes()
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "docs/architecture/persistence.md is not represented" in result.stderr
    assert catalog.read_bytes() == before


@pytest.mark.parametrize("usage", ["[Persistence][guide]", "[guide][]"])
def test_catalog_accepts_rendered_reference_links(tmp_path: Path, usage: str) -> None:
    _write_valid_repository(tmp_path)
    catalog = tmp_path / "docs/README.md"
    catalog.write_text(
        catalog.read_text().replace(
            "- [Persistence](architecture/persistence.md)",
            f"- {usage}\n\n[guide]: architecture/persistence.md#persistence",
        )
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unused_reference_cannot_index_a_cataloged_subtree(tmp_path: Path) -> None:
    _write_valid_repository(tmp_path)
    _write(
        tmp_path / "docs/adr/README.md",
        "# ADRs\n\n[unused]: 0001-old-decision.md\n",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "docs/adr/0001-old-decision.md is not represented" in result.stderr


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


@pytest.fixture
def navigable_repository(tmp_path: Path) -> Path:
    _write_valid_repository(tmp_path)
    policy = _COMO_POLICY.replace(
        'include = ["**/AGENTS.md", "ARCHITECTURE.md", "README.md", "docs/**/*.md"]',
        'include = ["**/AGENTS.md", "*.md", "docs/**/*.md"]',
    ).replace(
        'path = "docs/README.md"',
        'path = "docs/README.md"\nrequire-content-check = true',
    )
    policy += """\
link-columns = ["Read"]
path-columns = ["Implementation authority"]

[[tool.nox-python-standards.docs.navigation]]
path = "AGENTS.md"
targets = ["ARCHITECTURE.md"]

[[tool.nox-python-standards.docs.navigation]]
path = "README.md"
targets = ["docs/README.md"]

[[tool.nox-python-standards.docs.navigation]]
path = "ARCHITECTURE.md"
targets = ["docs/README.md"]

[[tool.nox-python-standards.docs.navigation]]
path = "docs/architecture/persistence.md"
targets = ["docs/DOMAIN.md#domain"]
"""
    _write(tmp_path / "pyproject.toml", policy)
    return tmp_path


def test_navigation_policy_preserves_historical_body_exclusions(
    navigable_repository: Path,
) -> None:
    result = _run_checker(navigable_repository)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("source", ["AGENTS.md", "README.md", "ARCHITECTURE.md"])
def test_navigation_requires_every_configured_entry_link(
    navigable_repository: Path, source: str
) -> None:
    path = navigable_repository / source
    # Remove only the entry route, leaving all router rows intact.
    path.write_text(
        path.read_text().replace("See [", "See `[").replace(").\n", ").`\n")
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert f"{source} requires a navigation link to" in result.stderr


@pytest.mark.parametrize(
    "route",
    [
        "Documentation-sync guide",
        "`docs/workflows/example.md`",
        "`[workflow](docs/workflows/example.md)`",
        "[workflow](https://example.invalid/guide.md)",
        "[source](application/example.py)",
        "[directory](docs/workflows/)",
        "![workflow](docs/workflows/example.md)",
        "[workflow](docs/workflows/example.md#absent)",
    ],
)
def test_router_requires_a_real_document_link_in_each_configured_column(
    navigable_repository: Path, route: str
) -> None:
    path = navigable_repository / "ARCHITECTURE.md"
    path.write_text(
        path.read_text().replace("[workflow](docs/workflows/example.md)", route)
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "ARCHITECTURE.md Task router row 1 column 'Read'" in result.stderr
    assert "must contain a local Markdown document link" in result.stderr


@pytest.mark.parametrize("route", ["[workflow][example]", "[example][]"])
def test_router_resolves_reference_definitions_from_its_document(
    navigable_repository: Path, route: str
) -> None:
    path = navigable_repository / "ARCHITECTURE.md"
    path.write_text(
        path.read_text().replace("[workflow](docs/workflows/example.md)", route)
        + "\n[example]: docs/workflows/example.md#responsibility\n"
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("authority", ["Application code", "`application/missing.py`"])
def test_router_requires_source_paths_in_the_configured_column(
    navigable_repository: Path, authority: str
) -> None:
    path = navigable_repository / "ARCHITECTURE.md"
    path.write_text(path.read_text().replace("`application/example.py`", authority))
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "row 1 column 'Implementation authority'" in result.stderr


def test_router_cannot_borrow_a_source_path_from_another_column(
    navigable_repository: Path,
) -> None:
    path = navigable_repository / "ARCHITECTURE.md"
    path.write_text(
        path.read_text().replace(
            "| Example | [workflow](docs/workflows/example.md) | "
            "`application/example.py` |",
            "| `application/example.py` | [workflow](docs/workflows/example.md) | "
            "See code |",
        )
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "row 1 column 'Implementation authority' must declare" in result.stderr


def test_catalog_requires_maintained_documents_to_receive_content_checks(
    tmp_path: Path,
) -> None:
    _write_valid_repository(tmp_path)
    config = tmp_path / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            'path = "docs/README.md"',
            'path = "docs/README.md"\nrequire-content-check = true',
        )
    )
    _write(tmp_path / "CONTRIBUTING.md", "# Contributing\n[Broken](missing.md)\n")
    catalog = tmp_path / "docs/README.md"
    catalog.write_text(catalog.read_text() + "\n[Contributing](../CONTRIBUTING.md)\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert (
        "CONTRIBUTING.md selected by docs/README.md has no content check"
        in result.stderr
    )
    assert "docs.include" in result.stderr
    assert "docs.exclude" in result.stderr
    config.write_text(
        config.read_text().replace('"ARCHITECTURE.md", "README.md",', '"*.md",')
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "CONTRIBUTING.md has broken link: missing.md" in result.stderr
    assert "has no content check" not in result.stderr


@pytest.mark.parametrize("path", ["ARCHITECTURE.md", "docs/README.md"])
def test_policy_documents_are_link_checked_outside_general_selection(
    tmp_path: Path, path: str
) -> None:
    _write_valid_repository(tmp_path)
    config = tmp_path / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            'include = ["**/AGENTS.md", "ARCHITECTURE.md", "README.md", '
            '"docs/**/*.md"]',
            'include = ["AGENTS.md"]',
        )
    )
    document = tmp_path / path
    document.write_text(document.read_text() + "\n[Broken](absent.md)\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert f"{path} has broken link: absent.md" in result.stderr


def test_navigation_sources_are_checked_and_links_resolve_from_source_directory(
    tmp_path: Path,
) -> None:
    _write_valid_repository(tmp_path)
    config = tmp_path / "pyproject.toml"
    config.write_text(
        config.read_text()
        + """\
[[tool.nox-python-standards.docs.navigation]]
path = "extra/ROUTES.md"
targets = ["docs/DOMAIN.md#domain"]
"""
    )
    _write(tmp_path / "extra/ROUTES.md", "[Domain](../docs/DOMAIN.md#domain)\n")
    assert _run_checker(tmp_path).returncode == 0
    _write(
        tmp_path / "extra/ROUTES.md",
        "[Domain](../docs/DOMAIN.md#domain)\n[Broken](absent.md)",
    )
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert "extra/ROUTES.md has broken link: absent.md" in result.stderr


@pytest.mark.parametrize("destination", ["../DOMAIN.md", "../DOMAIN.md#absent"])
def test_required_fragment_cannot_be_substituted_with_a_different_link(
    navigable_repository: Path, destination: str
) -> None:
    path = navigable_repository / "docs/architecture/persistence.md"
    path.write_text(f"# Persistence\n[Domain]({destination})\n")
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "requires a navigation link to docs/DOMAIN.md#domain" in result.stderr


@pytest.mark.parametrize(
    "route", ["[domain]: ../DOMAIN.md#domain", "![Domain](../DOMAIN.md#domain)"]
)
def test_definitions_and_images_cannot_satisfy_required_navigation(
    navigable_repository: Path, route: str
) -> None:
    _write(
        navigable_repository / "docs/architecture/persistence.md",
        f"# Persistence\n{route}\n",
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "requires a navigation link to docs/DOMAIN.md#domain" in result.stderr


def test_coverage_rule_with_no_catalog_members_is_actionable(
    navigable_repository: Path,
) -> None:
    config = navigable_repository / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            'include = ["docs/**/*.md", "*.md"]', 'include = ["docs/README.md"]'
        )
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert (
        "catalog include patterns matched no files other than the catalog"
        in result.stderr
    )


def test_explicit_content_exclusion_preserves_catalog_discovery(
    navigable_repository: Path,
) -> None:
    config = navigable_repository / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            'exclude = ["docs/generated/**", "docs/adr/[0-9]*.md"]',
            'exclude = ["docs/generated/**", "docs/adr/[0-9]*.md", "docs/DOMAIN.md"]',
        )
    )
    _write(
        navigable_repository / "docs/DOMAIN.md", "# Domain\n[Historical](absent.md)\n"
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("source", ["ARCHITECTURE.md", "docs/README.md"])
def test_policy_documents_cannot_exclude_their_own_links(
    tmp_path: Path, source: str
) -> None:
    _write_valid_repository(tmp_path)
    config = tmp_path / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            'exclude = ["docs/generated/**", "docs/adr/[0-9]*.md"]',
            f'exclude = ["docs/generated/**", "docs/adr/[0-9]*.md", "{source}"]',
        )
    )
    path = tmp_path / source
    path.write_text(path.read_text() + "\n[Broken](absent.md)\n")
    result = _run_checker(tmp_path)
    assert result.returncode == 1
    assert f"{source} has broken link: absent.md" in result.stderr


def test_router_link_requirement_applies_to_later_rows(
    navigable_repository: Path,
) -> None:
    path = navigable_repository / "ARCHITECTURE.md"
    path.write_text(
        path.read_text().replace(
            "[guide](docs/architecture/persistence.md)", "Guide pending"
        )
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "row 2 column 'Read' must contain" in result.stderr


def test_router_source_tokens_support_file_symbols(navigable_repository: Path) -> None:
    path = navigable_repository / "ARCHITECTURE.md"
    path.write_text(
        path.read_text().replace(
            "`application/example.py`", "`application/example.py::symbol`"
        )
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 0, result.stderr


def test_navigation_without_required_fragment_accepts_a_section_link(
    navigable_repository: Path,
) -> None:
    path = navigable_repository / "AGENTS.md"
    path.write_text(
        path.read_text().replace("(ARCHITECTURE.md)", "(ARCHITECTURE.md#system)")
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 0, result.stderr


def test_navigation_failures_are_read_only(navigable_repository: Path) -> None:
    _write(navigable_repository / "AGENTS.md", "# Instructions\nSee architecture.\n")
    before = {
        p: p.read_bytes()
        for p in navigable_repository.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    after = {
        p: p.read_bytes()
        for p in navigable_repository.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    assert before == after


@pytest.mark.parametrize("target", ["absent.md", "docs/DOMAIN.md#absent"])
def test_ineffective_navigation_targets_are_actionable(
    navigable_repository: Path, target: str
) -> None:
    config = navigable_repository / "pyproject.toml"
    config.write_text(
        config.read_text().replace(
            'targets = ["docs/DOMAIN.md#domain"]', f'targets = ["{target}"]'
        )
    )
    result = _run_checker(navigable_repository)
    assert result.returncode == 1
    assert "navigation target" in result.stderr
    assert target in result.stderr
