# Activity audit log

Apply the migration before starting the updated application:

```powershell
python manage.py migrate
```

Open Django admin -> Activity audit -> Staff activity logs. Superusers can view entries.
Other active staff need the **view_activitylog** permission, assigned directly
or through an auditor group. There are no audit API routes or frontend screens.
Entries cannot be added, edited, or deleted in admin, including by superusers.
The list shows local date/time, username, action, a readable activity description,
browser/operating system, and IP address. Search by customer name, phone, policy
number, vehicle number, insurance company name, username, action text, browser,
IP address, or record/request ID. Filters narrow results by action, record type,
and date. Open an activity to see a Field / Before / After table; technical data
is collapsed below it.

Customer and policy identifiers are saved with the event, so changing a name or
archiving a record does not erase its searchable description. A rename can be
found using either the old or new name. Existing entries are enriched from their
previously recorded history during migration; missing historical information is
left unknown. Older events have no device/IP information to recover.

Browser/operating system comes from the User-Agent and is reported, not a verified
hardware identity or computer hostname. IP addresses can be shared by multiple
devices on the same network. New events preserve both the device description and
the observed client IP.

## Coverage and guarantees

- Creates and edits of application business models, including customers,
  vehicles, insurance companies, policies, documents, payments, business and
  WhatsApp configuration, message status, and bulk upload configuration/receipts.
- Instance saves, queryset updates, bulk inserts/updates, archival deletes,
  cascading deletes, and deletion-batch restores share the same central hooks.
  A payment collection is a payment creation; its entry contains the amount,
  discount, payment method/date, and policy ID. Related policy changes have the
  same request ID.
- Successful API login, logout, and password changes, plus Django session
  login/logout (including admin). Session heartbeats and automatic timestamp
  updates are excluded. Failed requests are not recorded as successful actions.
- Each business mutation and its audit insert use the same database transaction.
  If audit persistence fails, that mutation fails and rolls back. Outer business
  transactions also roll back their audit entries. No post-commit queue can lose
  the event. Multi-step workflows retain their existing transaction boundaries.
- The actor is resolved after DRF authentication, for cookie and header tokens.
  Django admin uses its session user. Actor ID and username are historical values
  with no cascading user relationship. Unattributed commands/jobs are marked
  `system`, and each operation/cascade receives a correlation UUID. Request IDs
  are generated server-side, never trusted from client headers.
- Passwords, token/secret/PIN/OTP fields and message payload/parameter fields are
  redacted. Secret changes still produce events. No request bodies, query strings,
  cookies, authorization headers, or raw session identifiers are logged. Files
  are represented by stored names, never file contents.
- Actual persisted values are compared, including `update_fields`; no-op saves
  do not create noise. PostgreSQL row locks serialize changes captured by the
  hooks. SQLite retains its normal database locking semantics.

## Production operation

Use PostgreSQL for concurrent production traffic. Use a separate migration/owner
database role from the application's runtime role. Grant the runtime role only
SELECT and INSERT on `auditlog_activitylog` (and sequence access for inserts),
and explicitly revoke UPDATE, DELETE, and TRUNCATE on that table. ORM guards
protect ordinary application code; database privileges protect direct SQL.
A database owner can still alter data, so this is not a claim of tamper-proof
storage. Protect and monitor privileged access and database backups.

If Nginx proxies requests to Django, set `AUDIT_TRUSTED_PROXY_IPS` to the actual
direct proxy addresses (for example `127.0.0.1,::1` for a local proxy). Have the
proxy correctly set/append `X-Forwarded-For`. Only forwarding chains received
from a configured trusted peer are used; untrusted callers cannot replace the
logged IP by supplying that header. Without this setting, the direct peer IP is
logged. This setting does not change authentication or other proxy settings.

Audit entries contain historical customer and financial values. Limit the view
permission to designated administrators/auditors and secure database backups.
There is no automatic purge. Set a retention policy for your business and archive
through a separately authorized operations process before adding any purge.
Database indexes cover time, user/time, action/time, object history, and request
correlation; the admin uses pagination and avoids a second full-table count.

Bulk inserts with conflict-ignore/upsert modes are rejected because they cannot
reliably identify inserted versus changed rows. Use `update_or_create` instead.
Normal inserts and `bulk_update` are covered. Primary-key changes through
queryset updates are rejected to retain stable object
identity. Raw SQL, data fixtures, historical
migration models, direct Django auth user/group administration, and M2M changes
are outside the business model hooks. Django's existing admin log still covers
auth user/group administration. Routine reads/exports and failed login attempts
are outside this mutation audit's scope. Earlier activity cannot be reconstructed.

Jobs can use `auditlog.context.audit_context()` to correlate several operations.
Keep the context inside the worker execution; do not pass authenticated request
objects between workers. Attribute job execution to `system` unless a verified
initiating user is explicitly supplied to `record_event`.

Validation:

```powershell
python manage.py check
python manage.py test --noinput
python manage.py makemigrations --check --dry-run
```
