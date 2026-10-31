"""Common reusable test fixtures."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture
def module_factory(monkeypatch: pytest.MonkeyPatch):
    """Register temporary in-memory modules for the loader tests."""
    created = 0

    def build(**values: Any) -> str:
        nonlocal created
        created += 1
        name = f"_fastapi_settings_test_module_{created}"
        module = ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
        return name

    return build
