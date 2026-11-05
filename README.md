# nox-python-standards

The golden settings for Noxala Python repositories, with two operations:

```sh
nox-py-standards check
nox-py-standards sync
```

Each repository keeps complete, readable Ruff/Pyright configuration in its own
`pyproject.toml`. Editors and native commands use that ordinary local configuration.
The installed standards release checks those copies; explicit sync adopts its values.
Each repository owns its Makefile, hooks, CI, formatting, typing and helper scripts.

## Install and adopt

Install as a development dependency pinned to a reviewed full merged Git commit:

```text
nox-python-standards @ git+https://github.com/noxala/nox-python-standards.git@<full-merged-sha>
```

Python `>=3.14.10,<3.15` and Git are required. The package's only runtime dependency
is its TOML editor. Consumers install their own exact Ruff/Pyright pins; Node.js is
required by the Python Pyright launcher. Current supported versions are policy data
in `resources/versions.json`: Ruff `0.15.14`, Pyright `1.1.411`.

```toml
[dependency-groups]
dev = ["ruff==0.15.14", "pyright==1.1.411"]

[tool.nox-python-standards]
sources = ["."]
dependency-group = "dev"

[tool.nox-python-standards.ruff]
authorized_version = "v0.15.14"  # manual approval; sync never changes this
```

Keep local path/exclusion/import settings, run `uv run nox-py-standards sync`, review
and commit the configuration and `.noxala/PYTHON_CONVENTIONS.md` snapshot. Root agent
instructions should require reading the snapshot and state repository additions.

Advance through reviewed dependency/lockfile updates. Sync never changes tool pins,
lockfiles or approval. A tool upgrade requires deliberate dependency changes and
separate manual Ruff approval; sync may update the required Ruff version in config
but leaves the approval decision to the developer.

## Check and sync

`check` is read-only. It compares shared settings, ownership and conventions; rejects
competing native configs; then checks exact declared tool pins, manual Ruff approval
and active tool versions. Its only tool invocations are `ruff --version` and
`pyright --version`. Missing tools, drift and version mismatches fail with diagnostics.
The Pyright version probe selects its bundled pinned release and disables component
downloads; repositories own their normal Pyright execution and environment.

`sync` repairs shared configuration and the conventions snapshot, preserving local
settings/comments and approval. It needs neither Ruff nor Pyright installed. Invalid
TOML, unclassified overrides and conflicting native configs fail before writes.
Repeated sync is byte-stable. Each destination is replaced atomically.

Run from the consumer repository or a subdirectory. `--root /repo` selects an explicit
Git root. `python -m nox_python_standards` provides the same two operations.
Version `0.2.0` removes the old `config`, `versions`, `ruff`, `typecheck`, `headers`,
`hooks` and `fix` operations. `check` now validates standards only; lint, formatting,
source headers, typing and tests belong to each repository's checks.

## Native fix policy

The checked local settings include:

```toml
[tool.ruff]
required-version = "==0.15.14"
fix = false
fix-only = false
unsafe-fixes = false

[tool.ruff.lint]
extend-safe-fixes = ["PT007"]
extend-unsafe-fixes = []
fixable = ["ALL"]
unfixable = []
```

This explicitly approves PT007's otherwise-unsafe fix. A normal local
`ruff check --fix .` applies it and safe fixes; other unsafe fixes stay disabled.
Native Ruff enforces its exact required version. CLI flags can override native
settings, so each repository reviews and tests its own command recipes.

For example, a repository can maintain this local target:

```make
ruff:
	uv run --locked nox-py-standards check
	uv run --locked ruff format .
	uv run --locked ruff check --fix .
	uv run --locked ruff format .
```

Headers, hook installation, test workers, Tach, databases and workflow order are
repository responsibilities. This package does not wrap those operations.

## Configuration ownership

`resources/policy.json` owns shared fields; `resources/ownership.json` classifies
local keys and types. Missing shared values fail even when native defaults match.
Sources, exclusions, package classification and existing test exceptions remain
local. Tach owns its consumers' generated first-party lists. Unrelated tables are
preserved. Unclassified policy overrides, inheritance, root `ruff.toml`, `.ruff.toml`,
`pyrightconfig.json`, and nested Ruff configs affecting scoped Git sources fail.

The initial shared rules and conventions originated in COMO at
[`da28acec147d114270ba4524f51a47a5afb2515e`](https://github.com/noxala/como/tree/da28acec147d114270ba4524f51a47a5afb2515e).
This package has no dependency on a consumer repository.

## CI and package development

Consumers put `uv run --locked nox-py-standards check` immediately after locked
dependency installation, before any generator or fix hook, and first in local
pre-commit/pre-push hooks. Keep that gate unconditional and required for merge.
CI never syncs automatically. Run repository-specific checks afterward.

For this package:

```sh
uv sync --locked
uv run --locked nox-py-standards check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pyright --threads 4
uv run --locked pytest
uv run --locked python tools/verify_distribution.py
```

The Linux/macOS workflow uses native tools directly. Distribution verification
builds a wheel from the sdist and installs it in isolation. It exercises both
operations without tool installations, proves check reports missing tools, then
installs consumer-owned tools and verifies console/module checks.

Repository administrators should enable auto-merge and require `quality (Linux)`
and `quality (macOS)`. Package code does not change repository settings.
