# InsureLedger backend

Django 5.2 / Django REST Framework API for customers, vehicles, insurance policies,
payments, reports, bulk imports, business settings, activity audit and Meta WhatsApp notifications.
The browser application is maintained in the separate `insurance-managment-frontend` repository.

Start with [Installation](docs/INSTALLATION.md). Local development uses Python 3.11 and SQLite;
the documented production deployment uses Linux, Gunicorn, PostgreSQL and an HTTPS reverse proxy.
Direct dependencies are in `requirements.txt`; install the resolved `requirements.lock.txt` for delivery.
PostgreSQL includes both Psycopg and its binary implementation.

## Documentation

- [Delivery validation and remaining items](docs/VALIDATION.md)

- [Installation and first administrator](docs/INSTALLATION.md)
- [Environment configuration](docs/CONFIGURATION.md)
- [Architecture and API reference](docs/ARCHITECTURE.md)
- [Production deployment](docs/DEPLOYMENT.md)
- [Operations, backup, restore and rollback](docs/OPERATIONS.md)
- [Client handover and acceptance checklist](docs/HANDOVER.md)
- [Security and reporting](SECURITY.md), [contributing](CONTRIBUTING.md), [release notes](CHANGELOG.md)
- [Bulk upload](BULK_UPLOAD.md), [soft deletes](SOFT_DELETES.md), [activity audit](ACTIVITY_AUDIT.md)
- [WhatsApp setup](META_WHATSAPP_SETUP_GUIDE.md), [renewal reminder worker](WHATSAPP_RENEWAL_REMINDERS.md)

## Verification

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
```

GitHub Actions runs these checks against PostgreSQL. No deployment is performed by CI.
Do not include `.env`, virtual environments, databases, uploads, backups or build outputs in a source handover.
Source ownership and third-party obligations are described in [NOTICE](NOTICE.md).
