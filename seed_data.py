"""Create a compact, idempotent insurance demo dataset.

Run from the backend directory:

    python seed_data.py

The script creates or refreshes exactly 18 ``DEMO-INS-*`` policy records. It
never deletes non-seed data. Dates are relative to the run date so status and
dashboard filters remain meaningful when this is executed on another server.
"""

import os
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import transaction
from django.utils import timezone

from customers.models import Customer
from insurance.models import InsuranceCompany, InsuranceRecord
from payments.models import Payment
from vehicles.models import Vehicle


SEED_PREFIX = "DEMO-INS-"
SEED_NOTE = "[DEMO-SEED]"


def month_date(base: date, offset: int, day: int = 12) -> date:
    """Return a safe day in the month ``offset`` months from ``base``."""
    month_index = base.year * 12 + (base.month - 1) + offset
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(day, monthrange(year, month)[1]))


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def policy_specs(today: date):
    """Return 18 policies covering every records and dashboard filter."""
    return [
        # Current / active policies entered in different periods.
        dict(key="01", vehicle="01", company="HDFC ERGO", vehicle_type="Car",
             entry=today, start=today - timedelta(days=90), expiry=today + timedelta(days=275),
             premium=12000, discount=0, payment="paid", label="Current fully-paid policy entered today"),
        dict(key="02", vehicle="02", company="ICICI Lombard", vehicle_type="SUV",
             entry=today - timedelta(days=5), start=today - timedelta(days=365), expiry=today,
             premium=18000, discount=0, payment="partial", label="Policy expiring today"),
        dict(key="03", vehicle="03", company="Bajaj Allianz", vehicle_type="Motorcycle",
             entry=month_date(today, 0, 8), start=today - timedelta(days=362), expiry=today + timedelta(days=3),
             premium=3200, discount=0, payment="unpaid", label="Policy expiring in three days"),
        dict(key="04", vehicle="04", company="Tata AIG", vehicle_type="Commercial",
             entry=month_date(today, -1, 22), start=today - timedelta(days=355), expiry=today + timedelta(days=10),
             premium=28000, discount=1000, payment="paid", label="Policy expiring in ten days with discount"),

        # Unrenewed expired records: these must appear in Needs Renewal.
        dict(key="05", vehicle="05", company="New India Assurance", vehicle_type="Car",
             entry=month_date(today, -1, 10), start=today - timedelta(days=366), expiry=today - timedelta(days=1),
             premium=10500, discount=0, payment="paid", label="Recently expired and needs renewal"),
        dict(key="06", vehicle="06", company="United India Insurance", vehicle_type="Auto Rickshaw",
             entry=month_date(today, -2, 18), start=today - timedelta(days=410), expiry=today - timedelta(days=45),
             premium=7600, discount=0, payment="partial", label="Expired partial-payment policy needing follow-up"),

        # Early renewal pair: old remains current, linked new record is scheduled.
        dict(key="07", vehicle="07", company="HDFC ERGO", vehicle_type="SUV",
             entry=month_date(today, -3, 12), start=today - timedelta(days=335), expiry=today + timedelta(days=30),
             premium=19500, discount=500, payment="paid", label="Current policy with an early renewal"),
        dict(key="08", vehicle="07", company="HDFC ERGO", vehicle_type="SUV",
             entry=today, start=today + timedelta(days=31), expiry=today + timedelta(days=395),
             premium=20500, discount=0, payment="partial", previous="07", label="Scheduled early renewal"),

        # Completed renewal pair: old is history and new policy is current.
        dict(key="09", vehicle="08", company="ICICI Lombard", vehicle_type="Car",
             entry=month_date(today, -2, 5), start=today - timedelta(days=385), expiry=today - timedelta(days=20),
             premium=13000, discount=0, payment="paid", label="Old policy retained as renewed history"),
        dict(key="10", vehicle="08", company="ICICI Lombard", vehicle_type="Car",
             entry=month_date(today, -1, 28), start=today - timedelta(days=19), expiry=today + timedelta(days=345),
             premium=14200, discount=200, payment="paid", previous="09", label="Current policy created by renewal"),

        # A future-start policy created directly, not from renewal.
        dict(key="11", vehicle="09", company="Bajaj Allianz", vehicle_type="Motorcycle",
             entry=today, start=today + timedelta(days=15), expiry=today + timedelta(days=379),
             premium=3800, discount=0, payment="unpaid", label="Standalone scheduled policy"),

        # Dashboard month/payment/company mix.
        dict(key="12", vehicle="10", company="Tata AIG", vehicle_type="Truck",
             entry=month_date(today, -1, 14), start=today - timedelta(days=40), expiry=today + timedelta(days=325),
             premium=36000, discount=0, payment="paid", label="Previous-month paid commercial policy"),
        dict(key="13", vehicle="11", company="New India Assurance", vehicle_type="Car",
             entry=month_date(today, -2, 9), start=today - timedelta(days=75), expiry=today + timedelta(days=290),
             premium=11500, discount=0, payment="partial", label="Two-month-old partial policy"),
        dict(key="14", vehicle="12", company="United India Insurance", vehicle_type="Scooter",
             entry=month_date(today, -3, 20), start=today - timedelta(days=110), expiry=today + timedelta(days=255),
             premium=2900, discount=0, payment="unpaid", label="Three-month-old unpaid policy"),
        dict(key="15", vehicle="13", company="HDFC ERGO", vehicle_type="Commercial",
             entry=month_date(today, -12, 11), start=today - timedelta(days=500), expiry=today - timedelta(days=135),
             premium=42000, discount=2000, payment="paid", label="Previous-year paid policy for yearly filters"),
        dict(key="16", vehicle="14", company="ICICI Lombard", vehicle_type="Car",
             entry=month_date(today, -4, 7), start=today - timedelta(days=145), expiry=today + timedelta(days=220),
             premium=15000, discount=1500, payment="paid", label="Discounted policy for net-premium calculations"),
        dict(key="17", vehicle="15", company="Bajaj Allianz", vehicle_type="Motorcycle",
             entry=month_date(today, -5, 16), start=today - timedelta(days=175), expiry=today + timedelta(days=190),
             premium=4500, discount=0, payment="partial", label="Five-month-old motorcycle policy"),
        dict(key="18", vehicle="16", company="Tata AIG", vehicle_type="Taxi",
             entry=month_date(today, -13, 24), start=today - timedelta(days=760), expiry=today - timedelta(days=395),
             premium=22000, discount=0, payment="unpaid", label="Previous-year expired unpaid policy"),
    ]


@transaction.atomic
def seed():
    today = timezone.localdate()
    specs = policy_specs(today)

    companies = {}
    for name in sorted({spec["company"] for spec in specs}):
        company, _ = InsuranceCompany.objects.get_or_create(
            name=name,
            defaults={"is_active": True},
        )
        companies[name] = company

    # Reset only our own records so reruns can safely rebuild active flags,
    # renewal links, and payments without touching user-entered policies.
    seed_records = InsuranceRecord.objects.filter(policy_number__startswith=SEED_PREFIX)
    conflicts = seed_records.exclude(remarks__startswith=SEED_NOTE)
    if conflicts.exists():
        numbers = ", ".join(conflicts.values_list("policy_number", flat=True))
        raise RuntimeError(
            f"Refusing to overwrite non-seed policies using the reserved prefix: {numbers}"
        )
    seed_records.update(is_active=False, previous_policy=None)
    Payment.objects.filter(insurance_record__policy_number__startswith=SEED_PREFIX).delete()

    vehicles = {}
    for vehicle_key in sorted({spec["vehicle"] for spec in specs}):
        number = f"MH12SD10{int(vehicle_key):02d}"
        phone = f"+91910000{int(vehicle_key):04d}"
        customer_defaults = {
            "name": f"Demo Customer {int(vehicle_key):02d}",
            "alternative_mobile_number": f"+91920000{int(vehicle_key):04d}",
            "email": f"demo.customer{int(vehicle_key):02d}@example.com",
            "address": f"Demo Address {int(vehicle_key):02d}, Pune, Maharashtra",
        }
        customer = Customer.objects.filter(
            phone=phone,
            email=customer_defaults["email"],
        ).first()
        if customer is None:
            customer = Customer.objects.create(phone=phone, **customer_defaults)
        else:
            for field, value in customer_defaults.items():
                setattr(customer, field, value)
            customer.save()

        vehicle_type = next(
            spec["vehicle_type"] for spec in specs if spec["vehicle"] == vehicle_key
        )
        vehicle = Vehicle.objects.filter(vehicle_number=number).first()
        if vehicle is None:
            vehicle = Vehicle.objects.create(
                vehicle_number=number,
                customer=customer,
                vehicle_type=vehicle_type,
            )
        elif vehicle.customer_id != customer.id:
            raise RuntimeError(
                f"Refusing to reuse vehicle {number}; it belongs to a non-seed customer."
            )
        else:
            vehicle.vehicle_type = vehicle_type
            vehicle.save(update_fields=["vehicle_type", "updated_at"])
        vehicles[vehicle_key] = vehicle

    records = {}
    for spec in specs:
        policy_number = f"{SEED_PREFIX}{spec['key']}"
        customer = vehicles[spec["vehicle"]].customer
        previous = records.get(spec.get("previous"))
        is_current = spec["start"] <= today <= spec["expiry"]

        record, _ = InsuranceRecord.objects.update_or_create(
            policy_number=policy_number,
            defaults={
                "customer": customer,
                "vehicle": vehicles[spec["vehicle"]],
                "insurance_company": companies[spec["company"]],
                "entry_date": spec["entry"],
                "policy_start_date": spec["start"],
                "policy_expiry_date": spec["expiry"],
                "total_premium": money(spec["premium"]),
                "discount": money(spec["discount"]),
                "alternative_mobile_number": customer.alternative_mobile_number,
                "remarks": f"{SEED_NOTE} {spec['label']}",
                "previous_policy": previous,
                "is_active": is_current,
            },
        )
        records[spec["key"]] = record

        net_premium = record.total_premium - record.discount
        payment_kind = spec["payment"]
        if payment_kind == "paid":
            amounts = [net_premium]
        elif payment_kind == "partial":
            amounts = [(net_premium * Decimal("0.40")).quantize(Decimal("0.01"))]
        else:
            amounts = []

        for index, amount in enumerate(amounts, start=1):
            Payment.objects.create(
                insurance_record=record,
                amount=amount,
                payment_method=["Cash", "UPI", "Bank Transfer"][int(spec["key"]) % 3],
                payment_date=max(spec["entry"], min(today, spec["start"])),
                notes=f"{SEED_NOTE} Payment {index} for {policy_number}",
            )

    # Explicitly restore the intended two-record renewal states after every
    # record is present. This also makes reruns resilient to older seed runs.
    InsuranceRecord.objects.filter(pk=records["07"].pk).update(is_active=True)
    InsuranceRecord.objects.filter(pk=records["08"].pk).update(
        is_active=False, previous_policy=records["07"]
    )
    InsuranceRecord.objects.filter(pk=records["09"].pk).update(is_active=False)
    InsuranceRecord.objects.filter(pk=records["10"].pk).update(
        is_active=True, previous_policy=records["09"]
    )

    refreshed = list(
        InsuranceRecord.objects.filter(policy_number__startswith=SEED_PREFIX)
        .select_related("previous_policy", "renewed_policy")
        .prefetch_related("payments")
        .order_by("policy_number")
    )
    status_counts = {}
    payment_counts = {}
    for record in refreshed:
        status_counts[record.lifecycle_status] = status_counts.get(record.lifecycle_status, 0) + 1
        payment_counts[record.payment_status] = payment_counts.get(record.payment_status, 0) + 1

    print(f"Seeded {len(refreshed)} insurance records as of {today}.")
    print(f"Lifecycle statuses: {status_counts}")
    print(f"Payment statuses: {payment_counts}")
    print("Policy prefix: DEMO-INS- (safe to rerun; non-seed data is untouched)")


if __name__ == "__main__":
    seed()
