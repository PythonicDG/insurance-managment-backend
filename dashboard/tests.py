from decimal import Decimal
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceRecord
from payments.models import Payment
from vehicles.models import Vehicle

User = get_user_model()


class DashboardSummaryApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="testpassword123",
        )
        self.token = Token.objects.create(user=self.user)
        self.url = reverse("dashboard-summary")

        # Create Company
        self.company1 = InsuranceCompany.objects.create(name="HDFC ERGO", is_active=True)
        self.company2 = InsuranceCompany.objects.create(name="ICICI Lombard", is_active=True)

        # Create Customer & Vehicle
        self.customer = Customer.objects.create(
            name="Rajesh Kumar", phone="9876543210", email="rajesh@test.com"
        )
        self.vehicle1 = Vehicle.objects.create(
            customer=self.customer, vehicle_number="MH-12-AB-1234", vehicle_type="Car"
        )
        self.vehicle2 = Vehicle.objects.create(
            customer=self.customer, vehicle_number="DL-08-CD-5678", vehicle_type="Bike"
        )

        today = timezone.localdate()

        # Record 1: Paid in full
        self.rec1 = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle1,
            insurance_company=self.company1,
            policy_number="POL-1001",
            entry_date=today,
            policy_start_date=today,
            policy_expiry_date=today + timezone.timedelta(days=365),
            total_premium=Decimal("12500.00"),
        )
        Payment.objects.create(
            insurance_record=self.rec1,
            amount=Decimal("12500.00"),
            payment_date=today,
            payment_method="Cash",
        )

        # Record 2: Partial payment
        self.rec2 = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle2,
            insurance_company=self.company2,
            policy_number="POL-1002",
            entry_date=today,
            policy_start_date=today,
            policy_expiry_date=today + timezone.timedelta(days=365),
            total_premium=Decimal("8200.00"),
        )
        Payment.objects.create(
            insurance_record=self.rec2,
            amount=Decimal("4000.00"),
            payment_date=today,
            payment_method="Online",
        )

        # Record 3: Completely outstanding (no payments)
        self.rec3 = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle1,
            insurance_company=self.company1,
            policy_number="POL-1003",
            entry_date=today,
            policy_start_date=today,
            policy_expiry_date=today + timezone.timedelta(days=365),
            total_premium=Decimal("15000.00"),
        )

    def test_unauthenticated_access_denied(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_dashboard_summary_success(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data

        # Verify response structure
        self.assertIn("kpis", data)
        self.assertIn("business_summary", data)
        self.assertIn("payment_status_summary", data)
        self.assertIn("company_wise_summary", data)
        self.assertIn("recent_records", data)

        # Verify KPIs
        kpis = data["kpis"]
        self.assertTrue(kpis["is_all_time"])
        self.assertEqual(kpis["today_entries"], 3)
        # Total premium today = 12500 + 8200 + 15000 = 35700
        self.assertEqual(kpis["today_premium"], 35700.0)
        # Total received today = 12500 + 4000 = 16500
        self.assertEqual(kpis["today_received"], 16500.0)
        # Total outstanding = 35700 - 16500 = 19200
        self.assertEqual(kpis["total_outstanding"], 19200.0)
        self.assertEqual(kpis["total_policies"], 3)

        # Verify Payment Status Summary (1 Paid, 1 Partial, 1 Outstanding)
        status_summary = data["payment_status_summary"]
        self.assertEqual(status_summary["total_policies"], 3)
        self.assertEqual(status_summary["paid"]["count"], 1)
        self.assertEqual(status_summary["partial"]["count"], 1)
        self.assertEqual(status_summary["outstanding"]["count"], 1)

        # Verify Company Wise Summary
        companies = data["company_wise_summary"]
        self.assertTrue(len(companies) >= 2)
        company_names = [c["company_name"] for c in companies]
        self.assertIn("HDFC ERGO", company_names)
        self.assertIn("ICICI Lombard", company_names)

        # Verify Recent Records
        recent = data["recent_records"]
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0]["policy_number"], "POL-1003")

    def test_dashboard_summary_default_is_all_time(self):
        """
        Verify that requests without date parameters include records from all dates
        by default rather than only today's records.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        past_date = timezone.localdate() - timezone.timedelta(days=10)
        # Create a record in the past
        rec_past = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle1,
            insurance_company=self.company1,
            policy_number="POL-PAST-1",
            entry_date=past_date,
            policy_start_date=past_date,
            policy_expiry_date=past_date + timezone.timedelta(days=365),
            total_premium=Decimal("5000.00"),
        )
        Payment.objects.create(
            insurance_record=rec_past,
            amount=Decimal("5000.00"),
            payment_date=past_date,
            payment_method="Cash",
        )

        # Request without any date params
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kpis = response.data["kpis"]
        self.assertTrue(kpis["is_all_time"])
        # Should include all 4 records (3 from today + 1 from past)
        self.assertEqual(kpis["today_entries"], 4)
        self.assertEqual(kpis["today_premium"], 40700.0)
        self.assertEqual(kpis["today_received"], 21500.0)

    def test_dashboard_summary_date_filtering(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        today = timezone.localdate()
        yesterday = today - timezone.timedelta(days=1)

        # Filter for yesterday (should have 0 entries)
        response = self.client.get(self.url, {"start_date": str(yesterday), "end_date": str(yesterday)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        kpis = response.data["kpis"]
        self.assertEqual(kpis["today_entries"], 0)
        self.assertEqual(kpis["today_premium"], 0.0)
        self.assertEqual(kpis["today_received"], 0.0)
        self.assertEqual(kpis["total_outstanding"], 0.0)

        # Filter for today (should have 3 entries)
        response_today = self.client.get(self.url, {"start_date": str(today), "end_date": str(today)})
        self.assertEqual(response_today.status_code, status.HTTP_200_OK)
        kpis_today = response_today.data["kpis"]
        self.assertEqual(kpis_today["today_entries"], 3)
        self.assertEqual(kpis_today["today_premium"], 35700.0)
        self.assertEqual(kpis_today["today_received"], 16500.0)
        self.assertEqual(kpis_today["total_outstanding"], 19200.0)

    def test_business_summary_fixed_6_months_with_12_month_date_filter(self):
        """
        Ensure that applying a 12-month date filter at the top does NOT cause
        business_summary to return 12 items. It must strictly return 6 items.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        response = self.client.get(self.url, {"start_date": "2024-01-01", "end_date": "2024-12-31"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["business_summary"]), 6)

    def test_dashboard_business_summary_endpoint(self):
        """
        Test the dedicated DashboardBusinessSummaryView endpoint.
        """
        url = reverse("dashboard-business-summary")
        # Unauthorized access
        res_unauth = self.client.get(url)
        self.assertEqual(res_unauth.status_code, status.HTTP_401_UNAUTHORIZED)

        # Authenticated access defaults to 6 months
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res_auth = self.client.get(url)
        self.assertEqual(res_auth.status_code, status.HTTP_200_OK)
        self.assertIn("business_summary", res_auth.data)
        self.assertEqual(len(res_auth.data["business_summary"]), 6)

        # Query explicit 6-month window
        res_custom = self.client.get(url, {"start_month": "2024-01", "end_month": "2024-06"})
        self.assertEqual(res_custom.status_code, status.HTTP_200_OK)
        custom_summary = res_custom.data["business_summary"]
        self.assertEqual(len(custom_summary), 6)
        expected_keys = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
        self.assertEqual([item["month_key"] for item in custom_summary], expected_keys)

