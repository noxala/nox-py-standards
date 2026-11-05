# Python standards implementation instructions

Read [.noxala/PYTHON_CONVENTIONS.md](.noxala/PYTHON_CONVENTIONS.md) before Python
changes. `pyproject.toml` is authoritative for package versions and dependencies.

The public CLI has exactly two operations: `check` and `sync`. Keep it focused on
policy verification/adoption. Consumers own commands, Makefiles, hooks, header
helpers, formatting, linting, typing, tests and workflow order. Do not add tool
runners or install/upgrade dependencies. Version probes use only `--version`.

This package must work from a non-editable installation without COMO, Milan, Tach,
databases or network access after installation. Never import a consumer. Locate
consumer files from its Git root, never this package's location.

`resources/policy.json` owns shared settings, `resources/versions.json` owns tool
versions, and `resources/ownership.json` classifies local fields. Reject unclassified
keys and nested overrides. Keep native configs complete and readable locally.
Retain exact consumer tool pins and separate manual Ruff approval. Sync never
updates pins, lockfiles or approval. Unsafe fix approval remains exclusive to PT007
through Ruff's native `extend-safe-fixes` setting. Check validates active versions;
Ruff and Pyright are consumer tools, not runtime dependencies of this package.

Run `uv sync --locked` and `uv run --locked nox-py-standards check` before source
repairs. Run native `ruff format .`, `ruff check --fix .`, `ruff format .` until
stable, then pytest, `pyright --threads 4` and `python tools/verify_distribution.py`
in the project environment. Never use fixes or automatic sync to hide config drift.

Tests mirror owning modules under `test/`. Validate proposed settings before writes;
check never edits source/configuration. Keep sync explicit, minimal and idempotent.

Start new PRs from current `master`, request `denisgrenader`, and enable auto-merge
when supported. All quality checks must pass before merge. Migrate consumers only
after the package is merged and pinned to its immutable merged commit.
