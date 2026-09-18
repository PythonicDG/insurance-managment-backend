from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Customer
from vehicles.models import Vehicle


class CustomerAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.customer1 = Customer.objects.create(
            name="John Doe",
            phone="9876543210",
            email="john@example.com",
            address="123 Main St",
        )
        self.customer2 = Customer.objects.create(
            name="Jane Smith",
            phone="9123456780",
            email="jane@example.com",
            address="456 Elm St",
        )

        self.vehicle1 = Vehicle.objects.create(
            customer=self.customer1,
            vehicle_type="Four Wheeler",
            vehicle_number="MH12AB1234",
        )

    def test_customer_flow_helper_get_or_create(self):
        # Existing customer by phone
        cust, created = Customer.get_or_create_by_phone("9876543210")
        self.assertFalse(created)
        self.assertEqual(cust.id, self.customer1.id)

        # New customer by phone
        cust2, created2 = Customer.get_or_create_by_phone(
            "9998887776", name="Alice Wonderland"
        )
        self.assertTrue(created2)
        self.assertEqual(cust2.phone, "9998887776")
        self.assertEqual(cust2.name, "Alice Wonderland")

    def test_customer_list(self):
        response = self.client.get("/api/customers/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return both customers
        data = response.json()
        results = data if isinstance(data, list) else data.get("results", [])
        self.assertEqual(len(results), 2)

    def test_customer_search(self):
        # Search by name
        response = self.client.get("/api/customers/?search=Jane")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data if isinstance(data, list) else data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["phone"], "9123456780")

        # Search by phone
        response2 = self.client.get("/api/customers/?search=98765")
        data2 = response2.json()
        results2 = data2 if isinstance(data2, list) else data2.get("results", [])
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]["name"], "John Doe")

    def test_customer_details(self):
        from insurance.models import InsuranceCompany, InsuranceRecord, InsuranceDocument
        from payments.models import Payment
        from django.utils import timezone

        company = InsuranceCompany.objects.create(name="HDFC ERGO")
        record = InsuranceRecord.objects.create(
            customer=self.customer1,
            vehicle=self.vehicle1,
            insurance_company=company,
            policy_number="POL-TEST-001",
            policy_start_date=timezone.localdate(),
            policy_expiry_date=timezone.localdate() + timezone.timedelta(days=365),
            total_premium=10000.00,
        )
        Payment.objects.create(
            insurance_record=record,
            amount=4000.00,
            payment_method="Cash",
        )
        InsuranceDocument.objects.create(
            record=record,
            document_name="PolicyDoc.pdf",
        )

        response = self.client.get(f"/api/customers/{self.customer1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["name"], "John Doe")
        self.assertEqual(data["vehicles_count"], 1)
        self.assertEqual(data["total_records"], 1)
        self.assertEqual(float(data["total_premium"]), 10000.00)
        self.assertEqual(float(data["total_paid"]), 4000.00)
        self.assertEqual(float(data["total_outstanding"]), 6000.00)
        self.assertIn("vehicles", data)
        self.assertEqual(len(data["vehicles"]), 1)
        self.assertEqual(data["vehicles"][0]["vehicle_number"], "MH12AB1234")
        self.assertEqual(data["vehicles"][0]["records_count"], 1)

    def test_customer_records_action(self):
        from insurance.models import InsuranceCompany, InsuranceRecord
        from django.utils import timezone

        company = InsuranceCompany.objects.create(name="Bajaj Allianz")
        record = InsuranceRecord.objects.create(
            customer=self.customer1,
            vehicle=self.vehicle1,
            insurance_company=company,
            policy_number="POL-TEST-002",
            policy_start_date=timezone.localdate(),
            policy_expiry_date=timezone.localdate() + timezone.timedelta(days=365),
            total_premium=15000.00,
        )

        response = self.client.get(f"/api/customers/{self.customer1.id}/records/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        records = response.json()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["policy_number"], "POL-TEST-002")
        self.assertEqual(records[0]["insurance_company"]["name"], "Bajaj Allianz")

    def test_customer_documents_action(self):
        from insurance.models import InsuranceCompany, InsuranceRecord, InsuranceDocument
        from django.utils import timezone

        company = InsuranceCompany.objects.create(name="Tata AIG")
        record = InsuranceRecord.objects.create(
            customer=self.customer1,
            vehicle=self.vehicle1,
            insurance_company=company,
            policy_number="POL-TEST-003",
            policy_start_date=timezone.localdate(),
            policy_expiry_date=timezone.localdate() + timezone.timedelta(days=365),
            total_premium=20000.00,
        )
        InsuranceDocument.objects.create(
            record=record,
            document_name="VehicleRC.pdf",
        )

        response = self.client.get(f"/api/customers/{self.customer1.id}/documents/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        docs = response.json()
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["document_name"], "VehicleRC.pdf")
        self.assertEqual(docs[0]["policy_number"], "POL-TEST-003")
        self.assertEqual(docs[0]["vehicle_number"], "MH12AB1234")
        self.assertEqual(docs[0]["company_name"], "Tata AIG")

    def test_customer_update_patch(self):
        update_data = {
            "name": "Johnathan Doe",
            "address": "789 New St",
        }
        response = self.client.patch(
            f"/api/customers/{self.customer1.id}/",
            data=update_data,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.customer1.refresh_from_db()
        self.assertEqual(self.customer1.name, "Johnathan Doe")
        self.assertEqual(self.customer1.address, "789 New St")

    def test_customer_vehicles_action(self):
        from insurance.models import InsuranceCompany, InsuranceRecord
        from django.utils import timezone

        company = InsuranceCompany.objects.create(name="ICICI Lombard")
        InsuranceRecord.objects.create(
            customer=self.customer1,
            vehicle=self.vehicle1,
            insurance_company=company,
            policy_number="POL-TEST-004",
            policy_start_date=timezone.localdate(),
            policy_expiry_date=timezone.localdate() + timezone.timedelta(days=365),
            total_premium=5000.00,
        )

        response = self.client.get(f"/api/customers/{self.customer1.id}/vehicles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vehicles = response.json()
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["vehicle_number"], "MH12AB1234")
        self.assertEqual(vehicles[0]["records_count"], 1)

    def test_customer_create_post(self):
        # Direct POST creation should succeed and normalize phone
        response = self.client.post(
            "/api/customers/",
            data={
                "name": "New Customer",
                "phone": "+91 98765-11122",
                "email": "new@example.com",
                "address": "Some Street",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["name"], "New Customer")
        self.assertEqual(data["phone"], "+919876511122")
        self.assertIn("customer_id", data)
        self.assertEqual(data["customer_id"], data["id"])

    def test_lookup_by_normalized_phone(self):
        # Lookup using formatted phone number matching customer1 (9876543210)
        response = self.client.get("/api/customers/lookup/?phone=98765-43210")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["count"], 1)
        self.assertIsNotNone(data["customer"])
        self.assertEqual(data["customer"]["id"], self.customer1.id)
        self.assertEqual(data["customer"]["customer_id"], self.customer1.id)
        self.assertEqual(data["customer"]["name"], "John Doe")

    def test_multiple_customers_share_phone_number(self):
        # Multiple customers can share the same phone number
        customer_shared = Customer.objects.create(
            name="Brother Doe",
            phone="9876543210",
            email="brother@example.com",
            address="Same House, 123 Main St",
        )
        # Verify both have different customer_ids
        self.assertNotEqual(self.customer1.id, customer_shared.id)
        self.assertEqual(self.customer1.phone, customer_shared.phone)

        # Lookup returns both customers
        response = self.client.get("/api/customers/lookup/?phone=+91-9876543210")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["count"], 2)
        ids = [c["id"] for c in data["customers"]]
        self.assertIn(self.customer1.id, ids)
        self.assertIn(customer_shared.id, ids)

    def test_lookup_not_found(self):
        response = self.client.get("/api/customers/lookup/?phone=9999999999")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertFalse(data["found"])
        self.assertEqual(data["count"], 0)
        self.assertIsNone(data["customer"])
