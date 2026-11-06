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

Each selected document is checked for local inline and explicit/collapsed reference
links, missing targets, paths leaving the repository, and Markdown heading fragments.
Heading anchors include duplicate suffixes such as `#details-1`; percent-encoded
paths and fragments are decoded. Backtick and tilde fenced examples are ignored.
External schemes, network URLs, and site-root URLs are skipped. Fragments on
non-Markdown targets are not checked. The parser supports these repository guidance
conventions, rather than implementing all CommonMark or rendered HTML features;
use ordinary Markdown headings and explicit links for guidance routes.

`required` lists literal files or directories that must exist within the repository.
Configuration paths cannot be absolute or contain `..`. Read documents must be
regular files without symlink components. All policy tables reject unknown keys.

## Budgets

Each `budgets` rule has its own nonempty `include`, optional `exclude`, and at least
one positive integer limit: `max-bytes` or `max-words`. Both may be set. Limits apply
to the complete original file, including code examples; word counts use whitespace
splitting. A byte budget measures UTF-8 file bytes. Every budget rule must select at
least one file. Top-level exclusions affect link checking only, so budget selection
remains explicit.

## Catalogs

```toml
[[tool.nox-python-standards.docs.catalogs]]
path = "docs/README.md"
include = ["docs/**/*.md", "*.md"]
exclude = ["AGENTS.md", "README.md", "ARCHITECTURE.md", "docs/generated/**"]
```

Every selected file except the catalog itself must be linked directly from `path`,
or from a sibling `README.md` that is directly linked by the catalog. Catalog rules
use their own selection, independent of top-level exclusions. Historical ADR bodies
can therefore remain cataloged while their old links are excluded from content checks.
The catalog must exist; this rule does not generate or repair it.

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
skipped. Fenced examples do not satisfy metadata or sections. Every metadata rule
must select at least one document.

## Task routers

```toml
[[tool.nox-python-standards.docs.routers]]
path = "ARCHITECTURE.md"
section = "Task router"
columns = ["Task", "Read", "Implementation authority"]
```

The document and exact level-two section must exist. Its pipe table must have the
declared header, at least one task row, and the expected number of nonempty cells.
Repository path tokens in that section must exist. Links are validated through the
top-level document selection; include router documents there. This format does not
support escaped pipes inside table cells.

## Ownership and verification

The shared engine owns parsing and validation. Consumers own paths, budgets,
exclusions, catalog scope, metadata labels, and router columns. No consumer profile
is embedded in the package. The engine originated in
[COMO's guidance checker](https://github.com/noxala/como/blob/241b42243cae60e7a577f2f7d3592b1044f75ed9/tools/check_repository_guidance.py),
with tests covering its richer policy and nox-tach's compact guide policy.

This package checks its own documentation in CI. Tests cover configurable rules,
failure diagnostics, configuration validation, read-only behavior, and both installed
wheel forms; consumers retain only their invocation and any truly local generators.
