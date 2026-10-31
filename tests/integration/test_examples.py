"""Execute the documented examples in isolated Python processes."""

import pytest


@pytest.mark.parametrize(
    ("module", "output"),
    [
        ("examples.basic.app", "{'debug': False}"),
        ("examples.pydantic.app", "{'debug': True, 'has_api_key': True}"),
        ("examples.dependency_overrides.app", "{'debug': True}"),
        ("examples.independent.app", "{'debug': False} {'debug': True}"),
    ],
)
def test_executable_application_examples(run_python, module, output):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    if module == "examples.pydantic.app":
        pytest.importorskip("pydantic_settings")
    result = run_python(
        f"import runpy; runpy.run_module({module!r}, run_name='__main__')",
        env={
            "APP_DATABASE_URL": "postgresql://localhost/example",
            "APP_DEBUG": "true",
            "APP_API_KEY": "example-only-token",
        },
    )
    assert result.stdout.strip() == output
    assert "example-only-token" not in result.stdout
