"""Run with APP_DATABASE_URL set: python -m examples.pydantic.app."""

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI

from fastapi_settings import SettingsProxy, create_settings

config = create_settings(module="examples.pydantic.settings")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The model is constructed on this first access, using Pydantic's own sources.
    _ = config.database_url
    yield


app = FastAPI(lifespan=lifespan)


def get_settings() -> SettingsProxy:
    return config


@app.get("/config")
def read_config(selected: Annotated[SettingsProxy, Depends(get_settings)]):
    # Do not return credentials or serialize the entire settings object.
    return {"debug": selected.debug, "has_api_key": selected.api_key is not None}


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        response = client.get("/config")
        assert response.status_code == 200
        assert isinstance(response.json()["debug"], bool)
        print(response.json())
