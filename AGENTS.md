# nox-python-standards

`nox-py-standards` exposes only `check` and `sync`; consumers own tool execution.

- `check` is read-only; probes use only `--version`. Neither command installs or
  upgrades dependencies.
- `sync` is explicit, validated before writes and idempotent. Preserve local
  settings, pins, lockfiles and manual Ruff approval.
- Locate consumer files from their Git root. Installed wheels must work without
  consumer imports, databases or network access.

Read the references relevant to your task:

- Python edits: [conventions](.noxala/PYTHON_CONVENTIONS.md).
- CLI or policy edits: [behavior](README.md#check-and-sync),
  [ownership](README.md#configuration-ownership) and
  [fix policy](README.md#native-fix-policy). Canonical policy lives in
  `src/nox_python_standards/resources/`; package metadata in `pyproject.toml`.
- Code or packaging edits: run [validation](README.md#ci-and-package-development).
  Standards must pass before fixes; never auto-sync. Tests mirror modules in `test/`.
- Consumer adoption: [installation](README.md#install-and-adopt); use only a merged,
  immutable commit.

Start new PRs from current `master`; continue existing PRs on their branch.
Request `denisgrenader`, enable auto-merge when supported, and require all quality checks.
