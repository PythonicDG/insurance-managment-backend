# Client handover and acceptance - backend

## Delivery record (complete with the client)

| Item | Value to record |
| --- | --- |
| Client / repository owner | Client legal entity and repository administrator |
| Repository URL / final commit | Client-owned URL and full commit hash |
| Paired repository commit | Matching backend/frontend full commit hash |
| Release / environment | Approved release tag, hosting and actual domains |
| Technical / support owner | Named contacts and agreed support period |
| Backup owner / targets | Named owner, retention, recovery time and recovery point |
| Acceptance | Client approver, date, test results and accepted limitations |
| Contract / ownership | Signed project agreement reference |

## Source and account transfer

- [ ] Review repository diff and commit the delivery changes; record final commit IDs for both repos.
- [ ] Transfer/push repositories into client-owned private repositories with history as agreed.
- [ ] Enable branch protection, required CI/review, least-privilege access and dependency alerts.
- [ ] Run fresh installs and CI in the client's account; no passing hosted CI is implied by adding workflow files.
- [ ] Transfer hosting, DNS, TLS, database, SMTP and Meta account control through private channels.
- [ ] Generate/rotate client secrets and administrator credentials; remove unneeded delivery-party access.
- [ ] Transfer client data/media only through an agreed encrypted channel, separate from source Git repos.
- [ ] Supply the user manuals from the workspace deliverables folder if included in the project agreement.
- [ ] Record ownership terms, support contacts, release commits and all accepted limitations.

## Functional acceptance (staging with synthetic data)

- [ ] Fresh install, migrations and first admin creation follow the guide.
- [ ] Login, refresh, password change and logout work; protected routes reject unauthenticated requests.
- [ ] Add/edit customer and vehicle; create policy and detect duplicates.
- [ ] Record partial/full payment; verify discount, outstanding balance and printed receipt.
- [ ] Renew a policy; verify old/new links and lifecycle status.
- [ ] Verify dashboard/reports/date filters against known values.
- [ ] Upload/view a document under the agreed storage/access policy.
- [ ] Download import template, preview valid/invalid rows and import synthetic records.
- [ ] Set/verify export PIN and verify configured email notifications.
- [ ] Archive/restore a record and inspect activity audit.
- [ ] If WhatsApp is in scope, verify approved templates, signature-checked webhook, worker restart,
  test destination, delivery logs, opt-out behavior and consent process before enabling live sends.
- [ ] Restore database plus media in isolation and record recovery evidence.
- [ ] Verify HTTPS, proxy rate limits, production deploy checks and monitoring ownership.

## Boundaries to resolve or explicitly accept

The system has no dedicated health endpoint, automated end-to-end browser suite, configured monitoring,
automatic auth-token inactivity expiry, tenant isolation or complete business-role authorization model.
Uploaded documents use file URLs; confidential public hosting needs authenticated delivery controls.
WhatsApp positive consent is an operating process rather than a structured consent register.
External service availability, hosting capacity, license review and a production security assessment
must be validated separately. See [delivery validation](VALIDATION.md) for local test outcomes and advisory lint findings.
