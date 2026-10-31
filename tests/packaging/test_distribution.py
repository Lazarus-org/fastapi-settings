"""Regression checks for unsafe archives and the F-05 source-content omissions."""

from __future__ import annotations

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def validator():
    project = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "distribution_validator", project / ".github/scripts/validate_distribution.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "name",
    ["../outside.py", "/absolute.py", "C:/outside.py", "package\\outside.py"],
)
def test_unsafe_source_archive_paths_are_rejected(tmp_path, validator, name):
    artifact = tmp_path / "unsafe.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = 1
        archive.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="Unsafe distribution path"):
        validator._check_sdist(artifact)


@pytest.mark.parametrize(
    "name",
    ["package/.env", "package/.idea/workspace.xml", "package/__pycache__/config.pyc"],
)
def test_local_artifacts_are_rejected(tmp_path, validator, name):
    artifact = tmp_path / "local.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        entry = tarfile.TarInfo(name)
        entry.size = 1
        archive.addfile(entry, io.BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="Local artifact included"):
        validator._check_sdist(artifact)


def test_source_archive_symlinks_are_rejected(tmp_path, validator):
    artifact = tmp_path / "symlink.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        entry = tarfile.TarInfo("package/source.py")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../../outside.py"
        archive.addfile(entry)
    with pytest.raises(RuntimeError, match="Unsupported source archive entry"):
        validator._check_sdist(artifact)


@pytest.mark.parametrize(
    "missing",
    [
        "tests/unit/test_initialization.py",
        "examples/basic/app.py",
        "SECURITY.md",
        "src/fastapi_settings/py.typed",
    ],
)
def test_required_source_archive_files_cannot_be_omitted(tmp_path, validator, missing):
    artifact = tmp_path / "incomplete.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        for name in validator._source_files() - {missing}:
            archive.add(validator.PROJECT / name, arcname=f"package/{name}")
        metadata = tarfile.TarInfo("package/PKG-INFO")
        archive.addfile(metadata, io.BytesIO(b""))
    with pytest.raises(
        RuntimeError, match="Source archive is missing required files"
    ) as error:
        validator._check_sdist(artifact)
    assert missing in str(error.value)
