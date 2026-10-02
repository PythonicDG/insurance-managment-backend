# Operations

## Service checks

```sh
pm2 list
pm2 logs insurance-backend --lines 50
```

When the renewal worker is enabled, also inspect `pm2 logs insurance-renewals --lines 50` and the
WhatsApp delivery logs in Settings. Monitor API errors, disk space, database capacity, certificate
expiry and backup completion. An unauthenticated request to `/api/auth/profile/` should return 401.

## Backups

Back up the database and `media/` together. Pause API writes and the renewal worker for a coordinated
snapshot. Store encrypted copies outside the application host and test restoration periodically.
Database backups include user records, audit history and saved Meta credentials; restrict access.
Keep private environment credentials in the server's secret-management process.

For PostgreSQL, use `pg_dump` in custom format with the database connection configured in `.env`.
Use a private password file or the hosting backup service rather than a password in command arguments.
Restore with `pg_restore` into an empty isolated database using the matching source release.

For SQLite, stop writes before copying `db.sqlite3`. The SQLite backup API is also supported by
Python's sqlite3 module. Copy the associated `media/` directory with the same snapshot.

A restore check covers customer, vehicle, policy and payment counts; outstanding balances;
renewal links; audit history; and representative document downloads. Keep SMTP/WhatsApp disabled
and the worker stopped while testing restored data.

## Releases and rollback

Keep the backend/frontend release commits together. Before an update, take a database/media backup
and retain the previous source or build. Stop the worker, install the committed dependencies, apply
migrations, collect static files, restart the API/frontend and verify the main workflows.
Resume the worker after the API checks pass.

Roll back code alone only when it is compatible with the current schema. Otherwise stop writes and
restore the matched database/media backup and previous source release. A restore discards changes
made after the snapshot; account for those records before cutover. Preserve applied migration history.

## Archived records and interrupted reminders

Archived business records retain their deletion batch. The `restore_record` management command
restores that batch and checks constraints; see [Soft deletion](../SOFT_DELETES.md).
Keep audit history intact when recovering records.

A failed or interrupted reminder may already have been accepted by Meta. Inspect the provider message
ID and webhook status history before recovery. Do not reset jobs for an automatic resend.

## Credentials

Rotate database, SMTP and Meta credentials through private configuration. Update saved Meta settings
in the application as well as the service environment. Change the webhook verification token in both
Meta and application settings, and set the app secret in the backend environment.

After a credential or database exposure, revoke affected API tokens and review access logs.
Changing Django SECRET_KEY alone does not revoke database-backed API tokens.
