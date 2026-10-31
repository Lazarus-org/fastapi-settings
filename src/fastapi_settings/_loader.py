"""Load Python settings sources without handling environment values or validation."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import keyword
import sys
from collections.abc import Mapping
from types import ModuleType
from typing import Any

from .exceptions import (
    InvalidSettingsSourceError,
    SettingsInitializationError,
    SettingsModuleImportError,
)


def _is_initializing(spec: object) -> bool:
    """Read CPython's import-in-progress marker in one compatibility boundary.

    There is no public import-completion API. CPython 3.11--3.15 sets this
    marker before inserting a module in sys.modules and clears it after
    execution. No import locks or private importlib functions are acquired.
    Manually registered modules may have no spec/marker and are already usable.
    """
    return bool(getattr(spec, "_initializing", False))


def _executing_import() -> bool:
    """Whether this caller may hold an import lock and must not wait on a proxy.

    Inspect active module frames, including importlib's spec for custom loaders.
    This conservative check is only needed before initialization, not on cached
    reads. Frame inspection is available on the supported CPython interpreters;
    if unavailable, fail closed by disallowing a potentially unsafe wait.
    """
    frame = inspect.currentframe()
    if frame is None:
        return True
    try:
        while frame is not None:
            if _is_initializing(frame.f_globals.get("__spec__")):
                return True
            if frame.f_globals.get("__name__") in (
                "importlib._bootstrap",
                "_frozen_importlib",
            ) and _is_initializing(frame.f_locals.get("spec")):
                return True
            frame = frame.f_back
        return False
    finally:
        del frame


def _reject_partial_module(module: ModuleType | None) -> None:
    """Never snapshot a module while Python is executing its import."""
    if module is not None and _is_initializing(vars(module).get("__spec__")):
        raise SettingsInitializationError(
            "Settings module is still being imported; retry after import completes"
        )


def validate_module_name(module: str) -> str:
    """Validate a fully qualified dotted Python module path.

    Reject invalid paths at configuration time rather than waiting for access.
    """
    if not isinstance(module, str):
        raise TypeError("module must be a dotted Python import path string")
    # Source comparisons happen under the state lock. Store a plain string so
    # str-subclass methods cannot execute application code in that critical path.
    module = str.__str__(module)
    if not module or any(
        not part.isidentifier() or keyword.iskeyword(part) for part in module.split(".")
    ):
        raise ValueError("module must be a non-empty dotted Python import path")
    return module


def _public_name(name: object) -> bool:
    """Whether a key can be accessed as a public Python attribute."""
    return (
        isinstance(name, str)
        and name.isidentifier()
        and not keyword.iskeyword(name)
        and not name.startswith("_")
    )


def _load_object(source: object) -> dict[str, Any]:
    """Take a shallow snapshot of public attributes of an object or mapping."""
    if source is None or isinstance(source, (type, ModuleType)):
        raise InvalidSettingsSourceError(
            "SETTINGS must be a settings instance or mapping"
        )

    if isinstance(source, Mapping):
        # Invalid keys cannot be addressed through settings.KEY. Reject rather than
        # silently discarding configuration and making validation unpredictable.
        if not all(_public_name(key) for key in source):
            raise InvalidSettingsSourceError(
                "Settings mapping keys must be public Python attribute names"
            )
        values = dict(source)
    elif dataclasses.is_dataclass(source):
        values = {
            field.name: getattr(source, field.name)
            for field in dataclasses.fields(source)
            if _public_name(field.name)
        }
    else:
        # vars() covers normal objects and Pydantic BaseSettings instances.
        # Properties and class attributes are intentionally not treated as
        # instance configuration fields.
        try:
            attributes = vars(source)
        except TypeError:
            # Slotted instances without __dict__ are ordinary Python objects.
            attributes = {}
        values = {
            name: value for name, value in attributes.items() if _public_name(name)
        }
        for cls in type(source).__mro__:
            slots = cls.__dict__.get("__slots__", ())
            if isinstance(slots, str):
                slots = (slots,)
            for name in slots:
                if _public_name(name) and hasattr(source, name):
                    values[name] = getattr(source, name)

    if not values:
        raise InvalidSettingsSourceError("Settings source has no public settings")
    return values


def _load_module(module_name: str) -> dict[str, Any]:
    """Resolve a module using uppercase constants or one SETTINGS object."""
    _reject_partial_module(sys.modules.get(module_name))
    try:
        module = importlib.import_module(module_name)
    except SettingsInitializationError:
        # Preserve precise circular-initialization diagnostics.
        raise
    except Exception as exc:
        # Never embed exception text, as third-party import errors may include
        # sensitive configuration values. The original traceback is chained.
        raise SettingsModuleImportError(
            f"Unable to import settings module {module_name!r}"
        ) from exc

    _reject_partial_module(module)
    raw = vars(module)
    # Public uppercase bindings include imported constants/classes/functions.
    # Import provenance is deliberately irrelevant; module objects are excluded.
    constants = {
        name: value
        for name, value in raw.items()
        if name != "SETTINGS"
        and name.isupper()
        and not name.startswith("_")
        and not isinstance(value, ModuleType)
    }
    if "SETTINGS" in raw:
        if constants:
            raise InvalidSettingsSourceError(
                "Settings module cannot combine SETTINGS with uppercase constants"
            )
        return _load_object(raw["SETTINGS"])
    if not constants:
        raise InvalidSettingsSourceError(
            "Settings module must expose uppercase constants or a SETTINGS object"
        )
    return constants
