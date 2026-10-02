# Contributing

Work in a branch, describe the user-visible change, and open a pull request against the client repository.
Follow README.md to install the backend; use the documented runtime and committed dependency definitions.
Run CI checks locally before review. Include migration/deployment effects, validation and rollback needs.
Keep each migration committed and do not edit applied migration history. Keep backend API and frontend
payload changes compatible or release them together. Update environment examples and docs for config changes.

Never commit credentials, client records, uploaded documents, database backups or generated artifacts.
For dependency changes, update requirements.txt, resolve in a clean Python 3.11 virtual environment,
regenerate requirements.lock.txt using pip freeze, and run CI including PostgreSQL. The lock includes
the dependency versions verified during delivery; it is version-pinned, not a package hash lock.
Use synthetic data in bug reports. Do not switch off checks to make a change pass.
The React Compiler is not enabled; compiler-readiness diagnostics are advisory, while normal hook
correctness and TypeScript checks remain enforced. Avoid adding new advisory warnings.

Client repository administrators should configure protected default branches, required CI and review,
least-privilege access, dependency/security alerts and a release owner. These account-level settings are
not activated by files in this repository. Tag a release only after both repositories pass acceptance;
include exact commit IDs and deployment environment in the release record.
