# Repository handover

Repository: [PythonicDG/insurance-managment-backend](https://github.com/PythonicDG/insurance-managment-backend).
Companion application: [insurance-managment-frontend](https://github.com/PythonicDG/insurance-managment-frontend).

## Included source

The repository contains the Django application, database migrations, API tests, dependency definitions,
environment examples, local setup script, PM2 configuration and operating documentation.
The detailed implementation guides cover imports, soft deletion, audit history and WhatsApp renewals.

`requirements.lock.txt` records the resolved Python dependencies. `.env.example` provides local defaults;
`.env.production.example` documents production configuration. Private environment files, database copies,
uploaded documents, virtual environments and collected static files stay outside Git.

## Running and maintaining the system

Use [Installation](INSTALLATION.md) for a new checkout and [Deployment](DEPLOYMENT.md) for server updates.
Preserve applied migrations and take database/media backups before a release.
The API and renewal worker are separate PM2 processes. Saved WhatsApp credentials and sending settings
live in the database; changing environment variables alone does not replace them.

Use [Operations](OPERATIONS.md) for recovery and [Security](../SECURITY.md) for access controls.
[Validation](VALIDATION.md) records the checks performed on this source.

## Release verification

Verify administrator login/logout, a customer and vehicle, policy creation, partial/full payment,
renewal links, dashboard totals, document retrieval and an import preview using test data.
Check archive/restore behavior and activity history. For enabled WhatsApp integration, test the admin
destination, approved templates, delivery webhooks and renewal worker before customer messaging.

Keep the release commits for both repositories together. Repository administrators manage access,
required CI checks and reviews. Hosting credentials, account ownership and client data are transferred
through private administration channels, separately from the source archives.
