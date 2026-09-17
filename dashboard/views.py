from calendar import monthrange
from datetime import date
from decimal import Decimal
from django.db.models import (
    Case,
    Count,
    DecimalField,
    F,
    Q,
    Sum,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from insurance.models import InsuranceCompany, InsuranceRecord
from payments.models import Payment


class DashboardSummaryView(APIView):
    """
    High-performance dashboard summary API.
    Computes all KPI stats, monthly business trend, payment status donut breakdown,
    insurance company-wise premium distribution, and recent records using optimized
    database aggregations in minimal database trips.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        today = timezone.localdate()
        try:
            months_count = int(request.query_params.get("months", 6))
        except (ValueError, TypeError):
            months_count = 6
        months_count = max(1, min(months_count, 24))

        # ---------------------------------------------------------------------
        # 1. Top KPI Metrics
        # ---------------------------------------------------------------------
        today_entries = InsuranceRecord.objects.filter(entry_date=today).count()

        today_premium_aggr = InsuranceRecord.objects.filter(entry_date=today).aggregate(
            total=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField())
        )
        today_premium = float(today_premium_aggr["total"] or Decimal("0.00"))

        today_received_aggr = Payment.objects.filter(payment_date=today).aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )
        today_received = float(today_received_aggr["total"] or Decimal("0.00"))

        all_premium_aggr = InsuranceRecord.objects.aggregate(
            total=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField())
        )
        all_premium = all_premium_aggr["total"] or Decimal("0.00")

        all_received_aggr = Payment.objects.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )
        all_received = all_received_aggr["total"] or Decimal("0.00")

        total_outstanding_dec = max(Decimal("0.00"), all_premium - all_received)
        total_outstanding = float(total_outstanding_dec)

        total_policies = InsuranceRecord.objects.count()

        kpis = {
            "today_entries": today_entries,
            "today_premium": today_premium,
            "today_received": today_received,
            "total_outstanding": total_outstanding,
            "total_policies": total_policies,
            "total_premium": float(all_premium),
            "total_received": float(all_received),
        }

        # ---------------------------------------------------------------------
        # 2. Business Summary (Monthly trend for last N months)
        # ---------------------------------------------------------------------
        month_slots = []
        cur_year = today.year
        cur_month = today.month

        for i in range(months_count - 1, -1, -1):
            target_year = cur_year
            target_month = cur_month - i
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            _, last_day = monthrange(target_year, target_month)
            month_slots.append({
                "year": target_year,
                "month": target_month,
                "start": date(target_year, target_month, 1),
                "end": date(target_year, target_month, last_day),
                "month_name": date(target_year, target_month, 1).strftime("%b"),
                "month_key": f"{target_year}-{target_month:02d}",
            })

        range_start = month_slots[0]["start"]
        range_end = month_slots[-1]["end"]

        # Aggregate payments in range by month
        payments_in_range = (
            Payment.objects.filter(payment_date__gte=range_start, payment_date__lte=range_end)
            .values("payment_date")
            .annotate(total_amount=Sum("amount"))
        )

        payments_by_month_key = {}
        for p in payments_in_range:
            p_date = p["payment_date"]
            key = f"{p_date.year}-{p_date.month:02d}"
            payments_by_month_key[key] = (
                payments_by_month_key.get(key, Decimal("0.00")) + (p["total_amount"] or Decimal("0.00"))
            )

        # Aggregate records in range with their paid sum
        records_in_range = (
            InsuranceRecord.objects.filter(entry_date__gte=range_start, entry_date__lte=range_end)
            .annotate(
                paid_total=Coalesce(Sum("payments__amount"), Decimal("0.00"), output_field=DecimalField())
            )
            .values("entry_date", "total_premium", "paid_total")
        )

        records_by_month_key = {}
        for r in records_in_range:
            e_date = r["entry_date"]
            key = f"{e_date.year}-{e_date.month:02d}"
            if key not in records_by_month_key:
                records_by_month_key[key] = {
                    "premium": Decimal("0.00"),
                    "outstanding": Decimal("0.00"),
                }
            prem = r["total_premium"] or Decimal("0.00")
            paid = r["paid_total"] or Decimal("0.00")
            out = max(Decimal("0.00"), prem - paid)
            records_by_month_key[key]["premium"] += prem
            records_by_month_key[key]["outstanding"] += out

        business_summary = []
        for slot in month_slots:
            k = slot["month_key"]
            collected = float(payments_by_month_key.get(k, Decimal("0.00")))
            outstanding = float(records_by_month_key.get(k, {}).get("outstanding", Decimal("0.00")))
            business_summary.append({
                "month": slot["month_name"],
                "year": slot["year"],
                "month_key": k,
                "premium_collected": collected,
                "outstanding": outstanding,
            })

        # ---------------------------------------------------------------------
        # 3. Payment Status Summary (Donut Chart: Paid, Partial, Outstanding)
        # ---------------------------------------------------------------------
        records_with_payments = InsuranceRecord.objects.annotate(
            paid_sum=Coalesce(Sum("payments__amount"), Decimal("0.00"), output_field=DecimalField())
        )

        status_aggr = records_with_payments.aggregate(
            paid_count=Count(Case(When(paid_sum__gte=F("total_premium"), total_premium__gt=0, then=1))),
            partial_count=Count(
                Case(When(Q(paid_sum__gt=0) & Q(paid_sum__lt=F("total_premium")), then=1))
            ),
            outstanding_count=Count(
                Case(When(Q(paid_sum__lte=0) | Q(total_premium__lte=0, paid_sum__lte=0), then=1))
            ),
            paid_amount=Coalesce(
                Sum(Case(When(paid_sum__gte=F("total_premium"), then=F("total_premium")), default=Decimal("0.00"))),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            partial_amount=Coalesce(
                Sum(Case(When(Q(paid_sum__gt=0) & Q(paid_sum__lt=F("total_premium")), then=F("paid_sum")), default=Decimal("0.00"))),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )

        paid_cnt = status_aggr["paid_count"] or 0
        partial_cnt = status_aggr["partial_count"] or 0
        outstanding_cnt = status_aggr["outstanding_count"] or 0
        total_cnt = paid_cnt + partial_cnt + outstanding_cnt

        paid_pct = round((paid_cnt / total_cnt * 100), 1) if total_cnt > 0 else 0.0
        partial_pct = round((partial_cnt / total_cnt * 100), 1) if total_cnt > 0 else 0.0
        outstanding_pct = round(100.0 - paid_pct - partial_pct, 1) if total_cnt > 0 else 0.0

        payment_status_summary = {
            "total_policies": total_cnt,
            "paid": {
                "count": paid_cnt,
                "amount": float(status_aggr["paid_amount"] or Decimal("0.00")),
                "percentage": paid_pct,
            },
            "partial": {
                "count": partial_cnt,
                "amount": float(status_aggr["partial_amount"] or Decimal("0.00")),
                "percentage": partial_pct,
            },
            "outstanding": {
                "count": outstanding_cnt,
                "amount": total_outstanding,
                "percentage": outstanding_pct,
            },
        }

        # ---------------------------------------------------------------------
        # 4. Insurance Company-Wise Premium Collection (The requested graph)
        # ---------------------------------------------------------------------
        companies = (
            InsuranceCompany.objects.filter(is_active=True)
            .annotate(
                policy_count=Count("insurance_records", distinct=True),
                total_premium_sum=Coalesce(
                    Sum("insurance_records__total_premium"),
                    Decimal("0.00"),
                    output_field=DecimalField(),
                ),
                collected_sum=Coalesce(
                    Sum("insurance_records__payments__amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(),
                ),
            )
            .order_by("-total_premium_sum", "name")
        )

        overall_premium_float = float(all_premium) if all_premium > 0 else 1.0

        company_wise_summary = []
        for c in companies:
            c_prem = float(c.total_premium_sum or Decimal("0.00"))
            c_coll = float(c.collected_sum or Decimal("0.00"))
            c_out = max(0.0, c_prem - c_coll)
            c_share = min(100.0, round((c_prem / overall_premium_float * 100), 1)) if overall_premium_float > 0 else 0.0
            collection_rate = round((c_coll / c_prem * 100), 1) if c_prem > 0 else 0.0

            # Include companies that have policies or were recently active
            if c.policy_count > 0 or c_prem > 0:
                company_wise_summary.append({
                    "company_id": c.id,
                    "company_name": c.name,
                    "policy_count": c.policy_count,
                    "total_premium": c_prem,
                    "premium_collected": c_coll,
                    "outstanding": c_out,
                    "share_percentage": c_share,
                    "collection_rate": collection_rate,
                })

        # ---------------------------------------------------------------------
        # 5. Recent Insurance Records (Latest 6-8 records matching UI screenshot)
        # ---------------------------------------------------------------------
        recent_qs = (
            InsuranceRecord.objects.select_related("customer", "vehicle", "insurance_company")
            .prefetch_related("payments")
            .order_by("-entry_date", "-created_at", "-id")[:10]
        )

        recent_records = []
        for rec in recent_qs:
            total_prem = float(rec.total_premium or Decimal("0.00"))
            paid_sum = sum([p.amount for p in rec.payments.all()], Decimal("0.00"))
            paid_float = float(paid_sum)
            out_float = max(0.0, total_prem - paid_float)

            if paid_float >= total_prem and total_prem > 0:
                rec_status = "Paid"
            elif paid_float > 0:
                rec_status = "Partial"
            else:
                rec_status = "Outstanding"

            formatted_date = (
                rec.entry_date.strftime("%d %b %Y") if rec.entry_date else ""
            )

            recent_records.append({
                "id": rec.id,
                "policy_number": rec.policy_number,
                "entry_date": str(rec.entry_date),
                "formatted_date": formatted_date,
                "customer_name": rec.customer.name if rec.customer else "Unknown",
                "customer_phone": rec.customer.phone if rec.customer else "",
                "vehicle_number": rec.vehicle.vehicle_number if rec.vehicle else "N/A",
                "vehicle_type": rec.vehicle.vehicle_type if rec.vehicle else "Vehicle",
                "insurance_company": rec.insurance_company.name if rec.insurance_company else "N/A",
                "total_premium": total_prem,
                "paid_amount": paid_float,
                "outstanding": out_float,
                "status": rec_status,
            })

        return Response(
            {
                "kpis": kpis,
                "business_summary": business_summary,
                "payment_status_summary": payment_status_summary,
                "company_wise_summary": company_wise_summary,
                "recent_records": recent_records,
            },
            status=status.HTTP_200_OK,
        )
