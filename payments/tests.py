from decimal import Decimal
import datetime
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceRecord
from payments.models import Payment
from vehicles.models import Vehicle


class PaymentTransactionHistoryTestCase(APITestCase):
    def setUp(self):
        # Create user & authenticate
        self.user = User.objects.create_user(
            username="testagent", password="password123", email="agent@example.com"
        )
        self.client.force_authenticate(user=self.user)

        # Create active insurance company
        self.company = InsuranceCompany.objects.create(name="TATA AIG General Insurance")

        self.today = timezone.localdate()
        self.next_year = self.today + datetime.timedelta(days=365)

        # Create test customer and vehicle
        self.customer = Customer.objects.create(
            name="Rahul Varma",
            phone="9876543210",
            email="rahul@example.com",
            address="Mumbai, Maharashtra",
        )
        self.vehicle = Vehicle.objects.create(
            customer=self.customer,
            vehicle_number="MH01AB9999",
            vehicle_type="SUV",
        )

    def test_payment_model_structure_and_fields(self):
        """
        Store every payment separately with:
        insurance_record, amount, payment_method, payment_date, notes, created_at.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-TEST-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("15000.00"),
        )

        payment = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("5000.00"),
            payment_method="UPI",
            payment_date=self.today,
            notes="First instalment paid via GPay",
        )

        self.assertEqual(payment.insurance_record.id, record.id)
        self.assertEqual(payment.amount, Decimal("5000.00"))
        self.assertEqual(payment.payment_method, "UPI")
        self.assertEqual(payment.payment_date, self.today)
        self.assertEqual(payment.notes, "First instalment paid via GPay")
        self.assertIsNotNone(payment.created_at)

        # Check related_name 'payments'
        self.assertEqual(record.payments.count(), 1)
        self.assertEqual(record.payments.first().id, payment.id)

    def test_total_paid_outstanding_and_status_calculation(self):
        """
        Calculate total_paid = SUM(Payment.amount) and outstanding = total_premium - total_paid.
        Automatically determine status: UNPAID, PARTIAL, PAID.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-STATUS-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("10000.00"),
        )

        # Stage 1: Zero payments -> UNPAID
        self.assertEqual(record.total_paid, Decimal("0.00"))
        self.assertEqual(record.outstanding, Decimal("10000.00"))
        self.assertEqual(record.payment_status, "UNPAID")
        self.assertEqual(record.get_payment_status(), "UNPAID")

        # Stage 2: Partial payment -> PARTIAL
        p1 = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("4000.00"),
            payment_method="Bank Transfer",
            payment_date=self.today,
            notes="Partial payment 1",
        )
        self.assertEqual(record.total_paid, Decimal("4000.00"))
        self.assertEqual(record.outstanding, Decimal("6000.00"))
        self.assertEqual(record.payment_status, "PARTIAL")

        # Stage 3: Second partial payment -> still PARTIAL
        p2 = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("3000.00"),
            payment_method="Cash",
            payment_date=self.today,
            notes="Partial payment 2",
        )
        self.assertEqual(record.total_paid, Decimal("7000.00"))
        self.assertEqual(record.outstanding, Decimal("3000.00"))
        self.assertEqual(record.payment_status, "PARTIAL")

        # Stage 4: Final payment clearing outstanding -> PAID
        p3 = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("3000.00"),
            payment_method="UPI",
            payment_date=self.today,
            notes="Final settlement",
        )
        self.assertEqual(record.total_paid, Decimal("10000.00"))
        self.assertEqual(record.outstanding, Decimal("0.00"))
        self.assertEqual(record.payment_status, "PAID")

    def test_initial_payment_stored_as_normal_payment_on_record_creation(self):
        """
        Initial payment must also be stored as a normal Payment linked to that specific insurance record.
        """
        payload = {
            "policy_number": "POL-INIT-PAY-001",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "12500.00",
            "insurance_company_id": self.company.id,
            "customer_phone": "9876543210",
            "vehicle_number": "MH01AB9999",
            # Initial payment fields
            "initial_payment": "4500.00",
            "initial_payment_method": "UPI",
            "initial_payment_notes": "Initial downpayment at booking",
        }

        response = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        record_id = response.data["data"]["id"]

        record = InsuranceRecord.objects.get(pk=record_id)
        # Verify a normal Payment row exists in database
        self.assertEqual(Payment.objects.filter(insurance_record=record).count(), 1)
        initial_pay = Payment.objects.get(insurance_record=record)
        self.assertEqual(initial_pay.amount, Decimal("4500.00"))
        self.assertEqual(initial_pay.payment_method, "UPI")
        self.assertEqual(initial_pay.notes, "Initial downpayment at booking")

        # Verify calculations on record
        self.assertEqual(record.total_paid, Decimal("4500.00"))
        self.assertEqual(record.outstanding, Decimal("8000.00"))
        self.assertEqual(record.payment_status, "PARTIAL")

        # Verify returned detail payload contains payment info
        self.assertEqual(response.data["data"]["total_paid"], "4500.00")
        self.assertEqual(response.data["data"]["outstanding"], "8000.00")
        self.assertEqual(response.data["data"]["payment_status"], "PARTIAL")

    def test_payment_history_fetched_using_insurance_record_id_never_customer_phone(self):
        """
        Payment history must always be fetched using insurance_record_id, never customer phone/customer_id.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-FETCH-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("8000.00"),
        )
        Payment.objects.create(
            insurance_record=record,
            amount=Decimal("3000.00"),
            payment_method="Cash",
            payment_date=self.today,
            notes="Cash payment",
        )

        # 1. Fetching via insurance_record_id succeeds
        res_valid = self.client.get(f"/api/payments/?insurance_record_id={record.id}")
        self.assertEqual(res_valid.status_code, status.HTTP_200_OK)
        results = res_valid.data if isinstance(res_valid.data, list) else res_valid.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(Decimal(str(results[0]["amount"])), Decimal("3000.00"))

        # 2. Fetching via record-specific nested endpoint succeeds
        res_nested = self.client.get(f"/api/insurance/records/{record.id}/payments/")
        self.assertEqual(res_nested.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_nested.data), 1)

        # 3. Attempting to fetch by customer phone or customer_id without insurance_record_id is rejected
        res_phone = self.client.get(f"/api/payments/?phone={self.customer.phone}")
        self.assertEqual(res_phone.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("insurance_record_id", str(res_phone.data))

        res_cust_id = self.client.get(f"/api/payments/?customer_id={self.customer.id}")
        self.assertEqual(res_cust_id.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("insurance_record_id", str(res_cust_id.data))

    def test_cascade_delete_removes_all_payments_when_record_is_deleted(self):
        """
        When an InsuranceRecord is deleted, all its payments must be deleted automatically.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-DEL-PAY-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("9000.00"),
        )
        p1 = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("4000.00"),
            payment_method="UPI",
            payment_date=self.today,
        )
        p2 = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("5000.00"),
            payment_method="Cash",
            payment_date=self.today,
        )
        self.assertEqual(Payment.objects.filter(insurance_record_id=record.id).count(), 2)

        # Delete insurance record via API
        del_response = self.client.delete(f"/api/insurance/records/{record.id}/")
        self.assertEqual(del_response.status_code, status.HTTP_200_OK)

        # Verify record is deleted
        self.assertFalse(InsuranceRecord.objects.filter(id=record.id).exists())
        # Verify all associated payments were cascaded and deleted automatically
        self.assertFalse(Payment.objects.filter(id__in=[p1.id, p2.id]).exists())
        self.assertEqual(Payment.objects.filter(insurance_record_id=record.id).count(), 0)

    def test_exact_case_create_record_add_initial_payment_delete_record_create_new_record_same_phone(self):
        """
        Exact test required:
        create record → add initial payment → delete record → create new record with same phone
        → verify the new record has zero old payments.
        """
        shared_phone = "9988771122"

        # Step 1: Create record with initial payment
        create_payload = {
            "policy_number": "POL-FLOW-001",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "20000.00",
            "insurance_company_id": self.company.id,
            "customer_name": "Suresh Raina",
            "customer_phone": shared_phone,
            "vehicle_number": "UP14ZZ1234",
            "initial_payment": "7500.00",
            "initial_payment_method": "UPI",
            "initial_payment_notes": "First policy advance",
        }

        r1_response = self.client.post("/api/insurance/records/", create_payload, format="json")
        self.assertEqual(r1_response.status_code, status.HTTP_201_CREATED)
        r1_id = r1_response.data["data"]["id"]
        r1 = InsuranceRecord.objects.get(pk=r1_id)

        # Step 2: Verify initial payment exists on record 1
        self.assertEqual(r1.payments.count(), 1)
        self.assertEqual(r1.total_paid, Decimal("7500.00"))
        self.assertEqual(r1.outstanding, Decimal("12500.00"))
        self.assertEqual(r1.payment_status, "PARTIAL")

        old_payment_id = r1.payments.first().id
        self.assertTrue(Payment.objects.filter(pk=old_payment_id).exists())

        # Step 3: Delete record 1
        del_res = self.client.delete(f"/api/insurance/records/{r1_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)

        self.assertFalse(InsuranceRecord.objects.filter(pk=r1_id).exists())
        self.assertFalse(Payment.objects.filter(pk=old_payment_id).exists())

        # Step 4: Create new record with the SAME phone number
        r2_payload = {
            "policy_number": "POL-FLOW-002",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "16000.00",
            "insurance_company_id": self.company.id,
            "customer_name": "Suresh Raina",
            "customer_phone": shared_phone,
            "vehicle_number": "UP14ZZ5678",
            # No initial payment on new record
        }

        r2_response = self.client.post("/api/insurance/records/", r2_payload, format="json")
        self.assertEqual(r2_response.status_code, status.HTTP_201_CREATED)
        r2_id = r2_response.data["data"]["id"]
        r2 = InsuranceRecord.objects.get(pk=r2_id)

        # Step 5: Verify the new record has ZERO old payments!
        self.assertEqual(r2.payments.count(), 0)
        self.assertEqual(r2.total_paid, Decimal("0.00"))
        self.assertEqual(r2.outstanding, Decimal("16000.00"))
        self.assertEqual(r2.payment_status, "UNPAID")

        # Verify via API endpoint
        history_res = self.client.get(f"/api/payments/?insurance_record_id={r2_id}")
        self.assertEqual(history_res.status_code, status.HTTP_200_OK)
        history_data = history_res.data if isinstance(history_res.data, list) else history_res.data.get("results", [])
        self.assertEqual(len(history_data), 0)

        record_detail_res = self.client.get(f"/api/insurance/records/{r2_id}/")
        self.assertEqual(record_detail_res.status_code, status.HTTP_200_OK)
        self.assertEqual(record_detail_res.data["total_paid"], "0.00")
        self.assertEqual(record_detail_res.data["outstanding"], "16000.00")
        self.assertEqual(record_detail_res.data["payment_status"], "UNPAID")
        self.assertEqual(len(record_detail_res.data["payments"]), 0)

    def test_add_payment_via_api_and_recalculate_outstanding(self):
        """
        Test adding payment to an existing record via API and verify recalculation.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-ADD-PAY-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("10000.00"),
        )

        # POST /api/insurance/records/<id>/payments/
        pay_res = self.client.post(
            f"/api/insurance/records/{record.id}/payments/",
            {
                "amount": "6000.00",
                "payment_method": "Net Banking",
                "notes": "First tranche",
            },
            format="json",
        )
        self.assertEqual(pay_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(pay_res.data["total_paid"], "6000.00")
        self.assertEqual(pay_res.data["outstanding"], "4000.00")
        self.assertEqual(pay_res.data["payment_status"], "PARTIAL")

        # POST second payment via direct /api/payments/ endpoint
        pay2_res = self.client.post(
            "/api/payments/",
            {
                "insurance_record_id": record.id,
                "amount": "4000.00",
                "payment_method": "UPI",
                "notes": "Second tranche - settled",
            },
            format="json",
        )
        self.assertEqual(pay2_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(pay2_res.data["total_paid"], "10000.00")
        self.assertEqual(pay2_res.data["outstanding"], "0.00")
        self.assertEqual(pay2_res.data["payment_status"], "PAID")

        # Verify summary endpoint
        summary_res = self.client.get(f"/api/payments/history/?insurance_record_id={record.id}")
        self.assertEqual(summary_res.status_code, status.HTTP_200_OK)
        self.assertEqual(summary_res.data["total_paid"], "10000.00")
        self.assertEqual(summary_res.data["outstanding"], "0.00")
        self.assertEqual(summary_res.data["status"], "PAID")
        self.assertEqual(len(summary_res.data["payments"]), 2)

    def test_delete_individual_payment_recalculates_status(self):
        """
        Deleting a payment adjusts total_paid and reverts payment_status.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-REVERT-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("5000.00"),
        )
        pay = Payment.objects.create(
            insurance_record=record,
            amount=Decimal("5000.00"),
            payment_method="Cash",
            payment_date=self.today,
        )
        self.assertEqual(record.payment_status, "PAID")

        # Delete payment via /api/insurance/records/<id>/payments/<payment_id>/
        del_res = self.client.delete(f"/api/insurance/records/{record.id}/payments/{pay.id}/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)

        record.refresh_from_db()
        self.assertEqual(record.total_paid, Decimal("0.00"))
        self.assertEqual(record.outstanding, Decimal("5000.00"))
        self.assertEqual(record.payment_status, "UNPAID")

    def test_multiple_active_records_same_customer_never_share_payments(self):
        """
        Verify that when a customer has two separate records, payments made on record 1
        never leak, carry over, or show up on record 2.
        """
        # Record 1
        r1 = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-MULTI-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("12000.00"),
        )
        Payment.objects.create(
            insurance_record=r1,
            amount=Decimal("12000.00"),
            payment_method="UPI",
            payment_date=self.today,
        )
        self.assertEqual(r1.total_paid, Decimal("12000.00"))
        self.assertEqual(r1.outstanding, Decimal("0.00"))
        self.assertEqual(r1.payment_status, "PAID")

        # Record 2 for the same customer
        r2 = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-MULTI-002",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("15000.00"),
        )
        self.assertEqual(r2.payments.count(), 0)
        self.assertEqual(r2.total_paid, Decimal("0.00"))
        self.assertEqual(r2.outstanding, Decimal("15000.00"))
        self.assertEqual(r2.payment_status, "UNPAID")

        # Verify through payments API
        res_r2 = self.client.get(f"/api/payments/?insurance_record_id={r2.id}")
        self.assertEqual(res_r2.status_code, status.HTTP_200_OK)
        results = res_r2.data if isinstance(res_r2.data, list) else res_r2.data.get("results", [])
        self.assertEqual(len(results), 0)

        # Verify Record 1 still retains its payments
        res_r1 = self.client.get(f"/api/payments/?insurance_record_id={r1.id}")
        self.assertEqual(res_r1.status_code, status.HTTP_200_OK)
        results_r1 = res_r1.data if isinstance(res_r1.data, list) else res_r1.data.get("results", [])
        self.assertEqual(len(results_r1), 1)

    def test_initial_payment_as_nested_dict(self):
        """
        Test initial_payment passed as a dictionary with amount, method, date, notes.
        """
        payload = {
            "policy_number": "POL-DICT-PAY-001",
            "entry_date": str(self.today),
            "policy_start_date": str(self.today),
            "policy_expiry_date": str(self.next_year),
            "total_premium": "8000.00",
            "insurance_company_id": self.company.id,
            "customer_phone": "9876543210",
            "vehicle_number": "MH01AB9999",
            "initial_payment": {
                "amount": "8000.00",
                "payment_method": "Cheque",
                "payment_date": str(self.today),
                "notes": "Full premium via cheque #123456",
            },
        }

        res = self.client.post("/api/insurance/records/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        rec_id = res.data["data"]["id"]

        rec = InsuranceRecord.objects.get(pk=rec_id)
        self.assertEqual(rec.payments.count(), 1)
        self.assertEqual(rec.total_paid, Decimal("8000.00"))
        self.assertEqual(rec.outstanding, Decimal("0.00"))
        self.assertEqual(rec.payment_status, "PAID")
        self.assertEqual(rec.payments.first().payment_method, "Cheque")

    def test_payment_amount_validation(self):
        """
        Zero or negative payment amounts must be rejected.
        """
        record = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-VAL-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("5000.00"),
        )

        # Zero amount
        res_zero = self.client.post(
            "/api/payments/",
            {"insurance_record_id": record.id, "amount": "0.00"},
            format="json",
        )
        self.assertEqual(res_zero.status_code, status.HTTP_400_BAD_REQUEST)

        # Negative amount
        res_neg = self.client.post(
            "/api/payments/",
            {"insurance_record_id": record.id, "amount": "-500.00"},
            format="json",
        )
        self.assertEqual(res_neg.status_code, status.HTTP_400_BAD_REQUEST)

    def test_payment_status_filtering_on_records(self):
        """
        Test filtering insurance records by payment_status (PAID, PARTIAL, UNPAID).
        """
        # Unpaid
        r_unpaid = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-FILTER-UNPAID",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("10000.00"),
        )

        # Partial
        r_partial = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-FILTER-PARTIAL",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("10000.00"),
        )
        Payment.objects.create(
            insurance_record=r_partial,
            amount=Decimal("5000.00"),
            payment_method="Cash",
            payment_date=self.today,
        )

        # Paid
        r_paid = InsuranceRecord.objects.create(
            customer=self.customer,
            vehicle=self.vehicle,
            insurance_company=self.company,
            policy_number="POL-FILTER-PAID",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("10000.00"),
        )
        Payment.objects.create(
            insurance_record=r_paid,
            amount=Decimal("10000.00"),
            payment_method="UPI",
            payment_date=self.today,
        )

        # Query UNPAID
        res_u = self.client.get("/api/insurance/records/?payment_status=UNPAID")
        self.assertEqual(res_u.status_code, status.HTTP_200_OK)
        policies_u = [item["policy_number"] for item in res_u.data.get("results", [])]
        self.assertIn("POL-FILTER-UNPAID", policies_u)
        self.assertNotIn("POL-FILTER-PARTIAL", policies_u)
        self.assertNotIn("POL-FILTER-PAID", policies_u)

        # Query PARTIAL
        res_p = self.client.get("/api/insurance/records/?payment_status=PARTIAL")
        self.assertEqual(res_p.status_code, status.HTTP_200_OK)
        policies_p = [item["policy_number"] for item in res_p.data.get("results", [])]
        self.assertIn("POL-FILTER-PARTIAL", policies_p)
        self.assertNotIn("POL-FILTER-UNPAID", policies_p)
        self.assertNotIn("POL-FILTER-PAID", policies_p)

        # Query PAID
        res_f = self.client.get("/api/insurance/records/?payment_status=PAID")
        self.assertEqual(res_f.status_code, status.HTTP_200_OK)
        policies_f = [item["policy_number"] for item in res_f.data.get("results", [])]
        self.assertIn("POL-FILTER-PAID", policies_f)
        self.assertNotIn("POL-FILTER-UNPAID", policies_f)
        self.assertNotIn("POL-FILTER-PARTIAL", policies_f)


class LedgerApiTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ledger_tester", password="password123", email="ledger@example.com"
        )
        self.client.force_authenticate(user=self.user)

        self.company1 = InsuranceCompany.objects.create(name="HDFC ERGO")
        self.company2 = InsuranceCompany.objects.create(name="ICICI Lombard")

        self.today = timezone.localdate()
        self.next_year = self.today + datetime.timedelta(days=365)

        self.c1 = Customer.objects.create(name="Rajesh Kumar", phone="9876543210")
        self.v1 = Vehicle.objects.create(customer=self.c1, vehicle_number="MH12AB4821")

        self.c2 = Customer.objects.create(name="Priya Sharma", phone="9820477126")
        self.v2 = Vehicle.objects.create(customer=self.c2, vehicle_number="MH14KT9032")

        self.c3 = Customer.objects.create(name="Amit Patel", phone="9898021456")
        self.v3 = Vehicle.objects.create(customer=self.c3, vehicle_number="GJ01RK7319")

        # Record 1: Rajesh - HDFC - 1,28,500 total, 18,500 paid -> 1,10,000 outstanding (Partial)
        self.r1 = InsuranceRecord.objects.create(
            customer=self.c1,
            vehicle=self.v1,
            insurance_company=self.company1,
            policy_number="POL-LEDGER-001",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("128500.00"),
            entry_date=self.today,
        )
        Payment.objects.create(
            insurance_record=self.r1,
            amount=Decimal("18500.00"),
            payment_method="UPI",
            payment_date=self.today,
            notes="Initial token payment",
        )

        # Record 2: Priya - ICICI - 92,400 total, 0 paid -> 92,400 outstanding (Outstanding)
        self.r2 = InsuranceRecord.objects.create(
            customer=self.c2,
            vehicle=self.v2,
            insurance_company=self.company2,
            policy_number="POL-LEDGER-002",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("92400.00"),
            entry_date=self.today,
        )

        # Record 3: Amit - HDFC - 50,000 total, 50,000 paid -> 0 outstanding (Paid)
        self.r3 = InsuranceRecord.objects.create(
            customer=self.c3,
            vehicle=self.v3,
            insurance_company=self.company1,
            policy_number="POL-LEDGER-003",
            policy_start_date=self.today,
            policy_expiry_date=self.next_year,
            total_premium=Decimal("50000.00"),
            entry_date=self.today,
        )
        Payment.objects.create(
            insurance_record=self.r3,
            amount=Decimal("50000.00"),
            payment_method="Net Banking",
            payment_date=self.today,
            notes="Full premium payment",
        )

    def test_ledger_list_and_kpis(self):
        """Verify GET /api/payments/ledger/ returns KPI summary and pending records by default."""
        res = self.client.get("/api/payments/ledger/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        summary = res.data.get("summary", {})
        # Total premium across records = 128500 + 92400 + 50000 = 270900
        self.assertEqual(summary.get("total_premium"), 270900.0)
        # Total received = 18500 + 50000 = 68500
        self.assertEqual(summary.get("total_received"), 68500.0)
        # Total outstanding = 110000 + 92400 = 202400
        self.assertEqual(summary.get("total_outstanding"), 202400.0)
        # Pending customers = Rajesh and Priya = 2
        self.assertEqual(summary.get("total_customers_pending"), 2)

        results = res.data.get("results", [])
        # Default payment_status is 'outstanding_partial', so Paid record should be excluded from results
        self.assertEqual(len(results), 2)
        policy_numbers = [item["policy_number"] for item in results]
        self.assertIn("POL-LEDGER-001", policy_numbers)
        self.assertIn("POL-LEDGER-002", policy_numbers)
        self.assertNotIn("POL-LEDGER-003", policy_numbers)

        # Check fields on record
        r1_data = next(item for item in results if item["policy_number"] == "POL-LEDGER-001")
        self.assertEqual(r1_data["customer_name"], "Rajesh Kumar")
        self.assertEqual(r1_data["vehicle_number"], "MH12AB4821")
        self.assertEqual(r1_data["insurance_company_name"], "HDFC ERGO")
        self.assertEqual(float(r1_data["paid_amount"]), 18500.0)
        self.assertEqual(float(r1_data["outstanding"]), 110000.0)
        self.assertEqual(r1_data["status"], "Partial")

    def test_ledger_search_filter(self):
        """Verify search by customer name, phone, or vehicle number."""
        res = self.client.get("/api/payments/ledger/?search=Priya")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["policy_number"], "POL-LEDGER-002")

        res2 = self.client.get("/api/payments/ledger/?search=MH12")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        results2 = res2.data.get("results", [])
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]["policy_number"], "POL-LEDGER-001")

    def test_ledger_payment_status_filter(self):
        """Verify filtering by payment status choices."""
        # Query ALL statuses
        res_all = self.client.get("/api/payments/ledger/?payment_status=all")
        self.assertEqual(res_all.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_all.data.get("results", [])), 3)

        # Query Outstanding (Unpaid) only
        res_out = self.client.get("/api/payments/ledger/?payment_status=outstanding")
        self.assertEqual(res_out.status_code, status.HTTP_200_OK)
        results_out = res_out.data.get("results", [])
        self.assertEqual(len(results_out), 1)
        self.assertEqual(results_out[0]["policy_number"], "POL-LEDGER-002")

        # Query Partial only
        res_part = self.client.get("/api/payments/ledger/?payment_status=partial")
        self.assertEqual(res_part.status_code, status.HTTP_200_OK)
        results_part = res_part.data.get("results", [])
        self.assertEqual(len(results_part), 1)
        self.assertEqual(results_part[0]["policy_number"], "POL-LEDGER-001")

        # Query Paid only
        res_paid = self.client.get("/api/payments/ledger/?payment_status=paid")
        self.assertEqual(res_paid.status_code, status.HTTP_200_OK)
        results_paid = res_paid.data.get("results", [])
        self.assertEqual(len(results_paid), 1)
        self.assertEqual(results_paid[0]["policy_number"], "POL-LEDGER-003")

    def test_ledger_company_filter(self):
        """Verify filtering by insurance company."""
        res = self.client.get(f"/api/payments/ledger/?insurance_company_id={self.company2.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["policy_number"], "POL-LEDGER-002")

    def test_ledger_summary_endpoint(self):
        """Verify GET /api/payments/ledger/summary/."""
        res = self.client.get("/api/payments/ledger/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data.get("total_premium"), 270900.0)
        self.assertEqual(res.data.get("total_received"), 68500.0)
        self.assertEqual(res.data.get("total_outstanding"), 202400.0)
        self.assertEqual(res.data.get("total_customers_pending"), 2)

    def test_ledger_retrieve_detail_endpoint(self):
        """Verify GET /api/payments/ledger/<id>/ returns record + payment history."""
        res = self.client.get(f"/api/payments/ledger/{self.r1.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["policy_number"], "POL-LEDGER-001")
        self.assertIn("payments", res.data)
        self.assertEqual(len(res.data["payments"]), 1)
        self.assertEqual(float(res.data["payments"][0]["amount"]), 18500.0)

