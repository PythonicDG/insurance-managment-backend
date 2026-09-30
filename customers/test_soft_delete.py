from datetime import timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import UserSessionActivity
from bulk_upload.models import UploadReceipt, UploadTemplate
from config.soft_delete import SoftDeleteModel, SoftDeleteQuerySet
from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceDocument, InsuranceRecord
from payments.models import Payment
from payments.views import LedgerViewSet
from vehicles.models import Vehicle
from whatsapp_integration.models import WhatsAppMessageLog


class SoftDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="archive-tests")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.customer = Customer.objects.create(name="Archive Test", phone="9876543210")
        self.vehicle = Vehicle.objects.create(customer=self.customer, vehicle_number="TEST123")
        self.company = InsuranceCompany.objects.create(name="Archive insurer")
        self.record = self.make_record("ORIGINAL")
        self.payment = Payment.objects.create(insurance_record=self.record, amount=Decimal("100"))
        self.log = WhatsAppMessageLog.objects.create(
            customer=self.customer, insurance_record=self.record, payment=self.payment,
            recipient_phone=self.customer.phone,
        )

    def make_record(self, number, **kwargs):
        today = timezone.localdate()
        values = dict(customer=self.customer, vehicle=self.vehicle,
                      insurance_company=self.company, policy_number=number,
                      total_premium=Decimal("1000"), policy_start_date=today,
                      policy_expiry_date=today + timedelta(days=365))
        values.update(kwargs)
        return InsuranceRecord.objects.create(**values)

    def test_every_application_model_supports_soft_delete(self):
        labels = {"accounts", "customers", "vehicles", "insurance", "payments",
                  "settings_app", "whatsapp_integration", "bulk_upload", "dashboard"}
        for model in apps.get_models():
            if model._meta.app_label in labels:
                with self.subTest(model=model._meta.label):
                    self.assertTrue(issubclass(model, SoftDeleteModel))
                    self.assertIsInstance(model._base_manager.all(), SoftDeleteQuerySet)
                    self.assertEqual(model._base_manager.name, "all_objects")

    def test_customer_delete_preserves_history_and_audit_references(self):
        renewal = self.make_record("RENEWAL", previous_policy=self.record,
                                   policy_start_date=self.record.policy_expiry_date + timedelta(days=1),
                                   policy_expiry_date=self.record.policy_expiry_date + timedelta(days=366))
        count, _ = self.customer.delete()
        self.assertEqual(count, 5)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Vehicle.objects.count(), 0)
        self.assertEqual(InsuranceRecord.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        for model, row in [(Customer, self.customer), (Vehicle, self.vehicle),
                           (InsuranceRecord, self.record), (InsuranceRecord, renewal),
                           (Payment, self.payment)]:
            archived = model.all_objects.get(pk=row.pk)
            self.assertIsNotNone(archived.deleted_at)
            self.assertEqual(archived.deletion_batch, self.customer.deletion_batch)
        self.log.refresh_from_db()
        self.assertIsNone(self.log.deleted_at)
        self.assertEqual(self.log.customer_id, self.customer.pk)
        self.assertEqual(self.log.insurance_record_id, self.record.pk)
        self.assertEqual(self.log.payment_id, self.payment.pk)
        self.assertEqual(InsuranceRecord.all_objects.get(pk=renewal.pk).previous_policy_id, self.record.pk)
        self.assertEqual(self.customer.restore(), 5)
        self.assertEqual(InsuranceRecord.objects.count(), 2)
        self.assertEqual(self.record.payments.count(), 1)

    def test_queryset_admin_and_base_manager_deletes_are_soft(self):
        admin.site._registry[Customer].delete_queryset(None, Customer.objects.filter(pk=self.customer.pk))
        self.assertTrue(Customer.all_objects.filter(pk=self.customer.pk).exists())
        self.customer.restore()
        Vehicle._base_manager.filter(pk=self.vehicle.pk).delete()
        self.assertTrue(Vehicle.all_objects.filter(pk=self.vehicle.pk).exists())
        self.assertFalse(InsuranceRecord.objects.exists())

    def test_restore_does_not_revive_earlier_deletes(self):
        self.payment.delete()
        self.customer.delete()
        self.customer.restore()
        self.assertTrue(InsuranceRecord.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertIsNotNone(Payment.all_objects.get(pk=self.payment.pk).deleted_at)

    def test_repeated_deletion_is_idempotent(self):
        self.customer.delete()
        batch = self.customer.deletion_batch
        timestamp = self.customer.deleted_at
        self.assertEqual(self.customer.delete(), (0, {}))
        self.assertEqual(self.customer.deletion_batch, batch)
        self.assertEqual(self.customer.deleted_at, timestamp)

    def test_document_file_survives_delete_and_restore(self):
        with TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=directory):
            document = InsuranceDocument.objects.create(
                record=self.record, file=SimpleUploadedFile("policy.pdf", b"policy contents")
            )
            path = Path(document.file.path)
            document.delete()
            self.assertTrue(path.exists())
            self.assertFalse(InsuranceDocument.objects.exists())
            self.assertEqual(document.restore(), 1)
            self.assertEqual(path.read_bytes(), b"policy contents")
            self.customer.delete()
            self.assertTrue(path.exists())
            self.assertTrue(InsuranceDocument.all_objects.filter(pk=document.pk).exists())

    def test_api_delete_archives_and_hides_record(self):
        response = self.client.delete(f"/api/insurance/records/{self.record.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(InsuranceRecord.all_objects.filter(pk=self.record.pk).exists())
        self.assertEqual(self.client.get(f"/api/insurance/records/{self.record.pk}/").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/insurance/records/{self.record.pk}/").status_code, 404)

    def test_deleted_payments_are_excluded_from_ledger_and_discount_recovers(self):
        Payment.all_objects.filter(pk=self.payment.pk).update(discount=Decimal("50"))
        InsuranceRecord.objects.filter(pk=self.record.pk).update(discount=Decimal("50"))
        Payment.objects.filter(pk=self.payment.pk).delete()
        self.record.refresh_from_db()
        self.assertEqual(self.record.discount, 0)
        self.assertEqual(self.record.total_paid, 0)
        self.assertEqual(LedgerViewSet().get_annotated_queryset().get(pk=self.record.pk).annotated_paid, 0)
        self.payment.restore()
        self.record.refresh_from_db()
        self.assertEqual(self.record.discount, 50)
        self.assertEqual(self.record.total_paid, 100)

    def test_restoring_conflicting_policy_rolls_back_entire_batch(self):
        self.record.delete()
        self.make_record("REPLACEMENT")
        with self.assertRaises(IntegrityError):
            self.record.restore()
        self.assertIsNotNone(InsuranceRecord.all_objects.get(pk=self.record.pk).deleted_at)
        self.assertIsNotNone(Payment.all_objects.get(pk=self.payment.pk).deleted_at)

    def test_restore_requires_parent_from_separate_batch(self):
        self.payment.delete()
        self.record.delete()
        with self.assertRaises(ValidationError):
            self.payment.restore()
        self.record.restore()
        self.payment.restore()
        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())

    def test_audit_log_can_be_archived_without_erasing_links(self):
        self.log.delete()
        self.assertFalse(WhatsAppMessageLog.objects.exists())
        self.assertEqual(WhatsAppMessageLog.all_objects.get(pk=self.log.pk).payment_id, self.payment.pk)
        self.log.restore()
        self.assertTrue(WhatsAppMessageLog.objects.exists())

    def test_protected_template_can_archive_without_erasing_receipt(self):
        template = UploadTemplate.objects.create(name="Archive template", target="customers")
        receipt = UploadReceipt.objects.create(token_hash="test-token", template=template, user=self.user)
        template.delete()
        self.assertTrue(UploadReceipt.objects.filter(pk=receipt.pk).exists())
        self.assertEqual(receipt.template.pk, template.pk)

    def test_session_reuse_and_user_deletion_protection(self):
        activity = UserSessionActivity.objects.create(user=self.user)
        activity.delete()
        restored, created = UserSessionActivity.all_objects.update_or_create(
            user=self.user, defaults={"deleted_at": None, "deletion_batch": None}
        )
        self.assertFalse(created)
        self.assertEqual(restored.pk, activity.pk)
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_recovery_command(self):
        self.customer.delete()
        output = StringIO()
        call_command("restore_record", "customers.Customer", self.customer.pk, stdout=output)
        self.assertIn("Restored 4 record(s)", output.getvalue())
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def test_company_summary_excludes_archived_payments_without_multiplying_premium(self):
        Payment.objects.create(insurance_record=self.record, amount=Decimal("200"))
        self.payment.delete()
        response = self.client.get("/api/dashboard/summary/?period=all_time")
        self.assertEqual(response.status_code, 200)
        company = next(c for c in response.data["company_wise_summary"]
                       if c["company_id"] == self.company.pk)
        self.assertEqual(company["total_premium"], 1000)
        self.assertEqual(company["premium_collected"], 200)
        self.record.delete()
        response = self.client.get("/api/dashboard/summary/?period=all_time")
        self.assertEqual(response.data["company_wise_summary"], [])

    def test_archived_unique_identifier_returns_api_validation_error(self):
        self.company.delete()
        response = self.client.post("/api/insurance/companies/", {"name": self.company.name})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InsuranceCompany.all_objects.count(), 1)

    def test_admin_confirmation_keeps_protected_receipts(self):
        template = UploadTemplate.objects.create(name="Admin archive template", target="customers")
        UploadReceipt.objects.create(token_hash="admin-token", template=template, user=self.user)
        request = RequestFactory().get("/")
        self.user.is_superuser = True
        request.user = self.user
        _, counts, permissions, protected = admin.site._registry[UploadTemplate].get_deleted_objects(
            [template], request
        )
        self.assertEqual(sum(counts.values()), 1)
        self.assertEqual(permissions, set())
        self.assertEqual(protected, [])

    def test_restoring_overpaid_payment_rolls_back(self):
        self.payment.delete()
        Payment.objects.create(insurance_record=self.record, amount=Decimal("950"))
        with self.assertRaises(ValidationError):
            self.payment.restore()
        self.assertIsNotNone(Payment.all_objects.get(pk=self.payment.pk).deleted_at)

    def login_admin(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)

    def test_admin_deleted_and_all_filters(self):
        self.login_admin()
        active = Customer.objects.create(name="Live customer", phone="9999999999")
        self.customer.delete()
        url = "/admin/customers/customer/"
        for suffix, expected in [("", {active.pk}), ("?deletion_status=active", {active.pk}),
                                 ("?deletion_status=deleted", {self.customer.pk}),
                                 ("?deletion_status=all", {active.pk, self.customer.pk})]:
            with self.subTest(filter=suffix):
                response = self.client.get(url + suffix)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(set(response.context["cl"].queryset.values_list("pk", flat=True)), expected)
                self.assertContains(response, "deletion_status")

    def test_admin_deleted_detail_is_read_only(self):
        self.login_admin()
        self.customer.delete()
        url = f"/admin/customers/customer/{self.customer.pk}/change/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_change_permission"])
        self.assertFalse(response.context["has_delete_permission"])
        self.assertEqual(self.client.post(url, {"name": "Changed"}).status_code, 403)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.name, "Archive Test")

    def test_admin_restore_action_restores_related_records(self):
        self.login_admin()
        self.customer.delete()
        response = self.client.post("/admin/customers/customer/?deletion_status=deleted", {
            "action": "restore_selected", "_selected_action": [str(self.customer.pk)], "index": "0",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restored 4 record(s)")
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(Payment.objects.filter(pk=self.payment.pk).exists())

    def test_admin_restore_conflict_is_reported_without_partial_recovery(self):
        self.login_admin()
        self.record.delete()
        self.make_record("CONFLICTING-CURRENT")
        response = self.client.post("/admin/insurance/insurancerecord/?deletion_status=deleted", {
            "action": "restore_selected", "_selected_action": [str(self.record.pk)], "index": "0",
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "conflicts with existing records")
        self.assertIsNotNone(InsuranceRecord.all_objects.get(pk=self.record.pk).deleted_at)
        self.assertIsNotNone(Payment.all_objects.get(pk=self.payment.pk).deleted_at)

    def test_admin_restore_action_requires_superuser(self):
        self.user.is_staff = True
        self.user.save()
        self.user.user_permissions.add(Permission.objects.get(codename="change_customer"))
        self.client.force_login(self.user)
        self.customer.delete()
        response = self.client.get("/admin/customers/customer/?deletion_status=deleted")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("restore_selected", response.context["cl"].model_admin.get_actions(response.wsgi_request))
        self.assertTrue(response.context["cl"].queryset.filter(pk=self.customer.pk).exists())
