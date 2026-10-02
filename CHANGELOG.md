# Changelog

## 1.0.0 - 2026-10-02

- Added a local setup command that generates a private Django secret and preserves existing configuration.
- Added PM2 definitions for the API and renewal worker, with automatic repository/virtualenv resolution.
- Documented installation, environment settings, API modules, deployment, backups and recovery.
- Version-pinned resolved Python dependencies, including the complete PostgreSQL driver.
- Required SECRET_KEY at startup and added database/origin configuration checks.
- Added PostgreSQL CI and configuration/setup regression tests.
- Kept database copies, uploaded documents and generated files outside source delivery.
