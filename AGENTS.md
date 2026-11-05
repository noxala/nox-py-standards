# Python standards implementation instructions

Read [.noxala/PYTHON_CONVENTIONS.md](.noxala/PYTHON_CONVENTIONS.md) before Python
changes. `pyproject.toml` is authoritative for supported versions and dependencies.

This package must work from a non-editable installation without COMO, Milan,
Tach, databases or network access after installation. Never import a consumer.
Locate consumer files from its Git root, never this package's location.

`resources/policy.json` owns shared values. `resources/ownership.json` classifies
consumer fields; reject unclassified keys and nested overrides. Keep native
Ruff/Pyright configuration complete and readable in the consumer. Never silently
weaken policy, narrow coverage, add config inheritance or introduce automatic sync.

Tool dependencies in distribution metadata own the supported versions. Retain exact
direct consumer pins and a separate manual Ruff approval; no repair/sync command
may update pins, lockfiles or approval. Keep unsafe fixes exclusive to PT007.

Run `uv sync --locked`, `uv run nox-py-standards config check`,
`uv run nox-py-standards ruff fix` until stable, `uv run pytest`,
`uv run nox-py-standards typecheck --threads 4`, and
`uv run python tools/verify_distribution.py` for code/packaging changes.
Never use fixes to conceal a failing committed configuration gate.

Tests mirror owning modules under `test/`. Keep header rendering separate from
writes. Validate all proposed edits before mutation; check commands never edit
tracked source/configuration. Document any intentional behavior change from COMO.

Start new PRs from current `master`, request `denisgrenader`, and enable auto-merge
when supported. All quality checks must pass before merge. Do not migrate consumers
until the package is merged and pinned to its immutable merged commit.
