"""Context-local settings override semantics and concurrency tests."""

from __future__ import annotations

import asyncio
import concurrent.futures

import pytest

from fastapi_settings import create_settings
from fastapi_settings.exceptions import SettingsOverrideError
from fastapi_settings.testing import override_settings


def test_override_restores_original_value():
    proxy = create_settings(settings_object={"DEBUG": False})
    with override_settings(proxy, DEBUG=True):
        assert proxy.DEBUG is True
    assert proxy.DEBUG is False


def test_nested_overrides():
    proxy = create_settings(settings_object={"DEBUG": False, "PORT": 1000})
    with override_settings(proxy, DEBUG=True):
        with override_settings(proxy, DEBUG=False, PORT=2000):
            assert proxy.DEBUG is False
            assert proxy.PORT == 2000
        assert proxy.DEBUG is True
        assert proxy.PORT == 1000
    assert proxy.DEBUG is False


def test_override_does_not_mutate_source():
    source = {"DEBUG": False}
    proxy = create_settings(settings_object=source)
    with override_settings(proxy, DEBUG=True):
        assert source["DEBUG"] is False
    assert source["DEBUG"] is False


def test_unknown_override_is_rejected():
    proxy = create_settings(settings_object={"DEBUG": True})
    with (
        pytest.raises(SettingsOverrideError, match="unknown"),
        override_settings(proxy, DEBUG=False, NOT_DEFINED=True),
    ):
        pass


def test_empty_override_is_rejected():
    proxy = create_settings(settings_object={"DEBUG": True})
    with (
        pytest.raises(SettingsOverrideError, match="At least one"),
        override_settings(proxy),
    ):
        pass


def test_override_restores_on_exception():
    proxy = create_settings(settings_object={"DEBUG": False})
    with pytest.raises(RuntimeError), override_settings(proxy, DEBUG=True):
        raise RuntimeError("failure")
    assert proxy.DEBUG is False


def test_full_replacement_no_deep_merge():
    config = create_settings(settings_object={"DATABASES": {"main": 1, "backup": 2}})
    with override_settings(config, DATABASES={"main": 3}):
        assert config.DATABASES == {"main": 3}
    assert config.DATABASES == {"main": 1, "backup": 2}


def test_independent_instances_have_independent_overrides():
    first = create_settings(settings_object={"DEBUG": False})
    second = create_settings(settings_object={"DEBUG": False})
    with override_settings(first, DEBUG=True):
        assert first.DEBUG is True
        assert second.DEBUG is False


def test_invalid_target():
    with (
        pytest.raises(TypeError, match="SettingsProxy"),
        override_settings("not a proxy", DEBUG=True),  # type: ignore[arg-type]
    ):
        pass


def test_thread_context_isolation():
    config = create_settings(settings_object={"DEBUG": False})

    def worker():
        assert config.DEBUG is False
        with override_settings(config, DEBUG=True):
            assert config.DEBUG is True
        return config.DEBUG

    with (
        concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor,
        override_settings(config, DEBUG=True),
    ):
        assert list(executor.map(lambda _: worker(), range(20))) == [False] * 20
        assert config.DEBUG is True
    assert config.DEBUG is False


@pytest.mark.asyncio
async def test_async_tasks_keep_independent_contexts():
    config = create_settings(settings_object={"DEBUG": False})
    gate = asyncio.Event()

    async def overrider():
        with override_settings(config, DEBUG=True):
            gate.set()
            await asyncio.sleep(0)
            assert config.DEBUG is True
        return config.DEBUG

    async def observer():
        await gate.wait()
        assert config.DEBUG is False
        return config.DEBUG

    results = await asyncio.gather(overrider(), observer())
    assert results == [False, False]


@pytest.mark.asyncio
async def test_child_task_inherits_context_at_creation():
    config = create_settings(settings_object={"DEBUG": False})
    gate = asyncio.Event()

    async def child():
        await gate.wait()
        return config.DEBUG

    with override_settings(config, DEBUG=True):
        task = asyncio.create_task(child())
    gate.set()
    # Explicitly document Python's ContextVar child-task inheritance.
    assert await task is True
    assert config.DEBUG is False


@pytest.mark.asyncio
async def test_cancellation_cleans_nested_overrides_on_independent_proxies():
    first = create_settings(settings_object={"DEBUG": False})
    second = create_settings(settings_object={"DEBUG": False})
    entered = asyncio.Event()
    observed = []

    async def worker():
        try:
            with (
                override_settings(first, DEBUG=True),
                override_settings(second, DEBUG=True),
            ):
                entered.set()
                await asyncio.Future()
        finally:
            observed.append((first.DEBUG, second.DEBUG))

    task = asyncio.create_task(worker())
    await entered.wait()
    assert first.DEBUG is False and second.DEBUG is False
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert observed == [(False, False)]
