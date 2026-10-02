# Architecture and API map

Browser -> Next.js frontend -> Django REST API -> PostgreSQL (SQLite locally).
Django stores uploaded files in `media/`; an external reverse proxy/storage service must serve them in production.
SMTP and Meta WhatsApp are optional external dependencies. The renewal worker is a separate Django process.
No Redis/Celery dependency or automated cloud infrastructure is included.

| Module | Responsibility / API prefix |
| --- | --- |
| accounts | Login, logout, profile, password change and session tracking; `/api/auth/` |
| customers | Customer registry; `/api/customers/` |
| vehicles | Vehicle registry; `/api/vehicles/` |
| insurance | Insurers, policies, renewal links and document records; `/api/insurance/` |
| payments | Payment ledger; `/api/payments/` |
| dashboard | Dashboard/report aggregates; `/api/dashboard/` |
| settings_app | Agency branding, export PIN and email settings actions; `/api/settings/` |
| bulk_upload | Templates, preview and import; `/api/bulk-upload/` |
| whatsapp_integration | Config, messaging, delivery events, reminder outbox; `/api/whatsapp/` |
| auditlog | Change signals, request context and activity records; administered through Django Admin |
| config | Settings, URL routing, shared soft-delete behavior and admin customization |

## API conventions

Base URL is `<backend-origin>/api`. Keep trailing slashes on endpoint URLs.
Most routes require authentication. `POST /api/auth/login/` accepts JSON `username` and `password`;
the server sets the `insure_token` HttpOnly cookie. Browser requests include credentials.
`GET /api/auth/profile/`, `POST /api/auth/logout/`, `POST /api/auth/ping/` and
`POST /api/auth/change-password/` provide account operations. Password-change fields are
`verification_token`, `new_password`, and `confirm_password`. Obtain the verification
token by sending an email OTP with `POST /api/auth/change/request-otp/` and verifying
it with `POST /api/auth/change/verify-otp/` (purpose `password`). Tokens are single-use
and expire after 10 minutes. The API also accepts `Authorization: Token <key>`.

Settings contact changes use the same OTP flow with purpose `account_email`, `email`
(agency email), or `phone` (agency phone), followed by `POST /api/auth/change/contact/`
with `purpose`, `verification_token`, and `new_value`. Password/account email codes
go to the saved account email, falling back to the saved agency email. Agency contact
codes go to the saved agency email, falling back to the account email. Regular settings
updates cannot change contacts once a verification email exists. Initial agency email
setup is allowed only if neither saved email exists.
Authentication uses DRF tokens.

Core resources include `/api/customers/`, `/api/vehicles/`, `/api/insurance/companies/`,
`/api/insurance/records/`, `/api/insurance/documents/` and `/api/payments/`.
Bulk-upload routes: `GET templates/`, `GET templates/<id>/download/`, `POST preview/`, `POST import/`
under `/api/bulk-upload/`. The public Meta webhook is `/api/whatsapp/webhook/`.
See each app's `urls.py`, viewsets and serializers for all actions, parameters and validation.
Frontend request methods and shared payload interfaces are in `lib/api.ts` and `lib/bulk-upload-api.ts`.
The route definitions and serializers are the API reference for additional actions.

Errors normally use DRF status codes and JSON field/detail messages. Authentication failures are 401;
the frontend clears tab state and returns to login. Lists and special actions have their own shapes;
inspect serializers/client interfaces before building integrations.

## Persistence and boundaries

Keep every committed migration. Do not rebuild initial migrations during handover.
Business records support soft deletion; restoration uses the original deletion batch and validates constraints.
Audit records and WhatsApp logs can contain personal information and require controlled retention/backups.
The application is an agency management system; there is no implemented tenant boundary or granular
business role matrix. Do not use it as a multi-tenant service without additional authorization design.
