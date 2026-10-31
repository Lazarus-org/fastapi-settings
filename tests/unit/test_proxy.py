"""Lazy proxy, independence, and mutation prevention tests."""

from __future__ import annotations

import concurrent.futures

import pytest

from fastapi_settings import SettingsProxy, create_settings
from fastapi_settings.exceptions import SettingsNotConfiguredError


def test_unconfigured_proxy_fails_on_access():
    proxy = SettingsProxy()
    assert "unconfigured" in repr(proxy)
    with pytest.raises(SettingsNotConfiguredError):
        _ = proxy.DEBUG


def test_lazy_object_snapshot_is_stable():
    data = {"DEBUG": False}
    proxy = create_settings(settings_object=data)
    assert "configured" in repr(proxy)
    data["DEBUG"] = True
    assert proxy.DEBUG is True
    assert "initialized" in repr(proxy)


def test_readonly_proxy_rejects_assignment_and_deletion():
    proxy = create_settings(settings_object={"DEBUG": True})
    with pytest.raises(AttributeError, match="read-only"):
        proxy.DEBUG = False
    with pytest.raises(AttributeError, match="read-only"):
        del proxy.DEBUG
    with pytest.raises(AttributeError, match="read-only"):
        proxy._values = {}


def test_undefined_attribute_raises_attribute_error():
    proxy = create_settings(settings_object={"DEBUG": True})
    with pytest.raises(AttributeError):
        _ = proxy.DOES_NOT_EXIST
    assert not hasattr(proxy, "DOES_NOT_EXIST")


def test_independent_instances_cannot_affect_each_other():
    a = create_settings(settings_object={"DEBUG": True})
    b = create_settings(settings_object={"DEBUG": False})
    assert a.DEBUG is True
    assert b.DEBUG is False


def test_safe_repr_does_not_display_values_or_source():
    proxy = create_settings(settings_object={"API_KEY": "SUPER_SECRET_TEST_TOKEN"})
    assert "SUPER_SECRET_TEST_TOKEN" not in repr(proxy)
    assert "SUPER_SECRET_TEST_TOKEN" not in repr(proxy.API_KEY.__class__)
    _ = proxy.API_KEY
    assert repr(proxy) == "<SettingsProxy initialized>"


def test_threadsafe_initialization_is_consistent():
    data = {"PORT": 9090}
    proxy = create_settings(settings_object=data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        assert list(executor.map(lambda _: proxy.PORT, range(100))) == [9090] * 100
