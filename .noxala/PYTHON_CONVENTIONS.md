# Noxala Python conventions

Versioned by the installed `nox-py-standards` release. `nox-py-standards check`
verifies this snapshot; explicit `sync` adopts it. Review and commit changes.

## Tool policy

Keep complete Ruff/Pyright settings in local `pyproject.toml`. Shared values and
exact tool pins match the installed release. Paths, exclusions, import
classification and approved test exceptions stay local; Tach alone generates
first-party lists.

Ruff version approval is manual; sync, installation and CI never grant it.
Only PT007 is approved among unsafe fixes. Repositories own tool commands,
Makefiles, hooks and source-header helpers.

## Python guidance

These are review conventions, not an additional AST checker.

- Use supported modern syntax, built-in generics and PEP 695.
- Type fully for strict Pyright, without `Unknown`.
- Check nullability with `is None` / `is not None`.
- Prefer small abstractions to broad dependencies.
- Keep a repository-relative path header in each Python source.
- Default to `@dataclass(frozen=True, slots=True, kw_only=True)`; put factory
  methods on the dataclass, normally `@classmethod create(...)`.
- Keep orchestration and I/O with the owning subsystem.
- Test meaningful success, boundary, invalid-input and conflict behavior.
  Avoid tests that restate the implementation.
- Use `whitelist`, `blacklist` and `master`.

Follow repository instructions for architecture and domain rules.
