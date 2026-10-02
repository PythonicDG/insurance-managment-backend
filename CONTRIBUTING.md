# Backend maintenance

Work in a branch and describe the behavior changed by the pull request. Run Django checks, the
migration drift check and tests before review. Include database, environment and rollout effects.

Keep applied migrations unchanged. Add a new migration for model changes and verify it against
PostgreSQL through CI. Release API contract changes with the corresponding frontend update.

Update requirements.txt for direct dependency changes, resolve them in a clean Python 3.11 environment
and regenerate requirements.lock.txt. Commit both files and test the resolved installation.

Update environment examples and documentation when configuration changes. Use synthetic records
in tests and issue reports; keep credentials, uploads and database backups outside Git.
