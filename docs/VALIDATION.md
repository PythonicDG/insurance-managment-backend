# Delivery validation - 2026-10-02

Environment: Windows, Python 3.11.0 and Node.js 24.19.0. Results are local verification,
not a claim that the client's production deployment or hosted CI has been accepted.

| Check | Result |
| --- | --- |
| Backend existing full suite after settings/dependency changes | 184 tests passed. |
| Additional startup/configuration regression tests | 4 tests passed separately (config.tests). |
| Django check and migration drift | Passed; no pending model changes. |
| Django deploy check with explicit HTTPS/HSTS test configuration | Passed with no warnings; actual production values still require their own check. |
| Clean backend dependency install | Passed in a new virtual environment; dependency consistency passed. |
| Clean backend source smoke test | Empty SQLite migrations, new administrator, HttpOnly-cookie login, profile, logout and unauthenticated rejection passed. |
| Frontend lint | Passed: 0 errors, 53 warnings. |
| Frontend typecheck | Passed, including generated route types. |
| Frontend production build | Passed in the original and clean source copies; 14 pages generated. |
| Clean frontend dependency install | npm ci passed with the committed lockfile. |
| Environment examples | Version-controlled; private env files stay ignored. |
| Source ZIP verification | Archive integrity, SHA-256 checksums and source consistency passed. |
| Documentation links | Relative file links passed. |
| Current local secret exact-value check | No matches in delivered source or repository history. This is a limited check, not a comprehensive secret audit. |

## Frontend follow-up

The 53 warnings comprise 30 unused-variable warnings, 19 set-state-in-effect diagnostics,
1 manual-memoization diagnostic, 2 effect-dependency warnings and 1 location-navigation warning.
React Compiler is not enabled: compiler-readiness diagnostics are explicitly advisory in ESLint config.
They were changed from errors to warnings; hook-ordering correctness and mutation checks remain errors.
The ledger payment modal's conditional hook ordering was fixed using a separately mounted keyed form.
Unsafe explicit-any exception handling was replaced with typed error extraction.

npm reported a deprecation notice for locked ESLint 9.39.5. Review a compatible toolchain upgrade
in a separate tested change; no arbitrary dependency upgrade was made for delivery.
Install also reported a pending allowScripts review for unrs-resolver; lint/build passed as installed.

## Checks still required in the client environment

GitHub Actions workflows are supplied but have not been executed in the client account.
Local backend tests used SQLite; the supplied CI uses PostgreSQL. PostgreSQL production behavior,
Linux service units, real reverse proxy/TLS, SMTP, Meta approvals/billing and live delivery are not locally certified.
Complete the manual staging acceptance checklist, coordinated database/media restore and security review.
In particular, resolve or explicitly accept document file-URL access, auth-token lifetime and role/tenant limits
before a public deployment with confidential records.

The source snapshots include the handover changes from the working tree. No final delivery commit,
release tag, push, repository ownership transfer or account-level branch protection has been performed.
Record the final backend/frontend commit IDs after review and commit.
