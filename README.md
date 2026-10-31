# fastapi-settings

[![CI](https://github.com/Lazarus-org/fastapi-settings/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Lazarus-org/fastapi-settings/actions/workflows/ci.yml)
[![CPython](https://img.shields.io/badge/CPython-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14%20%7C%203.15-blue)](#installation)
[![Typing](https://img.shields.io/badge/typing-py.typed-blue)](#configuration-contract)
[![Runtime dependencies](https://img.shields.io/badge/runtime_dependencies-0-brightgreen)](https://github.com/Lazarus-org/fastapi-settings/blob/main/pyproject.toml)
[![uv](https://img.shields.io/badge/package_manager-uv-DE5FE9)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/badge/code_style-Ruff-261230)](https://docs.astral.sh/ruff/)
[![Conventional Commits](https://img.shields.io/badge/commits-Conventional_Commits-FE5196)](https://www.conventionalcommits.org/)
[![License](https://img.shields.io/github/license/Lazarus-org/fastapi-settings)](https://github.com/Lazarus-org/fastapi-settings/blob/main/LICENSE)
[![Coverage](https://codecov.io/gh/lazarus-org/dj-notification-api/branch/main/graph/badge.svg)](https://codecov.io/gh/lazarus-org/fastapi-settings)

Centralized, lazy application settings for Python and FastAPI projects, with a Django-inspired import experience and no required runtime dependencies.

`fastapi-settings` deliberately does **not** replace [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). It provides a common settings proxy, configurable module discovery, independent settings containers, and temporary test overrides. Environment parsing and value validation remain the application's responsibility.

## Installation

```bash
uv add fastapi-settings
```

CPython 3.11 or newer is required. Supported versions are CPython 3.11, 3.12, 3.13, 3.14, and 3.15. PyPy and other Python implementations are not currently supported. FastAPI, Pydantic, and Pydantic Settings are optional.

## Quick start

Create an importable Python settings module:

```python
# config/settings.py
DEBUG = False
DATABASE_URL = "postgresql://localhost/app"
FASTAPI_LOGGING = {"level": "INFO"}
```

Select it with an environment variable:

```bash
export FASTAPI_SETTINGS_MODULE=config.settings
```

Use the settings anywhere:

```python
from fastapi_settings import settings

if settings.DEBUG:
    print("Debug mode enabled")
```

The settings module is imported **only when a value is first accessed**. A selected module is imported through Python's standard import system, including its normal module caching behavior. The proxy takes a shallow snapshot of its top-level settings values at initialization.

### Explicit configuration

Instead of setting `FASTAPI_SETTINGS_MODULE`, explicitly configure the default proxy before accessing any settings:

```python
from fastapi_settings import configure, settings

configure(module="config.settings")
print(settings.DEBUG)
```

Or pass an existing object or mapping:

```python
configure(settings_object={"DEBUG": False, "PORT": 8000})
```

Pass **exactly one** of `module` or `settings_object`. Re-selecting the same module or the **same object instance** is idempotent; changing the source raises `SettingsAlreadyConfiguredError`. If `FASTAPI_SETTINGS_MODULE` is defined, explicit global configuration must select that exact module. After source selection, environment changes do not affect the proxy.

### Pydantic Settings

Use Pydantic for typed fields, environment variables, `.env` files, or secrets, then export a `SETTINGS` instance from your module:

```python
# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env")

    debug: bool = False
    database_url: str

SETTINGS = ApplicationSettings()
```

```python
from fastapi_settings import settings

print(settings.debug)
print(settings.database_url)
```

The package preserves field names and delegates all validation, environment precedence, and dotenv behavior to Pydantic. Install Pydantic Settings separately if you use this option:

```bash
uv add pydantic-settings
```

**Source selection:** A module must contain either public uppercase bindings **or** one `SETTINGS` object, not both. Every public uppercase binding is a setting, whether defined locally or imported, including scalar constants, classes, functions, and intentional re-exports:

```python
from socket import AF_INET
from pathlib import Path as PATH_CLASS

DEBUG = True
# settings.AF_INET, settings.PATH_CLASS, and settings.DEBUG are all available.
```

Private names, internal Python module attributes, lowercase bindings, and imported module objects are ignored in module-level mode. An imported uppercase binding alongside `SETTINGS` raises `InvalidSettingsSourceError`, just like a locally defined uppercase setting. Use lowercase or private aliases for helper imports in `SETTINGS` mode. No import-provenance inference or automatic case conversion occurs.

A `SETTINGS` object may be a mapping, a dataclass instance, or an ordinary object with public instance attributes. Mapping keys must be valid public Python attribute names. Ordinary object class attributes and properties are not included in the snapshot.

### Initialization and recovery

The lifecycle is **unconfigured → configured → initializing → initialized**. Source selection is permanent and follows the module-path/object-identity rules above. A failed attempt returns to **configured**, without publishing a snapshot; a later access retries the same source. There is no automatic reload after success.

Each proxy has one initialization owner. Ordinary concurrent readers wait for that attempt to finish. Imports and source-object inspection execute outside the proxy state lock; only source selection, ownership, snapshot publication, and waiter notification use that lock. All waiting readers are notified after success or failure, including cancellation through a `BaseException`.

Access during an incomplete settings-module import raises `SettingsInitializationError`. Do not read the proxy from the settings module or its import-time dependencies. If application code catches this exception and lets the module finish importing, a subsequent access can initialize the complete snapshot.

Recursive access by the initialization owner also raises `SettingsInitializationError`. A caller already executing import code or initializing another proxy will not wait on a busy proxy: it raises the same exception to prevent import-lock and cross-proxy cycles. Acyclic access to an idle independent proxy remains supported. Unrelated concurrent callers continue to wait normally. The package cannot resolve deadlocks created entirely by application locks or by application code joining workers that depend on its own initialization.

Python has no public import-completion query. Import-state detection relies on the private CPython implementation attribute `ModuleSpec._initializing`, checked before and after import, and active import frames to decide when waiting is unsafe. It does not acquire private importlib locks. CPython changes to this private attribute may require compatibility updates; this is why support currently targets CPython. Real-import subprocess tests run in the CPython 3.11–3.15 CI matrix. Manually registered, already constructed modules without that marker remain supported.

### Independent containers

Use separate settings proxies when multiple configurations are needed within one Python process:

```python
from fastapi_settings import create_settings

a = create_settings(module="config.settings.development")
b = create_settings(settings_object={"DEBUG": False})

print(a.DEBUG, b.DEBUG)
```

Unlike the default global `settings`, independent proxies never consult `FASTAPI_SETTINGS_MODULE` and require an explicit source.

### Isolated testing overrides

```python
from fastapi_settings import create_settings
from fastapi_settings.testing import override_settings

config = create_settings(settings_object={"DEBUG": False})

with override_settings(config, DEBUG=True):
    assert config.DEBUG is True

assert config.DEBUG is False
```

For the default global proxy, omit the first argument:

```python
from fastapi_settings import settings
from fastapi_settings.testing import override_settings

with override_settings(DEBUG=True):
    assert settings.DEBUG
```

An override must target existing top-level settings, replaces the **entire value** (no deep merge), and is automatically cleaned up even after an exception. Overrides do not validate types; create a Pydantic settings object yourself if you need validation.

Overrides use Python `contextvars` for thread and asyncio-task isolation. **A newly created child asyncio task inherits its creator's context:** if it outlives an override block, it can continue seeing that inherited override. Avoid spawning long-lived child tasks inside test override scopes.

### FastAPI dependencies

FastAPI's native dependency injection remains available; no special integration layer is needed:

```python
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi_settings import SettingsProxy, settings

app = FastAPI()

def get_settings() -> SettingsProxy:
    return settings

@app.get("/health")
def health(config: Annotated[SettingsProxy, Depends(get_settings)]):
    return {"debug": config.DEBUG}
```

FastAPI's `app.dependency_overrides` can replace `get_settings` in integration tests. Synchronous and asynchronous endpoints can use the same proxy. To fail before serving requests, access a required setting in a FastAPI lifespan handler; otherwise initialization remains lazy until the first access.

The proxy preserves original Pydantic field values and types, but its dynamic attributes do not provide static field checking. Return a concrete Pydantic settings class directly from a dependency when static typing matters more than proxy discovery and scoped overrides. Constructing a model before passing it to `create_settings` runs Pydantic initialization immediately; exporting a model from a lazily imported settings module defers construction until that module is imported. Overrides do not rerun model validation.

See the [runnable examples](https://github.com/Lazarus-org/fastapi-settings/tree/main/examples) for module-level settings, Pydantic environment configuration, native dependency overrides, and independent applications. Pydantic remains responsible for source precedence, custom sources, nested models, secrets, and validation.

## Configuration contract

| Detail | Behavior |
| --- | --- |
| Discovery | `FASTAPI_SETTINGS_MODULE` or explicit `configure()` |
| First access | Loads once and caches the resulting top-level snapshot |
| Object sources | Mapping, dataclass, or public instance attributes |
| Missing value | Normal `AttributeError` |
| Assignment or deletion | Rejected (`AttributeError`) |
| Mapping-style `settings["KEY"]` | Not supported |
| `.env` parsing | Not performed by the core; delegate to Pydantic or your application |
| Runtime reload | Not supported |
| Deep immutability | Not provided; nested mutable values remain shared |
| Production configuration mutation | Not supported |
| Testing | Context-local, reversible top-level replacements |

The public exceptions are exported from `fastapi_settings` and `fastapi_settings.exceptions`:

| Exception | Meaning |
| --- | --- |
| `FastAPISettingsError` | Base class for package-managed configuration errors |
| `SettingsNotConfiguredError` | No source is selected when a value is accessed |
| `SettingsAlreadyConfiguredError` | A different source or conflicting environment module is selected |
| `SettingsModuleImportError` | The selected module failed to import; its original exception is chained |
| `InvalidSettingsSourceError` | Empty or unsupported source, invalid mapping keys, or mixed module styles |
| `SettingsInitializationError` | Recursive, incomplete-import, or unsafe cyclic initialization |
| `SettingsOverrideError` | Empty overrides or unknown setting names |

Invalid call arguments raise `TypeError` or `ValueError`. Missing attributes on an initialized proxy raise `AttributeError`. Exceptions raised while inspecting a custom source object remain application exceptions.

`configure()` returns `None` and selects the global source without loading it. `create_settings()` returns a lazy `SettingsProxy`. The exported `SettingsProxy` name is available for annotations and instance checks; use the factory to construct configured independent instances. Empty mappings and objects with no public settings are rejected. Ordinary public slots are included alongside public instance attributes; properties and class attributes are excluded.

The proxy's representation never includes configuration values. Module import exceptions retain their Python exception causes for debugging, which means application or dependency exceptions might still reveal information in a traceback; secure the application-level error handling and logging accordingly. Treat settings modules as trusted application code, never as untrusted user-supplied paths.

## Development

We use [uv](https://docs.astral.sh/uv/) to manage project environments and dependencies. We also use the `uv_build` backend to create wheels and source distributions. Plain `uv sync` installs the default `dev` group, including test and quality tools. To use the checked-in lockfile without updating it and run the suite:

```bash
uv sync --locked
uv run --locked pytest -q --cov=fastapi_settings
uv run --locked ruff check src tests examples .github/scripts
uv run --locked ruff format --check src tests examples .github/scripts
uv run --locked mypy src/
```

The `quality` extra pins Ruff to 0.17.3, and the Ruff configuration requires that exact version locally and in CI. Update the pin and required version together after checking the full quality suite. It also provides mypy, Twine, Commitizen, pre-commit, tox, Bandit, and TOML/tox formatters. Ruff formats Python source, tests, examples, and CI scripts; Markdown is maintained separately.

Coverage measures both statements and branches, including subprocess import and concurrency regressions, and requires 100%. Each CPython matrix job runs the full suite with coverage, builds distributions, tests the extracted source archive, compares its rebuilt wheel's contents, and installs the wheel in a fresh environment without optional dependencies. Lint, formatting, type checks, and strict package-description validation run in a separate quality job. A configured matrix is not evidence of successful execution; consult the actual workflow results for compatibility validation.

To run the same distribution validation locally after building:

```bash
uv build
uv run --locked python -m twine check --strict dist/*
uv run --locked python .github/scripts/validate_distribution.py dist --test-sdist
```

Build into an empty `dist` directory. See the [contributor guide](https://github.com/Lazarus-org/fastapi-settings/blob/main/CONTRIBUTING.md) and [security policy](https://github.com/Lazarus-org/fastapi-settings/blob/main/SECURITY.md).

Use `uv run --locked cz commit` for Conventional Commits with the relevant issue footer. See [AUTHORS.md](https://github.com/Lazarus-org/fastapi-settings/blob/main/AUTHORS.md), [CONTRIBUTORS.md](https://github.com/Lazarus-org/fastapi-settings/blob/main/CONTRIBUTORS.md), and [CODE_OF_CONDUCT.md](https://github.com/Lazarus-org/fastapi-settings/blob/main/CODE_OF_CONDUCT.md) for project and community information.
