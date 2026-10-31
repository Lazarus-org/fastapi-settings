"""Integration with an independently configured Pydantic Settings instance."""

import sys

import pytest

from fastapi_settings import create_settings
from fastapi_settings.testing import override_settings

pydantic_settings = pytest.importorskip("pydantic_settings")


def test_pydantic_settings_object(monkeypatch):
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class ApplicationSettings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="DEMO_", extra="ignore")
        debug: bool = False
        database_url: str

    monkeypatch.setenv("DEMO_DEBUG", "yes")
    monkeypatch.setenv("DEMO_DATABASE_URL", "postgresql://localhost/demo")
    model = ApplicationSettings()
    proxy = create_settings(settings_object=model)
    assert proxy.debug is True
    assert proxy.database_url == "postgresql://localhost/demo"
    with override_settings(proxy, debug=False):
        assert proxy.debug is False
    assert model.debug is True


def test_pydantic_validation_is_delegated_to_pydantic():
    from pydantic import ValidationError
    from pydantic_settings import BaseSettings

    class ApplicationSettings(BaseSettings):
        required_field: int

    with pytest.raises(ValidationError):
        ApplicationSettings(required_field="not an integer")


@pytest.mark.parametrize("source", ["dotenv", "environment", "initialization"])
def test_real_pydantic_source_precedence_types_and_secrets(
    tmp_path, monkeypatch, source
):
    from pydantic import BaseModel, Field, SecretBytes, SecretStr
    from pydantic_settings import BaseSettings, SettingsConfigDict

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "P4_URL=dotenv\nP4_PORT=7000\nP4_DEBUG=true\n"
        'P4_DATABASE={"host":"dotenv","port":5432}\n'
        "P4_TOKEN=example-token\nP4_BINARY_TOKEN=example-bytes\n",
        encoding="utf-8",
    )

    class Database(BaseModel):
        host: str
        port: int

    class Config(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="P4_", env_file=dotenv, env_nested_delimiter="__"
        )
        url: str
        port: int = 8000
        debug: bool = False
        database: Database
        token: SecretStr
        binary_token: SecretBytes
        label: str | None = None
        tags: list[str] = Field(default_factory=list)

    kwargs = {}
    expected = "dotenv"
    if source != "dotenv":
        monkeypatch.setenv("P4_URL", "environment")
        monkeypatch.setenv("P4_DATABASE__HOST", "environment")
        expected = "environment"
    if source == "initialization":
        kwargs = {"url": "initialization"}
        expected = "initialization"
    model = Config(**kwargs)
    proxy = create_settings(settings_object=model)
    assert proxy.url == expected
    assert proxy.port == 7000 and isinstance(proxy.port, int)
    assert proxy.debug is True and proxy.label is None
    assert proxy.tags == []
    assert proxy.database is model.database
    assert proxy.database.host == ("dotenv" if source == "dotenv" else "environment")
    assert proxy.database.port == 5432
    assert proxy.token is model.token and isinstance(proxy.token, SecretStr)
    assert proxy.binary_token is model.binary_token and isinstance(
        proxy.binary_token, SecretBytes
    )
    assert proxy.token.get_secret_value() == "example-token"
    assert proxy.binary_token.get_secret_value() == b"example-bytes"
    assert "example-token" not in repr(proxy)
    assert "example-token" not in repr(proxy.token)
    with override_settings(proxy, port="not validated"):
        assert proxy.port == "not validated"
        assert model.port == 7000
    assert proxy.port == 7000


def test_custom_pydantic_sources_are_not_reordered_or_rerun(monkeypatch):
    from pydantic_settings import BaseSettings, SettingsConfigDict

    calls = []

    def custom_source():
        calls.append(True)
        return {"port": 9000}

    class Config(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="P4_CUSTOM_")
        port: int = 8000

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ):
            return custom_source, env_settings, init_settings

    monkeypatch.setenv("P4_CUSTOM_PORT", "7000")
    model = Config(port=6000)
    assert calls == [True]
    proxy = create_settings(settings_object=model)
    monkeypatch.setenv("P4_CUSTOM_PORT", "5000")
    assert proxy.port == 9000
    assert calls == [True]
    with override_settings(proxy, port=4000):
        assert proxy.port == 4000
    assert proxy.port == model.port == 9000
    assert calls == [True]


def test_settings_object_is_constructed_before_proxy_but_snapshot_is_lazy(monkeypatch):
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Config(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="P4_OBJECT_")
        mixedCase: int
        UPPERCASE: str = "preserved"

    monkeypatch.setenv("P4_OBJECT_MIXEDCASE", "1")
    model = Config()
    proxy = create_settings(settings_object=model)
    monkeypatch.setenv("P4_OBJECT_MIXEDCASE", "2")
    assert model.mixedCase == 1
    model.mixedCase = 3
    assert proxy.mixedCase == 3
    assert proxy.UPPERCASE == "preserved"
    model.mixedCase = 4
    assert proxy.mixedCase == 3
    with pytest.raises(AttributeError):
        _ = proxy.MIXEDCASE


def test_pydantic_module_constructs_model_only_on_first_access(
    settings_module, tmp_path, monkeypatch
):
    marker = tmp_path / "constructed"
    name = settings_module(
        f"""
        from pathlib import Path
        from pydantic_settings import BaseSettings, SettingsConfigDict
        class Config(BaseSettings):
            model_config = SettingsConfigDict(env_prefix='P4_LAZY_')
            port: int
            label: str | None = None
        SETTINGS = Config()
        Path({str(marker)!r}).write_text('constructed', encoding='utf-8')
        """
    )
    monkeypatch.setenv("P4_LAZY_PORT", "8080")
    proxy = create_settings(module=name)
    assert name not in sys.modules and not marker.exists()
    assert proxy.port == 8080 and proxy.label is None
    model = sys.modules[name].SETTINGS
    assert marker.read_text(encoding="utf-8") == "constructed"
    monkeypatch.setenv("P4_LAZY_PORT", "9000")
    assert proxy.port == model.port == 8080


@pytest.mark.parametrize("value", [None, "not-an-integer"])
def test_pydantic_module_validation_failure_preserves_cause_and_recovers(
    settings_module, monkeypatch, value
):
    from pydantic import ValidationError

    from fastapi_settings import SettingsModuleImportError

    name = settings_module(
        """
        from pydantic_settings import BaseSettings, SettingsConfigDict
        class Config(BaseSettings):
            model_config = SettingsConfigDict(env_prefix='P4_FAILURE_')
            required_port: int
            label: str = 'complete'
        SETTINGS = Config()
        """
    )
    monkeypatch.delenv("P4_FAILURE_REQUIRED_PORT", raising=False)
    if value is not None:
        monkeypatch.setenv("P4_FAILURE_REQUIRED_PORT", value)
    proxy = create_settings(module=name)
    with pytest.raises(SettingsModuleImportError) as failure:
        _ = proxy.required_port
    assert isinstance(failure.value.__cause__, ValidationError)
    assert failure.value.__cause__.errors()[0]["loc"] == ("required_port",)
    assert name not in sys.modules
    assert "not-an-integer" not in str(failure.value)
    monkeypatch.setenv("P4_FAILURE_REQUIRED_PORT", "8080")
    assert proxy.required_port == 8080 and proxy.label == "complete"
