# test/test_docs_config.py
from __future__ import annotations

from pathlib import Path

import pytest

from nox_python_standards.config import Configuration
from nox_python_standards.docs_config import DocsConfiguration
from nox_python_standards.repository import StandardsError


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"include": []},
        {"include": "*.md"},
        {"include": [""]},
        {"include": ["../*.md"]},
        {"include": ["/tmp/*.md"]},
        {"include": ["docs\\*.md"]},
        {"include": ["*.md"], "typo": True},
        {"include": ["*.md"], "required": ["*.md"]},
        {"include": ["*.md"], "required": ["../secret"]},
        {"include": ["*.md"], "budgets": {}},
        {"include": ["*.md"], "budgets": [{"include": ["*.md"]}]},
        {"include": ["*.md"], "budgets": [{"include": ["*.md"], "max-words": True}]},
        {"include": ["*.md"], "budgets": [{"include": ["*.md"], "max-bytes": 0}]},
        {"include": ["*.md"], "budgets": [{"include": ["*.md"], "max-words": 4.5}]},
        {"include": ["*.md"], "catalogs": [{"include": ["*.md"]}]},
        {"include": ["*.md"], "metadata": [{"include": ["*.md"]}]},
        {"include": ["*.md"], "routers": [{"path": "A.md", "columns": ["Task"]}]},
    ],
)
def test_invalid_policy_is_actionable(value: object) -> None:
    with pytest.raises(StandardsError, match=r"tool\.nox-python-standards\.docs"):
        DocsConfiguration.create(value)


def test_standards_check_and_sync_preserve_local_docs_policy(consumer: Path) -> None:
    path = consumer / "pyproject.toml"
    with path.open("a") as stream:
        stream.write(
            '\n[tool.nox-python-standards.docs]\ninclude = ["**/AGENTS.md"] # local\n'
            "\n[[tool.nox-python-standards.docs.budgets]]\n"
            'include = ["AGENTS.md"]\nmax-words = 450\n'
            "\n[[tool.nox-python-standards.docs.navigation]]\n"
            'path = "AGENTS.md"\ntargets = ["README.md"]\n'
        )
    before = path.read_bytes()
    Configuration.read(consumer).check()
    Configuration.read(consumer).sync()
    assert path.read_bytes() == before
    assert DocsConfiguration.read(consumer).budgets[0].max_words == 450
    assert DocsConfiguration.read(consumer).navigation[0].targets[0].path == "README.md"


def test_missing_docs_policy_is_not_a_silent_pass(consumer: Path) -> None:
    with pytest.raises(StandardsError, match="docs: expected a TOML table"):
        DocsConfiguration.read(consumer)


@pytest.mark.parametrize(
    "rule",
    [
        {},
        {"path": "README.md"},
        {"path": "README.md", "targets": []},
        {"path": "README.md", "targets": "GUIDE.md"},
        {"path": "README.md", "targets": [1]},
        {"path": "README.md", "targets": ["GUIDE.md"], "typo": True},
        *[
            {"path": "README.md", "targets": [target]}
            for target in (
                "",
                "#details",
                "../GUIDE.md",
                "/GUIDE.md",
                "https://example.invalid/GUIDE.md",
                "GUIDE.md?query",
                "GUIDE.md#",
                "GUIDE.md# ",
                "docs%2F..%2FGUIDE.md",
                "*.md",
                "source.py",
                "docs/",
                "docs\\GUIDE.md",
            )
        ],
    ],
)
def test_invalid_navigation_policy_is_actionable(rule: object) -> None:
    with pytest.raises(StandardsError, match=r"docs.navigation\[0\]"):
        DocsConfiguration.create({"include": ["*.md"], "navigation": [rule]})


@pytest.mark.parametrize(
    "settings",
    [
        {"link-columns": []},
        {"link-columns": "Read"},
        {"link-columns": ["Unknown"]},
        {"link-columns": ["Read", "Read"]},
        {"path-columns": []},
        {"path-columns": [False]},
        {"path-columns": ["Unknown"]},
        {"columns": ["Task", "Read", "Read"]},
    ],
)
def test_invalid_router_column_rules_are_actionable(
    settings: dict[str, object],
) -> None:
    rule: dict[str, object] = {
        "path": "A.md",
        "section": "Routes",
        "columns": ["Task", "Read"],
    }
    rule.update(settings)
    with pytest.raises(StandardsError, match=r"docs.routers\[0\]"):
        DocsConfiguration.create({"include": ["*.md"], "routers": [rule]})


@pytest.mark.parametrize("value", [None, "true", 1, [], {}])
def test_coverage_option_requires_a_boolean(value: object) -> None:
    with pytest.raises(
        StandardsError, match="require-content-check: expected a boolean"
    ):
        DocsConfiguration.create(
            {
                "include": ["*.md"],
                "catalogs": [
                    {
                        "path": "README.md",
                        "include": ["*.md"],
                        "require-content-check": value,
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "settings",
    [
        {"typo": True},
        {"columns": []},
        {"columns": ["Doc", "Doc"]},
        {"document-column": "Missing"},
        {"document-column": 1},
        {"section": ""},
        {"section": None},
        {"section": 1},
        {"required-columns": ["Missing"]},
        {"required-columns": "Doc"},
        {"required-columns": ["Doc", "Doc"]},
        {"path-columns": []},
        {"path-columns": ["Missing"]},
        {"accepted-values": {}},
        {"accepted-values": []},
        {"accepted-values": {"Missing": ["Current"]}},
        {"accepted-values": {"Status": []}},
        {"accepted-values": {"Status": "Current"}},
        {"accepted-values": {"Status": [1]}},
    ],
)
def test_invalid_catalog_table_settings_are_actionable(
    settings: dict[str, object],
) -> None:
    rule: dict[str, object] = {"columns": ["Doc", "Status"], "document-column": "Doc"}
    rule.update(settings)
    with pytest.raises(StandardsError, match=r"docs.catalogs\[0\].tables\[0\]"):
        DocsConfiguration.create(
            {
                "include": ["*.md"],
                "catalogs": [
                    {"path": "README.md", "include": ["*.md"], "tables": [rule]}
                ],
            }
        )


@pytest.mark.parametrize("tables", [[], {}, [None], [{}]])
def test_catalog_table_rules_cannot_be_empty_or_malformed(tables: object) -> None:
    with pytest.raises(StandardsError, match=r"docs.catalogs\[0\].tables"):
        DocsConfiguration.create(
            {
                "include": ["*.md"],
                "catalogs": [
                    {"path": "README.md", "include": ["*.md"], "tables": tables}
                ],
            }
        )
