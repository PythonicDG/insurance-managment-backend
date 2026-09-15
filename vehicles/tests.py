from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from customers.models import Customer
from .models import Vehicle


class VehicleAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.customer1 = Customer.objects.create(
            name="Alice Walker",
            phone="9876543211",
        )
        self.customer2 = Customer.objects.create(
            name="Bob Martin",
            phone="9123456789",
        )

        self.vehicle1 = Vehicle.objects.create(
            customer=self.customer1,
            vehicle_type="Four Wheeler",
            vehicle_number="MH12CD5678",
        )
        self.vehicle2 = Vehicle.objects.create(
            customer=self.customer1,
            vehicle_type="Two Wheeler",
            vehicle_number="MH12EF9012",
        )
        self.vehicle3 = Vehicle.objects.create(
            customer=self.customer2,
            vehicle_type="Commercial",
            vehicle_number="DL01XY3456",
        )

    def test_vehicle_flow_helper_get_or_create(self):
        # Existing vehicle returns existing record
        veh, created = Vehicle.get_or_create_vehicle(
            customer=self.customer1,
            vehicle_number="mh12cd5678",  # lowercase will be normalized
            vehicle_type="Four Wheeler",
        )
        self.assertFalse(created)
        self.assertEqual(veh.id, self.vehicle1.id)

        # New vehicle creates record
        veh2, created2 = Vehicle.get_or_create_vehicle(
            customer=self.customer2,
            vehicle_number="MH 14 ZZ 9999",
            vehicle_type="Two Wheeler",
        )
        self.assertTrue(created2)
        self.assertEqual(veh2.vehicle_number, "MH14ZZ9999")
        self.assertEqual(veh2.customer.id, self.customer2.id)

    def test_get_customer_vehicles_by_query_param(self):
        # Customer 1 has 2 vehicles
        response = self.client.get(f"/api/vehicles/?customer_id={self.customer1.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        results = data if isinstance(data, list) else data.get("results", [])
        self.assertEqual(len(results), 2)

        # Customer 2 has 1 vehicle
        response2 = self.client.get(f"/api/vehicles/?customer_id={self.customer2.id}")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        data2 = response2.json()
        results2 = data2 if isinstance(data2, list) else data2.get("results", [])
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]["vehicle_number"], "DL01XY3456")

    def test_get_customer_vehicles_by_action_url(self):
        response = self.client.get(f"/api/vehicles/customer/{self.customer1.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 2)

    def test_vehicle_update(self):
        response = self.client.patch(
            f"/api/vehicles/{self.vehicle1.id}/",
            data={"vehicle_type": "SUV"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.vehicle1.refresh_from_db()
        self.assertEqual(self.vehicle1.vehicle_type, "SUV")

    def test_vehicle_delete(self):
        response = self.client.delete(f"/api/vehicles/{self.vehicle1.id}/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Vehicle.objects.filter(id=self.vehicle1.id).exists())

    def test_manual_vehicle_create_is_disabled(self):
        # Direct POST creation should return 405 Method Not Allowed
        response = self.client.post(
            "/api/vehicles/",
            data={
                "customer": self.customer1.id,
                "vehicle_number": "KA01AB1111",
                "vehicle_type": "Car",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
