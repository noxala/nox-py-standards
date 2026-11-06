# test/test_markdown.py
from __future__ import annotations

import pytest

from nox_python_standards.markdown import markdown_links, markdown_tables


@pytest.mark.parametrize(
    "usage",
    [
        "[Guide](docs/GUIDE.md#details)",
        "[Guide][route]",
        "[route][]",
        "[Guide][ ROUTE ]",
        "[A `code` label][route]",
        "[A `code` label](docs/GUIDE.md#details)",
        "[A multiline\nlabel][route]",
    ],
)
def test_rendered_links_resolve_destinations(usage: str) -> None:
    links, errors = markdown_links(
        f'{usage}\n\n[route]: docs/GUIDE.md#details "Title"\n[unused]: absent.md\n'
    )
    assert not errors
    assert [link.destination for link in links] == ["docs/GUIDE.md#details"]
    assert links[0].path_text == "docs/GUIDE.md"
    assert links[0].fragment == "details"


@pytest.mark.parametrize(
    "text",
    [
        "[unused]: absent.md\n",
        "[unused]:\n",
        "`[Example](absent.md)`",
        "``[Example](absent.md) with ` inside``",
        "`multiline\n[Example](absent.md)\nspan`",
        "`[Example][ref]`\n[ref]: absent.md\n",
        "`[ref][]`\n[ref]: absent.md\n",
        "`[Example][undefined]`",
        "```md\n[Example](absent.md)\n```\n",
        "~~~md\n[Example][undefined]\n~~~\n",
        "````md\n```\n[Example](absent.md)\n````\n",
        "~~~md\n~~~ not a closing fence\n[Example](absent.md)\n~~~\n",
        "```md\n~~~\n[Example](absent.md)\n```\n",
        r"\[Example](absent.md)",
        r"\[Example][undefined]",
        "[Example\n\n](absent.md)",
        "[Example\n```\ncode\n```\n](absent.md)",
    ],
)
def test_non_navigation_does_not_produce_links_or_errors(text: str) -> None:
    assert markdown_links(text) == ((), ())


def test_each_reference_occurrence_resolves_once_and_first_definition_wins() -> None:
    links, errors = markdown_links(
        "[First][route] and [route][]\n[route]: first.md\n[ROUTE]: second.md\n"
    )
    assert not errors
    assert [link.destination for link in links] == ["first.md", "first.md"]


def test_collapsed_reference_preserves_inline_code_in_its_label() -> None:
    links, errors = markdown_links("[Read `code`][]\n[Read `code`]: guide.md\n")
    assert not errors
    assert [link.destination for link in links] == ["guide.md"]


@pytest.mark.parametrize(
    "definition", ["`[ref]: guide.md`", "```\n[ref]: guide.md\n```"]
)
def test_definition_in_code_does_not_resolve_a_reference(definition: str) -> None:
    links, errors = markdown_links(f"[Guide][ref]\n{definition}\n")
    assert not links
    assert errors == ("undefined link reference: [ref]",)


def test_used_reference_with_invalid_destination_is_reported() -> None:
    links, errors = markdown_links("[Guide][ref]\n[ref]:\n")
    assert not links
    assert errors == ("reference [ref] has empty link destination",)


def test_external_reference_has_no_local_navigation() -> None:
    assert markdown_links("[Guide][ref]\n[ref]: https://example.invalid/\n") == ((), ())


def test_code_in_link_label_cannot_create_a_nested_link() -> None:
    links, errors = markdown_links("[`[Example](absent.md)`](guide.md)")
    assert not errors
    assert [link.destination for link in links] == ["guide.md"]


def test_unclosed_code_span_and_escaped_backtick_do_not_hide_links() -> None:
    links, errors = markdown_links(r"\` and `` [Guide](guide.md)")
    assert not errors
    assert [link.destination for link in links] == ["guide.md"]


def test_escaped_backslash_does_not_escape_a_link() -> None:
    links, errors = markdown_links(r"\\[Guide](guide.md)")
    assert not errors
    assert [link.destination for link in links] == ["guide.md"]


def test_backticks_cannot_hide_navigation_in_another_paragraph() -> None:
    links, errors = markdown_links("`open\n\n[Guide](guide.md)\n\nclose`")
    assert not errors
    assert [link.destination for link in links] == ["guide.md"]


def test_link_fragments_resolve_references_in_the_full_document_context() -> None:
    links, errors = markdown_links(
        "[Guide][route]", reference_context="[route]: guide.md#details"
    )
    assert not errors
    assert [link.destination for link in links] == ["guide.md#details"]


@pytest.mark.parametrize("syntax", ["![Guide](guide.md)", "![Guide][route]"])
def test_images_are_distinguished_from_navigation(syntax: str) -> None:
    links, errors = markdown_links(syntax, reference_context="[route]: guide.md")
    assert not errors
    assert links[0].is_image


def test_escaped_image_marker_preserves_a_normal_link() -> None:
    links, errors = markdown_links(r"\![Guide](guide.md)")
    assert not errors
    assert not links[0].is_image


def test_categorized_pipe_tables_retain_cell_contents() -> None:
    tables = markdown_tables("""\
## First
| Doc | Authority |
| --- | :---: |
| [Guide](GUIDE.md) | `src/example.py` |

## Second
Doc | Status
:--- | ---:
[Plan][plan] | Planned (not implemented)
""")
    assert len(tables) == 2
    assert tables[0].columns == ("Doc", "Authority")
    assert tables[0].rows == (("[Guide](GUIDE.md)", "`src/example.py`"),)
    assert tables[1].rows == (("[Plan][plan]", "Planned (not implemented)"),)


@pytest.mark.parametrize(
    "text",
    [
        "| Doc | Status |\n| Guide | Current |\n",
        "| Doc | Status |\n| --- |\n",
        "| Doc | Status |\n| -- | --- |\n",
        "```md\n| Doc |\n| --- |\n| Guide |\n```",
        "`\n| Doc |\n| --- |\n| Guide |\n`",
    ],
)
def test_non_tables_and_code_examples_are_not_tables(text: str) -> None:
    assert markdown_tables(text) == ()


def test_pipe_table_empty_cells_and_malformed_rows_are_retained() -> None:
    tables = markdown_tables(
        "| Doc | Status |\n| --- | --- |\n| Guide | |\n| extra | cells | here |\n"
    )
    assert tables[0].rows == (("Guide", ""), ("extra", "cells", "here"))
