# Contributing to fastapi-settings

Bug reports, focused fixes, tests, and documentation improvements are welcome. Discuss substantial behavior or API changes before implementation.

## Development setup

Use CPython 3.11 or newer. The supported matrix is CPython 3.11–3.15.

```bash
git clone https://github.com/Lazarus-org/fastapi-settings.git
cd fastapi-settings
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test,quality]"
```

On PowerShell, activate with `.venv\Scripts\Activate.ps1` instead. Development tools are optional extras; installing the runtime package requires only the standard library. There is no UV or Poetry lockfile requirement.

## Quality workflow

```bash
python -m pytest
ruff check src tests examples .github/scripts
ruff format --check src tests examples .github/scripts
mypy src/
python -m pip check
python -m pre_commit run --all-files
```

Ruff 0.17.3 owns Python formatting and import checks. Update its dependency pin and required version together. The same pre-commit configuration is used locally and in CI; it checks files, lint, and formatting. The full suite is also available as a manual hook:

```bash
python -m pre_commit run pytest --hook-stage manual --all-files
```

Install the local Git hook stages and use Commitizen for commits:

```bash
python -m pre_commit install
cz commit
```

Commitizen uses Conventional Commits and reads version `1.0.0` from `project.version`. Include the appropriate issue footer, such as `Closes #123`. Running `cz commit` does not bump the package version. Version bumps, tags, pushes, and publication require a separate release decision.

## Compatibility and packaging

```bash
python -m tox list
python -m tox -e py313
python -m tox -e lint,type
python -m tox -e build
```

The five CPython environments run the complete suite, including optional framework integrations and executable examples. Missing interpreters cause failures rather than silently skipping compatibility checks. Report actual interpreter and dependency versions when sharing results.

Build into an empty output directory and validate the exact artifacts:

```bash
python -m build
python -m twine check --strict dist/*
python .github/scripts/validate_distribution.py dist --test-sdist
```

The validator checks wheel metadata, runtime files, license, typing marker, and source-archive completeness. It verifies core operation in a fresh environment without optional dependencies. The archive check runs tests from extracted sources and compares the rebuilt wheel's contents with the original.

`MANIFEST.in` includes tests, examples, maintainer documents, and the configuration needed to reproduce these checks. Keep credentials, local environments, IDE metadata, bytecode, and build outputs out of distributions.

## Design and pull requests

- Keep the core free of mandatory dependencies and framework imports.
- Preserve lazy initialization, source identity rules, shallow snapshots, and context-local overrides.
- Delegate parsing and validation to the application or Pydantic.
- Preserve exception causes without printing configuration values.
- Test real framework behavior and use bounded subprocesses for potential deadlocks.
- Use synchronization events or barriers instead of timing assumptions in concurrency tests.

Describe the problem, resulting behavior, relevant issue, and meaningful validation in each pull request. Refer to confirmed issue numbers in commits. Do not include credentials in code, examples, or fixtures.

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md), and [RELEASING.md](RELEASING.md). Local results do not establish hosted CI success or authorize publication.
