# Noxala Python conventions

This versioned snapshot is owned by the installed `nox-python-standards` release.
Run `nox-py-standards config check` to verify it, or explicitly run
`nox-py-standards config sync` to adopt that release. Review and commit the diff.

## Executable policy

Keep complete Ruff and Pyright settings in the consumer's `pyproject.toml`.
Shared keys must match the installed release; source paths, exclusions, package
classification and approved test exceptions belong to the consumer. Tach alone
generates its consumers' first-party package lists.

Use the exact supported tool versions. Ruff approval is a manual decision:
`config sync`, fixes, dependency installation and CI never grant approval.
The Ruff repair sequence uses unsafe fixes only for the PT007-only step.

## Written guidance

These are review conventions, not an additional AST lint framework:

- Use modern syntax supported by the repository's declared Python version,
  built-in generic forms and PEP 695 where supported.
- Add complete type hints that strict Pyright can resolve without `Unknown`.
- Use explicit `is None` / `is not None` when nullability is the condition.
- Prefer small explicit abstractions to broad dependencies.
- Retain a repository-relative path header in each Python source file.
- Normally use `@dataclass(frozen=True, slots=True, kw_only=True)`.
- Put factory methods on their dataclass, normally `@classmethod create(...)`.
  Keep workflow orchestration and I/O with the subsystem that owns them.
- Test meaningful success, boundary, invalid-input and conflict behavior.
  Avoid tests that only restate the implementation.
- Use `whitelist`, `blacklist` and `master` in code and documentation.

Read the consumer's instructions for its architecture and domain additions.
