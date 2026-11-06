# test/test_docs_metadata.py
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from nox_python_standards.docs_cli import main

_POLICY = """\
[tool.nox-python-standards.docs]
include = ["docs/*.md"]

[[tool.nox-python-standards.docs.metadata]]
include = ["docs/FLOW.md"]
fields = ["Status", "Read when"]
accepted-values = { Status = ["Current", "Planned (not implemented)"] }

[[tool.nox-python-standards.docs.metadata.path-groups]]
name = "implementation"
section = "Code and tests"
include = ["pkg/**/*.py"]

[[tool.nox-python-standards.docs.metadata.path-groups]]
name = "tests"
section = "Code and tests"
include = ["checks/**/*.py"]
"""
_WORKFLOW = """\
# Workflow

- Status: Current
- Read when: Changing the workflow
- Authority: `pkg/worker.py`

## Code and tests

- `pkg/worker.py::handler`
- `checks/test_worker.py::case`
"""


@pytest.fixture
def metadata_consumer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    for directory in ("docs", "pkg", "checks"):
        (tmp_path / directory).mkdir()
    (tmp_path / "pyproject.toml").write_text(_POLICY)
    (tmp_path / "docs/FLOW.md").write_text(_WORKFLOW)
    for filename in ("pkg/worker.py", "checks/test_worker.py"):
        (tmp_path / filename).write_text('raise RuntimeError("consumer imported")\n')
    return tmp_path


def test_metadata_status_and_path_groups_pass_without_imports(
    metadata_consumer: Path,
) -> None:
    assert main([]) == 0


@pytest.mark.parametrize("status", ["TBD", "current", "Planned"])
def test_unaccepted_workflow_status_fails(
    metadata_consumer: Path, status: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("Status: Current", f"Status: {status}")
    )
    assert main([]) == 1
    assert (
        f"docs/FLOW.md Status has unsupported value {status!r}"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    "status", ["Planned (not implemented)", "Planned\n  (not implemented)"]
)
def test_status_qualifiers_survive_continuation_lines(
    metadata_consumer: Path, status: str
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("Status: Current", f"Status: {status}")
    )
    assert main([]) == 0


def test_accepted_values_can_independently_require_consumer_named_fields(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "pyproject.toml").write_text("""\
[tool.nox-python-standards.docs]
include = ["docs/*.md"]
[[tool.nox-python-standards.docs.metadata]]
include = ["docs/FLOW.md"]
accepted-values = { Lifecycle = ["Active"] }
""")
    path = metadata_consumer / "docs/FLOW.md"
    path.write_text("- Lifecycle: Active\n")
    assert main([]) == 0
    path.write_text("# No metadata\n")
    assert main([]) == 1
    assert "missing '- Lifecycle: ...' metadata" in capsys.readouterr().err


def test_repeating_implementation_does_not_satisfy_tests(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("checks/test_worker.py::case", "./pkg/worker.py::other")
    )
    assert main([]) == 1
    assert (
        "path group 'tests' must declare an existing file matching: checks/**/*.py"
        in capsys.readouterr().err
    )


def test_path_groups_require_distinct_resolved_entry_points_when_patterns_overlap(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "pyproject.toml").write_text(
        _POLICY.replace("checks/**/*.py", "pkg/**/*.py")
    )
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("checks/test_worker.py::case", "./pkg/worker.py::other")
    )
    assert main([]) == 1
    assert (
        "path group 'tests' requires a distinct repository entry point"
        in capsys.readouterr().err
    )


def test_overlapping_groups_can_reassign_candidates_to_satisfy_every_group(
    metadata_consumer: Path,
) -> None:
    (metadata_consumer / "pyproject.toml").write_text(
        _POLICY.replace('include = ["pkg/**/*.py"]', 'include = ["**/*.py"]')
    )
    assert main([]) == 0


def test_group_directories_are_explicit_and_patterns_match_the_directory_itself(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("checks/test_worker.py::case", "checks/")
    )
    config = metadata_consumer / "pyproject.toml"
    config.write_text(
        _POLICY.replace(
            'include = ["checks/**/*.py"]', 'include = ["checks", "checks/**"]'
        )
    )
    assert main([]) == 1
    assert (
        "path group 'tests' must declare an existing file matching:"
        in capsys.readouterr().err
    )
    config.write_text(config.read_text() + "directories = true\n")
    assert main([]) == 0


def test_group_exclusions_prevent_an_entry_point_from_counting(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "pyproject.toml").write_text(
        _POLICY + 'exclude = ["checks/test_worker.py"]\n'
    )
    assert main([]) == 1
    assert "path group 'tests' must declare" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    ["- Tests: `checks/test_worker.py`\n", "\n## Other\n`checks/test_worker.py`\n"],
)
def test_paths_outside_the_configured_section_do_not_count(
    metadata_consumer: Path, extra: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = metadata_consumer / "docs/FLOW.md"
    if extra.startswith("- Tests"):
        path.write_text(
            extra + _WORKFLOW.replace("- `checks/test_worker.py::case`\n", "")
        )
    else:
        path.write_text(
            _WORKFLOW.replace("- `checks/test_worker.py::case`\n", "") + extra
        )
    assert main([]) == 1
    assert "path group 'tests' must declare" in capsys.readouterr().err


def test_groups_can_select_metadata_fields_or_sections(metadata_consumer: Path) -> None:
    (metadata_consumer / "pyproject.toml").write_text(
        _POLICY.replace('section = "Code and tests"', 'field = "Authority"', 1)
    )
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("- `pkg/worker.py::handler`\n", "")
    )
    assert main([]) == 0


def test_missing_group_section_is_actionable(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("## Code and tests", "## Other")
    )
    assert main([]) == 1
    error = capsys.readouterr().err
    assert "section 'Code and tests' path group 'tests' is missing" in error


@pytest.mark.parametrize(
    ("token", "diagnostic"),
    [
        ("pkg/missing.py", "references missing path: pkg/missing.py"),
        ("../outside.py", "references path outside repository: ../outside.py"),
    ],
)
def test_group_scopes_validate_every_declared_path_even_if_not_selected_by_patterns(
    metadata_consumer: Path,
    token: str,
    diagnostic: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(_WORKFLOW + f"- `{token}`\n")
    assert main([]) == 1
    assert diagnostic in capsys.readouterr().err


def test_fenced_paths_cannot_satisfy_a_group(
    metadata_consumer: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace(
            "- `checks/test_worker.py::case`",
            "```md\n- `checks/test_worker.py::case`\n```",
        )
    )
    assert main([]) == 1
    assert "path group 'tests' must declare" in capsys.readouterr().err


def test_metadata_path_rules_remain_optional(metadata_consumer: Path) -> None:
    (metadata_consumer / "pyproject.toml").write_text(
        _POLICY.split("accepted-values")[0] + 'path-sections = ["Code and tests"]\n'
    )
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("- `checks/test_worker.py::case`\n", "").replace(
            "Status: Current", "Status: TBD"
        )
    )
    assert main([]) == 0


@pytest.mark.parametrize("status", ["Current", "TBD"])
def test_workflow_checks_are_read_only(metadata_consumer: Path, status: str) -> None:
    (metadata_consumer / "docs/FLOW.md").write_text(
        _WORKFLOW.replace("Status: Current", f"Status: {status}")
    )
    before = {
        p: p.read_bytes()
        for p in metadata_consumer.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
    assert main([]) == (0 if status == "Current" else 1)
    assert before == {
        p: p.read_bytes()
        for p in metadata_consumer.rglob("*")
        if p.is_file() and ".git" not in p.parts
    }
