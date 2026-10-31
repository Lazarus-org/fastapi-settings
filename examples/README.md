# Runnable FastAPI examples

Run these commands from the repository root with CPython 3.11 or newer:

```bash
python -m pip install -e .
python -m pip install fastapi pydantic-settings httpx
```

These are optional application dependencies. The settings package itself does not require them. The examples are source-checkout examples; they are not installed as part of the wheel.

Each `app.py` exports a real FastAPI application. Running it as a module executes requests with `TestClient`, checks the responses, and exits; it does not start a web server. For interactive serving, use your ASGI server with the application import path, such as `examples.basic.app:app`.

## Module-level settings

```bash
python -m examples.basic.app
```

[basic/app.py](basic/app.py) selects [basic/settings.py](basic/settings.py) explicitly during application lifespan startup. It initializes the global proxy before requests are served and provides it through a native `Annotated` dependency. If `FASTAPI_SETTINGS_MODULE` is already set, it must match `examples.basic.settings`; otherwise unset it before running this example.

## Pydantic Settings and environment variables

Set the required database URL and optional values using your shell:

```bash
export APP_DATABASE_URL=postgresql://localhost/example
export APP_DEBUG=true
export APP_API_KEY=example-only-token
python -m examples.pydantic.app
```

PowerShell:

```powershell
$env:APP_DATABASE_URL = "postgresql://localhost/example"
$env:APP_DEBUG = "true"
$env:APP_API_KEY = "example-only-token"
python -m examples.pydantic.app
```

[pydantic/settings.py](pydantic/settings.py) also supports a `.env` file in the current working directory. Pydantic handles parsing, validation, the `APP_` prefix, and source precedence; environment values take priority over dotenv values. The required `database_url` has no fallback. `debug` defaults to `False`, and `api_key` is an optional `SecretStr`.

[pydantic/app.py](pydantic/app.py) constructs its model when the proxy is first accessed during lifespan startup. Invalid configuration therefore prevents startup. The endpoint reports whether a key exists without returning it or serializing the settings model.

## Native dependency overrides

```bash
python -m examples.dependency_overrides.app
```

[dependency_overrides/app.py](dependency_overrides/app.py) replaces a FastAPI dependency using `app.dependency_overrides`, then clears the replacement. This replaces the selected provider; it does not mutate the original configuration.

## Independent application configurations

```bash
python -m examples.independent.app
```

[independent/app.py](independent/app.py) creates two FastAPI applications in one process. Each receives an independent proxy. A scoped override on the first proxy leaves the second unaffected.

Independent proxies do not copy or reload Python modules. If two proxies reference the same module, Python imports that module normally and each proxy captures its own snapshot at first access. Nested mutable values may still be shared, as documented by the shallow-snapshot contract.

## Choosing a dynamic proxy or a typed model

The proxy provides a stable import point, lazy module discovery, and context-local overrides. Its attributes are dynamic: annotating a dependency as `SettingsProxy` does not let a type checker validate individual setting names or types.

For static field checking, a dependency can return your concrete Pydantic settings class directly. That uses FastAPI's native dependency mechanism and Pydantic's normal initialization timing, while bypassing proxy-specific overrides. Passing an already constructed model to `create_settings(settings_object=model)` preserves its field types and names, but model validation has already happened. `override_settings` replaces proxy values without rerunning Pydantic validators or changing the model.
