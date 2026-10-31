"""Real module and subprocess fixtures for optional integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def isolate_phase4_environment(monkeypatch):
    for name in os.environ:
        if name.startswith("P4_"):
            monkeypatch.delenv(name)


@pytest.fixture
def settings_module(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    names = []

    def write(body: str) -> str:
        name = f"phase4_settings_{uuid4().hex}"
        (tmp_path / f"{name}.py").write_text(textwrap.dedent(body), encoding="utf-8")
        names.append(name)
        return name

    yield write
    for name in names:
        sys.modules.pop(name, None)


@pytest.fixture
def run_python(tmp_path):
    def run(script: str, *, env: dict[str, str] | None = None):
        project = Path(__file__).resolve().parents[2]
        environment = os.environ.copy()
        environment.pop("FASTAPI_SETTINGS_MODULE", None)
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(project / "src"), str(project))
        )
        environment.update(env or {})
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    return run
