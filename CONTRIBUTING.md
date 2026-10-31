# Contributing to fastapi-settings

Bug reports, focused fixes, tests, and documentation improvements are welcome. Discuss substantial behavior or API changes before implementation.

## Development setup

Use CPython 3.11 or newer. The supported matrix is CPython 3.11–3.15.

```bash
git clone https://github.com/Lazarus-org/fastapi-settings.git
cd fastapi-settings
uv sync --locked
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first. uv creates `.venv` automatically; `uv run` works on both PowerShell and POSIX shells without activation. Plain `uv sync` installs the default `dev` dependency group, including tests and quality tools. Use `uv sync --locked` to require the checked-in lockfile and `uv sync --locked --no-dev` for a runtime-only environment. The `test` and `quality` extras remain available for tox and archive validation; installing the runtime package requires only the standard library. Commit `uv.lock` updates alongside dependency changes. Use `uv lock --upgrade-package PACKAGE` for a targeted update, then rerun the quality checks.

## Quality workflow

```bash
uv run --locked python -m pytest --cov=fastapi_settings
uv run --locked ruff check src tests examples .github/scripts
uv run --locked ruff format --check src tests examples .github/scripts
uv run --locked mypy src/
uv pip check
uv run --locked python -m pre_commit run --all-files
```

Coverage includes statements and branches across the test process and its Python subprocesses. Full-suite coverage runs must reach 100%; CI, tox, and the pre-commit/manual pytest hook enforce this threshold. For focused test selection, omit `--cov=fastapi_settings`.

Ruff 0.17.3 owns Python formatting and import checks. Update its dependency pin and required version together. The same pre-commit configuration is used locally and in CI. It checks file hygiene, formats TOML/tox and Python files, verifies the uv lockfile offline, runs mypy and Bandit on the core, and runs the full suite with the 100% coverage gate. All local tool hooks use the locked uv environment. The full suite is also available as a manual hook:

```bash
uv run --locked python -m pre_commit run pytest --hook-stage manual --all-files
```

Install the local Git hook stages and use Commitizen for commits:

```bash
uv run --locked python -m pre_commit install
uv run --locked cz commit
```

Commitizen uses Conventional Commits and its `uv` version provider reads version `1.0.0` from `project.version`. During an explicitly requested version bump, it also updates the matching package version in `uv.lock`. Include the appropriate issue footer, such as `Closes #123`. Running `uv run --locked cz commit` does not bump the package version. Version bumps, tags, pushes, and publication require a separate release decision.

## Compatibility and packaging

```bash
uv run --locked python -m tox list
uv run --locked python -m tox -e py313
uv run --locked python -m tox -e lint,type
uv run --locked python -m tox -e build
```

tox uses the `tox-uv` runner for environment creation, dependency installation, and package builds. The five CPython environments run the complete suite, including optional framework integrations and executable examples. Missing interpreters cause failures rather than silently skipping compatibility checks. Report actual interpreter and dependency versions when sharing results.

Build into an empty output directory and validate the exact artifacts:

```bash
uv build
uv run --locked python -m twine check --strict dist/*
uv run --locked python .github/scripts/validate_distribution.py dist --test-sdist
```

The validator checks wheel metadata, runtime files, license, typing marker, and source-archive completeness. It verifies core operation in a fresh environment without optional dependencies. The archive check runs tests from extracted sources and compares the rebuilt wheel's contents with the original.

The `uv_build` backend uses `[tool.uv.build-backend]` in `pyproject.toml` to include tests, examples, maintainer documents, and the configuration needed to reproduce these checks in source distributions. Wheels contain the runtime package, typing marker, metadata, and license files. Keep credentials, local environments, IDE metadata, bytecode, and build outputs out of distributions.

## Design and pull requests

- Keep the core free of mandatory dependencies and framework imports.
- Preserve lazy initialization, source identity rules, shallow snapshots, and context-local overrides.
- Delegate parsing and validation to the application or Pydantic.
- Preserve exception causes without printing configuration values.
- Test real framework behavior and use bounded subprocesses for potential deadlocks.
- Use synchronization events or barriers instead of timing assumptions in concurrency tests.

Describe the problem, resulting behavior, relevant issue, and meaningful validation in each pull request. Refer to confirmed issue numbers in commits. Do not include credentials in code, examples, or fixtures.

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [SECURITY.md](SECURITY.md). Local results do not establish hosted CI success or authorize publication.
