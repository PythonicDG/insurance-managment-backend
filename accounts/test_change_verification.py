import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from settings_app.models import BusinessSettings
from .models import AccountChangeChallenge


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountChangeVerificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("owner", email="owner@example.com", password="OriginalStrong@123")
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.business = BusinessSettings.objects.create(pk=1, email="agency@example.com", phone="9876543210")

    def post(self, endpoint, data):
        return self.client.post(f"/api/auth/{endpoint}/", data, format="json")

    def send(self, purpose):
        response = self.post("change/request-otp", {"purpose": purpose})
        self.assertEqual(response.status_code, 200, response.data)
        return re.search(r"\b\d{6}\b", mail.outbox[-1].body).group()

    def verify(self, purpose):
        otp = self.send(purpose)
        response = self.post("change/verify-otp", {"purpose": purpose, "otp": otp})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["verification_token"]

    def test_password_requires_otp_not_old_password(self):
        response = self.post("change-password", {"old_password": "OriginalStrong@123", "new_password": "ReplacementStrong@456"})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OriginalStrong@123"))

    def test_password_confirmation_validation_and_logout(self):
        token = self.verify("password")
        self.assertEqual(mail.outbox[-1].to, ["owner@example.com"])
        payload = dict(verification_token=token, new_password="ReplacementStrong@456", confirm_password="wrong")
        self.assertEqual(self.post("change-password", payload).status_code, 400)
        payload["confirm_password"] = payload["new_password"]
        response = self.post("change-password", payload)
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(payload["new_password"]))
        self.assertFalse(Token.objects.filter(pk=self.token.pk).exists())
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 401)

    def test_phone_requires_verification_and_token_is_single_use(self):
        token = self.verify("phone")
        self.assertEqual(mail.outbox[-1].to, ["agency@example.com"])
        payload = dict(purpose="phone", verification_token=token, new_value="+91 91234 56789")
        self.assertEqual(self.post("change/contact", payload).status_code, 200)
        self.assertEqual(self.post("change/contact", payload).status_code, 400)
        self.business.refresh_from_db()
        self.assertEqual(self.business.phone, payload["new_value"])

    def test_email_verifies_old_address_and_updates_only_agency(self):
        token = self.verify("email")
        self.assertEqual(mail.outbox[-1].to, ["agency@example.com"])
        response = self.post("change/contact", dict(purpose="email", verification_token=token, new_value="new@example.com"))
        self.assertEqual(response.status_code, 200)
        self.business.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.business.email, "new@example.com")
        self.assertEqual(self.user.email, "owner@example.com")

    def test_account_email_change(self):
        token = self.verify("account_email")
        response = self.post("change/contact", dict(purpose="account_email", verification_token=token, new_value="newowner@example.com"))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "newowner@example.com")

    def test_wrong_codes_lock_after_five_attempts(self):
        otp = self.send("phone")
        wrong = "000000" if otp != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.post("change/verify-otp", {"purpose": "phone", "otp": wrong}).status_code, 400)
        self.assertEqual(self.post("change/verify-otp", {"purpose": "phone", "otp": otp}).status_code, 400)
        self.assertEqual(AccountChangeChallenge.objects.get().attempts, 5)

    def test_expired_code_and_expired_grant_are_rejected(self):
        otp = self.send("phone")
        AccountChangeChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post("change/verify-otp", dict(purpose="phone", otp=otp)).status_code, 400)
        AccountChangeChallenge.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        token = self.verify("phone")
        AccountChangeChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post("change/contact", dict(purpose="phone", verification_token=token, new_value="9123456789")).status_code, 400)

    def test_grant_cannot_be_used_for_other_change_or_user(self):
        token = self.verify("phone")
        self.assertEqual(self.post("change/contact", dict(purpose="email", verification_token=token, new_value="attacker@example.com")).status_code, 400)
        other = User.objects.create_user("other", email="other@example.com")
        self.client.force_authenticate(other)
        self.assertEqual(self.post("change/contact", dict(purpose="phone", verification_token=token, new_value="9123456789")).status_code, 400)

    def test_direct_settings_updates_cannot_bypass_otp(self):
        for method in (self.client.patch, self.client.put):
            response = method("/api/settings/", {"email": "attacker@example.com", "phone": "9123456789"}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.business.refresh_from_db()
        self.assertEqual(self.business.email, "agency@example.com")
        self.assertEqual(self.client.patch("/api/settings/", {"business_name": "Updated Agency"}, format="json").status_code, 200)

    def test_resend_invalidates_old_grant(self):
        token = self.verify("phone")
        self.assertEqual(self.post("change/request-otp", {"purpose": "phone"}).status_code, 429)
        AccountChangeChallenge.objects.update(created_at=timezone.now() - timedelta(minutes=2))
        self.send("phone")
        self.assertEqual(self.post("change/contact", dict(purpose="phone", verification_token=token, new_value="9123456789")).status_code, 400)

    def test_changed_recipient_invalidates_challenge(self):
        token = self.verify("phone")
        self.business.email = "changed@example.com"
        self.business.save()
        self.assertEqual(self.post("change/contact", dict(purpose="phone", verification_token=token, new_value="9123456789")).status_code, 400)

    def test_send_failure_does_not_leave_usable_challenge(self):
        with patch("accounts.change_verification.send_mail", side_effect=RuntimeError("private SMTP details")):
            response = self.post("change/request-otp", {"purpose": "phone"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.data["message"])
        self.assertTrue(AccountChangeChallenge.objects.get().consumed)

    def test_unauthenticated_requests_are_rejected(self):
        self.client.credentials()
        for endpoint in ("change/request-otp", "change/verify-otp", "change/contact", "change-password"):
            self.assertEqual(self.post(endpoint, {}).status_code, 401)

    def test_invalid_contact_does_not_consume_verification(self):
        token = self.verify("phone")
        payload = dict(purpose="phone", verification_token=token, new_value="not a phone")
        self.assertEqual(self.post("change/contact", payload).status_code, 400)
        self.assertFalse(AccountChangeChallenge.objects.get().consumed)
        payload["new_value"] = "9123456789"
        self.assertEqual(self.post("change/contact", payload).status_code, 200)

    def test_missing_recipient_cannot_send_otp(self):
        self.user.email = ""
        self.user.save(update_fields=["email"])
        self.business.email = ""
        self.business.save()
        self.assertEqual(self.post("change/request-otp", {"purpose": "password"}).status_code, 400)
        self.assertFalse(AccountChangeChallenge.objects.exists())

    def test_initial_email_setup_only_without_any_saved_email(self):
        self.business.email = ""
        self.business.save()
        self.assertEqual(self.client.patch("/api/settings/", {"email": "new@example.com"}, format="json").status_code, 400)
        self.user.email = ""
        self.user.save(update_fields=["email"])
        self.assertEqual(self.client.patch("/api/settings/", {"email": "new@example.com"}, format="json").status_code, 200)
        self.assertEqual(self.client.patch("/api/settings/", {"email": "another@example.com"}, format="json").status_code, 400)
