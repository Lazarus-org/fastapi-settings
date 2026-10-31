# Security Policy

## Supported versions

Security fixes apply to the latest supported stable release. Older releases may not receive backported fixes.

## Reporting a vulnerability

Please **do not** open a public issue for an undisclosed vulnerability. Email the maintainers privately at either address:

- [aryan513966@gmail.com](mailto:aryan513966@gmail.com)
- [mehrshad_mirshekary@email.com](mailto:mehrshad_mirshekary@email.com)

Include reproduction steps, the affected version, and potential impact; redact real credentials and personal data. Do not post the report to the public [issue tracker](https://github.com/Lazarus-org/fastapi-settings/issues).

## Security expectations

Settings modules execute trusted application Python code on import. The package does not implement encryption, secrets storage, sandboxing, credential rotation, or arbitrary code execution prevention for deliberately selected settings modules. It avoids printing configuration values in its own representations and error messages, but external libraries and chained import exceptions can still expose values if application error logs are mishandled. Review logging and error handling in production applications.
