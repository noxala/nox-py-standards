# Noxala Python conventions

This versioned snapshot is owned by the installed `nox-python-standards` release.
Run `nox-py-standards check` to verify it, or explicitly run
`nox-py-standards sync` to adopt that release. Review and commit the diff.

## Executable policy

Keep complete Ruff and Pyright settings in the consumer's `pyproject.toml`.
Shared keys must match the installed release; source paths, exclusions, package
classification and approved test exceptions belong to the consumer. Tach alone
generates its consumers' first-party package lists.

Use the exact supported tool versions. Ruff approval is a manual decision:
`sync`, dependency installation and CI never grant approval.
Keep exact tool pins locally. The checked Ruff settings approve only PT007 among
otherwise-unsafe fixes (`extend-safe-fixes`); other unsafe fixes stay disabled.
Repositories own tool invocation, Makefiles, hooks and source-header helpers.

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
