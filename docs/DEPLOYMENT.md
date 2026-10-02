# Linux deployment with PM2

The server checkout is `/home/insurance/insurance-managment-backend`. The API binds to
`127.0.0.1:8000` behind the HTTPS reverse proxy. PM2 supervises Gunicorn and, when enabled,
the separate renewal worker.

## Environment

Keep the server's private `.env`. Production uses `DEBUG=False`, a generated SECRET_KEY,
the backend host in ALLOWED_HOSTS, the frontend origin in CORS_ALLOWED_ORIGINS, and matching
CSRF_TRUSTED_ORIGINS. PostgreSQL credentials and SMTP/Meta credentials belong in private configuration.
See [Configuration](CONFIGURATION.md) for the complete variable reference.

For a new host, `.env.production.example` documents the settings. Configure HTTPS at the reverse proxy
before enabling SECURE_SSL_REDIRECT. The proxy must preserve Host and overwrite X-Forwarded-Proto.
Serve collected `/static/` files from `staticfiles/` and keep the API/database ports private.

## Update the checkout

Back up the database and `media/` before applying a release. Activate the server's backend virtual
environment; the checkout supports `.venv`, `venv` or the shared `/home/insurance/venv` layout.

```sh
cd /home/insurance/insurance-managment-backend
git pull --ff-only
python -m pip install -r requirements.lock.txt
python manage.py check
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy --fail-level WARNING
```

Create an administrator with `python manage.py createsuperuser` only during initial installation.
Keep demo data out of the production database. Preserve existing environment files during updates.

## PM2 processes

`deploy/ecosystem.config.js` resolves the checkout and Python executable automatically. It defines:

| Process | Command |
| --- | --- |
| insurance-backend | Gunicorn, two workers, loopback port 8000 |
| insurance-renewals | process_renewal_reminders --watch |

First start of the API:

```sh
pm2 start deploy/ecosystem.config.js --only insurance-backend
pm2 save
```

After an update:

```sh
pm2 restart deploy/ecosystem.config.js --only insurance-backend --update-env
pm2 logs insurance-backend --lines 50
```

On an existing PM2 installation, run `pm2 list` before adopting the configuration. Keep one API process
on port 8000; reuse the current process or migrate its name during a maintenance window.

Start the renewal worker separately after verifying the saved sending configuration:

```sh
pm2 start deploy/ecosystem.config.js --only insurance-renewals
pm2 save
```

Use `pm2 restart deploy/ecosystem.config.js --only insurance-renewals --update-env` after worker updates.
Set up PM2 boot persistence with `pm2 startup`, follow the command it prints, then run `pm2 save`.
Run PM2 commands as the account that owns the processes.

Verify administrator login, API requests and document access after restarting. Review
[Security](../SECURITY.md) for the document-access and authentication boundaries, and
[Operations](OPERATIONS.md) for rollback and restore.
