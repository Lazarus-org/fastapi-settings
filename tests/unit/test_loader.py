"""Module source and object source loading tests."""

from __future__ import annotations

import dataclasses
import math

import pytest

from fastapi_settings import create_settings
from fastapi_settings.exceptions import (
    InvalidSettingsSourceError,
    SettingsModuleImportError,
)


def test_module_constants(module_factory):
    name = module_factory(DEBUG=False, DATABASE_URL="db", _SECRET="ignored", other=1)
    config = create_settings(module=name)
    assert config.DEBUG is False
    assert config.DATABASE_URL == "db"
    with pytest.raises(AttributeError):
        _ = config.other
    with pytest.raises(AttributeError):
        _ = config._SECRET


def test_module_ignores_imported_module(module_factory):
    name = module_factory(DEBUG=True, OS=math)
    config = create_settings(module=name)
    assert config.DEBUG
    with pytest.raises(AttributeError):
        _ = config.OS


def test_imported_uppercase_bindings_and_reexports_are_settings(module_factory):
    from pathlib import Path
    from socket import AF_INET
    from urllib.parse import urlparse

    name = module_factory(
        AF_INET=AF_INET,
        PATH_CLASS=Path,
        PARSE_URL=urlparse,
        EXPORTED=AF_INET,
        MODULE=math,
        _PRIVATE_IMPORT=Path,
        lowercase_import=urlparse,
    )
    proxy = create_settings(module=name)
    assert proxy.AF_INET == AF_INET
    assert proxy.PATH_CLASS is Path
    assert proxy.PARSE_URL is urlparse
    assert proxy.EXPORTED == AF_INET
    for ignored in ("MODULE", "_PRIVATE_IMPORT", "lowercase_import"):
        with pytest.raises(AttributeError):
            getattr(proxy, ignored)


@pytest.mark.parametrize("binding", [1, math.sqrt, str])
def test_uppercase_import_alongside_settings_is_invalid(module_factory, binding):
    proxy = create_settings(
        module=module_factory(IMPORTED=binding, SETTINGS={"OK": True})
    )
    with pytest.raises(InvalidSettingsSourceError, match="cannot combine"):
        _ = proxy.OK


def test_module_with_settings_mapping(module_factory):
    name = module_factory(SETTINGS={"debug": True, "database_url": "db"})
    config = create_settings(module=name)
    assert config.debug is True
    assert config.database_url == "db"
    with pytest.raises(AttributeError):
        _ = config.DEBUG


def test_module_with_settings_object(module_factory):
    class Settings:
        def __init__(self):
            self.DEBUG = False
            self.DATABASE_URL = "postgres"

    name = module_factory(SETTINGS=Settings())
    assert create_settings(module=name).DATABASE_URL == "postgres"


def test_mixed_module_source_is_invalid(module_factory):
    name = module_factory(DEBUG=True, SETTINGS={"DEBUG": False})
    config = create_settings(module=name)
    with pytest.raises(InvalidSettingsSourceError, match="cannot combine"):
        _ = config.DEBUG


def test_empty_module_is_invalid(module_factory):
    config = create_settings(module=module_factory(lowercase=True))
    with pytest.raises(InvalidSettingsSourceError, match="must expose"):
        _ = config.DEBUG


def test_module_import_error_preserves_cause():
    config = create_settings(module="_a_module_that_does_not_exist")
    with pytest.raises(SettingsModuleImportError) as exc:
        _ = config.DEBUG
    assert isinstance(exc.value.__cause__, ModuleNotFoundError)


def test_invalid_module_name_fails_at_configuration():
    for module in ("", "a..b", ".a", "a.", "a-b", "class.name", " a "):
        with pytest.raises(ValueError):
            create_settings(module=module)
    with pytest.raises(TypeError):
        create_settings(module=123)  # type: ignore[arg-type]


def test_dataclass_snapshot_including_slots():
    @dataclasses.dataclass(slots=True)
    class Config:
        debug: bool = False
        port: int = 8080
        _private: str = "internal"

    config = create_settings(settings_object=Config(debug=True))
    assert config.debug is True
    assert config.port == 8080
    with pytest.raises(AttributeError):
        _ = config._private


def test_invalid_mapping_keys_fail():
    for source in ({1: "bad"}, {"bad-key": 1}, {"_private": 1}, {"class": 2}):
        config = create_settings(settings_object=source)
        with pytest.raises(InvalidSettingsSourceError, match="mapping keys"):
            _ = config.DEBUG


def test_invalid_objects_fail():
    for source in (42, object(), {}, type("Config", (), {"DEBUG": True})):
        config = create_settings(settings_object=source)
        with pytest.raises(InvalidSettingsSourceError):
            _ = config.DEBUG


def test_no_public_instance_settings_rejected():
    class Config:
        def __init__(self):
            self._private = "private"

    config = create_settings(settings_object=Config())
    with pytest.raises(InvalidSettingsSourceError, match="no public"):
        _ = config.DEBUG


def test_snapshot_is_shallow_and_initialized_only_on_access(module_factory):
    source = {"DEBUG": False, "DATABASES": {"default": {"HOST": "old"}}}
    proxy = create_settings(settings_object=source)
    source["DEBUG"] = True
    assert proxy.DEBUG is True
    source["DEBUG"] = False
    assert proxy.DEBUG is True
    source["DATABASES"]["default"]["HOST"] = "new"
    assert proxy.DATABASES["default"]["HOST"] == "new"


def test_reassignment_in_module_after_init_does_not_change_snapshot(module_factory):
    import sys

    name = module_factory(DEBUG=True)
    proxy = create_settings(module=name)
    assert proxy.DEBUG is True
    sys.modules[name].DEBUG = False
    assert proxy.DEBUG is True


def test_ordinary_slotted_object_is_supported():
    class Config:
        __slots__ = ("DEBUG", "_internal")

        def __init__(self):
            self.DEBUG = True
            self._internal = "no"

    proxy = create_settings(settings_object=Config())
    assert proxy.DEBUG is True
    with pytest.raises(AttributeError):
        _ = proxy._internal
