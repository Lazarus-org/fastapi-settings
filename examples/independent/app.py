"""Run with: python -m examples.independent.app."""

from typing import Annotated

from fastapi import Depends, FastAPI

from fastapi_settings import SettingsProxy, create_settings
from fastapi_settings.testing import override_settings


def create_app(config: SettingsProxy) -> FastAPI:
    app = FastAPI()

    def get_settings() -> SettingsProxy:
        return config

    @app.get("/config")
    async def read_config(selected: Annotated[SettingsProxy, Depends(get_settings)]):
        return {"debug": selected.DEBUG}

    return app


first_settings = create_settings(module="examples.basic.settings")
second_settings = create_settings(settings_object={"DEBUG": True})
first_app = create_app(first_settings)
second_app = create_app(second_settings)


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    with TestClient(first_app) as first, TestClient(second_app) as second:
        assert first.get("/config").json() == {"debug": False}
        assert second.get("/config").json() == {"debug": True}
        with override_settings(first_settings, DEBUG=True):
            assert first.get("/config").json() == {"debug": True}
            assert second.get("/config").json() == {"debug": True}
        assert first.get("/config").json() == {"debug": False}
        print(first.get("/config").json(), second.get("/config").json())
