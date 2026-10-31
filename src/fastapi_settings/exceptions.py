"""Stable exception types for settings initialization and testing."""


class FastAPISettingsError(Exception):
    """Base exception for failures managed by fastapi-settings."""


class SettingsNotConfiguredError(FastAPISettingsError):
    """Raised when an accessed settings proxy has no configuration source."""


class SettingsAlreadyConfiguredError(FastAPISettingsError):
    """Raised when configuration conflicts with an already selected source."""


class SettingsModuleImportError(FastAPISettingsError):
    """Raised when importing a settings module fails."""


class InvalidSettingsSourceError(FastAPISettingsError):
    """Raised when a settings module or object violates the source contract."""


class SettingsInitializationError(FastAPISettingsError):
    """Raised for errors during initialization, including circular access."""


class SettingsOverrideError(FastAPISettingsError):
    """Raised when a temporary settings override cannot be applied."""
