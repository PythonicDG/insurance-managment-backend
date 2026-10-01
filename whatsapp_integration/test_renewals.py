from datetime import timedelta, datetime, time
from decimal import Decimal
from unittest.mock import Mock, patch
import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from customers.models import Customer
from vehicles.models import Vehicle
from insurance.models import InsuranceRecord, InsuranceCompany
from payments.models import Payment
from .models import WhatsAppConfig, RenewalReminderJob, WhatsAppMessageLog
from .renewals import enqueue, enqueue_due, dispatch_one, business_time, current_stage
from .serializers import WhatsAppConfigSerializer


class RenewalTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.now = timezone.make_aware(datetime.combine(self.today, time(10, 30)))
        self.config = WhatsAppConfig.objects.create(renewal_enabled=True, test_mode=False,
            renewal_skip_sundays=False, access_token="token", waba_id="waba", phone_number_id="phone",
            test_phone_number="919999988888", auto_send_policy_creation=False, auto_send_payment_receipt=False)
        self.customer = Customer.objects.create(name="Customer", phone="9876543210")
        self.company = InsuranceCompany.objects.create(name="Insurer")
        self.record = self.make_record("TEST", 30)
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_user(username="admin", password="test"))

    def make_record(self, number, days):
        vehicle = Vehicle.objects.create(customer=self.customer, vehicle_number=number, vehicle_type="Car")
        return InsuranceRecord.objects.create(customer=self.customer, vehicle=vehicle,
            insurance_company=self.company, policy_number=number, policy_start_date=self.today - timedelta(days=335),
            policy_expiry_date=self.today + timedelta(days=days), total_premium=Decimal("100"))

    def approval(self, stage=30):
        return Mock(status_code=200, json=Mock(return_value={"data": [{"name": f"policy_renewal_reminder_{stage}d",
                    "status": "APPROVED", "language": "en"}]}))

    def sent(self):
        return Mock(status_code=200, json=Mock(return_value={"messages": [{"id": "wamid.test"}]}))

    def run_dispatch(self):
        with patch("whatsapp_integration.renewals.timezone.now", return_value=self.now):
            return dispatch_one()

    def test_all_stages_and_no_duplicate_queue(self):
        for days in [15, 7, 2, 0]:
            self.make_record(f"STAGE{days}", days)
        self.assertEqual(enqueue_due(), 5)
        self.assertEqual(enqueue_due(), 0)
        self.assertEqual(set(RenewalReminderJob.objects.values_list("stage", flat=True)), {30, 15, 7, 2, 0})
        self.assertEqual(current_stage(29), 30)
        self.assertEqual(current_stage(14), 15)
        self.assertIsNone(current_stage(-1))

    @patch("whatsapp_integration.renewals.requests.post")
    def test_paid_after_queue_never_sent(self, post):
        enqueue(self.record)
        Payment.objects.create(insurance_record=self.record, amount=100)
        self.assertFalse(self.run_dispatch())
        post.assert_not_called()
        self.assertEqual(RenewalReminderJob.objects.get().status, "skipped")

    @patch("whatsapp_integration.renewals.requests.post")
    def test_scheduled_renewal_after_queue_never_sent(self, post):
        enqueue(self.record)
        InsuranceRecord.objects.create(customer=self.customer, vehicle=self.record.vehicle, insurance_company=self.company,
            policy_number="NEXT", previous_policy=self.record,
            policy_start_date=self.record.policy_expiry_date + timedelta(days=1),
            policy_expiry_date=self.record.policy_expiry_date + timedelta(days=366), total_premium=100)
        self.assertFalse(self.run_dispatch())
        post.assert_not_called()

    @patch("whatsapp_integration.renewals.requests.get")
    @patch("whatsapp_integration.renewals.requests.post")
    def test_recheck_payment_immediately_before_send(self, post, get):
        enqueue(self.record)
        def approved(*args, **kwargs):
            Payment.objects.create(insurance_record=self.record, amount=100)
            return self.approval()
        get.side_effect = approved
        self.assertTrue(self.run_dispatch())
        post.assert_not_called()
        self.assertEqual(WhatsAppMessageLog.objects.get().status, "skipped")

    @patch("whatsapp_integration.renewals.requests.get")
    @patch("whatsapp_integration.renewals.requests.post")
    def test_template_payload_wamid_cooldown_cap_and_spacing(self, post, get):
        get.return_value, post.return_value = self.approval(), self.sent()
        enqueue(self.record)
        second = self.make_record("SECOND", 30)
        enqueue(second)
        self.assertTrue(self.run_dispatch())
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], "template")
        self.assertEqual([p["text"] for p in payload["template"]["components"][0]["parameters"]],
            ["Customer", "TEST", "TEST", self.record.policy_expiry_date.isoformat(), "Insurer"])
        self.assertEqual(WhatsAppMessageLog.objects.get().wamid, "wamid.test")
        self.assertFalse(self.run_dispatch())  # global spacing
        self.now += timedelta(seconds=5)
        self.assertFalse(self.run_dispatch())  # same phone
        second.customer = Customer.objects.create(name="Other", phone="9876543211")
        second.save()
        self.config.renewal_daily_cap = 1
        self.config.save()
        self.assertFalse(self.run_dispatch())
        self.assertEqual(post.call_count, 1)

    @patch("whatsapp_integration.renewals.requests.get")
    @patch("whatsapp_integration.renewals.requests.post")
    def test_unapproved_template_and_timeout_not_retried(self, post, get):
        get.return_value = Mock(json=Mock(return_value={"data": []}))
        enqueue(self.record)
        self.assertTrue(self.run_dispatch())
        self.assertEqual(RenewalReminderJob.objects.get().status, "failed")
        self.now += timedelta(seconds=5)
        self.assertFalse(self.run_dispatch())
        post.assert_not_called()

    @patch("whatsapp_integration.renewals.requests.get")
    @patch("whatsapp_integration.renewals.requests.post")
    def test_live_mode_test_only_uses_admin(self, post, get):
        get.return_value, post.return_value = self.approval(), self.sent()
        response = self.client.post("/api/whatsapp/renewals/send-test/", {"stage": 30}, format="json")
        self.assertEqual(response.status_code, 202)
        post.assert_not_called()
        self.assertTrue(self.run_dispatch())
        self.assertEqual(post.call_args.kwargs["json"]["to"], self.config.test_phone_number)
        self.assertTrue(WhatsAppMessageLog.objects.get().is_test)

    @patch("whatsapp_integration.renewals.requests.post")
    def test_manual_endpoint_queues_without_network_and_deduplicates(self, post):
        url = f"/api/whatsapp/records/{self.record.pk}/renewal/"
        self.assertEqual(self.client.post(url).status_code, 202)
        self.assertEqual(self.client.post(url).status_code, 202)
        self.assertEqual(RenewalReminderJob.objects.count(), 1)
        post.assert_not_called()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.post(url).status_code, 401)

    def test_business_windows_sundays_holidays_and_settings_validation(self):
        for clock, expected in [(time(9, 30), False), (time(10, 29), False), (time(10, 30), True),
                                (time(12), False), (time(16, 30), False), (time(19, 30), False)]:
            self.assertEqual(business_time(self.config, timezone.make_aware(datetime.combine(self.today, clock))), expected)
        self.config.renewal_send_time = time(16, 30)
        self.assertTrue(business_time(self.config, timezone.make_aware(datetime.combine(self.today, time(17)))))
        self.assertFalse(business_time(self.config, timezone.make_aware(datetime.combine(self.today, time(18)))))
        self.config.renewal_holidays = [self.today.isoformat()]
        self.assertFalse(business_time(self.config, timezone.make_aware(datetime.combine(self.today, time(17)))))
        self.config.renewal_holidays = []
        self.config.renewal_skip_sundays = True
        sunday = self.today + timedelta(days=(6 - self.today.weekday()) % 7)
        self.assertFalse(business_time(self.config, timezone.make_aware(datetime.combine(sunday, time(17)))))
        for data in [{"renewal_send_time": "03:00"}, {"renewal_stages": [1]}, {"renewal_daily_cap": 0}, {"renewal_holidays": ["bad"]}]:
            self.assertFalse(WhatsAppConfigSerializer(self.config, data=data, partial=True).is_valid())

    def test_disabled_stages_and_master(self):
        self.config.renewal_enabled = False
        self.config.save()
        self.assertEqual(enqueue_due(), 0)
        self.config.renewal_enabled = True
        self.config.renewal_stages = [0]
        self.config.save()
        self.assertEqual(enqueue_due(), 0)
        self.assertEqual(self.client.post(f"/api/whatsapp/records/{self.record.pk}/renewal/").status_code, 400)
        self.assertEqual(RenewalReminderJob.objects.count(), 0)

    def test_webhook_keeps_event_history_without_regression_and_resend_blocked(self):
        log = WhatsAppMessageLog.objects.create(recipient_phone="919876543210", message_type="RENEWAL_REMINDER", wamid="wamid.history", status="sent")
        for state in ["read", "delivered", "sent", "read"]:
            self.client.post("/api/whatsapp/webhook/", {"entry": [{"changes": [{"value": {"statuses": [
                {"id": log.wamid, "status": state, "timestamp": "100"}]}}]}]}, format="json")
        log.refresh_from_db()
        self.assertEqual(log.status, "read")
        self.assertEqual(len(log.delivery_events), 3)
        self.assertEqual(self.client.post(f"/api/whatsapp/logs/{log.pk}/resend/").status_code, 400)

    @patch("whatsapp_integration.renewals.requests.get")
    @patch("whatsapp_integration.renewals.requests.post")
    def test_timeout_and_interrupted_claim_never_retried(self, post, get):
        get.return_value = self.approval()
        post.side_effect = requests.Timeout("Accepted outcome unknown")
        enqueue(self.record)
        self.assertTrue(self.run_dispatch())
        self.now += timedelta(seconds=5)
        self.assertFalse(self.run_dispatch())
        self.assertEqual(post.call_count, 1)
        self.assertIn("unknown", WhatsAppMessageLog.objects.get().error_message)
        RenewalReminderJob.objects.filter(record=self.record).update(status="attempting")
        self.assertFalse(self.run_dispatch())

    @patch("whatsapp_integration.renewals.requests.post")
    def test_stop_opt_out_and_missing_test_phone_are_fail_closed(self, post):
        enqueue(self.record)
        self.client.post("/api/whatsapp/webhook/", {"entry": [{"changes": [{"value": {"messages": [
            {"from": "919876543210", "text": {"body": "STOP"}}]}}]}]}, format="json")
        self.assertFalse(self.run_dispatch())
        self.assertIn("opted out", RenewalReminderJob.objects.get().reason)
        self.config.test_mode = True
        self.config.test_phone_number = ""
        self.config.save()
        self.assertEqual(self.client.post("/api/whatsapp/renewals/send-test/").status_code, 400)
        post.assert_not_called()

    @patch.dict("os.environ", {"WHATSAPP_APP_SECRET": "test-app-secret"})
    def test_webhook_signature_rejects_forged_events(self):
        response = self.client.post("/api/whatsapp/webhook/", {"entry": []}, format="json")
        self.assertEqual(response.status_code, 403)
