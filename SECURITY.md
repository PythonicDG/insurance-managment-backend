# Security

Send security reports privately to the repository administrators through the existing project contact
channel. Include the affected commit, reproduction and impact using synthetic data.
Keep credentials and customer records out of public issues.

## Deployment controls

- Use HTTPS and keep Gunicorn/PostgreSQL ports private.
- Configure explicit host/origin allowlists, trusted proxy headers and login rate limits at the proxy.
- Restrict Django Admin and database access. Protect the private env, backups and uploaded documents.
- Verify WHATSAPP_APP_SECRET before exposing the Meta webhook. Keep test mode enabled during integration testing.

## Application boundaries

Authentication uses database-backed tokens and an HttpOnly cookie. Tokens are revoked on logout and
password change; automatic inactivity expiry is disabled. Closing a tab clears browser state but does
not guarantee server-side token revocation.

Document records are authenticated, but uploaded files currently use media URLs. A publicly served
media URL is accessible to anyone who has it. Confidential document hosting needs access controls
at the storage/download layer. The application is a single-agency system without tenant isolation
or a granular business-role matrix.

Audit and messaging logs contain personal information. Limit access and include them in the backup
retention policy. WhatsApp positive consent is maintained operationally; opt-outs are persisted.

## Credential exposure

Rotate exposed database, SMTP and Meta credentials, revoke affected API tokens and review access logs.
Update persisted Meta settings as well as service environment variables. Changing SECRET_KEY alone
does not revoke API tokens. Coordinate shared Git-history changes with repository administrators.
