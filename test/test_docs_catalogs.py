# test/test_docs_catalogs.py
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from nox_python_standards.docs_cli import main

_HEADER = (
    "| Document | Status | Read when | Authority | Notes |\n"
    "| --- | --- | --- | --- | --- |\n"
)
_POLICY = """\
[tool.nox-python-standards.docs]
include = ["*.md", "docs/*.md"]
exclude = ["docs/HISTORY.md"]

[[tool.nox-python-standards.docs.catalogs]]
path = "docs/README.md"
include = ["docs/*.md"]
require-content-check = true

[[tool.nox-python-standards.docs.catalogs.tables]]
columns = ["Document", "Status", "Read when", "Authority", "Notes"]
document-column = "Document"
required-columns = ["Document", "Status", "Read when", "Authority"]
path-columns = ["Authority"]
[tool.nox-python-standards.docs.catalogs.tables.accepted-values]
Status = ["Current", "Planned (not implemented)", "Decision history"]
"""
_GUIDE_ROW = (
    "| [Guide](GUIDE.md#details) | Current | Code changes | "
    "`src/example.py::symbol` | |\n"
)
_PLAN_ROW = "| [Plan][plan] | Planned (not implemented) | Design changes | `src/` | |\n"
_HISTORY_ROW = (
    "| [History](HISTORY.md) | Decision history | Old decisions | "
    "`docs/HISTORY.md` | |\n"
)


@pytest.fixture
def catalog_consumer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text(_POLICY)
    (tmp_path / "docs/README.md").write_text(
        "# Catalog\n\n## Guides\n\n"
        + _HEADER
        + _GUIDE_ROW
        + _PLAN_ROW
        + "\n## Decisions\n\n"
        + _HEADER
        + _HISTORY_ROW
        + "\n[plan]: PLAN.md\n"
    )
    (tmp_path / "docs/GUIDE.md").write_text("# Guide\n## Details\n")
    (tmp_path / "docs/PLAN.md").write_text("# Plan\n")
    (tmp_path / "docs/HISTORY.md").write_text("# History\n[Old](absent.md)\n")
    (tmp_path / "src/example.py").write_text(
        'raise RuntimeError("consumer imported")\n'
    )
    return tmp_path


def test_categorized_tables_preserve_qualifiers_paths_and_history(
    catalog_consumer: Path,
) -> None:
    assert main([]) == 0


@pytest.mark.parametrize(
    ("old", "new", "diagnostic"),
    [
        (
            "| Document | Status | Read when | Authority | Notes |",
            "| Document | State | Read when | Authority | Notes |",
            "requires columns: Document, Status",
        ),
        ("| Current |", "| TBD |", "column 'Status' has unsupported value 'TBD'"),
        (
            "Planned (not implemented)",
            "Planned",
            "column 'Status' has unsupported value 'Planned'",
        ),
        ("| Code changes |", "| |", "column 'Read when' must be nonempty"),
        (
            "[Guide](GUIDE.md#details)",
            "Guide pending",
            "column 'Document' must contain a local Markdown document link",
        ),
        (
            "[Guide](GUIDE.md#details)",
            "`[Guide](GUIDE.md#details)`",
            "column 'Document' must contain",
        ),
        (
            "[Guide](GUIDE.md#details)",
            "![Guide](GUIDE.md#details)",
            "column 'Document' must contain",
        ),
        (
            "[Guide](GUIDE.md#details)",
            "[Guide](https://example.invalid/GUIDE.md)",
            "column 'Document' must contain",
        ),
        (
            "[Guide](GUIDE.md#details)",
            "[Source](../src/example.py)",
            "column 'Document' must contain",
        ),
        (
            "[Guide](GUIDE.md#details)",
            "[Directory](../src/)",
            "column 'Document' must contain",
        ),
        (
            "[Guide](GUIDE.md#details)",
            "[Guide](GUIDE.md#absent)",
            "column 'Document' must contain",
        ),
        (
            "`src/example.py::symbol`",
            "Implementation",
            "column 'Authority' must declare at least one repository path",
        ),
        (
            "`src/example.py::symbol`",
            "`src/absent.py`",
            "column 'Authority' references missing path: src/absent.py",
        ),
        (
            "| Code changes |",
            "| Code changes | extra |",
            "contains missing or extra cells",
        ),
        ("| Code changes |", "|", "contains missing or extra cells"),
    ],
)
def test_invalid_catalog_rows_have_actionable_diagnostics(
    catalog_consumer: Path,
    old: str,
    new: str,
    diagnostic: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = catalog_consumer / "docs/README.md"
    path.write_text(path.read_text().replace(old, new))
    assert main([]) == 1
    error = capsys.readouterr().err
    assert "docs/README.md table 1" in error
    assert diagnostic in error


def test_later_tables_receive_validation(
    catalog_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = catalog_consumer / "docs/README.md"
    path.write_text(path.read_text().replace("Decision history", "TBD"))
    assert main([]) == 1
    assert "table 2" in capsys.readouterr().err


def test_list_links_cannot_bypass_table_coverage(
    catalog_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = catalog_consumer / "docs/README.md"
    path.write_text(
        path.read_text().replace(_GUIDE_ROW, "") + "\n- [Guide](GUIDE.md#details)\n"
    )
    assert main([]) == 1
    assert "docs/GUIDE.md is not represented" in capsys.readouterr().err


@pytest.mark.parametrize("wrapper", ["{}", "```md\n{}\n```", "`\n{}\n`"])
def test_a_catalog_without_real_tables_fails(
    catalog_consumer: Path, wrapper: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = catalog_consumer / "docs/README.md"
    body = (
        "[Guide](GUIDE.md)\n[Plan](PLAN.md)\n[History](HISTORY.md)"
        if wrapper == "{}"
        else _HEADER + _GUIDE_ROW
    )
    path.write_text(wrapper.format(body))
    assert main([]) == 1
    assert "has no catalog tables; requires columns:" in capsys.readouterr().err


def test_link_list_remains_valid_without_table_rules(catalog_consumer: Path) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.split("[[tool.nox-python-standards.docs.catalogs.tables]]")[0]
    )
    (catalog_consumer / "docs/README.md").write_text(
        "[Guide](GUIDE.md)\n[Plan](PLAN.md)\n[History](HISTORY.md)\n"
    )
    assert main([]) == 0


def test_required_columns_default_to_all_columns(
    catalog_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.replace(
            'required-columns = ["Document", "Status", "Read when", "Authority"]\n', ""
        )
    )
    assert main([]) == 1
    assert "column 'Notes' must be nonempty" in capsys.readouterr().err


def test_table_rules_can_differ_by_catalog_section(catalog_consumer: Path) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.replace("columns = [", 'section = "Guides"\ncolumns = [', 1)
        + """\
[[tool.nox-python-standards.docs.catalogs.tables]]
section = "Decisions"
columns = ["Document", "Status", "Read when", "Authority", "Notes"]
document-column = "Document"
required-columns = ["Status", "Read when", "Authority"]
accepted-values = { Status = ["Decision history"] }
"""
    )
    path = catalog_consumer / "docs/README.md"
    path.write_text(
        path.read_text().replace("`docs/HISTORY.md`", "Historical decisions")
    )
    assert main([]) == 0


def test_unmatched_section_rule_is_not_a_silent_pass(
    catalog_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.replace("columns = [", 'section = "Missing"\ncolumns = [', 1)
    )
    assert main([]) == 1
    assert "is missing '## Missing'" in capsys.readouterr().err


def test_catalog_failures_are_read_only(catalog_consumer: Path) -> None:
    path = catalog_consumer / "docs/README.md"
    path.write_text(path.read_text().replace("| Current |", "| TBD |"))
    before = {
        p: p.read_bytes()
        for p in catalog_consumer.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    assert main([]) == 1
    assert before == {
        p: p.read_bytes()
        for p in catalog_consumer.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }


def test_catalog_column_names_and_status_vocabulary_are_consumer_owned(
    catalog_consumer: Path,
) -> None:
    for name in ("pyproject.toml", "docs/README.md"):
        path = catalog_consumer / name
        text = path.read_text()
        for old, new in (
            ("Document", "Guide"),
            ("Status", "Lifecycle"),
            ("Read when", "Use for"),
            ("Authority", "Owner"),
            ("Current", "Active"),
        ):
            text = text.replace(old, new)
        path.write_text(text)
    assert main([]) == 0


def test_generated_status_qualifiers_remain_explicit(catalog_consumer: Path) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.replace(
            '"Decision history"]', '"Decision history", "Generated (projection only)"]'
        )
    )
    (catalog_consumer / "docs/GENERATED.md").write_text("# Generated\n")
    catalog = catalog_consumer / "docs/README.md"
    catalog.write_text(
        catalog.read_text().replace(
            _HISTORY_ROW,
            _HISTORY_ROW
            + "| [Generated](GENERATED.md) | Generated (projection only) | "
            "Module ownership | `docs/GENERATED.md` | |\n",
        )
    )
    assert main([]) == 0


def test_cataloged_subtree_readme_retains_indirect_history_discovery(
    catalog_consumer: Path,
) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.replace("docs/*.md", "docs/**/*.md").replace(
            'exclude = ["docs/HISTORY.md"]',
            'exclude = ["docs/HISTORY.md", "docs/adr/0001.md"]',
        )
    )
    (catalog_consumer / "docs/adr").mkdir()
    (catalog_consumer / "docs/adr/README.md").write_text("# ADRs\n[0001](0001.md)\n")
    (catalog_consumer / "docs/adr/0001.md").write_text(
        "# Old decision\n[Old](absent.md)\n"
    )
    catalog = catalog_consumer / "docs/README.md"
    catalog.write_text(
        catalog.read_text().replace(
            _HISTORY_ROW,
            _HISTORY_ROW
            + "| [ADRs](adr/README.md) | Decision history | Old decisions | "
            "`docs/adr/README.md` | |\n",
        )
    )
    assert main([]) == 0


def test_catalog_tables_require_at_least_one_document_row(
    catalog_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = catalog_consumer / "docs/README.md"
    path.write_text(_HEADER)
    assert main([]) == 1
    assert "has no document rows" in capsys.readouterr().err


def test_document_only_table_needs_no_standard_metadata_columns(
    catalog_consumer: Path,
) -> None:
    config = catalog_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.split("[[tool.nox-python-standards.docs.catalogs.tables]]")[0]
        + """\
[[tool.nox-python-standards.docs.catalogs.tables]]
columns = ["Guide"]
document-column = "Guide"
"""
    )
    (catalog_consumer / "docs/README.md").write_text(
        "| Guide |\n| --- |\n| [Guide](GUIDE.md) |\n"
        "| [Plan](PLAN.md) |\n| [History](HISTORY.md) |\n"
    )
    assert main([]) == 0
