# nox-py-standards

Shared Noxala Python settings, checked against complete local `pyproject.toml`
files. Each repository owns its Makefile, hooks, CI and native tool commands.

From 0.4.2, the distribution is named `nox-py-standards`, matching its GitHub
repository and CLI. Published files use the `nox_py_standards` prefix. The Python
import namespace remains `nox_python_standards`, and configuration continues to
use `[tool.nox-python-standards]`. Replace the old dependency name when upgrading;
existing release tags and artifacts are not renamed or overwritten.

## Install and adopt

Use the Python/uv versions in [pyproject.toml](pyproject.toml), Git, and Node.js
on PATH for `check`.

Configure authenticated access to the private registry (see [publishing](#publishing)),
then add development dependencies with an exact version and the
[approved tool versions](src/nox_python_standards/resources/versions.json):

```toml
[dependency-groups]
dev = [
    "nox-py-standards==0.4.3",
    "ruff==0.15.14",
    "pyright==1.1.411",
]

[tool.nox-python-standards]
sources = ["."]
dependency-group = "dev"

[tool.nox-python-standards.ruff]
authorized_version = "v0.15.14"  # manual approval
```

Keep local path/exclusion/import settings. Lock and install dependencies, run
`uv run nox-py-standards sync`, then review and commit the config, lockfile and
`.noxala/PYTHON_CONVENTIONS.md`. Root agent instructions should require that
snapshot before Python edits and state repository-specific rules.

For upgrades, review the release, update pins/lockfile, install, and explicitly
sync. Ruff version changes require separate manual approval.

## Check and sync

- **`check`** verifies shared settings, ownership, conventions, config discovery,
  exact tool pins, manual Ruff approval and active tool versions. It is read-only;
  tool calls are limited to `--version` probes. Node must exist before probing
  Pyright; the probe selects its bundled pinned release without downloading tools.
- **`sync`** adopts shared settings and conventions, preserving local settings,
  comments, dependency pins, lockfiles and approval. It needs no Ruff/Pyright
  installation. Invalid TOML, unclassified overrides and competing configs block
  writes. Repeated sync is byte-stable; each changed file is replaced atomically.

Run from any consumer subdirectory, or use `nox-py-standards --root /repo check`.
`python -m nox_python_standards` exposes the same commands. Neither command installs
dependencies. Repositories control their normal tool execution and environment.

From 0.1: `config check/sync` becomes `check/sync`; other commands are removed.
`check` no longer runs source lint, formatting, headers, typing or tests.

## Documentation checks

The same distribution also ships `nox-docs-check`, a separate read-only command
for documentation links, guidance budgets, catalogs, metadata, and task routers.
Repositories declare their own rules under `[tool.nox-python-standards.docs]`.
See [configuration and adoption](docs/DOCUMENTATION_CHECKS.md). It does not change
the `nox-py-standards check/sync` command contract or run consumer tools.
Complete [compact](docs/examples/compact.toml) and
[progressive-disclosure](docs/examples/progressive.toml) policy examples are tested
in CI; adapt them explicitly to the consuming repository.

Release 0.4.3 enables Ruff `PLC0415` (`import-outside-top-level`) in the shared
policy. Consumer adoption flags imports inside functions and other blocks.

## Native fix policy

Checked Ruff settings enforce its exact version and approve PT007 via
`extend-safe-fixes = ["PT007"]`; other unsafe fixes remain disabled. Keep repair
recipes local, for example:

```make
ruff:
	uv run --locked nox-py-standards check
	uv run --locked ruff format .
	uv run --locked ruff check --fix .
	uv run --locked ruff format .
```

Repeat until stable. CLI flags can override settings; review and test recipes
to preserve the policy.

## Configuration ownership

| Authority | Owns |
| --- | --- |
| [policy.json](src/nox_python_standards/resources/policy.json) | Shared settings |
| [ownership.json](src/nox_python_standards/resources/ownership.json) | Local keys and types |
| [versions.json](src/nox_python_standards/resources/versions.json) | Exact Ruff/Pyright versions |

Shared values must match exactly, even when native defaults agree. Paths,
exclusions, import classification and approved test exceptions stay local; Tach
owns generated first-party lists. Unrelated tables are preserved.

Unclassified overrides, inheritance, root `ruff.toml`, `.ruff.toml` or
`pyrightconfig.json`, and nested Ruff configs affecting scoped Git sources fail.

Policy originated in [COMO](https://github.com/noxala/como/tree/da28acec147d114270ba4524f51a47a5afb2515e);
this package has no consumer dependency.

## CI and package development

Consumers run `uv run --locked nox-py-standards check` after locked installation,
before generators/fixes, and first in local pre-commit/pre-push hooks. Require
the gate unconditionally, then run repository checks. Never auto-sync in CI.

For code or packaging changes here:

```sh
uv sync --locked
uv run --locked nox-py-standards check
uv run --locked nox-docs-check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pyright --threads 4
uv run --locked pytest
uv run --locked python tools/verify_distribution.py
```

[CI](.github/workflows/ci.yml) runs on Linux/macOS. Distribution verification
rebuilds from sdist and tests an isolated, non-editable installation, including
sync without tools and check with missing/present tools.

Repository administrators should enable auto-merge and require `quality (Linux)`
and `quality (macOS)`.

## Publishing

Licensed under [0BSD](LICENSE). Releases publish wheels and sdists to the private
Google Artifact Registry `noxala-org-python` in `us-central1`, project
`prj-noxala-org-bootstrap-e7b2`. No PyPI upload or stored publishing secret is used.

Before the first upload, extend and apply the organization
[registry access contract](https://github.com/noxala/gcp-infrastructure/blob/master/docs/PYTHON_PACKAGES.md)
to admit this repository's immutable numeric identity, caller
`noxala/nox-py-standards/.github/workflows/publish.yml`, and reusable publisher
`noxala/nox-py-standards/.github/workflows/publish-python.yml@refs/heads/master`.
The existing cloud policy admits only `nox-py-common`; these workflows alone do
not grant access. Local installation and consumer CI also need reviewed reader
access and a resolver-scoped private index; keep public dependencies on PyPI.

For each release, update `project.version` and this installation example, run
`uv lock`, and merge through the required checks. Publish a GitHub release tagged
`v<version>` at that merged commit. [Release assets](.github/workflows/publish.yml)
calls the [private publisher](.github/workflows/publish-python.yml) from protected
`master`. It resolves the exact tagged commit, requires merged source and a matching
package name/version, reruns Linux/macOS quality checks, then builds distributions.
Only after validation does it authenticate through Google workload federation and
upload. It also attaches the wheel, sdist and `SHA256SUMS` to the GitHub release.

For this release, publish `v0.4.3` after merging. The release assets
will be `nox_py_standards-0.4.3-py3-none-any.whl` and
`nox_py_standards-0.4.3.tar.gz`. For an existing tag of the renamed distribution, run
**Actions → Release assets → Run workflow** from `master` with that tag. Select
`registry-only` to retain existing GitHub assets, including immutable releases.
The rebuilt wheel must match any existing wheel asset. Source archive timestamps,
ownership and gzip metadata are normalized for reproducible retries. Matching
registry files are skipped; different bytes fail without overwriting anything.

Tags before 0.4.2 contain the old distribution name and are rejected by the renamed
publisher. Publish the new release instead of moving old tags or renaming old files.

Verify a successful live upload and authenticated consumer installs before making
the repository private or deleting existing PyPI releases. Existing consumers
and lockfiles must be migrated separately; this change does not update them.
