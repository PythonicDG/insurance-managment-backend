# InsureLedger backend

Django REST API for the InsureLedger insurance management application. It manages customers,
vehicles, policies, renewals, payments, uploaded documents, bulk imports and activity history.
Business settings, export verification, SMTP notifications and Meta WhatsApp messaging are included.

**Version:** 1.0.0. **Runtime:** Python 3.11, Django 5.2.17, Django REST Framework 3.18.1.
SQLite is the local development database; PostgreSQL is supported for production.
Install dependencies from `requirements.lock.txt`. Direct dependencies are maintained in `requirements.txt`.

The [frontend repository](https://github.com/PythonicDG/insurance-managment-frontend) contains the Next.js application.

## Start locally

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock.txt
python scripts/configure_local.py
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

The setup command generates a private secret and retains an existing `.env`.
Local email is printed to the console and WhatsApp sending is disabled.
Sign in at `http://localhost:8000/admin/` with the administrator created above.
Windows commands are in [Installation](docs/INSTALLATION.md).

## Documentation

| Guide | Contents |
| --- | --- |
| [Installation](docs/INSTALLATION.md) | Windows/Linux setup, database selection and troubleshooting |
| [Configuration](docs/CONFIGURATION.md) | Environment variables and saved integration settings |
| [Architecture](docs/ARCHITECTURE.md) | Modules, authentication and API routes |
| [Deployment](docs/DEPLOYMENT.md) | Linux server updates and PM2 processes |
| [Operations](docs/OPERATIONS.md) | Backups, restore, rollback and credential rotation |
| [Handover](docs/HANDOVER.md) | Repository contents and maintenance responsibilities |
| [Validation](docs/VALIDATION.md) | Recorded checks and test coverage |

Feature references: [bulk upload](BULK_UPLOAD.md), [soft deletion](SOFT_DELETES.md),
[activity audit](ACTIVITY_AUDIT.md), [WhatsApp setup](META_WHATSAPP_SETUP_GUIDE.md),
[renewal reminders](WHATSAPP_RENEWAL_REMINDERS.md).

## Checks

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
```

GitHub Actions runs checks against PostgreSQL. Production processes are defined in
`deploy/ecosystem.config.js`; deployment does not run automatically from CI.
See [Contributing](CONTRIBUTING.md), [Security](SECURITY.md) and [NOTICE](NOTICE.md).
