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
        response = self.client.get(f"/api/customers/{self.customer1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["name"], "John Doe")
        self.assertEqual(data["vehicles_count"], 1)
        self.assertIn("vehicles", data)
        self.assertEqual(len(data["vehicles"]), 1)
        self.assertEqual(data["vehicles"][0]["vehicle_number"], "MH12AB1234")

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
        response = self.client.get(f"/api/customers/{self.customer1.id}/vehicles/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        vehicles = response.json()
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["vehicle_number"], "MH12AB1234")

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
