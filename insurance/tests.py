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
