"""FastAPI dependency integration without any framework-specific package code."""

import asyncio
import sys
from typing import Annotated

import pytest

from fastapi_settings import SettingsProxy, create_settings
from fastapi_settings.testing import override_settings

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
TestClient = pytest.importorskip("fastapi.testclient").TestClient


def _application(config):
    """Build a real application using FastAPI's native dependency mechanism."""
    app = fastapi.FastAPI()
    app.state.config = config

    def get_config():
        return app.state.config

    @app.get("/config")
    async def read_config(
        selected: Annotated[SettingsProxy, fastapi.Depends(get_config)],
    ):
        return {"value": selected.VALUE}

    return app


def test_fastapi_dependency_injection_and_overrides():
    config = create_settings(settings_object={"DEBUG": False})
    app = fastapi.FastAPI()

    def get_config():
        return config

    @app.get("/config")
    def read_config(selected: Annotated[SettingsProxy, fastapi.Depends(get_config)]):
        return {"debug": selected.DEBUG}

    with TestClient(app) as client:
        assert client.get("/config").json() == {"debug": False}
        app.dependency_overrides[get_config] = lambda: create_settings(
            settings_object={"DEBUG": True}
        )
        assert client.get("/config").json() == {"debug": True}


@pytest.mark.parametrize("synchronous", [False, True])
def test_application_state_sync_and_async_endpoints(settings_module, synchronous):
    name = settings_module("VALUE = 42")
    config = create_settings(module=name)
    app = fastapi.FastAPI()
    app.state.config = config

    def get_config(request: fastapi.Request):
        return request.app.state.config

    def sync_endpoint(selected: Annotated[SettingsProxy, fastapi.Depends(get_config)]):
        return {"value": selected.VALUE}

    async def async_endpoint(
        selected: Annotated[SettingsProxy, fastapi.Depends(get_config)],
    ):
        return {"value": selected.VALUE}

    app.get("/config")(sync_endpoint if synchronous else async_endpoint)
    assert name not in sys.modules
    with TestClient(app) as client:
        assert name not in sys.modules
        assert client.get("/config").json() == {"value": 42}
    assert name in sys.modules
    assert app.state.config is config


@pytest.mark.parametrize("environment", [False, True])
def test_global_settings_initialized_in_lifespan(
    settings_module, run_python, environment
):
    name = settings_module("VALUE = 42")
    selection = (
        f"os.environ['FASTAPI_SETTINGS_MODULE'] = {name!r}"
        if environment
        else f"configure(module={name!r})"
    )
    run_python(
        f"""
        import os, sys
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from fastapi_settings import configure, settings
        {selection}
        events = []
        @asynccontextmanager
        async def lifespan(app):
            assert settings.VALUE == 42
            app.state.config = settings
            events.append('startup')
            try: yield
            finally: events.append('shutdown')
        app = FastAPI(lifespan=lifespan)
        @app.get('/config')
        async def read(): return {{'value': app.state.config.VALUE}}
        assert {name!r} not in sys.modules
        with TestClient(app) as client:
            assert events == ['startup']
            assert client.get('/config').json() == {{'value': 42}}
        assert events == ['startup', 'shutdown']
        """
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (None, "SettingsNotConfiguredError"),
        ("missing", "SettingsModuleImportError"),
        ("invalid", "InvalidSettingsSourceError"),
    ],
)
def test_lifespan_configuration_failures(settings_module, run_python, source, expected):
    name = settings_module("DEBUG = True\nSETTINGS = {'DEBUG': False}")
    selection = (
        ""
        if source is None
        else f"configure(module={name if source == 'invalid' else name + '_missing'!r})"
    )
    run_python(
        f"""
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from fastapi_settings import configure, settings, {expected}
        {selection}
        started = []
        @asynccontextmanager
        async def lifespan(app):
            settings.DEBUG
            started.append(True)
            yield
        app = FastAPI(lifespan=lifespan)
        try:
            with TestClient(app): pass
        except {expected}: pass
        else: raise AssertionError('invalid startup was accepted')
        assert started == []
        """
    )


def test_missing_global_configuration_at_request_time(run_python):
    run_python(
        """
        from typing import Annotated
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient
        from fastapi_settings import settings, SettingsNotConfiguredError, SettingsProxy
        app = FastAPI()
        def get_config(): return settings
        @app.get('/config')
        async def read(config: Annotated[SettingsProxy, Depends(get_config)]):
            return {'value': config.VALUE}
        with TestClient(app) as client:
            try: client.get('/config')
            except SettingsNotConfiguredError: pass
            else: raise AssertionError('missing configuration was accepted')
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get('/config')
            assert response.status_code == 500
            assert response.text == 'Internal Server Error'
        """
    )


@pytest.mark.parametrize("synchronous", [False, True])
def test_async_dependency_override_context_reaches_endpoints(synchronous):
    config = create_settings(settings_object={"VALUE": 0})
    app = fastapi.FastAPI()

    async def get_config():
        with override_settings(config, VALUE=42):
            yield config

    def sync_endpoint(selected: Annotated[SettingsProxy, fastapi.Depends(get_config)]):
        return {"value": selected.VALUE}

    async def async_endpoint(
        selected: Annotated[SettingsProxy, fastapi.Depends(get_config)],
    ):
        return {"value": selected.VALUE}

    app.get("/config")(sync_endpoint if synchronous else async_endpoint)
    with TestClient(app) as client:
        assert client.get("/config").json() == {"value": 42}
    assert config.VALUE == 0


def test_request_failure_cleans_yield_dependency_override():
    config = create_settings(settings_object={"VALUE": 0})
    app = fastapi.FastAPI()
    cleanup = []

    async def get_config():
        try:
            with override_settings(config, VALUE=42):
                yield config
        finally:
            cleanup.append(config.VALUE)

    @app.get("/failure")
    async def fail(selected: Annotated[SettingsProxy, fastapi.Depends(get_config)]):
        assert selected.VALUE == 42
        raise RuntimeError("example request failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/failure").status_code == 500
    assert cleanup == [0] and config.VALUE == 0


@pytest.mark.asyncio
async def test_concurrent_requests_keep_override_contexts_separate():
    config = create_settings(settings_object={"VALUE": -1})
    app = fastapi.FastAPI()
    ready = asyncio.Event()
    arrivals = 0

    async def get_config(request: fastapi.Request):
        with override_settings(config, VALUE=int(request.path_params["value"])):
            yield config

    @app.get("/config/{value}")
    async def read_config(
        selected: Annotated[SettingsProxy, fastapi.Depends(get_config)],
    ):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 8:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=5)
        return {"value": selected.VALUE}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(
            *(client.get(f"/config/{i}") for i in range(8))
        )
    assert [response.json() for response in responses] == [
        {"value": i} for i in range(8)
    ]
    assert config.VALUE == -1


@pytest.mark.asyncio
async def test_independent_applications_and_overrides(settings_module):
    first = create_settings(module=settings_module("VALUE = 1"))
    second = create_settings(module=settings_module("VALUE = 2"))
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_application(first)),
            base_url="http://first",
        ) as a,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_application(second)),
            base_url="http://second",
        ) as b,
    ):
        responses = await asyncio.gather(a.get("/config"), b.get("/config"))
        assert [r.json() for r in responses] == [{"value": 1}, {"value": 2}]
        with override_settings(first, VALUE=10):
            responses = await asyncio.gather(a.get("/config"), b.get("/config"))
            assert [r.json() for r in responses] == [{"value": 10}, {"value": 2}]
        assert first.VALUE == 1 and second.VALUE == 2


def test_same_module_has_independent_snapshots_and_shared_nested_values(
    settings_module,
):
    name = settings_module("VALUE = 1\nNESTED = {'shared': True}")
    first = create_settings(module=name)
    second = create_settings(module=name)
    with TestClient(_application(first)) as a:
        assert a.get("/config").json() == {"value": 1}
        module = sys.modules[name]
        module.VALUE = 2
        with TestClient(_application(second)) as b:
            assert b.get("/config").json() == {"value": 2}
            assert sys.modules[name] is module
            assert first.NESTED is second.NESTED is module.NESTED
            with override_settings(first, VALUE=10):
                assert a.get("/config").json() == {"value": 10}
                assert b.get("/config").json() == {"value": 2}
    assert first.VALUE == 1 and second.VALUE == 2


def test_failed_application_initialization_does_not_affect_another(settings_module):
    from fastapi_settings import InvalidSettingsSourceError

    name = settings_module("SETTINGS = {}")
    failed = create_settings(module=name)
    healthy = create_settings(settings_object={"VALUE": 2})
    with TestClient(_application(failed)) as a, TestClient(_application(healthy)) as b:
        with pytest.raises(InvalidSettingsSourceError):
            a.get("/config")
        assert b.get("/config").json() == {"value": 2}
        # An initially invalid imported source may be repaired before retry.
        sys.modules[name].SETTINGS["VALUE"] = 1
        assert a.get("/config").json() == {"value": 1}
        assert healthy.VALUE == 2


def test_independent_application_initialization_can_run_concurrently(
    settings_module, run_python
):
    support = settings_module("from threading import Barrier\ngate = Barrier(2)")
    names = [
        settings_module(
            f"import {support} as support\nsupport.gate.wait(5)\nVALUE = {value}"
        )
        for value in (1, 2)
    ]
    run_python(
        f"""
        import importlib
        from concurrent.futures import ThreadPoolExecutor
        from typing import Annotated
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient
        from fastapi_settings import create_settings, SettingsProxy
        importlib.import_module({support!r})
        def request(name):
            config = create_settings(module=name)
            app = FastAPI()
            def get_config(): return config
            @app.get('/config')
            async def read(selected: Annotated[SettingsProxy, Depends(get_config)]):
                return {{'value': selected.VALUE}}
            with TestClient(app) as client:
                return client.get('/config').json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, name) for name in {names!r}]
            responses = [future.result(timeout=10) for future in futures]
        assert responses == [{{'value': 1}}, {{'value': 2}}]
        """
    )
