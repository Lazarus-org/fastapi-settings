"""Run with: python -m examples.basic.app."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI

from fastapi_settings import SettingsProxy, configure, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure(module="examples.basic.settings")
    # Resolve once at startup so configuration errors fail before serving requests.
    _ = settings.DEBUG
    app.state.config = settings
    yield


app = FastAPI(lifespan=lifespan)


def get_settings() -> SettingsProxy:
    return app.state.config


@app.get("/config")
async def read_config(config: Annotated[SettingsProxy, Depends(get_settings)]):
    return {"debug": config.DEBUG}


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/config")
        assert response.status_code == 200
        assert response.json() == {"debug": False}
        print(response.json())
