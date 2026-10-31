# Release preparation

Version `1.0.0` is currently unreleased. This checklist prepares reviewable artifacts; it does not authorize a tag, push, GitHub release, or package publication.

## Repository and reporting details

The canonical repository is [Lazarus-org/fastapi-settings](https://github.com/Lazarus-org/fastapi-settings). Project URLs are recorded in `pyproject.toml`; private reporting addresses are recorded in [SECURITY.md](SECURITY.md). Confirm that these destinations remain correct before publishing.

Confirm the intended PyPI owner and publication process separately. The release-candidate workflow validates tags, runs the reusable CI workflow, and retains candidate artifacts on GitHub. It contains no package-publishing job and requires no PyPI credentials.

## Validate the candidate

1. Review source changes and assign the correct issue references before creating commits. Keep local IDE files, environments, and credentials out of version control.
2. Confirm that the package version and changelog agree. Add a release date only when the release is approved. Retain the CPython support statement and zero mandatory runtime dependencies.
3. Run the full tests and quality checks in [CONTRIBUTING.md](CONTRIBUTING.md).
4. Require actual green hosted results for all CPython 3.11–3.15 jobs and the quality job before publication. Local Windows results do not establish Ubuntu runner compatibility.
5. Build into an empty `dist` directory and check the exact artifacts:

```bash
python -m build
python -m twine check --strict dist/*
python .github/scripts/validate_distribution.py dist --test-sdist
```

The source archive must contain tests, examples, contributor/security/release documents, and the CI scripts needed to reproduce these checks. The wheel must contain the runtime package, typing marker, license, and metadata. Source-only material and local artifacts must stay out of the wheel.

The archive test verifies that its package is imported from the extracted source tree, runs the full suite there, and rebuilds its wheel. It compares wheel entry names and contents, ignoring ZIP timestamps. For byte-for-byte reproducibility checks, build twice with the same build-tool versions and a fixed `SOURCE_DATE_EPOCH`, then compare SHA-256 hashes. Default build timestamps are not a reproducibility guarantee.

## Final handoff

Record the actual interpreter and dependency versions, test results, artifact hashes, and any unresolved limitations. Review the rendered package description, license, examples, and security-reporting instructions. Preserve the validated artifacts; rebuilding requires repeating validation.

Commits, release dates, tags, uploads, and release announcements require their own approval. Do not interpret a passing build or this checklist as production-readiness certification.
