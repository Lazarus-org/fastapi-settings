"""Validate distribution contents, isolated wheel operation, and optional sdist tests.

This CI helper uses only the standard library and pip supplied by venv.
"""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[2]
FORBIDDEN_PARTS = {
    ".git",
    ".idea",
    ".venv",
    ".tox",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}


def _check_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
    ):
        raise RuntimeError(f"Unsafe distribution path: {name}")
    if (
        set(path.parts) & FORBIDDEN_PARTS
        or path.name.startswith(".env")
        or path.suffix in {".pyc", ".pyo"}
    ):
        raise RuntimeError(f"Local artifact included in distribution: {name}")
    return path


def _source_files() -> set[str]:
    required = {
        "pyproject.toml",
        "MANIFEST.in",
        "LICENSE",
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "RELEASING.md",
        "AUTHORS.md",
        "CONTRIBUTORS.md",
        "CODE_OF_CONDUCT.md",
        "tox.ini",
        ".pre-commit-config.yaml",
        ".github/dependabot.yml",
        ".gitignore",
        ".gitattributes",
    }
    for directory, suffixes in (
        ("src", {".py", ".pyi"}),
        ("tests", {".py"}),
        ("examples", {".py", ".md"}),
        (".github/scripts", {".py"}),
        (".github/workflows", {".yml", ".yaml"}),
    ):
        for file in (PROJECT / directory).rglob("*"):
            relative = file.relative_to(PROJECT)
            if set(relative.parts) & FORBIDDEN_PARTS:
                continue
            if file.is_file() and (file.suffix in suffixes or file.name == "py.typed"):
                required.add(relative.as_posix())
    return required


def _check_metadata(metadata) -> None:
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    for key, expected in (
        ("Name", project["name"]),
        ("Version", project["version"]),
        ("Requires-Python", project["requires-python"]),
        ("License-Expression", project["license"]),
    ):
        if metadata[key] != expected:
            raise RuntimeError(f"Distribution {key} does not match pyproject.toml")
    if (
        "Programming Language :: Python :: Implementation :: CPython"
        not in metadata.get_all("Classifier", [])
    ):
        raise RuntimeError("Distribution metadata must identify CPython support")
    if metadata.get("Description-Content-Type", "").split(";")[0] != "text/markdown":
        raise RuntimeError("Distribution must declare a Markdown description")
    expected_urls = {
        f"{label}, {url}" for label, url in project.get("urls", {}).items()
    }
    if set(metadata.get_all("Project-URL", [])) != expected_urls:
        raise RuntimeError("Distribution project URLs do not match pyproject.toml")
    if project["dependencies"]:
        raise RuntimeError("The project must have zero mandatory runtime dependencies")
    # Current extras use simple equality markers. Do not accept active runtime
    # requirements or broaden this check into another marker-parsing engine.
    extra_markers = {
        f'extra == "{extra}"' for extra in project["optional-dependencies"]
    }
    for requirement in metadata.get_all("Requires-Dist", []):
        if requirement.partition(";")[2].strip() not in extra_markers:
            raise RuntimeError(f"Unexpected runtime dependency: {requirement}")
    if "LICENSE" not in metadata.get_all("License-File", []):
        raise RuntimeError("Distribution metadata must declare LICENSE")


def _wheel_contents(wheel: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("Wheel has duplicate entries")
        for name in names:
            _check_path(name)
        return {
            entry.filename: archive.read(entry)
            for entry in archive.infolist()
            if not entry.is_dir()
        }


def _check_wheel(wheel: Path) -> dict[str, bytes]:
    contents = _wheel_contents(wheel)
    metadata_names = [name for name in contents if name.endswith(".dist-info/METADATA")]
    if len(metadata_names) != 1:
        raise RuntimeError("Wheel must have exactly one metadata directory")
    metadata = email.parser.BytesParser().parsebytes(contents[metadata_names[0]])
    _check_metadata(metadata)
    info = metadata_names[0].rsplit("/", 1)[0]
    required = {
        f"{info}/{name}" for name in ("METADATA", "WHEEL", "RECORD", "licenses/LICENSE")
    }
    required.add("fastapi_settings/py.typed")
    if required - contents.keys():
        raise RuntimeError(
            f"Wheel is missing required files: {sorted(required - contents.keys())}"
        )
    for name, data in contents.items():
        if name.startswith("fastapi_settings/"):
            source = PROJECT / "src" / name
            if not source.is_file() or data != source.read_bytes():
                raise RuntimeError(f"Wheel runtime file differs from source: {name}")
        elif not name.startswith(info + "/"):
            raise RuntimeError(f"Source-only or unexpected wheel file: {name}")
    runtime_files = {
        path.removeprefix("src/") for path in _source_files() if path.startswith("src/")
    }
    if runtime_files - contents.keys():
        raise RuntimeError("Wheel is missing runtime source files")
    if contents[f"{info}/licenses/LICENSE"] != (PROJECT / "LICENSE").read_bytes():
        raise RuntimeError("Wheel license differs from the project license")
    return contents


def _check_sdist(sdist: Path) -> dict[str, bytes]:
    files = {}
    roots = set()
    with tarfile.open(sdist) as archive:
        for member in archive.getmembers():
            path = _check_path(member.name)
            roots.add(path.parts[0])
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) < 2:
                raise RuntimeError(f"Unsupported source archive entry: {member.name}")
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            if relative in files:
                raise RuntimeError(f"Duplicate source archive entry: {relative}")
            stream = archive.extractfile(member)
            if stream is None:
                raise RuntimeError(f"Unreadable source archive entry: {relative}")
            with stream:
                files[relative] = stream.read()
    if len(roots) != 1:
        raise RuntimeError("Source archive must have one top-level directory")
    required = _source_files() | {"PKG-INFO"}
    if required - files.keys():
        raise RuntimeError(
            f"Source archive is missing required files: {sorted(required - files.keys())}"
        )
    for name in required - {"PKG-INFO"}:
        if files[name] != (PROJECT / name).read_bytes():
            raise RuntimeError(f"Source archive file differs from checkout: {name}")
    _check_metadata(email.parser.BytesParser().parsebytes(files["PKG-INFO"]))
    return files


def _test_sdist(files: dict[str, bytes], wheel_contents: dict[str, bytes]) -> None:
    with tempfile.TemporaryDirectory(prefix="fastapi-settings-sdist-") as directory:
        root = Path(directory)
        source = root / "source"
        # Entries have already been checked and are regular files only. Writing
        # them explicitly also works on CPython 3.11 releases without tar filters.
        for name, content in files.items():
            target = source.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(source / "src")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proof = (
            "from pathlib import Path; import fastapi_settings; "
            f"assert Path(fastapi_settings.__file__).resolve().is_relative_to(Path({str(source / 'src')!r}))"
        )
        subprocess.run(
            [sys.executable, "-c", proof], cwd=source, env=env, check=True, timeout=30
        )
        subprocess.run(
            [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"],
            cwd=source,
            env=env,
            check=True,
            timeout=300,
        )
        output = root / "rebuilt"
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(output)],
            cwd=source,
            env=env,
            check=True,
            timeout=300,
        )
        rebuilt = list(output.glob("*.whl"))
        if len(rebuilt) != 1 or _wheel_contents(rebuilt[0]) != wheel_contents:
            raise RuntimeError(
                "Wheel rebuilt from the source archive has different contents"
            )
    print("Extracted source tests and rebuilt-wheel content comparison passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default="dist", type=Path)
    parser.add_argument(
        "--test-sdist",
        action="store_true",
        help="Test extracted sources and compare their rebuilt wheel",
    )
    args = parser.parse_args()
    artifact_dir = args.directory.resolve()
    wheels = list(artifact_dir.glob("*.whl"))
    sdists = list(artifact_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("Expected exactly one wheel and one source distribution")

    wheel_contents = _check_wheel(wheels[0])
    sdist_files = _check_sdist(sdists[0])
    for artifact in (wheels[0], sdists[0]):
        print(
            f"SHA256 {artifact.name}: {hashlib.sha256(artifact.read_bytes()).hexdigest()}"
        )

    probe = textwrap.dedent("""\
        import importlib.util
        import sys
        from importlib.metadata import distribution
        from pathlib import Path

        import fastapi_settings
        from fastapi_settings import configure, create_settings, settings
        from fastapi_settings.testing import override_settings

        assert sys.implementation.name == 'cpython'
        assert Path(fastapi_settings.__file__).resolve().is_relative_to(Path(sys.prefix))
        for name in ('fastapi', 'pydantic', 'pydantic_settings', 'django'):
            assert importlib.util.find_spec(name) is None, name

        configure(settings_object={'OK': True})
        assert settings.OK is True
        independent = create_settings(settings_object={'OK': False})
        with override_settings(independent, OK=True):
            assert independent.OK is True
        assert independent.OK is False

        module = Path('application_settings.py')
        module.write_text('VALUE = 42\\n', encoding='utf-8')
        sys.path.insert(0, str(module.resolve().parent))
        assert create_settings(module='application_settings').VALUE == 42

        print('Installed wheel:', distribution('fastapi-settings').version)
        print('Core access and overrides passed with optional packages absent.')
    """)

    with tempfile.TemporaryDirectory(prefix="fastapi-settings-wheel-") as directory:
        root = Path(directory)
        environment = root / "venv"
        subprocess.run(
            [sys.executable, "-I", "-m", "venv", str(environment)], check=True
        )
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        # No index access: the wheel must install without fetching dependencies.
        subprocess.run(
            [
                str(python),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                str(wheels[0]),
            ],
            check=True,
        )
        subprocess.run([str(python), "-I", "-c", probe], cwd=root, check=True)
        subprocess.run(
            [str(python), "-I", "-m", "pip", "--isolated", "check"], check=True
        )

    print("Wheel, source distribution, and dependency isolation checks passed.")
    if args.test_sdist:
        _test_sdist(sdist_files, wheel_contents)


if __name__ == "__main__":
    main()
