# Meta WhatsApp setup for InsureLedger

This guide describes the application integration. Meta account eligibility, interface labels, billing,
limits, token policies and template approval can change; verify them in the client-owned Meta account.
Consult [Meta Cloud API documentation](https://developers.facebook.com/docs/whatsapp/cloud-api/),
[current pricing](https://developers.facebook.com/docs/whatsapp/pricing/) and
[Business Messaging Policy](https://business.whatsapp.com/policy) before enabling live messages.

## Account and credentials

1. Use the client's Meta Business Portfolio and developer app; assign named owners and restrict access.
2. In the Meta app's WhatsApp setup, obtain the Phone Number ID and WhatsApp Business Account ID (WABA).
   Use the available test sender/approved test recipients first. Register the client's business number
   according to the requirements shown in Meta; verify business identity/billing when requested.
3. Create a system-user access token with access to the assigned WhatsApp assets and the permissions
   `whatsapp_business_messaging` and `whatsapp_business_management`. Follow the expiration options and
   rotation policy available for that account. Store/transfer the token privately, never in Git.
4. Save the credentials in application Settings > WhatsApp. Keep test mode active and set the admin
   test phone including country code. The local environment template disables messaging initially.
5. Submit the policy/payment drafts below and the five renewal templates in
   [WHATSAPP_RENEWAL_REMINDERS.md](WHATSAPP_RENEWAL_REMINDERS.md). Match the exact approved names/languages.
   Confirm the configured Graph API version is supported in the client's app; the code defaults to v21.0.
6. Generate a private random webhook verification token and save it in both the application's WhatsApp
   configuration and Meta. Use a distinct token for each deployment.

## Webhook and worker

Use the backend HTTPS origin followed by `/api/whatsapp/webhook/` as the callback URL.
Subscribe to message events. The saved webhook verify token handles Meta's GET challenge;
set `WHATSAPP_APP_SECRET` in the backend service environment for POST signature validation.
The app secret and verify token are different values. Restart the API after environment changes.

The renewal outbox requires a separate supervised process:

```sh
python manage.py process_renewal_reminders --watch
```

Follow [renewal operation and safeguards](WHATSAPP_RENEWAL_REMINDERS.md) for scheduling, caps, consent,
opt-outs, holiday rules and interrupted attempts. Most WhatsApp environment values initialize saved
database settings; changing the environment alone does not overwrite existing stored settings.

## Acceptance before live mode

- Confirm the master switch and test mode, test destination and approved templates.
- Create a synthetic policy/payment and verify receipt on the admin phone and delivery logs.
- Test each renewal stage through the UI and inspect worker/provider IDs and webhook delivery events.
- Validate the customer's consent process and STOP/UNSUBSCRIBE handling.
- Confirm client billing, account limits, token owner/rotation, webhook signature secret and incident owner.
- Switch to live mode only after the client accepts test results; record the setting change and owner.

## Policy and payment template drafts

Submit these drafts for approval. Utility is the proposed category; Meta determines the final category and approval status. Use the exact names and matching approved language in saved application settings.

### How to Create Templates in WhatsApp Manager:
1. Go to **Meta Developer Portal** $\rightarrow$ **WhatsApp** $\rightarrow$ **Quick Links** $\rightarrow$ Click **WhatsApp Manager** (or visit [business.facebook.com/wa/manage/message-templates](https://business.facebook.com/wa/manage/message-templates)).
2. Click the **Create Template** button.
3. Follow the specifications below for each template:

---

### Template 1: Policy Issued Notification
- **Category**: Select **Utility**.
- **Template Name**: `insurance_policy_issued` *(Must be all lowercase with underscores)*.
- **Language**: `English` (code: `en`).
- **Header**: None (or optional Text header: `Insurance Policy Issued`).
- **Body Text** *(Copy and paste the exact text below)*:
```text
Dear {{1}}, your vehicle insurance for {{2}} has been issued successfully.

*Policy Details:*
• Policy Number: {{3}}
• Insurance Company: {{4}}
• Valid Till: {{5}}
• Total Premium: {{6}}
• Amount Paid: {{7}}
• Outstanding Balance: {{8}}

Thank you for choosing our services. Please contact us if you have any questions.
```
- **Sample Values for Approval** (synthetic examples):
  - `{{1}}`: `Rahul Sharma`
  - `{{2}}`: `MH 12 AB 1234`
  - `{{3}}`: `POL-2026-9912`
  - `{{4}}`: `HDFC ERGO General Insurance`
  - `{{5}}`: `2027-09-25`
  - `{{6}}`: `INR 14,500.00`
  - `{{7}}`: `INR 5,000.00`
  - `{{8}}`: `INR 9,500.00`
- Click **Submit**. Wait for the actual approval status in WhatsApp Manager; no approval time is guaranteed.

---

### Template 2: Payment Receipt Notification
- **Category**: Select **Utility**.
- **Template Name**: `payment_receipt_collected` *(Must be all lowercase with underscores)*.
- **Language**: `English` (code: `en`).
- **Body Text** *(Copy and paste the exact text below)*:
```text
Dear {{1}}, we have received your payment of {{4}} for vehicle {{2}}.

*Payment Receipt:*
• Receipt ID: {{3}}
• Amount Paid: {{4}}
• Payment Date: {{5}}
• Payment Mode: {{6}}
• Remaining Outstanding: {{7}}

Thank you for your prompt payment!
```
- **Sample Values for Approval**:
  - `{{1}}`: `Rahul Sharma`
  - `{{2}}`: `MH 12 AB 1234`
  - `{{3}}`: `RCP-1042`
  - `{{4}}`: `INR 5,000.00`
  - `{{5}}`: `2026-09-25`
  - `{{6}}`: `UPI`
  - `{{7}}`: `INR 4,500.00`
- Click **Submit**.

---
