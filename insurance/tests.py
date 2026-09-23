import datetime
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceDocument, InsuranceRecord
from vehicles.models import Vehicle


class InsuranceRecordAPITestCase(APITestCase):
    def setUp(self):
        # Create user & authenticate
        self.user = User.objects.create_user(
            username="agent1", password="password123", email="agent1@example.com"
        )
        self.client.force_authenticate(user=self.user)

        # Create active insurance company
        self.company = InsuranceCompany.objects.create(name="HDFC ERGO General Insurance")

        self.today = timezone.localdate()
        self.next_year = self.today + datetime.timedelta(days=365)
        self.past_date = self.today - datetime.timedelta(days=100)

    def test_create_record_auto_customer_and_vehicle(self):
        """
        Flow:
        Create Record
              ↓
        Customer Created/Found
              ↓
        Vehicle Created/Found
              ↓
        Insurance Record Created
        """
        payload = {
            "policy_number": "POL-2026-001",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "15499.50",
            "remarks": "Comprehensive Cover",
            "insurance_company_id": self.company.id,
            # Customer fields
            "customer_phone": "9876543210",
            "customer_name": "Rajesh Sharma",
            "customer_email": "rajesh@example.com",
            "customer_address": "Pune, Maharashtra",
            # Vehicle fields
            "vehicle_number": "MH 12 AB 1234",
            "vehicle_type": "Four Wheeler",
        }

        response = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["message"], "Insurance record created successfully.")

        record_data = response.data["data"]
        self.assertEqual(record_data["policy_number"], "POL-2026-001")
        self.assertEqual(record_data["status"], "active")

        # Verify Customer created
        customer = Customer.objects.filter(phone="9876543210").first()
        self.assertIsNotNone(customer)
        self.assertEqual(customer.name, "Rajesh Sharma")
        self.assertEqual(record_data["customer"]["id"], customer.id)

        # Verify Vehicle created
        vehicle = Vehicle.objects.filter(vehicle_number="MH12AB1234").first()
        self.assertIsNotNone(vehicle)
        self.assertEqual(vehicle.vehicle_type, "Four Wheeler")
        self.assertEqual(record_data["vehicle"]["id"], vehicle.id)

    def test_create_record_with_existing_customer_and_vehicle(self):
        """Test reusing existing customer and vehicle via IDs."""
        customer = Customer.objects.create(name="Anita Roy", phone="9123456780")
        vehicle = Vehicle.objects.create(
            customer=customer, vehicle_number="MH14CD5678", vehicle_type="Two Wheeler"
        )

        payload = {
            "policy_number": "POL-2026-002",
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "3200.00",
            "insurance_company_id": self.company.id,
            "customer_id": customer.id,
            "vehicle_id": vehicle.id,
        }

        response = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        record_data = response.data["data"]
        self.assertEqual(record_data["customer"]["id"], customer.id)
        self.assertEqual(record_data["vehicle"]["id"], vehicle.id)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Vehicle.objects.count(), 1)

    def test_duplicate_policy_number_is_rejected(self):
        """Duplicate insurance policy numbers should be rejected."""
        customer = Customer.objects.create(name="Aarav Nair", phone="9876500001")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="TN01AA1111")
        InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="DUP-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=12000,
        )

        duplicate_payload = {
            "policy_number": "DUP-001",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "15000.00",
            "insurance_company_id": self.company.id,
            "customer_phone": "9876500002",
            "customer_name": "New Customer",
            "customer_email": "new@example.com",
            "customer_address": "Chennai",
            "vehicle_number": "TN01AA2222",
            "vehicle_type": "Four Wheeler",
        }

        response = self.client.post("/api/insurance/records/", duplicate_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("policy_number", response.data)
        self.assertIn("DUP-001", str(response.data["policy_number"]))
        self.assertIn("Aarav Nair", str(response.data["policy_number"]))

    def test_duplicate_policy_number_case_insensitive_and_whitespace(self):
        """Case-insensitive and whitespace-padded duplicate policy numbers should be rejected."""
        customer = Customer.objects.create(name="Rohit Sharma", phone="9876511111")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH01AA1234")
        InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="POL-CASE-123",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=15000,
        )

        # Attempt to create with lowercase and leading/trailing spaces
        duplicate_payload = {
            "policy_number": "   pol-case-123   ",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "16000.00",
            "insurance_company_id": self.company.id,
            "customer_phone": "9876522222",
            "customer_name": "Another Customer",
            "vehicle_number": "MH01AA5678",
        }

        response = self.client.post("/api/insurance/records/", duplicate_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("policy_number", response.data)
        self.assertTrue(any("already registered" in str(err) for err in response.data["policy_number"]))

    def test_model_level_trim_and_duplicate_validation(self):
        """Model level save() should trim spaces and raise ValidationError on case-insensitive duplicate."""
        from django.core.exceptions import ValidationError

        customer = Customer.objects.create(name="Sunil Gavaskar", phone="9876533333")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH02BB1111")
        record1 = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="   TRIM-POL-999   ",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=5000,
        )
        self.assertEqual(record1.policy_number, "TRIM-POL-999")

        # Second record with case-variant should fail on save
        record2 = InsuranceRecord(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="trim-pol-999",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=6000,
        )
        with self.assertRaises(ValidationError) as ctx:
            record2.save()
        self.assertIn("policy_number", ctx.exception.message_dict)

    def test_check_duplicate_endpoint(self):
        """Test GET /api/insurance/records/check-duplicate/ with existing context."""
        customer = Customer.objects.create(name="Kapil Dev", phone="9876544444")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="DL01XY9999", vehicle_type="SUV")
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="CHECK-DUP-777",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=25000,
        )

        # Check existing (case-insensitive & padded)
        res = self.client.get("/api/insurance/records/check-duplicate/?policy_number=  check-dup-777  ")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_duplicate"])
        self.assertIsNotNone(res.data["record"])
        self.assertEqual(res.data["record"]["id"], record.id)
        self.assertEqual(res.data["record"]["customer"]["name"], "Kapil Dev")
        self.assertEqual(res.data["record"]["vehicle"]["vehicle_number"], "DL01XY9999")
        self.assertEqual(res.data["record"]["policy_expiry_date"], str(self.next_year))

        # Check existing when excluded by ID (edit mode)
        res_exclude = self.client.get(f"/api/insurance/records/check-duplicate/?policy_number=CHECK-DUP-777&exclude_id={record.id}")
        self.assertEqual(res_exclude.status_code, status.HTTP_200_OK)
        self.assertFalse(res_exclude.data["is_duplicate"])
        self.assertIsNone(res_exclude.data["record"])

        # Check non-existent
        res_non = self.client.get("/api/insurance/records/check-duplicate/?policy_number=UNIQUE-POLICY-12345")
        self.assertEqual(res_non.status_code, status.HTTP_200_OK)
        self.assertFalse(res_non.data["is_duplicate"])
        self.assertIsNone(res_non.data["record"])

    def test_list_records_search_and_pagination(self):
        """Test search by policy number, customer, and vehicle with pagination."""
        customer1 = Customer.objects.create(name="Vikram Singh", phone="9988776655")
        vehicle1 = Vehicle.objects.create(customer=customer1, vehicle_number="DL01AA1111")
        InsuranceRecord.objects.create(
            customer=customer1,
            vehicle=vehicle1,
            insurance_company=self.company,
            policy_number="HDFC-POL-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=10000,
        )

        customer2 = Customer.objects.create(name="Sneha Patil", phone="9988776644")
        vehicle2 = Vehicle.objects.create(customer=customer2, vehicle_number="MH12ZZ9999")
        InsuranceRecord.objects.create(
            customer=customer2,
            vehicle=vehicle2,
            insurance_company=self.company,
            policy_number="ICICI-POL-002",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=12000,
        )

        # Search for Vikram
        res_vikram = self.client.get("/api/insurance/records/?search=Vikram")
        self.assertEqual(res_vikram.status_code, status.HTTP_200_OK)
        self.assertEqual(res_vikram.data["count"], 1)
        self.assertEqual(res_vikram.data["results"][0]["policy_number"], "HDFC-POL-001")

        # Search for vehicle number
        res_vehicle = self.client.get("/api/insurance/records/?search=MH12ZZ")
        self.assertEqual(res_vehicle.status_code, status.HTTP_200_OK)
        self.assertEqual(res_vehicle.data["count"], 1)

        # Pagination test: page_size=1
        res_paged = self.client.get("/api/insurance/records/?page_size=1")
        self.assertEqual(res_paged.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_paged.data["results"]), 1)
        self.assertIsNotNone(res_paged.data["next"])

    def test_list_records_filters(self):
        """Test filters by status (active vs expired) and foreign keys."""
        customer = Customer.objects.create(name="Amit Kumar", phone="9898989898")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="KA01BB2222")

        # Active record
        InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="ACT-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=5000,
        )

        # Expired record
        InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="EXP-001",
            policy_start_date=self.past_date,
            policy_expiry_date=self.past_date + datetime.timedelta(days=10),
            total_premium=4500,
        )

        # Status active filter
        res_active = self.client.get("/api/insurance/records/?status=active")
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertEqual(res_active.data["count"], 1)
        self.assertEqual(res_active.data["results"][0]["policy_number"], "ACT-001")

        # Status expired filter
        res_expired = self.client.get("/api/insurance/records/?status=expired")
        self.assertEqual(res_expired.status_code, status.HTTP_200_OK)
        self.assertEqual(res_expired.data["count"], 1)
        self.assertEqual(res_expired.data["results"][0]["policy_number"], "EXP-001")

    def test_record_filters_expiring_soon_and_expiring_today(self):
        """Test filtering by expiring_soon (next 10 days) and expiring_today."""
        customer = Customer.objects.create(name="Exp Test Customer", phone="9988776655")

        v_today = Vehicle.objects.create(customer=customer, vehicle_number="EX-TODAY")
        v_5d = Vehicle.objects.create(customer=customer, vehicle_number="EX-5D")
        v_10d = Vehicle.objects.create(customer=customer, vehicle_number="EX-10D")
        v_11d = Vehicle.objects.create(customer=customer, vehicle_number="EX-11D")
        v_exp = Vehicle.objects.create(customer=customer, vehicle_number="EX-PAST")

        rec_today = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=v_today,
            insurance_company=self.company,
            policy_number="POL-EXP-TODAY",
            policy_start_date=self.today - datetime.timedelta(days=365),
            policy_expiry_date=self.today,
            total_premium=5000,
        )
        rec_5d = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=v_5d,
            insurance_company=self.company,
            policy_number="POL-EXP-5D",
            policy_start_date=self.today - datetime.timedelta(days=360),
            policy_expiry_date=self.today + datetime.timedelta(days=5),
            total_premium=5000,
        )
        rec_10d = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=v_10d,
            insurance_company=self.company,
            policy_number="POL-EXP-10D",
            policy_start_date=self.today - datetime.timedelta(days=355),
            policy_expiry_date=self.today + datetime.timedelta(days=10),
            total_premium=5000,
        )
        rec_11d = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=v_11d,
            insurance_company=self.company,
            policy_number="POL-EXP-11D",
            policy_start_date=self.today - datetime.timedelta(days=354),
            policy_expiry_date=self.today + datetime.timedelta(days=11),
            total_premium=5000,
        )
        rec_past = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=v_exp,
            insurance_company=self.company,
            policy_number="POL-EXP-PAST",
            policy_start_date=self.today - datetime.timedelta(days=366),
            policy_expiry_date=self.today - datetime.timedelta(days=1),
            total_premium=5000,
        )

        # Verify model status property
        self.assertEqual(rec_today.status, "expiring_soon")
        self.assertEqual(rec_5d.status, "expiring_soon")
        self.assertEqual(rec_10d.status, "expiring_soon")
        self.assertEqual(rec_11d.status, "active")
        self.assertEqual(rec_past.status, "expired")

        # Test API: expiring_soon (next 10 days)
        res_soon = self.client.get("/api/insurance/records/?status=expiring_soon")
        self.assertEqual(res_soon.status_code, status.HTTP_200_OK)
        soon_policies = [r["policy_number"] for r in res_soon.data["results"]]
        self.assertIn("POL-EXP-TODAY", soon_policies)
        self.assertIn("POL-EXP-5D", soon_policies)
        self.assertIn("POL-EXP-10D", soon_policies)
        self.assertNotIn("POL-EXP-11D", soon_policies)
        self.assertNotIn("POL-EXP-PAST", soon_policies)

        # Test API: expiring_today
        res_today = self.client.get("/api/insurance/records/?status=expiring_today")
        self.assertEqual(res_today.status_code, status.HTTP_200_OK)
        today_policies = [r["policy_number"] for r in res_today.data["results"]]
        self.assertIn("POL-EXP-TODAY", today_policies)
        self.assertNotIn("POL-EXP-5D", today_policies)
        self.assertNotIn("POL-EXP-10D", today_policies)
        self.assertNotIn("POL-EXP-11D", today_policies)

    def test_record_details(self):
        """Test retrieving insurance record details."""
        customer = Customer.objects.create(name="Rohit Verma", phone="9777777777")
        vehicle = Vehicle.objects.create(
            customer=customer, vehicle_number="UP32CC3333", vehicle_type="Car"
        )
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="DET-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=8000,
        )

        response = self.client.get(f"/api/insurance/records/{record.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["policy_number"], "DET-001")
        self.assertEqual(response.data["customer"]["name"], "Rohit Verma")
        self.assertEqual(response.data["vehicle"]["vehicle_number"], "UP32CC3333")
        self.assertEqual(response.data["insurance_company"]["name"], self.company.name)
        self.assertIn("documents", response.data)

    def test_update_record(self):
        """Test updating an insurance record."""
        customer = Customer.objects.create(name="Pooja Mehta", phone="9666666666")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="GJ01DD4444")
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="UPD-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=6000,
        )

        response = self.client.patch(
            f"/api/insurance/records/{record.id}/",
            {"total_premium": "7500.00", "remarks": "Updated with add-on cover"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["total_premium"], "7500.00")
        self.assertEqual(response.data["data"]["remarks"], "Updated with add-on cover")

        record.refresh_from_db()
        self.assertEqual(record.total_premium, 7500.00)

    def test_delete_record(self):
        """Test deleting an insurance record."""
        customer = Customer.objects.create(name="Kiran Shah", phone="9555555555")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="RJ14EE5555")
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="DEL-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=5000,
        )

        response = self.client.delete(f"/api/insurance/records/{record.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(InsuranceRecord.objects.filter(id=record.id).exists())

    def test_document_upload_and_delete_via_record_endpoints(self):
        """Test upload and delete document under /api/insurance/records/<id>/documents/."""
        customer = Customer.objects.create(name="Manoj Tiwari", phone="9444444444")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="HR26FF6666")
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="DOC-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=9000,
        )

        fake_pdf = SimpleUploadedFile(
            "policy_document.pdf",
            b"%PDF-1.4 sample content",
            content_type="application/pdf",
        )

        # Upload document
        upload_res = self.client.post(
            f"/api/insurance/records/{record.id}/documents/",
            {"file": fake_pdf, "document_name": "Original Policy PDF"},
            format="multipart",
        )
        self.assertEqual(upload_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(upload_res.data["message"], "Document uploaded successfully.")
        doc_id = upload_res.data["data"]["id"]

        # List documents for record
        list_res = self.client.get(f"/api/insurance/records/{record.id}/documents/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.data), 1)
        self.assertEqual(list_res.data[0]["document_name"], "Original Policy PDF")

        # Delete document
        del_res = self.client.delete(
            f"/api/insurance/records/{record.id}/documents/{doc_id}/"
        )
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(InsuranceDocument.objects.filter(id=doc_id).exists())

    def test_direct_documents_viewset(self):
        """Test upload and delete document via direct /api/insurance/documents/ endpoint."""
        customer = Customer.objects.create(name="Deepak Joshi", phone="9333333333")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="PB10GG7777")
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="DOC-002",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=4000,
        )

        fake_pdf = SimpleUploadedFile(
            "rc_book.pdf", b"%PDF-1.4 rc content", content_type="application/pdf"
        )

        upload_res = self.client.post(
            "/api/insurance/documents/",
            {
                "record_id": record.id,
                "file": fake_pdf,
                "document_name": "RC Book Copy",
            },
            format="multipart",
        )
        self.assertEqual(upload_res.status_code, status.HTTP_201_CREATED)
        doc_id = upload_res.data["data"]["id"]

        # Direct delete
        del_res = self.client.delete(f"/api/insurance/documents/{doc_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertFalse(InsuranceDocument.objects.filter(id=doc_id).exists())

    def test_create_record_updates_existing_customer_details_without_duplicate(self):
        """Editing customer name/address with customer_id updates customer in-place without duplicate."""
        existing_cust = Customer.objects.create(
            name="Original Name",
            phone="9876500001",
            address="Original Address",
            email="orig@example.com",
        )
        initial_customer_count = Customer.objects.count()

        payload = {
            "policy_number": "POL-UPDATE-001",
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "5000.00",
            "insurance_company_id": self.company.id,
            "customer_id": existing_cust.id,
            "customer_name": "Updated Name",
            "customer_address": "New Address 123",
            "customer_phone": "9876500001",
            "vehicle_number": "MH01AA1111",
            "vehicle_type": "Car",
        }
        res = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Ensure no duplicate customer was created
        self.assertEqual(Customer.objects.count(), initial_customer_count)
        existing_cust.refresh_from_db()
        self.assertEqual(existing_cust.name, "Updated Name")
        self.assertEqual(existing_cust.address, "New Address 123")

    def test_create_record_new_customer_same_phone_different_person(self):
        """Creating a new customer sharing the same phone creates separate customer with unique customer_id."""
        existing_cust = Customer.objects.create(
            name="Father Doe",
            phone="9876500002",
            address="Family Home",
        )
        initial_count = Customer.objects.count()

        payload = {
            "policy_number": "POL-SHARED-001",
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "6000.00",
            "insurance_company_id": self.company.id,
            "create_new_customer": True,
            "customer_name": "Son Doe",
            "customer_phone": "9876500002",
            "customer_address": "Apartment 4B",
            "vehicle_number": "MH02BB2222",
            "vehicle_type": "Bike",
        }
        res = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Separate customer must be created
        self.assertEqual(Customer.objects.count(), initial_count + 1)
        new_cust = Customer.objects.filter(name="Son Doe").first()
        self.assertIsNotNone(new_cust)
        self.assertNotEqual(new_cust.id, existing_cust.id)
        self.assertEqual(new_cust.phone, existing_cust.phone)
        self.assertEqual(res.data["data"]["customer"]["id"], new_cust.id)

    def test_create_record_fails_if_active_policy_exists_on_vehicle(self):
        """Vehicle number + Active insurance exists: Don't create a new record."""
        customer = Customer.objects.create(name="Ramesh Kumar", phone="9876543200")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH12AB9999", vehicle_type="Car")
        InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="ACT-POL-9999",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=10000,
            is_active=True,
        )

        payload = {
            "policy_number": "NEW-POL-9999",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "12000.00",
            "insurance_company_id": self.company.id,
            "customer_id": customer.id,
            "vehicle_number": "MH12AB9999",
            "vehicle_type": "Car",
        }
        res = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("vehicle_number", res.data)
        self.assertIn("Active policy already exists", str(res.data["vehicle_number"]))

    def test_create_record_succeeds_if_previous_policy_is_expired(self):
        """Vehicle number + Previous insurance is expired: Allow creating new record while keeping old as history."""
        customer = Customer.objects.create(name="Sunil Gupta", phone="9876543201")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH12CD8888", vehicle_type="Car")
        old_record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="OLD-EXP-8888",
            policy_start_date=self.past_date,
            policy_expiry_date=self.past_date + datetime.timedelta(days=10),
            total_premium=8000,
            is_active=False,
        )

        payload = {
            "policy_number": "NEW-ACT-8888",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "14000.00",
            "insurance_company_id": self.company.id,
            "customer_id": customer.id,
            "vehicle_number": "MH12CD8888",
            "vehicle_type": "Car",
        }
        res = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Both records must exist in database
        self.assertEqual(InsuranceRecord.objects.filter(vehicle=vehicle).count(), 2)
        old_record.refresh_from_db()
        self.assertFalse(old_record.is_active)

        new_record = InsuranceRecord.objects.get(policy_number="NEW-ACT-8888")
        self.assertTrue(new_record.is_active)

    def test_database_constraint_one_active_policy_per_vehicle(self):
        """Database constraint enforces only one active policy per vehicle."""
        from django.db import IntegrityError
        customer = Customer.objects.create(name="Anil Kapoor", phone="9876543202")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH12EF7777", vehicle_type="Car")
        InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="ACT-001-7777",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=5000,
            is_active=True,
        )

        # Attempting to save a second active record directly should raise IntegrityError or ValidationError
        with self.assertRaises((IntegrityError, Exception)):
            rec2 = InsuranceRecord(
                customer=customer,
                vehicle=vehicle,
                insurance_company=self.company,
                policy_number="ACT-002-7777",
                policy_start_date=self.today,
                policy_expiry_date=self.next_year,
                total_premium=6000,
                is_active=True,
            )
            rec2.save()

    def test_check_vehicle_endpoint(self):
        """Test GET /api/insurance/records/check-vehicle/ for active, expired, and non-existent vehicles."""
        customer = Customer.objects.create(name="Deepak Joshi", phone="9876543203")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH12GH6666", vehicle_type="SUV")
        record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="POL-CHK-6666",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=15000,
            is_active=True,
        )

        # 1. Active vehicle check
        res_active = self.client.get("/api/insurance/records/check-vehicle/?vehicle_number=MH12GH6666")
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        self.assertTrue(res_active.data["has_active_policy"])
        self.assertEqual(res_active.data["active_record"]["id"], record.id)

        # 2. Exclude by id (edit mode)
        res_exclude = self.client.get(f"/api/insurance/records/check-vehicle/?vehicle_number=MH12GH6666&exclude_id={record.id}")
        self.assertEqual(res_exclude.status_code, status.HTTP_200_OK)
        self.assertFalse(res_exclude.data["has_active_policy"])

        # 3. Non-existent vehicle
        res_none = self.client.get("/api/insurance/records/check-vehicle/?vehicle_number=MH99ZZ0000")
        self.assertEqual(res_none.status_code, status.HTTP_200_OK)
        self.assertFalse(res_none.data["exists"])
        self.assertFalse(res_none.data["has_active_policy"])

    def test_renew_endpoint(self):
        """Test POST /api/insurance/records/<id>/renew/ archives old policy and creates new active policy."""
        customer = Customer.objects.create(name="Kavita Rao", phone="9876543204")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_number="MH12IJ5555", vehicle_type="Car")
        old_record = InsuranceRecord.objects.create(
            customer=customer,
            vehicle=vehicle,
            insurance_company=self.company,
            policy_number="OLD-POL-5555",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=9000,
            is_active=True,
        )

        renew_payload = {
            "policy_number": "RENEW-POL-5555",
            "total_premium": "11000.00",
            "remarks": "Renewed policy with bonus discount",
        }
        res = self.client.post(f"/api/insurance/records/{old_record.id}/renew/", renew_payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["previous_record_id"], old_record.id)

        old_record.refresh_from_db()
        self.assertFalse(old_record.is_active)

        new_rec = InsuranceRecord.objects.get(policy_number="RENEW-POL-5555")
        self.assertTrue(new_rec.is_active)
        self.assertEqual(new_rec.vehicle_id, vehicle.id)
        self.assertEqual(InsuranceRecord.objects.filter(vehicle=vehicle).count(), 2)

        # Vehicle history endpoint check
        hist_res = self.client.get(f"/api/insurance/records/{new_rec.id}/vehicle-history/")
        self.assertEqual(hist_res.status_code, status.HTTP_200_OK)
        self.assertEqual(hist_res.data["total_records"], 2)
