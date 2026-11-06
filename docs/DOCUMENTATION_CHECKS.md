# Documentation checks

`nox-docs-check` is a separate, read-only command shipped in
`nox-python-standards` starting with 0.3.0. `nox-py-standards` continues to expose
only `check` and `sync`. Repositories own their Makefiles, hooks, CI, and generated
architecture reports.

## Adoption

Pin a published standards release and configure checks in the consumer's
`pyproject.toml`:

```toml
[tool.nox-python-standards.docs]
include = ["**/AGENTS.md", "README.md", "docs/**/*.md", ".noxala/*.md"]
exclude = ["docs/generated/**"]
required = ["AGENTS.md", "README.md"]

[[tool.nox-python-standards.docs.budgets]]
include = ["AGENTS.md"]
max-words = 450
```

Run `uv run --locked nox-docs-check` from any consumer subdirectory, or pass
`--root /absolute/repo` to select its Git root. `python -m
nox_python_standards.docs_cli` exposes the same command; `--version` reports the
installed standards release. Exit status is zero on success and one for invalid
configuration, missing files, or documentation failures. Argument errors use
argparse's exit status two.

The command reads repository files and Git's file inventory. It does not import
consumer modules, probe Ruff/Pyright, run generators, fetch URLs, install tools, or
modify files. `nox-py-standards sync` preserves local documentation policy and does
not adopt documentation rules automatically. Add the command to the repository's
existing `docs-check` target and unconditional CI checks.

## File selection and links

`include` is required and nonempty; `exclude` defaults to empty. Patterns use
repository-relative, case-sensitive pathlib glob matching: `*` matches within one
path component, while `**` spans zero or more components. `**/AGENTS.md` therefore
includes the root guide and scoped guides. Git supplies tracked and nonignored
untracked files; standard build, virtual-environment, and vendor directories are
excluded by the shared [repository inventory](../src/nox_python_standards/repository.py).
An empty document selection fails. Missing tracked documents also fail.

Each selected document is checked for local links, missing targets, paths leaving
the repository, and Markdown heading fragments. Supported navigation syntax is
`[Guide](guide.md#details)`, `[Guide][route]`, and `[route][]`, with single-line
reference definitions such as `[route]: guide.md#details "Optional title"`. Labels
may span lines within a paragraph and contain inline code. Reference labels ignore
case and normalize whitespace; the first definition wins. Only actual link
occurrences contribute destinations: unused definitions are ignored, including
their targets. A used undefined reference reports `undefined link reference`;
an invalid destination reports a malformed link. Local image destinations are
also checked.

Backtick code spans (including multiline spans), backtick/tilde fenced blocks,
and backslash-escaped opening brackets do not create links or reference usages.
Fence closers must use the opening character, at least its run length, and no
trailing text. Code examples and unused definitions cannot satisfy catalog coverage.
If an older policy relied on a definition alone, add `[Guide][route]` or an inline
link in the catalog or its cataloged subtree README.

Heading anchors include duplicate suffixes such as `#details-1`; percent-encoded
paths and fragments are decoded. External schemes, network URLs, and site-root
URLs are skipped. Fragments on non-Markdown targets are not checked. The parser
supports these repository guidance conventions, rather than all CommonMark or
rendered HTML features. Shortcut references (`[route]`), nested bracket labels,
balanced parentheses inside destinations, multiline definitions, indented code
blocks, and HTML navigation are outside the supported subset. Use fenced examples,
ordinary Markdown headings, and explicit links for guidance routes.

`required` lists literal files or directories that must exist within the repository.
Configuration paths cannot be absolute or contain `..`. Read documents must be
regular files without symlink components. All policy tables reject unknown keys.
Configured catalog, router, and navigation source documents always receive link
validation, even outside `include` or inside `exclude`. Their own links define
the policy's reading routes. Other documents retain the explicit file selection.

## Budgets

Each `budgets` rule has its own nonempty `include`, optional `exclude`, and at least
one positive integer limit: `max-bytes` or `max-words`. Both may be set. Limits apply
to the complete original file, including code examples; word counts use whitespace
splitting. A byte budget measures UTF-8 file bytes. Every budget rule must select at
least one file. Top-level exclusions affect link checking only, so budget selection
remains explicit.

## Required navigation

```toml
[[tool.nox-python-standards.docs.navigation]]
path = "AGENTS.md"
targets = ["ARCHITECTURE.md#task-router", "docs/README.md"]
```

Each optional rule requires a rendered local link from `path` to every configured
target. Both settings use repository-root-relative paths; actual Markdown link
destinations still resolve relative to the source document. Targets must name
existing `.md` files. Percent-encoded paths/fragments are decoded. A configured
fragment requires that exact heading route; omitting it accepts a link to the
document or any valid heading in it. Missing targets or headings fail even if the
required route has not yet been written.

Inline, explicit-reference, and collapsed-reference links count. External links,
images, code examples, unused reference definitions, and prose routes do not.
For example, deleting a route reports `AGENTS.md requires a navigation link to
ARCHITECTURE.md#task-router`. Checking a route verifies target existence and its
heading, but full target-body validation still depends on content selection.
Empty target lists and malformed paths fail configuration validation.

## Catalogs

```toml
[[tool.nox-python-standards.docs.catalogs]]
path = "docs/README.md"
include = ["docs/**/*.md", "*.md"]
exclude = ["AGENTS.md", "README.md", "ARCHITECTURE.md", "docs/generated/**"]
require-content-check = true  # optional; default false
```

Every selected file except the catalog itself must be linked directly from `path`,
or from a sibling `README.md` that is directly linked by the catalog. Catalog rules
use their own selection, independent of top-level exclusions. Historical ADR bodies
can therefore remain cataloged while their old links are excluded from content checks.
The catalog must exist; this rule does not generate or repair it.

With `require-content-check = true`, every catalog-selected document must receive
link validation or match a top-level `docs.exclude` pattern. This detects maintained
guides omitted from `docs.include`. The diagnostic names the document and catalog
and asks for inclusion or an explicit exemption. Catalog rules with this option
must select at least one member besides the catalog itself. Catalog discovery and
content validation remain independent: excluding an ADR body from content checking
does not remove its discovery requirement.

For a COMO-style policy, start with broader root coverage and explicit historical
exclusions, then add the catalog, navigation, and router rules shown here:

```toml
[tool.nox-python-standards.docs]
include = ["**/AGENTS.md", "*.md", "docs/**/*.md", ".noxala/*.md"]
exclude = ["docs/generated/**", "docs/adr/[0-9]*.md"]
required = ["AGENTS.md", "README.md", "ARCHITECTURE.md", "docs/README.md"]
```

The immediate consumer fix for a cataloged `CONTRIBUTING.md` is adding `*.md` to
top-level content selection. Its broken links are then checked. The coverage option
prevents future root guides from falling through the same gap; it does not silently
change consumer selections. Generated-report freshness stays consumer-owned.

### Catalog tables

Table semantics are optional. Add one or more `catalogs.tables` rules to a catalog
that needs document-selection metadata:

```toml
[[tool.nox-python-standards.docs.catalogs.tables]]
columns = ["Document", "Status", "Read when", "Authority"]
document-column = "Document"
path-columns = ["Authority"]  # optional

[tool.nox-python-standards.docs.catalogs.tables.accepted-values]
Status = [
    "Current",
    "Planned (not implemented)",
    "Generated (projection only)",
    "Decision history",
]
```

Each rule checks every pipe table in its scope. Omitting `section` checks all
tables in the catalog, including tables under different category headings. Setting
`section = "Architecture"` limits a rule to that exact level-two section, including
its subsections. Use separate section rules when categories have different columns
or source-path requirements. For example, current architecture entries may require
source paths while a decision-history table uses a prose authority description.
All configured sections must exist and contain at least one table.

Tables must have the exact configured header and at least one document row.
`required-columns` defaults to every configured column; set it explicitly to permit
empty optional cells. An empty list permits empty cells except where document-link,
path, or accepted-value rules independently require content. `document-column`
always requires a real local Markdown document link in each row. Link destinations
resolve from the catalog, and reference definitions may live elsewhere in it.
Images, directories, source-file links, code examples, and prose do not substitute.

Optional `path-columns` require existing repository paths in backticks in every
named cell, using the metadata path conventions below. Files and directories are
accepted, and `file.py::symbol` resolves at file level. `accepted-values` maps any
configured column to its accepted full cell values, after trimming outer whitespace.
Matching is case- and formatting-sensitive. Qualifiers are preserved: `Planned`
does not match `Planned (not implemented)`. Status vocabulary and all column names
belong to the consumer; the checker supplies no default status meanings.

With table rules enabled, catalog discovery uses links in the document columns of
the checked tables. A selected member cannot bypass metadata by moving its link
into an ordinary list or another cell. Indirection through a cataloged subtree
README still works; table rules apply to that README only if it has its own catalog
rule. Without `tables`, a simple link-list catalog retains its original behavior.

Missing columns, empty required cells, absent document links, invalid paths, and
unsupported values identify the catalog, optional section, table, row, and column
where applicable. Table and row numbers start at 1 within the rule's scope. Missing
tables and empty tables fail explicitly. Unknown or duplicate column references,
empty table-rule arrays, and malformed accepted-value settings fail configuration
validation. A header/delimiter row is required; delimiter cells use at least three
hyphens with optional alignment colons. Cells are single-line, and each table line
must contain a pipe; outer pipes are optional for multi-column lines. Pipes inside
cells (including escaped pipes or pipes in code spans) are
outside the supported table subset. Fenced and inline-code table examples do not
count as tables.

## Metadata and source paths

```toml
[[tool.nox-python-standards.docs.metadata]]
include = ["docs/workflows/**/*.md"]
exclude = ["**/README.md"]
fields = ["Status", "Read when", "Authority"]
path-fields = ["Authority"]
path-sections = ["Code and tests"]
```

Each selected document must contain nonempty `- Label: value` entries for `fields`.
Indented continuation lines belong to the value. `path-fields` additionally require
at least one existing repository path in inline backticks. `path-sections` require
an exact level-two heading and at least one existing path in its section.
Paths resolve from the repository root, not the document directory. Tokens such as
`test/example.py::test_case` resolve to the file; wildcard/template tokens are
skipped. Recognized path tokens contain `/` or end in `.py`/`.md`; use `./Makefile`
or `./assets` for other root files or directories. Fenced examples do not satisfy
metadata or sections. Every metadata rule must select at least one document.

## Task routers

```toml
[[tool.nox-python-standards.docs.routers]]
path = "ARCHITECTURE.md"
section = "Task router"
columns = ["Task", "Read", "Implementation authority"]
link-columns = ["Read"]  # optional
path-columns = ["Implementation authority"]  # optional
```

The document and exact level-two section must exist. Its pipe table must have the
declared header, at least one task row, and the expected number of nonempty cells.
Repository path tokens in that section must exist. Optional `link-columns` require
at least one local link to an existing `.md` document in each named cell on every
task row. Images, directories, source-file links, prose, and code tokens cannot
substitute. Reference links can use definitions elsewhere in the document. Linked
fragments must exist.

Optional `path-columns` independently require repository paths in backticks in
each named cell. Existing files and directories are accepted; `file.py::symbol`
resolves at file level. All declared paths must exist, including paths in other
columns. A link or path in another cell cannot satisfy a column's requirement.
Diagnostics identify the source, section, task row (starting at 1), and column.
Configured column names must be distinct members of `columns`; explicitly empty
column lists fail. Omitting both options retains the compact shape-only policy.
Router documents always receive link validation. The pipe-table format does not
support escaped pipes inside cells.

## Ownership and verification

The shared engine owns parsing and validation. Consumers own paths, budgets,
exclusions, catalog scope, metadata labels, and router columns. No consumer profile
is embedded in the package. The engine originated in
[COMO's guidance checker](https://github.com/noxala/como/blob/241b42243cae60e7a577f2f7d3592b1044f75ed9/tools/check_repository_guidance.py),
with tests covering its richer policy and nox-tach's compact guide policy.

This package checks its own documentation in CI. Tests cover configurable rules,
failure diagnostics, configuration validation, read-only behavior, and both installed
wheel forms; consumers retain only their invocation and any truly local generators.
