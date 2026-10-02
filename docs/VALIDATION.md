# Validation — 1.0.0

Checked on 2026-10-02 with Python 3.11.0 on Windows.

| Check | Result |
| --- | --- |
| Full Django suite | 190 tests passed |
| Django system check | No issues |
| Migration drift | No changes detected |
| Dependency consistency | pip check passed |
| Local setup | Generated a private secret, retained development defaults and preserved an existing env byte for byte |
| PM2 configuration | JavaScript syntax passed; process commands and resolved paths checked |

The suite includes authentication, policies, payments, imports, soft deletion, audit history,
renewal reminders, startup configuration and the local environment setup command.
The local run uses SQLite. CI provisions PostgreSQL and runs migrations and the same suite.

The clean-install check covered database creation, administrator creation, cookie login,
profile access, logout and unauthenticated rejection. HTTPS/HSTS settings also passed Django's
deployment check in an isolated configuration.

The PM2 configuration is intended for Linux. Live TLS/proxy behavior, database restore and SMTP/Meta
delivery are checked in the deployed environment using the operating and integration guides.
