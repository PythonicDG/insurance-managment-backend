import io
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from rest_framework.test import APITestCase

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceRecord
from vehicles.models import Vehicle
from .admin import UploadColumnFormSet
from .models import UploadColumn, UploadReceipt, UploadTemplate
from .schema import validate_columns
from .services import convert


class BulkUploadTests(APITestCase):
    def setUp(self):
        self.upload_bytes = {}
        self.user = User.objects.create_user(username="bulk-agent", password="test-pass")
        self.client.force_authenticate(self.user)
        self.template = UploadTemplate.objects.get(name="Standard Customers")
        self.insurance = UploadTemplate.objects.get(name="Standard Insurance Records")
        self.company = InsuranceCompany.objects.create(name="Example Insurance")

    def file(self, headers, rows):
        # Preview/import bind to exact bytes. Regenerating XLSX can change ZIP
        # timestamps even with identical cells, causing timing-dependent failures.
        key = (tuple(headers), tuple(tuple(row) for row in rows))
        if key not in self.upload_bytes:
            workbook = Workbook()
            workbook.active.append(headers)
            for row in rows:
                workbook.active.append(row)
            stream = io.BytesIO()
            workbook.save(stream)
            self.upload_bytes[key] = stream.getvalue()
        stream = io.BytesIO(self.upload_bytes[key])
        stream.name = "clients.xlsx"
        return stream

    def submit(self, headers, rows, template=None, token=None):
        payload = {"template_id": (template or self.template).pk, "file": self.file(headers, rows)}
        if token:
            payload["preview_token"] = token
        return self.client.post(f'/api/bulk-upload/{"import" if token else "preview"}/', payload, format="multipart")

    def insurance_data(self, policy="POL-1", vehicle="MH12AB1234"):
        today = timezone.localdate()
        return ["Phone", "Vehicle Number", "Insurance Company", "Policy No", "Start Date", "Expiry Date", "Premium"], [
            "9876543210", vehicle, self.company.name, policy, today, today + timedelta(days=365), "1200.00"
        ]

    def test_authentication_and_read_only_configuration_api(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get("/api/bulk-upload/templates/").status_code, [401, 403])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/bulk-upload/templates/").status_code, 200)
        self.assertEqual(self.client.post("/api/bulk-upload/templates/", {"name": "Changed"}).status_code, 405)
        self.assertEqual(self.client.patch(f"/api/bulk-upload/templates/{self.template.pk}/download/", {}).status_code, 405)

    def test_dynamic_header_alias_and_preview_leaves_database_unchanged(self):
        column = self.template.columns.get(field_name="phone")
        column.column_name = "Client Contact"
        column.aliases = "Telephone"
        column.save()
        response = self.submit([" NAME ", "telephone"], [["Alice", 9876543210]])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(Customer.objects.count(), 0)
        imported = self.submit([" NAME ", "telephone"], [["Alice", 9876543210]], token=response.data["preview_token"])
        self.assertEqual(imported.status_code, 200, imported.data)
        self.assertEqual(Customer.objects.get().phone, "9876543210")
        self.assertEqual(UploadReceipt.objects.count(), 1)

    def test_download_follows_admin_columns_and_is_safe_text(self):
        column = self.template.columns.get(field_name="name")
        column.column_name = "=Customer"
        column.save()
        self.template.columns.get(field_name="address").delete()
        response = self.client.get(f"/api/bulk-upload/templates/{self.template.pk}/download/")
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(io.BytesIO(response.content))
        headers = [c.value for c in workbook.active[1]]
        self.assertIn("=Customer", headers)
        self.assertNotIn("Address", headers)
        self.assertEqual(workbook.active["A1"].data_type, "s")
        self.assertEqual(workbook.active["B2"].number_format, "@")

    def test_required_header_and_empty_value_are_rejected(self):
        response = self.submit(["Name"], [["Alice"]])
        self.assertEqual(response.status_code, 400)
        response = self.submit(["Name", "Phone"], [["Alice", None]])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["errors"][0]["row"], 2)
        self.assertEqual(Customer.objects.count(), 0)

    def test_default_value_optional_column_and_unknown_header(self):
        column = self.template.columns.get(field_name="address")
        column.default_value = "Pune"
        column.save()
        preview = self.submit(["Phone", "Unused"], [["0123456789", "ignore"]])
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertTrue(preview.data["warnings"])
        response = self.submit(["Phone", "Unused"], [["0123456789", "ignore"]], token=preview.data["preview_token"])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Customer.objects.get().phone, "0123456789")
        self.assertEqual(Customer.objects.get().address, "Pune")

    def test_duplicate_and_ambiguous_headers(self):
        for headers in (["Phone", " phone "], ["Phone", "Mobile Number"]):
            response = self.submit(headers, [["9876543210", "9876543210"]])
            self.assertEqual(response.status_code, 400)

    def test_formula_and_bad_email_report_actual_excel_rows(self):
        response = self.submit(["Phone", "Email"], [["9876543210", "ok@example.com"], [None, None],
                                                       ["9876543211", "bad-email"], ["=1234567890", ""]])
        self.assertEqual(response.status_code, 400)
        self.assertEqual([e["row"] for e in response.data["errors"]], [4, 5])
        self.assertEqual(Customer.objects.count(), 0)

    def test_existing_customer_is_skipped_without_overwriting(self):
        customer = Customer.objects.create(name="Alice", phone="9876543210", address="Original")
        response = self.submit(["Name", "Phone", "Address"], [["Alice", "9876543210", "Replacement"]])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["skipped"], 1)
        imported = self.submit(["Name", "Phone", "Address"], [["Alice", "9876543210", "Replacement"]], token=response.data["preview_token"])
        self.assertEqual(imported.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.address, "Original")

    def test_import_requires_preview_and_rejects_changed_file_or_config(self):
        headers, rows = ["Phone"], [["9876543210"]]
        missing = self.client.post("/api/bulk-upload/import/", {"template_id": self.template.pk, "file": self.file(headers, rows)}, format="multipart")
        self.assertEqual(missing.status_code, 400)
        preview = self.submit(headers, rows)
        token = preview.data["preview_token"]
        self.assertEqual(self.submit(headers, [["9876543211"]], token=token).status_code, 400)
        column = self.template.columns.get(field_name="name")
        column.column_name = "Client Name"
        column.save()
        self.assertEqual(self.submit(headers, rows, token=token).status_code, 400)
        self.assertEqual(Customer.objects.count(), 0)

    def test_preview_is_user_bound_expires_and_cannot_be_replayed(self):
        headers, rows = ["Phone"], [["9876543210"]]
        preview = self.submit(headers, rows)
        token = preview.data["preview_token"]
        other = User.objects.create_user(username="other")
        self.client.force_authenticate(other)
        self.assertEqual(self.submit(headers, rows, token=token).status_code, 400)
        self.client.force_authenticate(self.user)
        with patch("django.core.signing.time.time", return_value=timezone.now().timestamp() + 1900):
            self.assertEqual(self.submit(headers, rows, token=token).status_code, 400)
        self.assertEqual(self.submit(headers, rows, token=token).status_code, 200)
        self.assertEqual(self.submit(headers, rows, token=token).status_code, 400)
        self.assertEqual(Customer.objects.count(), 1)

    def test_insurance_preview_and_import_reuse_existing_business_rules(self):
        headers, row = self.insurance_data()
        preview = self.submit(headers, [row], template=self.insurance)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(InsuranceRecord.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Vehicle.objects.count(), 0)
        response = self.submit(headers, [row], template=self.insurance, token=preview.data["preview_token"])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(InsuranceRecord.objects.get().policy_number, "POL-1")
        duplicate = self.submit(headers, [row], template=self.insurance)
        self.assertEqual(duplicate.status_code, 400)

    def test_duplicate_policy_within_file_rolls_back_all_related_objects(self):
        headers, row = self.insurance_data()
        response = self.submit(headers, [row, row], template=self.insurance)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["errors"][0]["row"], 3)
        self.assertEqual(InsuranceRecord.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Vehicle.objects.count(), 0)

    def test_changed_database_after_preview_cancels_whole_import(self):
        headers, row = self.insurance_data()
        _, row2 = self.insurance_data("POL-2", "MH12AB1235")
        preview = self.submit(headers, [row, row2], template=self.insurance)
        self.assertEqual(preview.status_code, 200)
        other_preview = self.submit(headers, [row2], template=self.insurance)
        self.assertEqual(self.submit(headers, [row2], template=self.insurance, token=other_preview.data["preview_token"]).status_code, 200)
        response = self.submit(headers, [row, row2], template=self.insurance, token=preview.data["preview_token"])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(InsuranceRecord.objects.count(), 1)
        self.assertFalse(Vehicle.objects.filter(vehicle_number="MH12AB1234").exists())
        self.assertEqual(UploadReceipt.objects.count(), 1)

    def test_unknown_company_and_invalid_dates_are_rejected(self):
        headers, row = self.insurance_data()
        row[2] = "Unknown company"
        self.assertEqual(self.submit(headers, [row], template=self.insurance).status_code, 400)
        row[2] = self.company.name
        row[5] = "2020-01-01"
        self.assertEqual(self.submit(headers, [row], template=self.insurance).status_code, 400)

    def test_multiple_active_policies_for_one_vehicle_are_rejected(self):
        headers, row = self.insurance_data()
        _, second = self.insurance_data("POL-2")
        response = self.submit(headers, [row, second], template=self.insurance)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Active policy already exists", str(response.data["errors"]))
        self.assertEqual(InsuranceRecord.objects.count(), 0)

    def test_conflicting_vehicle_owner_is_rejected_without_mutation(self):
        owner = Customer.objects.create(name="Owner", phone="9876543211")
        vehicle = Vehicle.objects.create(customer=owner, vehicle_number="MH12AB1234", vehicle_type="Car")
        headers, row = self.insurance_data()
        response = self.submit(headers, [row], template=self.insurance)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(InsuranceRecord.objects.count(), 0)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.customer_id, owner.pk)

    def test_file_and_row_limits(self):
        with patch("bulk_upload.services.MAX_ROWS", 1):
            self.assertEqual(self.submit(["Phone"], [["9876543210"], ["9876543211"]]).status_code, 400)
        with patch("bulk_upload.services.MAX_FILE_BYTES", 10):
            self.assertEqual(self.submit(["Phone"], [["9876543210"]]).status_code, 400)
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post("/api/bulk-upload/preview/", {"template_id": self.template.pk,
                                   "file": SimpleUploadedFile("bad.xlsx", b"invalid")}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_admin_rejects_required_removal_and_alias_collisions(self):
        columns = list(self.template.columns.all())
        with self.assertRaises(ValidationError):
            validate_columns("customers", [c for c in columns if c.field_name != "phone"])
        columns[0].aliases = "phone"
        with self.assertRaises(ValidationError):
            validate_columns("customers", columns)

    def test_admin_inline_formset_rejects_required_deletion(self):
        factory = inlineformset_factory(UploadTemplate, UploadColumn, formset=UploadColumnFormSet,
                                       fields=["column_name", "field_name", "aliases", "is_required", "default_value", "position", "is_active"], extra=0)
        columns = list(self.template.columns.all())
        data = {"columns-TOTAL_FORMS": str(len(columns)), "columns-INITIAL_FORMS": str(len(columns))}
        for index, column in enumerate(columns):
            prefix = f"columns-{index}-"
            for key in ["id", "column_name", "field_name", "aliases", "default_value", "position"]:
                data[prefix + key] = str(getattr(column, key))
            data[prefix + "template"] = str(self.template.pk)
            if column.is_required:
                data[prefix + "is_required"] = "on"
            data[prefix + "is_active"] = "on"
            if column.field_name == "phone":
                data[prefix + "DELETE"] = "on"
        formset = factory(data, instance=self.template, prefix="columns")
        self.assertFalse(formset.is_valid())
        self.assertIn("Required mappings", str(formset.non_form_errors()))

    def test_numeric_and_date_conversions(self):
        self.assertEqual(convert(9876543210.0, "text"), "9876543210")
        self.assertEqual(convert("31/12/2026", "date"), "2026-12-31")
        self.assertEqual(convert(1e20, "text"), "100000000000000000000")
        with self.assertRaises(ValueError):
            convert("NaN", "decimal")
