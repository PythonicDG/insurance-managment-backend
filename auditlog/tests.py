from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceRecord
from payments.models import Payment
from settings_app.models import BusinessSettings
from vehicles.models import Vehicle
from whatsapp_integration.models import WhatsAppConfig

from .context import audit_context, current_request
from .models import ActivityLog


class ActivityAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("operator", password="StrongPassword@123")
        self.client = APIClient()
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def entries(self, obj):
        return ActivityLog.objects.filter(object_type=obj._meta.label_lower, object_id=str(obj.pk))

    def test_real_api_token_attribution_and_field_changes(self):
        response = self.client.post("/api/customers/", {"name": "Alice", "phone": "9876543210"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        customer = Customer.objects.get(pk=response.data["id"])
        entry = self.entries(customer).get()
        self.assertEqual(entry.actor_id, str(self.user.pk))
        self.assertEqual(entry.actor_username, "operator")
        self.assertEqual(entry.request_method, "POST")
        self.assertEqual(entry.request_path, "/api/customers/")
        self.assertEqual(entry.changes["name"], {"before": None, "after": "Alice"})
        response = self.client.patch(f"/api/customers/{customer.pk}/", {"name": "Bob"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        entry = self.entries(customer).filter(action="update").get()
        self.assertEqual(entry.changes["name"], {"before": "Alice", "after": "Bob"})
        self.assertNotIn("updated_at", entry.changes)
        self.assertIsNone(current_request.get())

    def test_cookie_auth_login_logout_and_no_heartbeat_noise(self):
        self.client.credentials()
        response = self.client.post("/api/auth/login/", {"username": "operator", "password": "StrongPassword@123"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ActivityLog.objects.filter(action="login", actor_id=str(self.user.pk)).count(), 1)
        self.client.cookies = response.cookies
        response = self.client.post("/api/customers/", {"phone": "1234567890"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ActivityLog.objects.filter(object_type="customers.customer").get().actor_id, str(self.user.pk))
        before = ActivityLog.objects.count()
        self.assertEqual(self.client.post("/api/auth/ping/").status_code, 200)
        self.assertEqual(ActivityLog.objects.count(), before)
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        self.assertEqual(ActivityLog.objects.filter(action="logout").count(), 1)

    def test_failed_and_unauthenticated_writes_are_not_success_events(self):
        before = ActivityLog.objects.count()
        self.assertEqual(self.client.post("/api/customers/", {}, format="json").status_code, 400)
        self.client.credentials()
        self.assertIn(self.client.post("/api/customers/", {"phone": "123"}).status_code, (401, 403))
        self.assertEqual(ActivityLog.objects.count(), before)

    def test_cascade_delete_restore_and_payment_collection(self):
        customer = Customer.objects.create(name="Alice", phone="9876543210")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="GJ01AB1234")
        company = InsuranceCompany.objects.create(name="Insurer")
        today = timezone.localdate()
        record = InsuranceRecord.objects.create(customer=customer, vehicle=vehicle, insurance_company=company,
            policy_number="AUDIT-1", policy_start_date=today, policy_expiry_date=today + timedelta(days=365), total_premium=1000)
        response = self.client.post("/api/payments/", {"insurance_record": record.pk, "amount": "100", "payment_method": "Cash"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        payment = Payment.objects.get(insurance_record=record)
        self.assertEqual(self.entries(payment).get().actor_id, str(self.user.pk))
        self.assertEqual(self.entries(payment).get().changes["amount"]["after"], "100.00")
        # Customers are archived through admin; the customer API has no DELETE.
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        response = self.client.post(reverse("admin:customers_customer_delete", args=[customer.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        deletes = ActivityLog.objects.filter(action="delete")
        self.assertEqual(deletes.count(), 4)
        self.assertEqual(set(deletes.values_list("actor_id", flat=True)), {str(self.user.pk)})
        self.assertEqual(len(set(deletes.values_list("request_id", flat=True))), 1)
        response = self.client.post(reverse("admin:customers_customer_changelist") + "?deletion_status=deleted", {
            "action": "restore_selected", "_selected_action": [str(customer.pk)], "index": "0"
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ActivityLog.objects.filter(action="restore").count(), 4)
        restores = ActivityLog.objects.filter(action="restore")
        self.assertEqual(set(restores.values_list("actor_id", flat=True)), {str(self.user.pk)})
        self.assertEqual(len(set(restores.values_list("request_id", flat=True))), 1)

    def test_queryset_bulk_updates_and_noop_save(self):
        customers = Customer.objects.bulk_create([Customer(phone="111"), Customer(phone="222")])
        self.assertEqual(ActivityLog.objects.filter(action="create").count(), 2)
        Customer.objects.filter(pk__in=[c.pk for c in customers]).update(name="Changed")
        self.assertEqual(ActivityLog.objects.filter(action="update").count(), 2)
        for customer in customers:
            customer.name = "Bulk"
        Customer.objects.bulk_update(customers, ["name"])
        self.assertEqual(ActivityLog.objects.filter(action="update").count(), 4)
        customer = Customer.objects.get(pk=customers[0].pk)
        before = self.entries(customer).count()
        customer.name = "Unsaved"
        customer.save(update_fields=["phone"])
        self.assertEqual(self.entries(customer).count(), before)

    def test_secret_redaction_and_changed_secret_is_logged(self):
        settings = BusinessSettings.objects.create(export_pin="secret-pin", pin_otp="123456")
        config = WhatsAppConfig.objects.create(access_token="secret-token", webhook_verify_token="secret-webhook")
        settings.export_pin = "replacement-pin"
        settings.save()
        import json
        data = json.dumps(list(ActivityLog.objects.values_list("changes", flat=True)))
        for secret in ("secret-pin", "123456", "secret-token", "secret-webhook", "replacement-pin"):
            self.assertNotIn(secret, data)
        self.assertEqual(self.entries(settings).filter(action="update").get().changes["export_pin"]["after"], "[REDACTED]")
        self.assertIn("access_token", self.entries(config).get().changes)

    def test_rollback_and_audit_failure_rollback_business_write(self):
        before = ActivityLog.objects.count()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                Customer.objects.create(phone="rollback")
                raise RuntimeError("rollback")
        self.assertFalse(Customer.objects.filter(phone="rollback").exists())
        self.assertEqual(ActivityLog.objects.count(), before)
        with patch("auditlog.services.record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                Customer.objects.create(phone="failure")
        self.assertFalse(Customer.objects.filter(phone="failure").exists())

    def test_immutable_and_preserves_identity_after_username_change(self):
        response = self.client.post("/api/customers/", {"phone": "9876543210"}, format="json")
        self.assertEqual(response.status_code, 201)
        entry = ActivityLog.objects.get()
        with self.assertRaises(ValidationError):
            entry.save()
        with self.assertRaises(ValidationError):
            entry.delete()
        with self.assertRaises(ValidationError):
            ActivityLog.objects.filter(pk=entry.pk).update(actor_username="forged")
        with self.assertRaises(ValidationError):
            ActivityLog.objects.all().delete()
        self.user.username = "renamed-operator"
        self.user.save()
        entry.refresh_from_db()
        self.assertEqual(entry.actor_username, "operator")

    def test_admin_view_permission_and_readonly_detail(self):
        customer = Customer.objects.create(phone="9876543210")
        entry = self.entries(customer).get()
        url = reverse("admin:auditlog_activitylog_changelist")
        detail = reverse("admin:auditlog_activitylog_change", args=[entry.pk])
        staff = User.objects.create_user("auditor", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url).status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename="view_activitylog"))
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {"actor_username": "forged"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auditlog_activitylog_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:auditlog_activitylog_delete", args=[entry.pk])).status_code, 403)
        self.assertEqual(self.client.get("/api/auditlog/").status_code, 404)

    def test_context_reset_after_exception(self):
        with self.assertRaises(RuntimeError):
            with audit_context(object()):
                raise RuntimeError()
        self.assertIsNone(current_request.get())

    def test_password_change_audits_without_password_and_revokes_token(self):
        from accounts.models import AccountChangeChallenge
        from django.contrib.auth.hashers import make_password
        self.user.email = "operator@example.com"
        self.user.save(update_fields=["email"])
        AccountChangeChallenge.objects.create(
            user=self.user, purpose="password", recipient=self.user.email,
            otp_hash="", token_hash=make_password("verified-test-token"),
            verified=True, expires_at=timezone.now() + timedelta(minutes=10),
        )
        response = self.client.post("/api/auth/change-password/", {
            "verification_token": "verified-test-token", "new_password": "NewStrongPassword@456",
            "confirm_password": "NewStrongPassword@456",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        entry = ActivityLog.objects.get(action="password_change")
        self.assertEqual(entry.actor_id, str(self.user.pk))
        self.assertEqual(entry.changes, {})
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_audit_failure_rolls_back_queryset_update(self):
        customer = Customer.objects.create(phone="123")
        with patch("auditlog.services.record_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                Customer.objects.filter(pk=customer.pk).update(name="Changed")
        customer.refresh_from_db()
        self.assertEqual(customer.name, "")

    def test_matching_insert_between_capture_and_update_is_not_changed_without_audit(self):
        from .services import snapshot
        customer = Customer.objects.create(phone="123")
        inserted = []

        def capture(row):
            if row.pk == customer.pk and not inserted:
                inserted.append(None)
                inserted[0] = Customer.objects.create(phone="456")
            return snapshot(row)

        with patch("auditlog.services.snapshot", side_effect=capture):
            self.assertEqual(Customer.objects.filter(name="").update(name="Changed"), 1)
        inserted[0].refresh_from_db()
        self.assertEqual(inserted[0].name, "")
        self.assertEqual(self.entries(inserted[0]).filter(action="update").count(), 0)


class FriendlyActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("manager", "manager@example.com", "StrongPassword@123")
        self.client = APIClient()
        self.client.force_login(self.user)
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.customer = Customer.objects.create(name="Rahul Patel", phone="9876543210")
        self.vehicle = Vehicle.objects.create(customer=self.customer, vehicle_number="GJ01AB4321")
        self.company = InsuranceCompany.objects.create(name="Example Insurer")
        today = timezone.localdate()
        self.record = InsuranceRecord.objects.create(customer=self.customer, vehicle=self.vehicle,
            insurance_company=self.company, policy_number="POL-SEARCH-123", total_premium=1000,
            policy_start_date=today, policy_expiry_date=today + timedelta(days=365))
        self.list_url = reverse("admin:auditlog_activitylog_changelist")

    def test_customer_keywords_find_related_deleted_payments_and_records(self):
        response = self.client.post("/api/payments/", {"insurance_record": self.record.pk, "amount": "500"}, format="json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0 Safari/537.36",
            REMOTE_ADDR="198.51.100.24", HTTP_X_FORWARDED_FOR="203.0.113.99")
        self.assertEqual(response.status_code, 201, response.data)
        payment_entry = ActivityLog.objects.get(object_type="payments.payment", action="create")
        self.assertIn("Collected payment of Rs 500.00", payment_entry.summary)
        self.assertIn("Rahul Patel", payment_entry.summary)
        self.assertEqual(payment_entry.device, "Chrome on Windows")
        self.assertEqual(payment_entry.ip_address, "198.51.100.24")
        self.client.post(reverse("admin:customers_customer_delete", args=[self.customer.pk]), {"post": "yes"})
        for keyword in ("Rahul Patel", "9876543210", "POL-SEARCH-123", "GJ01AB4321", "manager"):
            response = self.client.get(self.list_url, {"q": keyword})
            self.assertEqual(response.status_code, 200)
            ids = set(response.context["cl"].queryset.values_list("pk", flat=True))
            self.assertIn(payment_entry.pk, ids, keyword)
        response = self.client.get(self.list_url, {"q": "Rahul", "action__exact": "delete"})
        self.assertEqual(response.context["cl"].queryset.count(), 4)
        self.assertContains(response, "Deleted Customer: Rahul Patel")
        self.assertContains(response, "Date and time")
        self.assertContains(response, "Username")
        self.assertContains(response, "Browser / system")
        response = self.client.get(self.list_url, {"q": "198.51.100.24"})
        self.assertIn(payment_entry.pk, response.context["cl"].queryset.values_list("pk", flat=True))

    def test_rename_searches_both_names_and_keeps_historical_related_customer_name(self):
        entry = ActivityLog.objects.get(object_type="insurance.insurancerecord", action="create")
        self.customer.name = "Rahul Shah"
        self.customer.save()
        rename = ActivityLog.objects.get(object_type="customers.customer", action="update")
        for keyword in ("Rahul Patel", "Rahul Shah", "edited Rahul"):
            response = self.client.get(self.list_url, {"q": keyword})
            self.assertIn(rename.pk, response.context["cl"].queryset.values_list("pk", flat=True))
        entry.refresh_from_db()
        self.assertEqual(entry.customer_name, "Rahul Patel")

    def test_summary_search_does_not_expose_secrets(self):
        settings = BusinessSettings.objects.create(business_name="Agency", export_pin="do-not-copy-pin", pin_otp="654321")
        entry = ActivityLog.objects.get(object_type="settings_app.businesssettings", object_id=str(settings.pk))
        self.assertNotIn("do-not-copy-pin", entry.search_text + entry.summary)
        self.assertNotIn("654321", entry.search_text + entry.summary)

    def test_detail_shows_safe_before_after_table_and_local_time(self):
        self.customer.name = '<script>alert("test")</script>'
        self.customer.save()
        entry = ActivityLog.objects.get(object_type="customers.customer", action="update")
        response = self.client.get(reverse("admin:auditlog_activitylog_change", args=[entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<th>Before</th>", html=True)
        self.assertContains(response, "<th>After</th>", html=True)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("test")</script>')
        self.assertContains(response, "IST")

    def test_client_ip_requires_trusted_proxy_and_handles_invalid_values(self):
        from django.test import RequestFactory, override_settings
        from .services import client_ip
        factory = RequestFactory()
        request = factory.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7, 127.0.0.2")
        with override_settings(AUDIT_TRUSTED_PROXY_IPS=[]):
            self.assertEqual(client_ip(request), "127.0.0.1")
        with override_settings(AUDIT_TRUSTED_PROXY_IPS=["127.0.0.1", "127.0.0.2"]):
            self.assertEqual(client_ip(request), "198.51.100.7")
            request.META["HTTP_X_FORWARDED_FOR"] = "invalid-address"
            self.assertEqual(client_ip(request), "127.0.0.1")
        request.META["REMOTE_ADDR"] = "invalid-address"
        self.assertIsNone(client_ip(request))

    def test_legacy_backfill_uses_historical_names(self):
        from importlib import import_module
        from types import SimpleNamespace
        from django.db.migrations.loader import MigrationLoader
        self.customer.name = "Rahul Shah"
        self.customer.save()
        self.customer.delete()
        historical_apps = MigrationLoader(connection).project_state([
            ("auditlog", "0002_alter_activitylog_options_activitylog_customer_name_and_more")
        ]).apps
        migration = import_module("auditlog.migrations.0003_describe_existing_activities")
        migration.describe_existing(historical_apps, SimpleNamespace(connection=connection))
        original = ActivityLog.objects.get(object_type="insurance.insurancerecord", action="create")
        deleted = ActivityLog.objects.get(object_type="insurance.insurancerecord", action="delete")
        self.assertEqual(original.customer_name, "Rahul Patel")
        self.assertEqual(deleted.customer_name, "Rahul Shah")
        self.assertIn("Rahul Shah", deleted.search_text)
