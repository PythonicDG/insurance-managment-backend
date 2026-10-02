# Operations runbook

Assign named client owners for hosting, database, backups, credentials, incidents and releases.
Agree retention, recovery point/time targets and support coverage before acceptance.
Monitor API failures/latency, frontend availability, disk space, database capacity, TLS expiry,
SMTP failures and renewal-worker/delivery logs. No monitoring service is preconfigured.
An unauthenticated request to `/api/auth/profile/` should return 401; this checks routing/auth,
not complete database or external-service health. There is no dedicated health endpoint.

## Backup and restore

Back up the database AND `media/`; source code alone cannot restore client records or attachments.
Store encrypted, access-controlled copies outside the application host and regularly restore them in isolation.
Database backups include Meta configuration/access tokens, users and personal data; protect them as secrets.
Keep environment secrets separately in a client-controlled secret store. Never commit backup files.

For PostgreSQL, use the client database tools and a private `.pgpass`/secret mechanism:

```sh
pg_dump --format=custom --host=DB_HOST --username=DB_USER --dbname=DB_NAME --file=/secure-backups/insureledger.dump
```

For a consistent coordinated snapshot, pause writes and the renewal worker during database/media capture.
Back up `media/` with the hosting provider's encrypted storage snapshot/backup tooling.
For SQLite, stop writes and use SQLite's backup API (or a stopped-server copy); do not copy a live
database and assume it is consistent. SQLite is intended for local use in this delivery.

Restore into an EMPTY isolated PostgreSQL database, using matching release source and media snapshot:

```sh
pg_restore --no-owner --no-acl --host=DB_HOST --username=DB_USER --dbname=RESTORE_DB /secure-backups/insureledger.dump
```

Use credentials that own/can create objects in the target database. Keep SMTP/WhatsApp disabled,
block outbound messaging while inspecting restored saved config, and keep the worker stopped.
Check customer/policy/payment counts, balances, renewal links, audit records and representative document downloads.
Record actual restore duration and snapshot timestamp. Only cut over after an agreed maintenance window.

## Release / rollback

Record both repository commits. Run CI and acceptance checks before tagging a release in each repo.
Take database/media backups, stop the worker, deploy dependencies/source, apply migrations, collect static,
restart API/frontend, smoke test, then resume the worker. Retain the previous release artifact.
If code alone is compatible with the current schema, revert to the previous artifact and restart services.
Otherwise stop writes and restore the matched pre-release database/media snapshot and source version.
Restoring discards post-backup changes; obtain the incident owner's decision. Never blindly reverse migrations.

## Record recovery and reminders

Archive operations are soft deletes. Follow SOFT_DELETES.md; an operator can run
`python manage.py restore_record customers.Customer <id>` to restore a batch after reviewing conflicts.
Do not directly delete rows or reset audit history. Failed/interrupted renewal jobs may already have reached
Meta: inspect provider IDs and webhook history before recovery. Do not blindly reset/retry jobs.

## Credential rotation

Update hosting/CI secrets, SMTP credentials, PostgreSQL credentials and Django SECRET_KEY separately.
Update persisted Meta credentials in Settings > WhatsApp; changing env alone may not replace them.
Rotate the webhook verification token in both Meta and saved application settings, and supply the app secret
in the service environment. If credentials or the database were exposed, revoke DRF auth tokens as well.
Changing Django SECRET_KEY alone does not invalidate the database-backed API tokens.
