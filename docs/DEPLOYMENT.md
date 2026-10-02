# Production deployment

This guide describes a Linux deployment with client-owned domains `app.example.com` and `api.example.com`.
Replace every example value. It is a deployment procedure, not a claim that hosting has been provisioned.
Use Python 3.11, PostgreSQL, Node.js for the separate frontend, TLS certificates and a reverse proxy.

1. Provision an unprivileged service account, a dedicated PostgreSQL role/database, persistent storage,
   TLS and firewall rules. Keep PostgreSQL and the Gunicorn port private.
2. Check out the agreed backend release. Create `.venv` and install `requirements.lock.txt`.
3. Copy `.env.production.example` to `.env`; set a generated secret, database credentials, actual
   backend/frontend domains and SMTP values. Restrict `.env` permissions to the service account.
   Keep WhatsApp disabled until the client's Meta setup is verified.
4. Back up existing database and uploads before changing an existing deployment. Run:

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy --fail-level WARNING
.venv/bin/python manage.py createsuperuser
```

Create the administrator only on initial setup. Generate its password privately and transfer it securely.
Do not run seed_data.py on production. Resolve all deploy-check warnings against the real environment.

5. Run the API under a supervisor, with this repository as the working directory:

```sh
.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 60 --access-logfile - --error-logfile -
```

Gunicorn is for Linux, not Windows. Size worker count/timeouts for the actual host and measured workload.
Use `deploy/insureledger-api.service.example` as a systemd starting point; replace paths/account names.
6. Reverse proxy HTTPS `api.example.com` to 127.0.0.1:8000. Preserve Host and overwrite
   X-Forwarded-Proto with the actual connection scheme. Only trust headers from this proxy.
   Serve `/static/` from `staticfiles/`. Size request limits for the agreed import/document limits.
   Enforce login rate limits at the proxy, restrict admin access and collect service logs.
7. Uploaded insurance documents currently use file URLs rather than authorization-checked downloads.
   Publicly serving all of `/media/` exposes files to anyone with their URLs. Before accepting a public
   deployment with confidential documents, agree and implement an authenticated download/storage policy.
   Run a private network deployment meanwhile if appropriate to the client's accepted use.
8. Build/start the frontend using its deployment guide. Verify CORS and cookies with a real browser.
   Same-site HTTPS subdomains work with host-only auth cookies and SameSite=Lax; unrelated domains require
   separately validated cookie/CSRF design and may encounter browser third-party-cookie restrictions.
9. If renewals are enabled, run `.venv/bin/python manage.py process_renewal_reminders --watch` as a
   separate supervised process. Use the provided worker unit example. Verify approved templates,
   test phone, consent process, webhook signature secret and delivery logs before live mode.
10. Complete docs/HANDOVER.md and record exact backend/frontend commit IDs and test results.

Reference: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).
