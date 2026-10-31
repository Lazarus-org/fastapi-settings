"""Run with: python -m examples.dependency_overrides.app."""

from typing import Annotated

from fastapi import Depends, FastAPI

from fastapi_settings import SettingsProxy, create_settings

config = create_settings(settings_object={"DEBUG": False})
app = FastAPI()


def get_settings() -> SettingsProxy:
    return config


@app.get("/config")
async def read_config(selected: Annotated[SettingsProxy, Depends(get_settings)]):
    return {"debug": selected.DEBUG}


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    replacement = create_settings(settings_object={"DEBUG": True})
    with TestClient(app) as client:
        assert client.get("/config").json() == {"debug": False}
        app.dependency_overrides[get_settings] = lambda: replacement
        try:
            response = client.get("/config")
            assert response.json() == {"debug": True}
            print(response.json())
        finally:
            app.dependency_overrides.clear()
        assert client.get("/config").json() == {"debug": False}
