from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core import mail
from rest_framework import status
from rest_framework.test import APIClient

from .models import BusinessSettings
from .email_service import send_export_notification_email


class ExportNotificationEmailTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testagent",
            email="agent@example.com",
            first_name="Ramesh",
            last_name="Patil",
            password="secretpassword",
        )
        BusinessSettings.objects.all().delete()
        self.business_settings = BusinessSettings.objects.create(
            id=1,
            business_name="Patil Insurance Agency",
            email="owner@patilinsurance.com",
            phone="+919876543210",
            address="101 MG Road, Pune",
        )
        self.url = reverse("notify-export")

    def test_unauthenticated_request_rejected(self):
        response = self.client.post(self.url, {
            "action_type": "export_csv",
            "source_module": "insurance_records",
            "record_count": 25,
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_export_notification_dispatches_email_without_attachments(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "action_type": "export_csv",
            "source_module": "insurance_records",
            "record_count": 42,
            "filters": {
                "status": "Active",
                "search": "MH12",
                "date_from": "2026-01-01",
            },
        }

        # Clear mailbox before test
        mail.outbox = []

        # Test service directly with async_dispatch=False to verify email contents synchronously
        success, message = send_export_notification_email(
            action_type="export_csv",
            source_module="insurance_records",
            record_count=42,
            user=self.user,
            client_ip="127.0.0.1",
            filters=payload["filters"],
            async_dispatch=False,
        )

        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        self.assertIn("owner@patilinsurance.com", sent_email.to)
        self.assertIn("Exported to CSV", sent_email.subject)
        self.assertIn("Insurance Records", sent_email.subject)
        self.assertIn("42", sent_email.subject)

        # Check body text
        self.assertIn("Ramesh Patil (testagent)", sent_email.body)
        self.assertIn("127.0.0.1", sent_email.body)
        self.assertIn("42 record(s)", sent_email.body)
        self.assertIn("MH12", sent_email.body)

        # Strictly verify NO attachments
        self.assertEqual(len(sent_email.attachments), 0, "No attachments should be present in the alert email.")

    def test_api_endpoint_notify_export_success(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "action_type": "save_pdf",
            "source_module": "outstanding_ledger",
            "record_count": 15,
            "filters": {
                "payment_status": "UNPAID",
            },
        }

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["recipient"], "owner@patilinsurance.com")

    def test_print_all_notification(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            "action_type": "print_all",
            "source_module": "insurance_records",
            "record_count": 100,
        }

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

    def test_missing_business_email_handled_gracefully(self):
        # Empty business email
        self.business_settings.email = ""
        self.business_settings.save()

        self.client.force_authenticate(user=self.user)
        payload = {
            "action_type": "export_csv",
            "source_module": "insurance_records",
            "record_count": 10,
        }

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["success"])
        self.assertIn("No email address found", response.data["message"])

    def test_test_email_endpoint(self):
        self.client.force_authenticate(user=self.user)
        test_email_url = reverse("test-email")
        mail.outbox = []

        response = self.client.post(test_email_url, {"email": "owner@patilinsurance.com"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@patilinsurance.com"])

    def test_verify_export_pin_when_not_set(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("verify-export-pin")

        # PIN not set yet
        response = self.client.post(url, {"pin": "1234"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data.get("pin_not_set"))

    def test_verify_export_pin_valid_and_invalid(self):
        self.client.force_authenticate(user=self.user)
        self.business_settings.set_export_pin("4321")
        self.business_settings.save()

        url = reverse("verify-export-pin")

        # Invalid PIN
        res_wrong = self.client.post(url, {"pin": "9999"})
        self.assertEqual(res_wrong.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res_wrong.data["success"])

        # Valid PIN
        res_correct = self.client.post(url, {"pin": "4321"})
        self.assertEqual(res_correct.status_code, status.HTTP_200_OK)
        self.assertTrue(res_correct.data["success"])

    def test_request_pin_otp_success(self):
        self.client.force_authenticate(user=self.user)
        mail.outbox = []
        url = reverse("pin-request-otp")

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        self.business_settings.refresh_from_db()
        self.assertTrue(bool(self.business_settings.pin_otp))
        self.assertEqual(len(self.business_settings.pin_otp), 6)
        self.assertIsNotNone(self.business_settings.pin_otp_expires_at)

        # Verify email dispatched
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("PIN Setup Code", mail.outbox[0].subject)
        self.assertIn(self.business_settings.pin_otp, mail.outbox[0].body)

    def test_set_export_pin_flow(self):
        self.client.force_authenticate(user=self.user)
        # Request OTP first
        self.client.post(reverse("pin-request-otp"))
        self.business_settings.refresh_from_db()
        otp = self.business_settings.pin_otp

        set_url = reverse("pin-set")

        # Test invalid OTP
        res_bad_otp = self.client.post(set_url, {
            "otp": "000000",
            "new_pin": "5678",
            "confirm_pin": "5678",
        })
        self.assertEqual(res_bad_otp.status_code, status.HTTP_400_BAD_REQUEST)

        # Test mismatched PIN
        res_mismatch = self.client.post(set_url, {
            "otp": otp,
            "new_pin": "5678",
            "confirm_pin": "1234",
        })
        self.assertEqual(res_mismatch.status_code, status.HTTP_400_BAD_REQUEST)

        # Test successful set
        mail.outbox = []
        res_success = self.client.post(set_url, {
            "otp": otp,
            "new_pin": "5678",
            "confirm_pin": "5678",
        })
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        self.assertTrue(res_success.data["success"])

        self.business_settings.refresh_from_db()
        self.assertTrue(self.business_settings.check_export_pin("5678"))
        self.assertEqual(self.business_settings.pin_otp, "")
        self.assertIsNone(self.business_settings.pin_otp_expires_at)

        # Check confirmation email
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Export Security PIN Updated", mail.outbox[0].subject)

    def test_serializer_is_export_pin_set(self):
        from .serializers import BusinessSettingsSerializer
        serializer_unconfigured = BusinessSettingsSerializer(self.business_settings)
        self.assertFalse(serializer_unconfigured.data["is_export_pin_set"])

        self.business_settings.set_export_pin("1234")
        self.business_settings.save()

        serializer_configured = BusinessSettingsSerializer(self.business_settings)
        self.assertTrue(serializer_configured.data["is_export_pin_set"])

    def test_remove_export_pin_success_and_failures(self):
        from django.utils import timezone
        from datetime import timedelta

        self.client.force_authenticate(user=self.user)
        remove_url = reverse("pin-remove")

        # 1. Failure when PIN not set
        res_no_pin = self.client.post(remove_url, {"otp": "123456"})
        self.assertEqual(res_no_pin.status_code, status.HTTP_400_BAD_REQUEST)

        # Configure PIN & OTP
        self.business_settings.set_export_pin("9876")
        self.business_settings.pin_otp = "654321"
        self.business_settings.pin_otp_expires_at = timezone.now() + timedelta(minutes=10)
        self.business_settings.save()

        # 2. Failure with invalid OTP
        res_bad_otp = self.client.post(remove_url, {"otp": "000000"})
        self.assertEqual(res_bad_otp.status_code, status.HTTP_400_BAD_REQUEST)

        # 3. Successful removal with correct OTP
        mail.outbox = []
        res_success = self.client.post(remove_url, {"otp": "654321"})
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        self.assertTrue(res_success.data["success"])

        self.business_settings.refresh_from_db()
        self.assertEqual(self.business_settings.export_pin, "")
        self.assertFalse(self.business_settings.is_export_pin_set)
        self.assertEqual(self.business_settings.pin_otp, "")
        self.assertIsNone(self.business_settings.pin_otp_expires_at)

        # Verify removal alert email
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("PIN Removed", mail.outbox[0].subject)


