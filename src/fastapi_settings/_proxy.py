"""Lazy, independent, read-only settings proxies with scoped test overlays."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ._loader import _executing_import, _load_module, _load_object, validate_module_name
from .exceptions import (
    SettingsAlreadyConfiguredError,
    SettingsInitializationError,
    SettingsNotConfiguredError,
    SettingsOverrideError,
)

_UNSET = object()
_ENVIRONMENT_VARIABLE = "FASTAPI_SETTINGS_MODULE"
_initializations = threading.local()


@dataclass(frozen=True, slots=True)
class _ModuleSource:
    name: str


@dataclass(frozen=True, slots=True, eq=False)
class _ObjectSource:
    value: object


_Source = _ModuleSource | _ObjectSource


class SettingsProxy:
    """A lazy, read-only, context-override-aware proxy for application settings.

    Instances created with ``create_settings`` are isolated from the global
    environment and each other. ``settings`` is the only instance configured
    to discover ``FASTAPI_SETTINGS_MODULE`` on first access.

    Settings are shallow snapshots: top-level assignments to the source after
    initialization do not propagate; nested mutable values remain shared.
    """

    _allow_environment: bool
    _source: _Source | None
    _values: Mapping[str, Any] | None
    _owner: int | None
    _lock: threading.Condition
    _overrides: ContextVar[tuple[Mapping[str, Any], ...]]

    __slots__ = (
        "_allow_environment",
        "_lock",
        "_overrides",
        "_owner",
        "_source",
        "_values",
    )

    def __init__(self, *, _allow_environment: bool = False) -> None:
        object.__setattr__(self, "_allow_environment", _allow_environment)
        object.__setattr__(self, "_source", None)
        object.__setattr__(self, "_values", None)
        object.__setattr__(self, "_owner", None)
        object.__setattr__(self, "_lock", threading.Condition())
        object.__setattr__(
            self,
            "_overrides",
            ContextVar(f"fastapi_settings_overrides_{id(self)}", default=()),
        )

    def __repr__(self) -> str:
        """Return configuration status without exposing any setting values."""
        if self._values is not None:
            state = "initialized"
        elif self._source is not None:
            state = "configured"
        else:
            state = "unconfigured"
        return f"<SettingsProxy {state}>"

    def __setattr__(self, name: str, value: object) -> None:
        """Prohibit runtime mutation, including of proxy internals."""
        raise AttributeError("SettingsProxy attributes are read-only")

    def __delattr__(self, name: str) -> None:
        """Prohibit deletion of settings and proxy internals."""
        raise AttributeError("SettingsProxy attributes are read-only")

    def __getattr__(self, name: str) -> Any:
        """Resolve settings lazily and consult current context-local overrides."""
        if name.startswith("_"):
            raise AttributeError(name)
        values = self._snapshot()
        if name not in values:
            raise AttributeError(name)
        for overrides in reversed(self._overrides.get()):
            if name in overrides:
                return overrides[name]
        return values[name]

    def _configure(self, source: _Source) -> None:
        """Select the configuration source, rejecting conflicting selections."""
        with self._lock:
            if self._source is not None:
                if not _same_source(self._source, source):
                    raise SettingsAlreadyConfiguredError(
                        "Settings source has already been selected"
                    )
                # Once selected, the environment is no longer consulted.
                return

            if self._allow_environment:
                env_module = os.environ.get(_ENVIRONMENT_VARIABLE)
                if env_module is not None:
                    # Invalid values fail explicitly rather than being ignored.
                    env_module = validate_module_name(env_module)
                    if not (
                        isinstance(source, _ModuleSource) and source.name == env_module
                    ):
                        raise SettingsAlreadyConfiguredError(
                            "Explicit settings source conflicts with FASTAPI_SETTINGS_MODULE"
                        )

            object.__setattr__(self, "_source", source)

    def _snapshot(self) -> Mapping[str, Any]:
        """Claim, load outside the state lock, and publish one complete snapshot.

        Source selection is permanent; failed attempts return to configured.
        Ordinary readers wait for the owner. Importing/initializing callers
        never wait on another owner, avoiding import and cross-proxy cycles.
        Every exit, including BaseException, clears ownership and wakes readers.
        """
        with self._lock:
            if self._values is not None:
                return self._values

        # Inspection and all application callbacks run outside the state lock.
        depth = getattr(_initializations, "depth", 0)
        can_wait = depth == 0 and not _executing_import()
        owner = threading.get_ident()
        with self._lock:
            while self._values is None and self._owner is not None:
                if self._owner == owner:
                    raise SettingsInitializationError(
                        "Recursive settings initialization detected"
                    )
                if not can_wait:
                    raise SettingsInitializationError(
                        "Cannot wait for settings during import or initialization"
                    )
                self._lock.wait()
            if self._values is not None:
                return self._values

            source = self._source
            if source is None and self._allow_environment:
                env_module = os.environ.get(_ENVIRONMENT_VARIABLE)
                if env_module is not None:
                    source = _ModuleSource(validate_module_name(env_module))
                    object.__setattr__(self, "_source", source)
            if source is None:
                raise SettingsNotConfiguredError(
                    "Settings are not configured; use configure() or set "
                    "FASTAPI_SETTINGS_MODULE"
                )

            object.__setattr__(self, "_owner", owner)

        _initializations.depth = depth + 1
        try:
            if isinstance(source, _ModuleSource):
                loaded = _load_module(source.name)
            else:
                loaded = _load_object(source.value)
            snapshot = MappingProxyType(loaded)
            with self._lock:
                object.__setattr__(self, "_values", snapshot)
            return snapshot
        finally:
            _initializations.depth = depth
            with self._lock:
                object.__setattr__(self, "_owner", None)
                self._lock.notify_all()

    @contextmanager
    def _override(self, changes: Mapping[str, Any]) -> Iterator[None]:
        """Install a reversible, context-local overlay, checking each setting."""
        values = self._snapshot()
        if not changes:
            raise SettingsOverrideError("At least one setting must be overridden")
        if any(name not in values for name in changes):
            raise SettingsOverrideError("Cannot override an unknown setting")
        # Copy the dict to protect the context from mutation through the caller.
        previous = self._overrides.get()
        token = self._overrides.set((*previous, MappingProxyType(dict(changes))))
        try:
            yield
        finally:
            self._overrides.reset(token)


def _same_source(left: _Source, right: _Source) -> bool:
    """Compare module sources by path and object sources by identity."""
    if isinstance(left, _ModuleSource) and isinstance(right, _ModuleSource):
        return left.name == right.name
    if isinstance(left, _ObjectSource) and isinstance(right, _ObjectSource):
        return left.value is right.value
    return False


def _make_source(*, module: str | None, settings_object: object) -> _Source:
    """Enforce exactly one non-null settings source argument."""
    if module is not None:
        if settings_object is not _UNSET:
            raise ValueError("Pass module or settings_object, not both")
        return _ModuleSource(validate_module_name(module))
    if settings_object is _UNSET:
        raise ValueError("Exactly one of module or settings_object is required")
    if settings_object is None:
        raise ValueError("settings_object cannot be None")
    return _ObjectSource(settings_object)


settings = SettingsProxy(_allow_environment=True)


def configure(*, module: str | None = None, settings_object: object = _UNSET) -> None:
    """Explicitly select the default settings source without loading it.

    Calling this repeatedly with the same module or object identity is
    idempotent. Conflicting sources raise SettingsAlreadyConfiguredError.
    """
    settings._configure(_make_source(module=module, settings_object=settings_object))


def create_settings(
    *, module: str | None = None, settings_object: object = _UNSET
) -> SettingsProxy:
    """Create a lazily loaded settings proxy with an independent source."""
    source = _make_source(module=module, settings_object=settings_object)
    proxy = SettingsProxy()
    proxy._configure(source)
    return proxy
