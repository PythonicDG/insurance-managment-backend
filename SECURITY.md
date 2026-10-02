# Security and private reporting

Report suspected security issues privately to the client-designated repository/security owner.
Agree and record that contact before handover. Do not post credentials or customer data in public issues.
Include affected version, reproduction and impact using synthetic data. Support periods/response times
are established by the project agreement; none are invented by this repository.

Protect env files, database/media backups, SMTP/Meta credentials and client admin accounts.
Use HTTPS, restricted admin access, host/origin allowlists, backups and proxy login rate limiting.
The API supports cookie/token authentication; tokens currently have no automatic inactivity expiry.
The system has no completed multi-tenant/role isolation design. Uploaded documents currently use file URLs;
an authenticated document delivery policy is required before confidential files are exposed on public hosting.
No penetration test, security certification or comprehensive dependency audit is claimed.

If a secret was previously committed, removing it from the current tree is insufficient: rotate it and
review history/access under the client's incident procedure. Do not rewrite shared history without coordination.
Review SECURITY.md, deployment docs and acceptance items whenever changing auth, exports or uploads.
