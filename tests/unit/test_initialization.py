"""Explicit and environment-driven initialization behavior."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

import fastapi_settings._proxy as internal_proxy
from fastapi_settings import SettingsProxy, create_settings
from fastapi_settings.exceptions import (
    SettingsAlreadyConfiguredError,
    SettingsInitializationError,
    SettingsNotConfiguredError,
)


def _run_script(
    script: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    execution_env = os.environ.copy()
    execution_env["PYTHONPATH"] = os.path.join(project_root, "src")
    execution_env.pop("FASTAPI_SETTINGS_MODULE", None)
    execution_env.update(env or {})
    return subprocess.run(
        [sys.executable, "-c", script],
        env=execution_env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_import_is_lazy():
    result = _run_script("from fastapi_settings import settings; print(repr(settings))")
    assert result.returncode == 0, result.stderr
    assert "<SettingsProxy unconfigured>" in result.stdout


def test_default_unconfigured_raises():
    result = _run_script("from fastapi_settings import settings; print(settings.DEBUG)")
    assert result.returncode != 0
    assert "SettingsNotConfiguredError" in result.stderr


def test_explicit_default_module_and_idempotence():
    result = _run_script(
        "import types, sys; "
        "m=types.ModuleType('config_test'); m.DEBUG=True; sys.modules['config_test']=m; "
        "from fastapi_settings import configure, settings; "
        "configure(module='config_test'); configure(module='config_test'); "
        "print(settings.DEBUG)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_default_environment_module(module_factory, monkeypatch):
    name = module_factory(DEBUG=True)
    # This test is intentionally in-process to exercise a new environment-aware
    # proxy without modifying the real global default proxy.
    monkeypatch.setenv("FASTAPI_SETTINGS_MODULE", name)
    proxy = SettingsProxy(_allow_environment=True)
    assert proxy.DEBUG is True


def test_environment_and_explicit_module_same_is_allowed(monkeypatch, module_factory):
    name = module_factory(DEBUG=True)
    monkeypatch.setenv("FASTAPI_SETTINGS_MODULE", name)
    proxy = SettingsProxy(_allow_environment=True)
    proxy._configure(internal_proxy._ModuleSource(name))
    assert proxy.DEBUG is True


def test_conflicting_environment_source_is_rejected(monkeypatch):
    monkeypatch.setenv("FASTAPI_SETTINGS_MODULE", "application.settings")
    proxy = SettingsProxy(_allow_environment=True)
    with pytest.raises(SettingsAlreadyConfiguredError):
        proxy._configure(internal_proxy._ModuleSource("other.settings"))
    with pytest.raises(SettingsAlreadyConfiguredError):
        proxy._configure(internal_proxy._ObjectSource({"DEBUG": True}))


def test_environment_read_at_first_access(monkeypatch, module_factory):
    name = module_factory(DEBUG=True)
    proxy = SettingsProxy(_allow_environment=True)
    monkeypatch.setenv("FASTAPI_SETTINGS_MODULE", name)
    assert proxy.DEBUG is True
    monkeypatch.delenv("FASTAPI_SETTINGS_MODULE")
    assert proxy.DEBUG is True


def test_independent_proxy_ignores_environment(monkeypatch):
    monkeypatch.setenv("FASTAPI_SETTINGS_MODULE", "application.settings")
    proxy = create_settings(settings_object={"DEBUG": True})
    assert proxy.DEBUG is True
    with pytest.raises(SettingsNotConfiguredError):
        _ = SettingsProxy().DEBUG


def test_same_module_is_idempotent_after_init(module_factory):
    name = module_factory(DEBUG=True)
    proxy = SettingsProxy()
    proxy._configure(internal_proxy._ModuleSource(name))
    assert proxy.DEBUG is True
    proxy._configure(internal_proxy._ModuleSource(name))
    assert proxy.DEBUG is True


def test_same_object_is_idempotent_and_different_object_rejected():
    source = {"DEBUG": True}
    proxy = SettingsProxy()
    proxy._configure(internal_proxy._ObjectSource(source))
    proxy._configure(internal_proxy._ObjectSource(source))
    with pytest.raises(SettingsAlreadyConfiguredError):
        proxy._configure(internal_proxy._ObjectSource({"DEBUG": True}))


def test_reconfiguring_module_to_object_is_rejected(module_factory):
    proxy = SettingsProxy()
    proxy._configure(internal_proxy._ModuleSource(module_factory(DEBUG=True)))
    with pytest.raises(SettingsAlreadyConfiguredError):
        proxy._configure(internal_proxy._ObjectSource({"DEBUG": True}))


def test_source_arguments_exactly_one():
    with pytest.raises(ValueError):
        create_settings()
    with pytest.raises(ValueError):
        create_settings(module="app.settings", settings_object={"DEBUG": True})
    with pytest.raises(ValueError):
        create_settings(settings_object=None)


def test_module_source_identity_does_not_invoke_string_subclass_callbacks():
    result = _run_script(
        "from fastapi_settings import configure\n"
        "class ModuleName(str):\n"
        "    def __eq__(self, other):\n"
        "        raise AssertionError('source equality executed application code')\n"
        "    def __str__(self):\n"
        "        raise AssertionError('source normalization called user code')\n"
        "configure(module=ModuleName('application.settings'))\n"
        "configure(module=ModuleName('application.settings'))\n"
    )
    assert result.returncode == 0, result.stderr


def test_recursive_access_detected(monkeypatch):
    proxy = create_settings(module="fake.settings")

    def recursive_loader(_: str):
        _ = proxy.DEBUG

    monkeypatch.setattr(internal_proxy, "_load_module", recursive_loader)
    with pytest.raises(SettingsInitializationError, match="Recursive"):
        _ = proxy.DEBUG


def test_initialization_failure_does_not_poison_proxy(monkeypatch):
    proxy = create_settings(module="fake.settings")
    count = 0

    def fail_then_recover(_: str):
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("temporary failure")
        return {"DEBUG": True}

    monkeypatch.setattr(internal_proxy, "_load_module", fail_then_recover)
    with pytest.raises(RuntimeError):
        _ = proxy.DEBUG
    assert proxy.DEBUG is True
    assert count == 2


def test_configure_idempotent_even_when_environment_changes(
    monkeypatch, module_factory
):
    name = module_factory(DEBUG=True)
    proxy = SettingsProxy(_allow_environment=True)
    proxy._configure(internal_proxy._ModuleSource(name))
    assert proxy.DEBUG is True
    monkeypatch.setenv("FASTAPI_SETTINGS_MODULE", "another.module")
    proxy._configure(internal_proxy._ModuleSource(name))
    assert proxy.DEBUG is True


def test_explicit_default_object_configuration():
    result = _run_script(
        "from fastapi_settings import configure, settings; "
        "data={'DEBUG': True}; configure(settings_object=data); "
        "configure(settings_object=data); print(settings.DEBUG)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_default_override_with_explicit_object():
    script = (
        "from fastapi_settings import configure, settings\n"
        "from fastapi_settings.testing import override_settings\n"
        "configure(settings_object={'DEBUG': False})\n"
        "with override_settings(DEBUG=True):\n"
        "    print(settings.DEBUG)\n"
        "print(settings.DEBUG)\n"
    )
    result = _run_script(script)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["True", "False"]


def test_configured_module_is_not_imported_until_first_access(tmp_path):
    (tmp_path / "lazy_app.py").write_text("DEBUG = True\n", encoding="utf-8")
    script = (
        "import sys\n"
        "from fastapi_settings import settings\n"
        "print('lazy_app' in sys.modules)\n"
        "print(settings.DEBUG)\n"
        "print('lazy_app' in sys.modules)\n"
    )
    env = {"FASTAPI_SETTINGS_MODULE": "lazy_app"}
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    execution_env = os.environ.copy()
    execution_env.update(env)
    execution_env["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), os.path.join(project_root, "src")]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=execution_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["False", "True", "True"]
