"""Testing utilities for safely scoped, context-local settings overrides."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from ._proxy import SettingsProxy, settings


@contextmanager
def override_settings(
    target: SettingsProxy | None = None, /, **overrides: Any
) -> Iterator[None]:
    """Temporarily replace existing settings without modifying their source.

    If ``target`` is omitted, the default ``settings`` proxy is used. This
    context manager supports nesting and isolates independent async contexts.
    Values are not validated or recursively merged.
    """
    proxy = settings if target is None else target
    if not isinstance(proxy, SettingsProxy):
        raise TypeError("target must be a SettingsProxy")
    with proxy._override(overrides):
        yield
