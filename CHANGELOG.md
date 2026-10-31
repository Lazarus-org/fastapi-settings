# Changelog

All notable changes to this project will be documented here. Versioning follows Semantic Versioning.

## [1.0.0] - 2026-10-31

- Added a lazy, Django-inspired settings proxy.
- Added configuration through a Python module or preconstructed settings object.
- Added independent settings instances and conflict detection.
- Added shallow, read-only top-level settings snapshots.
- Added temporary, context-local test overrides with nested scope support.
- Added dedicated configuration exceptions and safe proxy representations.
- Added integration tests for Pydantic Settings and FastAPI dependency injection.
- Added recovery after initialization failures, incomplete-import rejection, and cross-proxy cycle detection.
- Added executable FastAPI examples for lifespan startup, dependency overrides, and independent applications.
- Added CPython 3.11–3.15 compatibility checks and clean-wheel dependency isolation validation.
- Included tests, examples, maintainer documentation, and validation scripts in the source distribution.
- Adopted uv for dependency management, uv_build packaging, and tox environment provisioning.
- Enforced 100% statement and branch coverage, including subprocess import and concurrency regressions.
- Added locked pre-commit checks for formatting, linting, types, security scanning, and tests.
- Documented contributor workflows, community expectations, and release and publishing procedures.
