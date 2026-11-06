# nox-python-standards

Shared Noxala Python settings, checked against complete local `pyproject.toml`
files. Each repository owns its Makefile, hooks, CI and native tool commands.

## Install and adopt

Use the Python/uv versions in [pyproject.toml](pyproject.toml), Git, and Node.js
on PATH for `check`.

Add development dependencies with an exact PyPI version and the
[approved tool versions](src/nox_python_standards/resources/versions.json):

```toml
[dependency-groups]
dev = [
    "nox-python-standards==0.2.1",
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

Licensed under [0BSD](LICENSE). Releases publish wheels and sdists to
[PyPI](https://pypi.org/project/nox-python-standards/) through GitHub OIDC;
no persistent PyPI token is needed.

One-time setup: on your [PyPI publishing page](https://pypi.org/manage/account/publishing/),
add a pending GitHub publisher with project `nox-python-standards`, owner `noxala`,
repository `nox-python-standards`, workflow `publish.yml`, and environment `pypi`.
The GitHub repository must have the matching `pypi` environment.

For each release, update `project.version` and this installation example, run
`uv lock`, and merge through the required checks. Publish a GitHub release tagged
`v<version>` at that merged commit. [Publish](.github/workflows/publish.yml)
reruns Linux/macOS quality checks, requires the tag to match the package version
and belong to `master`, builds distributions, then uploads through the `pypi`
environment. To publish an existing tag, run Publish manually from `master`
with that tag. A failed upload can be retried before either file is published;
after a partial upload, inspect PyPI before retrying. Published files cannot be
overwritten; subsequent changes need a new version.
