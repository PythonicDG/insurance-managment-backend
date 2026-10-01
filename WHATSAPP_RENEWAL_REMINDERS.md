# WhatsApp renewal reminders

## Setup and operation

1. Run `python manage.py migrate` in the backend directory.
2. Submit the five templates below in WhatsApp Manager. Use the exact names, text and three quick-reply buttons in the listed order. Select English (`en`) or match the saved renewal language code to the actual approved language, such as `en_US`.
3. Save Meta credentials including WABA ID. The token needs access to read WABA templates (`whatsapp_business_management`) and send messages (`whatsapp_business_messaging`). The worker checks the exact name, language and APPROVED status before every attempt. Pending, paused, disabled or missing templates fail closed.
4. In Settings → WhatsApp, save the admin test phone, holiday dates, stage selection, daily cap and preferred send time. Automatic renewals default OFF, stages default ON, cap defaults 100, time defaults 10:30, and Sunday/holiday skipping defaults ON. Holidays are explicitly configured dates; no regional calendar is inferred.
5. Run `python manage.py process_renewal_reminders --watch` under your deployment process supervisor. This is a separate process from Django/Gunicorn. Alternatively schedule `python manage.py process_renewal_reminders` every minute using cron or Windows Task Scheduler, with the backend directory as the working directory and the backend virtualenv Python as the executable. Overlapping workers are serialized by the database. Configure automatic restart on failure. Do not run the worker inside a web request.
6. Click Send Test Reminder for each stage during the selected window. A 202 response means queued, not delivered. Inspect Settings → WhatsApp delivery logs for the result and `wamid`. Test jobs always use the saved admin phone even in live mode and share the safety cap/cooldown. After verifying the templates, enable automatic reminders and select live/test mode as needed.
7. Subscribe the existing HTTPS `/api/whatsapp/webhook/` endpoint to Meta's messages events for sent/delivered/read/failed tracking. Set `WHATSAPP_APP_SECRET` to your Meta app secret to enforce signature validation. `hub.verify_token` is only for GET verification; it is not the POST signature secret.

Renewals use only template messages, regardless of the 24-hour window. [WhatsApp's Business Messaging Policy](https://business.whatsapp.com/policy) governs approved-template initiation, customer consent and opt-out handling. Message only customers who have agreed to receive these notifications. Incoming STOP or UNSUBSCRIBE text messages create a persistent phone-level renewal opt-out checked before dispatch. Agents can also maintain this list in Django Admin. There is no automatic START/re-subscribe; remove an opt-out only after obtaining fresh consent. The ERP has no structured positive-consent register; manage eligible customer contact data accordingly.

## Behavior and safety

- Stages are 30, 15, 7, 2 and 0 days before expiry. At a missed run, only the current stage is queued: days 30–16 → 30d, 15–8 → 15d, 7–3 → 7d, 2–1 → 2d, expiry day → 0d. Sunday/holiday postponement therefore sends within the stage's remaining window. An expiry-day reminder skipped on a Sunday is never sent on Monday after expiry. No old-stage burst occurs.
- Stop checks run at enqueue, claim and immediately before sending. Archived, inactive, expired, future/scheduled, linked renewed, newer-policy-for-same-vehicle, and PAID policies are excluded. **PAID refers to the existing record's premium/payment status**, as requested, even if its renewal premium has not yet been collected. A linked successor suppresses reminders even if scheduled or archived.
- Manual row buttons use the same stages, deduplication, stop rules, hours, cooldown and cap. They can queue when automatic reminders are OFF, provided WhatsApp and the relevant stage are enabled. They never dispatch synchronously. Automatic jobs remain queued while the automation switch is OFF; they are rechecked when enabled.
- Local timezone is Django `TIME_ZONE` (default Asia/Kolkata). Select a time in 10:00–11:59 or 16:30–17:59. The worker sends from that time until 12:00 or 18:00, exclusively, in the chosen window. It never sends outside those windows. The daily cap counts attempts (including failures and tests), not successful deliveries. Reservation occurs before network calls.
- All renewal destinations are normalized. Each destination gets at most one attempted reminder per local day, across vehicles, stages, manual sends, tests and overlapping workers. In test mode every job goes to the admin destination, so this also limits automated test-mode sends to one per day.
- Global renewal rate is at most 15 reserved attempts per minute (minimum four seconds between reservations). These limits cover the renewal outbox, not existing policy-issued/payment notifications.
- A database constraint permits one non-test job per policy/expiry/stage. Claimed attempts are committed before network calls, preventing duplicate sends after worker restarts. Failed or interrupted jobs are **not automatically retried**, since a timed-out Meta request may already have been accepted. An interrupted job remains `attempting` with a queued audit log; investigate it and provider delivery events before considering a controlled recovery. Do not reset it blindly.
- Queued jobs are in `RenewalReminderJob`; dispatch audit records include request/response, parameters, destination, stage, errors, `wamid`, and delivery event history in `WhatsAppMessageLog`. Skipped claim checks get audit logs. Webhook status history preserves events and never regresses a read message to sent. Renewal-log resends are disabled to prevent bypassing the worker.
- Quick replies initiate a customer reply; they do not themselves buy insurance, generate a quote or call the agent. This implementation does not add automated inbound sales handling.

## Copy-ready Meta templates

The categories below are proposed submission categories for these drafts. Meta determines the final classification and approval. The quotation/comparison template is deliberately Marketing; the other drafts are specific existing-policy notifications proposed as Utility. Do not add discounts, guaranteed NCB savings or broad promotions to the Utility drafts.

All five use these exact body variables and sample values when submitting:

| Variable | Meaning | Sample |
|---|---|---|
| `{{1}}` | Customer name | Ramesh Kumar |
| `{{2}}` | Vehicle number | MH12AB1234 |
| `{{3}}` | Policy number | POL-100200 |
| `{{4}}` | Expiry date | 2026-12-31 |
| `{{5}}` | Insurer name | HDFC ERGO |

For **every template**, add three **Quick Reply** buttons in this exact order:

1. `Renew Now`
2. `Request Quote`
3. `Contact Agent`

Use text headers with no header variables. No footer is required. Do not convert these quick replies to URL/call buttons without changing the sender's payload.

### 30 days — Awareness and NCB review

Template name: `policy_renewal_reminder_30d`  
Category: **Utility**  
Header (Text):

```text
Policy expiry notice
```

Body:

```text
Hello {{1}},

Your insurance policy {{3}} with {{5}} for vehicle {{2}} expires on {{4}}.

Please review your renewal details and claim history with your agent so your No Claim Bonus eligibility can be checked before renewal.

If renewal or payment has already been completed, please contact your agent to update this policy record.
```

### 15 days — Quotation and comparison

Template name: `policy_renewal_reminder_15d`  
Category: **Marketing**  
Header (Text):

```text
Policy renewal quotation
```

Body:

```text
Hello {{1}},

Your insurance policy {{3}} with {{5}} for vehicle {{2}} expires on {{4}}.

You can request a renewal quotation and ask your agent to compare available cover options, premiums and applicable No Claim Bonus details.

If renewal or payment has already been completed, please contact your agent to update this policy record. Reply STOP to stop WhatsApp renewal reminders.
```

### 7 days — Urgent follow-up

Template name: `policy_renewal_reminder_7d`  
Category: **Utility**  
Header (Text):

```text
Upcoming policy expiry
```

Body:

```text
Hello {{1}},

Your insurance policy {{3}} with {{5}} for vehicle {{2}} expires on {{4}}. Our records do not yet show a completed renewal.

Please contact your agent to confirm the renewal status and any pending documents or payment needed before expiry.

If you have already renewed or paid, please share the confirmation with your agent so this record can be updated.
```

### 2 days — Final reminder and lapse risk

Template name: `policy_renewal_reminder_2d`  
Category: **Utility**  
Header (Text):

```text
Final policy expiry reminder
```

Body:

```text
Hello {{1}},

This is a final reminder that insurance policy {{3}} with {{5}} for vehicle {{2}} expires on {{4}}. Our records do not yet show a completed renewal.

Coverage may lapse after expiry unless renewal is completed. Please contact your agent to confirm the renewal requirements and status.

If you have already renewed or paid, please share the confirmation with your agent so this record can be updated.
```

### Expiry day — Immediate action

Template name: `policy_renewal_reminder_0d`  
Category: **Utility**  
Header (Text):

```text
Your policy expires today
```

Body:

```text
Hello {{1}},

Your insurance policy {{3}} with {{5}} for vehicle {{2}} expires today, {{4}}. Our records do not yet show a completed renewal.

Please contact your agent today to confirm renewal and avoid a gap in coverage. Your agent can confirm the exact policy expiry time and renewal requirements.

If you have already renewed or paid, please share the confirmation with your agent so this record can be updated.
```

## Validation

Run `python manage.py test whatsapp_integration --noinput`. The new tests cover stage scheduling, idempotency, settings validation, business windows, Sundays/holidays, stop checks after enqueue and during approval lookup, approved-template payloads, phone cooldown, rate spacing, daily cap, test-only routing in live mode, authentication, queue-only endpoints, and delivery-history ordering.
