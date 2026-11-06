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
        )
    before = path.read_bytes()
    Configuration.read(consumer).check()
    Configuration.read(consumer).sync()
    assert path.read_bytes() == before
    assert DocsConfiguration.read(consumer).budgets[0].max_words == 450


def test_missing_docs_policy_is_not_a_silent_pass(consumer: Path) -> None:
    with pytest.raises(StandardsError, match="docs: expected a TOML table"):
        DocsConfiguration.read(consumer)
