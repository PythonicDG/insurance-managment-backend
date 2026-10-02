# Configuration reference

Django loads `.env` from the repository root. Process environment variables take precedence.
Use `.env.example` for local development and `.env.production.example` as a production starting point.
Empty credentials are intentional; obtain client values through a private channel.

| Variable | Purpose / format |
| --- | --- |
| SECRET_KEY | Required generated secret; use different keys per environment. |
| DEBUG | True locally; False in production. Controls auth-cookie Secure flag. |
| ALLOWED_HOSTS | Comma-separated backend hostnames, no protocol or path. |
| CORS_ALLOWED_ORIGINS | Exact comma-separated frontend origins including protocol and port. Explicit list replaces local defaults. |
| CSRF_TRUSTED_ORIGINS | Trusted HTTPS origins for Django Admin / CSRF-protected requests. |
| DB_ENGINE | sqlite, postgres or postgresql. Unrecognized values fail startup. |
| DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT | PostgreSQL connection; ignored by SQLite. |
| TIME_ZONE | Defaults to Asia/Kolkata; reminder schedules use this timezone. |
| AUDIT_TRUSTED_PROXY_IPS | Proxy IP allowlist for client-IP audit attribution; never use arbitrary untrusted proxies. |
| AUTH_COOKIE_SAMESITE | Lax by default. Same-site app/api subdomains are the documented topology. |
| AUTH_COOKIE_DOMAIN | Blank means host-only (recommended). Changing domain changes logout-cookie matching. |
| SECURE_SSL_REDIRECT | Enable with HTTPS and a trusted proxy configured to overwrite X-Forwarded-Proto. |
| SECURE_HSTS_SECONDS | 0 locally; production template starts at 3600; increase after verifying TLS. |
| SECURE_HSTS_INCLUDE_SUBDOMAINS, SECURE_HSTS_PRELOAD | False initially; enable only after every affected hostname supports HTTPS. |
| EMAIL_BACKEND | Console locally; django.core.mail.backends.smtp.EmailBackend for real mail. |
| EMAIL_HOST, EMAIL_PORT | SMTP server and integer port. |
| EMAIL_USE_TLS, EMAIL_USE_SSL | Select the provider's transport; do not enable both. |
| EMAIL_HOST_USER, EMAIL_HOST_PASSWORD | SMTP credentials or application password. |
| DEFAULT_FROM_EMAIL | Verified sender address. |
| EMAIL_TIMEOUT | Integer network timeout in seconds. |
| ADMIN_NOTIFICATION_EMAIL | Recipient for application export notifications. |
| WHATSAPP_ENABLED, WHATSAPP_TEST_MODE | Initial master switch and test mode; templates default disabled / test mode. |
| WHATSAPP_TEST_PHONE | Admin test destination including country code. |
| WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_WABA_ID | Client Meta identifiers. |
| WHATSAPP_API_TOKEN | Client Meta system-user token; persisted in database-backed settings. |
| WHATSAPP_API_VERSION | Defaults to v21.0 in this code; verify availability in the client's Meta app before enabling. |
| WHATSAPP_DEFAULT_COUNTRY_CODE | Defaults to 91. |
| WHATSAPP_WEBHOOK_VERIFY_TOKEN | Generate a private random token for Meta GET verification. |
| WHATSAPP_APP_SECRET | Meta app secret used on every webhook POST for signature validation. Required before public live integration. |
| WHATSAPP_TEMPLATE_POLICY_CREATED, WHATSAPP_TEMPLATE_PAYMENT_COLLECTED | Approved template names. |

WhatsApp configuration lives in `WhatsAppConfig`. Environment values seed the first configuration;
on later reads only empty token, phone-number ID, WABA ID and test phone may be filled from the environment.
Changing the environment alone does not overwrite saved settings or switch sending mode.
Rotate/update stored values in Settings > WhatsApp and verify the result. Template languages,
renewal stages, send time, caps and holidays are managed in the UI/database, not additional env variables.

The separate frontend uses only `NEXT_PUBLIC_API_URL`: backend origin without `/api`.
An empty value makes requests same-origin under `/api`; use that only with an explicit proxy route.
Public values are embedded during the frontend build. Secrets must never use the NEXT_PUBLIC prefix.
