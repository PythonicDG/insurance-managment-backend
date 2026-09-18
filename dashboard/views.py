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

        # Parse date filter parameters
        start_date_param = request.query_params.get("start_date", "").strip()
        end_date_param = request.query_params.get("end_date", "").strip()

        start_date = None
        end_date = None
        is_all_time = False

        if start_date_param.lower() in ["all", "all_time"] or request.query_params.get("filter") == "all":
            is_all_time = True
        elif start_date_param:
            try:
                start_date = date.fromisoformat(start_date_param)
            except ValueError:
                start_date = today
            if end_date_param:
                try:
                    end_date = date.fromisoformat(end_date_param)
                except ValueError:
                    end_date = start_date
            else:
                end_date = start_date
        elif end_date_param:
            try:
                end_date = date.fromisoformat(end_date_param)
                start_date = end_date
            except ValueError:
                start_date = today
                end_date = today
        else:
            # Default to today
            start_date = today
            end_date = today

        # ---------------------------------------------------------------------
        # 1. Top KPI Metrics
        # ---------------------------------------------------------------------
        all_premium_aggr = InsuranceRecord.objects.aggregate(
            total=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField())
        )
        all_premium = all_premium_aggr["total"] or Decimal("0.00")

        all_received_aggr = Payment.objects.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )
        all_received = all_received_aggr["total"] or Decimal("0.00")

        all_outstanding_dec = max(Decimal("0.00"), all_premium - all_received)
        all_outstanding = float(all_outstanding_dec)

        if not is_all_time and start_date and end_date:
            period_records = InsuranceRecord.objects.filter(entry_date__gte=start_date, entry_date__lte=end_date)
            period_payments = Payment.objects.filter(payment_date__gte=start_date, payment_date__lte=end_date)

            entries_count = period_records.count()
            period_premium_aggr = period_records.aggregate(
                total=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField())
            )
            period_premium = float(period_premium_aggr["total"] or Decimal("0.00"))

            period_received_aggr = period_payments.aggregate(
                total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
            )
            period_received = float(period_received_aggr["total"] or Decimal("0.00"))

            # Outstanding for the records created in this period
            period_records_paid_aggr = period_records.aggregate(
                total=Coalesce(Sum("payments__amount"), Decimal("0.00"), output_field=DecimalField())
            )
            period_records_paid = period_records_paid_aggr["total"] or Decimal("0.00")
            period_outstanding = float(max(Decimal("0.00"), (period_premium_aggr["total"] or Decimal("0.00")) - period_records_paid))
        else:
            entries_count = InsuranceRecord.objects.count()
            period_premium = float(all_premium)
            period_received = float(all_received)
            period_outstanding = all_outstanding

        total_policies = InsuranceRecord.objects.count()

        kpis = {
            "today_entries": entries_count,
            "today_premium": period_premium,
            "today_received": period_received,
            "total_outstanding": period_outstanding,
            "all_time_outstanding": all_outstanding,
            "total_policies": total_policies,
            "total_premium": float(all_premium),
            "total_received": float(all_received),
            "filter_start_date": str(start_date) if start_date else None,
            "filter_end_date": str(end_date) if end_date else None,
            "is_all_time": is_all_time,
        }

        # ---------------------------------------------------------------------
        # 2. Business Summary (Monthly trend)
        # ---------------------------------------------------------------------
        month_slots = []
        if not is_all_time and start_date and end_date:
            diff_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
            if diff_months > 1:
                trend_months = min(max(diff_months, 1), 24)
                ref_year = end_date.year
                ref_month = end_date.month
            else:
                trend_months = months_count
                ref_year = end_date.year
                ref_month = end_date.month
        else:
            trend_months = months_count
            ref_year = today.year
            ref_month = today.month

        for i in range(trend_months - 1, -1, -1):
            target_year = ref_year
            target_month = ref_month - i
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
        if not is_all_time and start_date and end_date:
            base_status_records = InsuranceRecord.objects.filter(entry_date__gte=start_date, entry_date__lte=end_date)
        else:
            base_status_records = InsuranceRecord.objects.all()

        records_with_payments = base_status_records.annotate(
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
                "amount": period_outstanding,
                "percentage": outstanding_pct,
            },
        }

        # ---------------------------------------------------------------------
        # 4. Insurance Company-Wise Premium Collection (The requested graph)
        # ---------------------------------------------------------------------
        if not is_all_time and start_date and end_date:
            rec_filter = Q(insurance_records__entry_date__gte=start_date, insurance_records__entry_date__lte=end_date)
            companies = (
                InsuranceCompany.objects.filter(is_active=True)
                .annotate(
                    policy_count=Count("insurance_records", filter=rec_filter, distinct=True),
                    total_premium_sum=Coalesce(
                        Sum("insurance_records__total_premium", filter=rec_filter),
                        Decimal("0.00"),
                        output_field=DecimalField(),
                    ),
                    collected_sum=Coalesce(
                        Sum("insurance_records__payments__amount", filter=rec_filter),
                        Decimal("0.00"),
                        output_field=DecimalField(),
                    ),
                )
                .order_by("-total_premium_sum", "name")
            )
            context_premium = period_premium if period_premium > 0 else 1.0
        else:
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
            context_premium = float(all_premium) if all_premium > 0 else 1.0

        company_wise_summary = []
        for c in companies:
            c_prem = float(c.total_premium_sum or Decimal("0.00"))
            c_coll = float(c.collected_sum or Decimal("0.00"))
            c_out = max(0.0, c_prem - c_coll)
            c_share = min(100.0, round((c_prem / context_premium * 100), 1)) if context_premium > 0 else 0.0
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
        # 5. Recent Insurance Records (Latest records matching filter)
        # ---------------------------------------------------------------------
        recent_base = (
            InsuranceRecord.objects.select_related("customer", "vehicle", "insurance_company")
            .prefetch_related("payments")
        )
        if not is_all_time and start_date and end_date:
            period_recent = list(
                recent_base.filter(entry_date__gte=start_date, entry_date__lte=end_date)
                .order_by("-entry_date", "-created_at", "-id")[:10]
            )
            if period_recent:
                recent_qs = period_recent
            else:
                recent_qs = recent_base.order_by("-entry_date", "-created_at", "-id")[:10]
        else:
            recent_qs = recent_base.order_by("-entry_date", "-created_at", "-id")[:10]

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
