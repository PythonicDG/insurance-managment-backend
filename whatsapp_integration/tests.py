from unittest.mock import MagicMock, patch
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceRecord
from payments.models import Payment
from vehicles.models import Vehicle
from .models import WhatsAppConfig, WhatsAppMessageLog
from .services import WhatsAppClient, normalize_phone_number

User = get_user_model()


class WhatsAppIntegrationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testadmin", password="password123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.config = WhatsAppConfig.objects.create(
            is_enabled=True,
            test_mode=True,
            test_phone_number="919999988888",
            phone_number_id="123456789012345",
            waba_id="987654321098765",
            access_token="EAABtesttoken123456",
            api_version="v21.0",
            default_country_code="91",
            policy_template_name="insurance_policy_issued",
            payment_template_name="payment_receipt_collected",
            webhook_verify_token="test_secret_token_123",
        )

        self.customer = Customer.objects.create(
            name="Ramesh Kumar",
            phone="9876543210",
        )
        self.vehicle = Vehicle.objects.create(
            customer=self.customer,
            vehicle_number="MH12AB1234",
            vehicle_type="Car",
        )
        self.company = InsuranceCompany.objects.create(name="HDFC ERGO")
        import datetime
        self.record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-100200",
            policy_start_date=datetime.date(2026, 1, 1),
            policy_expiry_date=datetime.date(2026, 12, 31),
            total_premium=Decimal("12500.00"),
        )
        self.payment = Payment.objects.create(
            insurance_record=self.record,
            amount=Decimal("5000.00"),
            payment_method="UPI",
            payment_date=datetime.date(2026, 1, 5),
        )

    def test_phone_number_normalization(self):
        self.assertEqual(normalize_phone_number("9876543210"), "919876543210")
        self.assertEqual(normalize_phone_number("+91 98765 43210"), "919876543210")
        self.assertEqual(normalize_phone_number("098765-43210"), "919876543210")
        self.assertEqual(normalize_phone_number("919876543210"), "919876543210")
        self.assertEqual(normalize_phone_number(""), "")

    @patch("whatsapp_integration.services.requests.post")
    def test_send_template_message_in_test_mode(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messaging_product": "whatsapp",
            "messages": [{"id": "wamid.HBgLM...test"}]
        }
        mock_post.return_value = mock_response

        # Call with customer's phone
        log = WhatsAppClient.send_template_message(
            to_phone=self.customer.phone,
            template_name="insurance_policy_issued",
            body_parameters=["Ramesh", "MH12AB1234"],
            context_data={"customer": self.customer, "insurance_record": self.record},
        )

        self.assertIsNotNone(log)
        # Because test_mode=True and test_phone_number="919999988888", recipient must be redirected
        self.assertEqual(log.recipient_phone, "919999988888")
        self.assertTrue(log.is_test)
        self.assertEqual(log.status, "sent")
        self.assertEqual(log.wamid, "wamid.HBgLM...test")

    def test_webhook_get_verification(self):
        # Verification success
        response = self.client.get(
            "/api/whatsapp/webhook/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "test_secret_token_123",
                "hub.challenge": "challenge_token_response_xyz",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), "challenge_token_response_xyz")

        # Verification failure
        bad_response = self.client.get(
            "/api/whatsapp/webhook/",
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_token_response_xyz",
            },
        )
        self.assertEqual(bad_response.status_code, 403)

    def test_webhook_post_status_update(self):
        log = WhatsAppMessageLog.objects.create(
            recipient_phone="919876543210",
            status="sent",
            wamid="wamid.test_delivery_id_123",
        )

        webhook_payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.test_delivery_id_123",
                                        "status": "delivered",
                                        "timestamp": "1710000000",
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        response = self.client.post(
            "/api/whatsapp/webhook/",
            webhook_payload,
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        log.refresh_from_db()
        self.assertEqual(log.status, "delivered")

    def test_config_api_endpoints(self):
        get_res = self.client.get("/api/whatsapp/config/")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertTrue(get_res.data["test_mode"])
        self.assertEqual(get_res.data["test_phone_number"], "919999988888")

        put_res = self.client.put(
            "/api/whatsapp/config/",
            {"test_phone_number": "919888877777", "auto_send_policy_creation": False},
            format="json",
        )
        self.assertEqual(put_res.status_code, status.HTTP_200_OK)
        self.assertEqual(put_res.data["data"]["test_phone_number"], "919888877777")
        self.assertFalse(put_res.data["data"]["auto_send_policy_creation"])
