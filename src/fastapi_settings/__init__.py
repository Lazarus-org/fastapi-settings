"""Centralized, lazy application settings for Python and FastAPI applications.

Importing this package does not import application settings or initialize them.
"""

from ._proxy import SettingsProxy, configure, create_settings, settings
from .exceptions import (
    FastAPISettingsError,
    InvalidSettingsSourceError,
    SettingsAlreadyConfiguredError,
    SettingsInitializationError,
    SettingsModuleImportError,
    SettingsNotConfiguredError,
    SettingsOverrideError,
)

__all__ = [
    "FastAPISettingsError",
    "InvalidSettingsSourceError",
    "SettingsAlreadyConfiguredError",
    "SettingsInitializationError",
    "SettingsModuleImportError",
    "SettingsNotConfiguredError",
    "SettingsOverrideError",
    "SettingsProxy",
    "configure",
    "create_settings",
    "settings",
]
