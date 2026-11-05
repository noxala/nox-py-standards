# nox-python-standards

Shared Noxala Python policy with **complete checked local configuration**. Ruff,
Pyright and editors read each repository's ordinary `pyproject.toml`. The installed
release verifies those copies; only explicit `config sync` changes them.

Initial policy and helper behavior come from COMO
[`da28acec147d114270ba4524f51a47a5afb2515e`](https://github.com/noxala/como/tree/da28acec147d114270ba4524f51a47a5afb2515e),
implementing the standalone-package stage of
[COMO #518](https://github.com/noxala/como/issues/518). Consumers have not migrated.

## Installation and adoption

Python `>=3.14.10,<3.15`, uv `>=0.13.6`, Git and Node.js (for Pyright) are required.
The distribution pins Ruff `0.15.14`, Pyright `1.1.411` and its TOML round-trip editor.
Install only as a consumer **development** dependency, pinned to a reviewed full
merged commit:

```text
nox-python-standards @ git+https://github.com/noxala/nox-python-standards.git@<full-merged-sha>
```

Authenticate private Git access before `uv sync --locked`, using a credential helper
or appropriately scoped app/token. Do not put credentials in tracked URLs or logs.
A repository-scoped Actions token does not grant cross-repository access.

Keep exact direct `ruff==0.15.14` and `pyright==1.1.411` pins in the selected
dependency group. Configure the source scope explicitly:

```toml
[tool.nox-python-standards]
sources = ["."]
dependency-group = "dev"

[tool.nox-python-standards.ruff]
authorized_version = "v0.15.14"  # manual approval, never written by sync
```

Retain all local Ruff/Pyright tables. Run `uv run nox-py-standards config sync`,
review the local shared-field diff and `.noxala/PYTHON_CONVENTIONS.md`, then commit
the dependency pin, lockfile and copies together. Root instructions must explicitly
tell agents to read the local conventions snapshot and state domain additions.

For an upgrade, review the central release first, update the immutable dependency
pin and lockfile, install, explicitly sync, then review the ordinary local diff.
Update direct tool pins when required. A changed Ruff version requires separate
manual approval; sync never grants it. Run the normal consumer CI before merging.
No command fetches a moving branch or installs/upgrades tools.

## Commands

Run from anywhere inside the consumer Git repository, or put `--root /repo` before
the command. `python -m nox_python_standards` uses the same implementation.

| Command after `nox-py-standards` | Behavior |
| --- | --- |
| `config check` | Read-only shared values, ownership, discovery and conventions gate |
| `config sync` | Explicitly repair shared fields and conventions, preserving local data/comments |
| `versions` | Verify release/consumer/executable pins and manual Ruff approval |
| `ruff check` | Config/version gates, format check, lint check |
| `ruff fix` | Config/version gates, format, unsafe PT007 fix, safe lint fix, format |
| `typecheck [--threads N] [--watch]` | Config/version gates, native Pyright |
| `headers check` / `headers fix` | Git-aware repository-relative source headers |
| `hooks check` | Verify executable pre-commit-managed pre-push hook; never install |
| `check` | Config/version/header/Ruff/Pyright verification; excludes local hook prerequisite |
| `fix` | Config/version gates, header repair and Ruff repair; never sync |

Failures stop the command and return nonzero. Tool execution uses the same absolute
launcher paths that were version-validated. Wrappers accept no config replacement
or policy override flags. `make ruff` consumers should delegate to `ruff fix`, not
the broader `fix` command. Normal tool caches may be created by check commands.
Pyright runs its bundled pinned version with update warnings disabled; Node must
already be on PATH. Environment overrides cannot select a newer Pyright release.

## Ownership and native discovery

Installed `resources/policy.json` owns every explicitly shared field; array order
and types matter. Missing shared fields fail even when native defaults match.
`resources/ownership.json` describes local keys and their types. Unrelated tool,
project and dependency tables are untouched. The initial narrow exceptions are
`test/**/*.py = ["SLF001"]` and Pyright's `root = "test"` private-access exception.
Other nested diagnostics require a reviewed schema extension.

Source paths, exclusions and package classification remain local decisions.
Tach alone generates its consumers' `known-first-party`. Config sync preserves
them and never changes dependencies, approval, source code or installed resources.
Malformed TOML, unclassified overrides, invalid local fields and conflicting native
configs block sync before writes. Each changed file is replaced atomically.

Root `ruff.toml`, `.ruff.toml`, `pyrightconfig.json`, inheritance and nested Ruff
configs affecting scoped Git sources are rejected, including relevant untracked
sources and ignored configs above them. Generic vendor/environment directories are
excluded from discovery. Fixtures outside source scope may hold example configs.

Headers preserve supported UTF-8 LF/CRLF files, shebangs, long-path treatment,
executable permissions and tracked/non-ignored-untracked discovery. All candidate
files are rendered before any writes. Compared with COMO's helper, this explicitly
rejects symlinks, unsupported encodings/line endings and unsafe coding-cookie moves,
handles tracked deletions, and repairs a shebang lacking its final newline.
These are safety fixes to malformed/unsupported input; supported COMO rendering is
unchanged. Hook detection honors Git worktrees and custom `core.hooksPath`.

## CI and development

```sh
uv sync --locked
uv run nox-py-standards config check
uv run nox-py-standards versions
uv run nox-py-standards ruff check
uv run nox-py-standards typecheck --threads 4
uv run pytest
uv run python tools/verify_distribution.py
```

The Linux/macOS workflow builds and installs this package before invoking the CLI.
It checks configuration before any source checks. The distribution check builds a
wheel from the sdist, installs it without editable paths into a clean environment,
then uses a separate Git consumer with no `PYTHONPATH` or sibling checkout dependency.

Consumer migration must put an unconditional `uv run --locked nox-py-standards
config check` immediately after locked installation, before generation/fix hooks,
and first in local pre-commit/pre-push hooks with `fail_fast: true`. No automatic
sync, path filtering or `continue-on-error` may hide drift. Make it a required merge
check. Keep consumer application tests and architecture gates.

Repository administrators must enable auto-merge and require both `quality (Linux)`
and `quality (macOS)` checks. The initial inherited review rule does not require
status checks. This package's PR does not change repository administration settings.
