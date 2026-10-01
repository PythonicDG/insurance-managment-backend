"""Durable, fail-closed renewal outbox; only the management worker calls Meta."""
from datetime import time, timedelta
import requests
from django.db import models, transaction
from django.utils import timezone
from insurance.models import InsuranceRecord
from .models import RenewalReminderJob, RenewalReminderOptOut, WhatsAppConfig, WhatsAppMessageLog
from .services import WhatsAppClient, normalize_phone_number

STAGES = (30, 15, 7, 2, 0)


def template_name(stage):
    return f"policy_renewal_reminder_{stage}d"


def current_stage(days):
    # Missed Sunday/holiday dispatches catch up within their stage's window.
    return next((s for s in reversed(STAGES) if 0 <= days <= s), None)


def stop_reason(record, today):
    if record.deleted_at or record.customer.deleted_at or record.vehicle.deleted_at:
        return "Policy, customer or vehicle is archived."
    if record.policy_start_date > today:
        return "Policy is scheduled."
    if record.policy_expiry_date < today or not record.is_active:
        return "Policy is expired or inactive."
    if InsuranceRecord.all_objects.filter(previous_policy_id=record.pk).exists():
        return "Policy already has a renewal (including scheduled renewals)."
    if InsuranceRecord.objects.filter(vehicle_id=record.vehicle_id,
                                      policy_expiry_date__gt=record.policy_expiry_date).exclude(pk=record.pk).exists():
        return "A newer policy exists for this vehicle."
    if record.payment_status == "PAID":
        return "Policy is already paid."
    return ""


def business_time(config, now):
    local = timezone.localtime(now)
    clock = local.time().replace(tzinfo=None)
    if not (time(10) <= clock < time(12) or time(16, 30) <= clock < time(18)):
        return False
    # Choose one send window per day, with dispatch allowed after the preference.
    if clock < config.renewal_send_time or (config.renewal_send_time < time(12) and clock >= time(12)):
        return False
    if config.renewal_skip_sundays and local.weekday() == 6:
        return False
    if config.renewal_skip_holidays and local.date().isoformat() in config.renewal_holidays:
        return False
    return True


def enqueue(record, source="manual"):
    today = timezone.localdate()
    reason = stop_reason(record, today)
    stage = current_stage((record.policy_expiry_date - today).days)
    if reason or stage is None:
        raise ValueError(reason or "Policy is outside the 30-day renewal window.")
    if stage not in WhatsAppConfig.get_config().renewal_stages:
        raise ValueError("This reminder stage is disabled.")
    return RenewalReminderJob.all_objects.get_or_create(
        record=record, expiry_date=record.policy_expiry_date, stage=stage,
        defaults={"source": source})


def enqueue_due():
    config = WhatsAppConfig.get_config()
    if not config.is_enabled or not config.renewal_enabled:
        return 0
    today = timezone.localdate()
    count = 0
    records = InsuranceRecord.objects.filter(
        is_active=True, policy_start_date__lte=today,
        policy_expiry_date__range=(today, today + timedelta(days=30))
    ).select_related("customer", "vehicle")
    for record in records.iterator():
        stage = current_stage((record.policy_expiry_date - today).days)
        if stage not in config.renewal_stages or stop_reason(record, today):
            continue
        _, created = enqueue(record, "automatic")
        count += created
    return count


def make_payload(config, job, record, phone):
    params = ([record.customer.name or "Customer", record.vehicle.vehicle_number,
               record.policy_number, record.policy_expiry_date.isoformat(), record.insurance_company.name]
              if record else ["Test Customer", "MH12AB1234", "POL-TEST-001",
                              job.expiry_date.isoformat(), "Test General Insurance"])
    return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": phone,
            "type": "template", "template": {"name": template_name(job.stage),
            "language": {"code": config.renewal_language}, "components": [
                {"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]},
                *[{"type": "button", "sub_type": "quick_reply", "index": str(i),
                   "parameters": [{"type": "payload", "payload": f"renewal:{job.pk}:{action}"}]}
                  for i, action in enumerate(("renew", "quote", "contact"))]]}}


def skip(job, reason):
    job.status, job.reason = "skipped", reason
    job.log = WhatsAppMessageLog.objects.create(
        insurance_record=job.record, recipient_phone=job.recipient_phone,
        message_type="RENEWAL_REMINDER", template_name=template_name(job.stage),
        status="skipped", error_message=reason, is_test=job.is_test)
    job.save()


def claim_one():
    config_id = WhatsAppConfig.get_config().pk
    with transaction.atomic():
        # An actual write also serializes SQLite workers (select_for_update alone does not).
        models.QuerySet(model=WhatsAppConfig).filter(pk=config_id).update(updated_at=timezone.now())
        config = WhatsAppConfig.objects.select_for_update().get(pk=config_id)
        now = timezone.now()
        if not config.is_enabled or not business_time(config, now):
            return None
        if config.renewal_last_attempt_at and (now - config.renewal_last_attempt_at).total_seconds() < 4:
            return None  # global ceiling: 15 messages/minute, including overlapping workers
        today = timezone.localdate(now)
        attempts = RenewalReminderJob.all_objects.filter(attempted_at__date=today)
        if attempts.count() >= config.renewal_daily_cap:
            return None
        jobs = RenewalReminderJob.objects.filter(status="queued").select_for_update().order_by("expiry_date", "stage", "id")
        for job in jobs:
            if not job.is_test and job.source == "automatic" and not config.renewal_enabled:
                continue
            if not job.is_test and job.stage not in config.renewal_stages:
                skip(job, "Reminder stage disabled.")
                continue
            record = (InsuranceRecord.all_objects.select_related("customer", "vehicle", "insurance_company")
                      .filter(pk=job.record_id).first())
            if not job.is_test:
                reason = stop_reason(record, today) if record else "Policy no longer exists."
                if not reason and (record.policy_expiry_date != job.expiry_date or
                                   current_stage((job.expiry_date - today).days) != job.stage):
                    reason = "Reminder stage or expiry date is stale."
                if reason:
                    skip(job, reason)
                    continue
            original_phone = normalize_phone_number(
                (record.customer.phone or record.alternative_mobile_number) if record else config.test_phone_number,
                config.default_country_code)
            phone = normalize_phone_number(config.test_phone_number, config.default_country_code) if (job.is_test or config.test_mode) else original_phone
            job.recipient_phone = phone
            if not job.is_test and RenewalReminderOptOut.objects.filter(recipient_phone=original_phone).exists():
                skip(job, "Customer opted out of renewal reminders.")
                continue
            if not phone or not 8 <= len(phone) <= 15:
                skip(job, "Valid recipient/admin test phone is required; no customer fallback.")
                continue
            if attempts.filter(recipient_phone=phone).exists():
                continue  # one dispatch attempt per destination per local day
            if not config.access_token or not config.phone_number_id or not config.waba_id:
                skip(job, "Meta token, Phone Number ID and WABA ID are required.")
                continue
            payload = make_payload(config, job, record, phone)
            job.log = WhatsAppMessageLog.objects.create(
                insurance_record=record, customer=record.customer if record else None,
                recipient_phone=phone, message_type="RENEWAL_REMINDER", template_name=template_name(job.stage),
                parameters={"body": [p["text"] for p in payload["template"]["components"][0]["parameters"]],
                            "stage": job.stage, "original_recipient": original_phone},
                request_payload=payload, is_test=job.is_test or config.test_mode)
            job.status, job.attempted_at = "attempting", now
            job.save()
            config.renewal_last_attempt_at = now
            config.save(update_fields=["renewal_last_attempt_at"])
            return job.pk
    return None


def dispatch_one():
    job_id = claim_one()
    if job_id is None:
        return False
    job = RenewalReminderJob.objects.select_related("log").get(pk=job_id)
    config = WhatsAppConfig.get_config()
    approved_config = (config.renewal_language, config.waba_id, config.phone_number_id, config.access_token, config.api_version)
    log = job.log
    try:
        headers = {"Authorization": f"Bearer {config.access_token.strip()}"}
        # Never assume that a local template name implies Meta approval.
        endpoint = WhatsAppClient.get_api_endpoint(config)
        version = endpoint.split("/")[3]
        response = requests.get(f"https://graph.facebook.com/{version}/{config.waba_id}/message_templates",
                                params={"name": template_name(job.stage), "fields": "name,status,language"},
                                headers=headers, timeout=12)
        response.raise_for_status()
        approved = any(t.get("name") == template_name(job.stage) and t.get("status") == "APPROVED" and
                       t.get("language") == config.renewal_language for t in response.json().get("data", []))
        if not approved:
            raise ValueError("Meta template is not approved for the configured language.")
        with transaction.atomic():
            models.QuerySet(model=WhatsAppConfig).filter(pk=config.pk).update(updated_at=timezone.now())
            config = WhatsAppConfig.objects.select_for_update().get(pk=config.pk)
            record = (InsuranceRecord.all_objects.select_for_update().select_related("customer", "vehicle", "insurance_company")
                      .filter(pk=job.record_id).first())
            reason = ""
            if approved_config != (config.renewal_language, config.waba_id, config.phone_number_id, config.access_token, config.api_version):
                reason = "Meta credentials or template language changed during approval check."
            elif not config.is_enabled or not business_time(config, timezone.now()):
                reason = "Sending disabled or business window has closed."
            elif not job.is_test:
                reason = stop_reason(record, timezone.localdate()) if record else "Policy no longer exists."
                if not reason and (record.policy_expiry_date != job.expiry_date or
                    current_stage((job.expiry_date - timezone.localdate()).days) != job.stage):
                    reason = "Reminder stage or expiry date changed."
                if job.stage not in config.renewal_stages or (job.source == "automatic" and not config.renewal_enabled):
                    reason = "Reminder automation/stage disabled."
            if (config.test_mode or job.is_test) and log.recipient_phone != normalize_phone_number(config.test_phone_number, config.default_country_code):
                reason = "Admin test destination changed; queue a new test."
            elif not config.test_mode and not job.is_test and record and log.recipient_phone != normalize_phone_number(
                    record.customer.phone or record.alternative_mobile_number, config.default_country_code):
                reason = "Customer destination changed during approval check."
            if not job.is_test and record and RenewalReminderOptOut.objects.filter(recipient_phone=normalize_phone_number(
                    record.customer.phone or record.alternative_mobile_number, config.default_country_code)).exists():
                reason = "Customer opted out of renewal reminders."
            if reason:
                log.status, log.error_message = "skipped", reason
                job.status, job.reason = "skipped", reason
            else:
                # Rebuild parameters from current policy immediately before the request.
                log.request_payload = make_payload(config, job, record, log.recipient_phone)
                log.parameters["body"] = [p["text"] for p in log.request_payload["template"]["components"][0]["parameters"]]
                response = requests.post(WhatsAppClient.get_api_endpoint(config), json=log.request_payload,
                                         headers={"Authorization": f"Bearer {config.access_token.strip()}"}, timeout=12)
                try:
                    log.response_payload = response.json()
                except ValueError:
                    log.response_payload = {"raw_text": response.text}
                messages = log.response_payload.get("messages", [])
                if response.status_code in (200, 201) and messages and messages[0].get("id"):
                    log.wamid, log.status = messages[0]["id"], "sent"
                    job.status = "sent"
                else:
                    log.status, job.status = "failed", "failed"
                    log.error_message = f"Meta HTTP {response.status_code}: {log.response_payload}"
            log.save()
            job.save()
    except (requests.RequestException, ValueError) as exc:
        log.status, log.error_message = "failed", str(exc)
        log.save()
        job.status, job.reason = "failed", str(exc)
        job.save()
    return True
