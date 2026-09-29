from calendar import monthrange
from datetime import date, timedelta
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


def calculate_business_summary(
    start_date=None,
    end_date=None,
    start_month=None,
    end_month=None,
    months_count=6,
    ref_year=None,
    ref_month=None,
):
    """
    Computes monthly business summary (collected premium and outstanding amounts)
    strictly bounded to a maximum 6-month span to maintain visual harmony in the chart.
    """
    today = timezone.localdate()
    month_slots = []

    parsed_start = None
    parsed_end = None

    if start_month:
        try:
            parts = [int(p) for p in str(start_month).strip().split("-")]
            if len(parts) == 2 and 1 <= parts[1] <= 12:
                parsed_start = (parts[0], parts[1])
        except (ValueError, TypeError):
            pass

    if end_month:
        try:
            parts = [int(p) for p in str(end_month).strip().split("-")]
            if len(parts) == 2 and 1 <= parts[1] <= 12:
                parsed_end = (parts[0], parts[1])
        except (ValueError, TypeError):
            pass

    if not parsed_start and start_date:
        if isinstance(start_date, str):
            try:
                sd = date.fromisoformat(start_date)
                parsed_start = (sd.year, sd.month)
            except ValueError:
                pass
        elif isinstance(start_date, date):
            parsed_start = (start_date.year, start_date.month)

    if not parsed_end and end_date:
        if isinstance(end_date, str):
            try:
                ed = date.fromisoformat(end_date)
                parsed_end = (ed.year, ed.month)
            except ValueError:
                pass
        elif isinstance(end_date, date):
            parsed_end = (end_date.year, end_date.month)

    if parsed_start and parsed_end:
        cur_y, cur_m = parsed_start
        end_y, end_m = parsed_end
        if (cur_y, cur_m) > (end_y, end_m):
            cur_y, cur_m, end_y, end_m = end_y, end_m, cur_y, cur_m

        slots_temp = []
        while (cur_y, cur_m) <= (end_y, end_m) and len(slots_temp) < 6:
            _, last_day = monthrange(cur_y, cur_m)
            slots_temp.append({
                "year": cur_y,
                "month": cur_m,
                "start": date(cur_y, cur_m, 1),
                "end": date(cur_y, cur_m, last_day),
                "month_name": date(cur_y, cur_m, 1).strftime("%b"),
                "month_key": f"{cur_y}-{cur_m:02d}",
            })
            cur_m += 1
            if cur_m > 12:
                cur_m = 1
                cur_y += 1
        month_slots = slots_temp

    if not month_slots:
        if ref_year is None or ref_month is None:
            if parsed_end:
                ref_year, ref_month = parsed_end
            elif parsed_start:
                ref_year, ref_month = parsed_start
                ref_month += (months_count - 1)
                while ref_month > 12:
                    ref_month -= 12
                    ref_year += 1
            else:
                ref_year = today.year
                ref_month = today.month

        months_count = min(max(int(months_count), 1), 6)
        for i in range(months_count - 1, -1, -1):
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

    # Aggregate records in range by entry date with their paid sum
    # All payments for a policy map back to the month of the policy's entry_date
    records_in_range = (
        InsuranceRecord.objects.filter(entry_date__gte=range_start, entry_date__lte=range_end)
        .annotate(
            paid_total=Coalesce(Sum("payments__amount"), Decimal("0.00"), output_field=DecimalField())
        )
        .values("entry_date", "total_premium", "discount", "paid_total")
    )

    records_by_month_key = {}
    for r in records_in_range:
        e_date = r["entry_date"]
        key = f"{e_date.year}-{e_date.month:02d}"
        if key not in records_by_month_key:
            records_by_month_key[key] = {
                "premium": Decimal("0.00"),
                "discount": Decimal("0.00"),
                "collected": Decimal("0.00"),
                "outstanding": Decimal("0.00"),
            }
        prem = r["total_premium"] or Decimal("0.00")
        disc = r.get("discount") or Decimal("0.00")
        paid = r["paid_total"] or Decimal("0.00")
        out = max(Decimal("0.00"), prem - disc - paid)
        records_by_month_key[key]["premium"] += prem
        records_by_month_key[key]["discount"] += disc
        records_by_month_key[key]["collected"] += paid
        records_by_month_key[key]["outstanding"] += out

    business_summary = []
    for slot in month_slots:
        k = slot["month_key"]
        month_data = records_by_month_key.get(k, {})
        collected = float(month_data.get("collected", Decimal("0.00")))
        disc_val = float(month_data.get("discount", Decimal("0.00")))
        outstanding = float(month_data.get("outstanding", Decimal("0.00")))
        business_summary.append({
            "month": slot["month_name"],
            "year": slot["year"],
            "month_key": k,
            "premium_collected": collected,
            "discount": disc_val,
            "outstanding": outstanding,
        })

    return business_summary


class DashboardSummaryView(APIView):
    """
    High-performance dashboard summary API.
    Computes all KPI stats, monthly business trend, payment status donut breakdown,
    insurance company-wise premium distribution, and recent records using optimized
    database aggregations in minimal database trips.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        InsuranceRecord.activate_due_scheduled()
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
            # Default to all-time data
            is_all_time = True

        # ---------------------------------------------------------------------
        # 1. Top KPI Metrics
        # ---------------------------------------------------------------------
        all_premium_aggr = InsuranceRecord.objects.aggregate(
            total=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField())
        )
        all_premium = all_premium_aggr["total"] or Decimal("0.00")

        all_discount_aggr = InsuranceRecord.objects.aggregate(
            total=Coalesce(Sum("discount"), Decimal("0.00"), output_field=DecimalField())
        )
        all_discount = all_discount_aggr["total"] or Decimal("0.00")

        all_received_aggr = Payment.objects.aggregate(
            total=Coalesce(Sum("amount"), Decimal("0.00"), output_field=DecimalField())
        )
        all_received = all_received_aggr["total"] or Decimal("0.00")

        all_outstanding_dec = max(Decimal("0.00"), all_premium - all_discount - all_received)
        all_outstanding = float(all_outstanding_dec)

        if not is_all_time and start_date and end_date:
            period_records = InsuranceRecord.objects.filter(entry_date__gte=start_date, entry_date__lte=end_date)

            entries_count = period_records.count()
            period_premium_aggr = period_records.aggregate(
                total=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField())
            )
            period_premium = float(period_premium_aggr["total"] or Decimal("0.00"))

            period_discount_aggr = period_records.aggregate(
                total=Coalesce(Sum("discount"), Decimal("0.00"), output_field=DecimalField())
            )
            period_discount = float(period_discount_aggr["total"] or Decimal("0.00"))

            # Received payments anchored to records entered in this period (regardless of when paid)
            period_received_aggr = period_records.aggregate(
                total=Coalesce(Sum("payments__amount"), Decimal("0.00"), output_field=DecimalField())
            )
            period_received = float(period_received_aggr["total"] or Decimal("0.00"))

            # Outstanding for the records created in this period: Total Premium - Discount - Received
            period_outstanding = float(
                max(
                    Decimal("0.00"),
                    (period_premium_aggr["total"] or Decimal("0.00"))
                    - (period_discount_aggr["total"] or Decimal("0.00"))
                    - (period_received_aggr["total"] or Decimal("0.00")),
                )
            )
        else:
            entries_count = InsuranceRecord.objects.count()
            period_premium = float(all_premium)
            period_discount = float(all_discount)
            period_received = float(all_received)
            period_outstanding = all_outstanding

        total_policies = InsuranceRecord.objects.count()

        ten_days_later = today + timedelta(days=10)
        expiring_today_count = InsuranceRecord.objects.filter(
            policy_expiry_date=today,
            renewed_policy__isnull=True,
        ).count()
        expiring_soon_count = InsuranceRecord.objects.filter(
            is_active=True,
            renewed_policy__isnull=True,
            policy_expiry_date__gte=today,
            policy_expiry_date__lte=ten_days_later,
        ).count()

        kpis = {
            "today_entries": entries_count,
            "today_premium": period_premium,
            "today_discount": period_discount,
            "today_received": period_received,
            "total_outstanding": period_outstanding,
            "all_time_outstanding": all_outstanding,
            "total_policies": total_policies,
            "total_premium": float(all_premium),
            "total_discount": float(all_discount),
            "all_time_discount": float(all_discount),
            "total_received": float(all_received),
            "expiring_today_count": expiring_today_count,
            "expiring_soon_count": expiring_soon_count,
            "filter_start_date": str(start_date) if start_date else None,
            "filter_end_date": str(end_date) if end_date else None,
            "is_all_time": is_all_time,
        }

        # ---------------------------------------------------------------------
        # 2. Business Summary (Monthly trend - fixed 6-month span, independent of global filter)
        # ---------------------------------------------------------------------
        business_summary = calculate_business_summary(months_count=6)

        # ---------------------------------------------------------------------
        # 3. Payment Status Summary (Donut Chart: Paid, Partial, Outstanding)
        # ---------------------------------------------------------------------
        if not is_all_time and start_date and end_date:
            base_status_records = InsuranceRecord.objects.filter(entry_date__gte=start_date, entry_date__lte=end_date)
        else:
            base_status_records = InsuranceRecord.objects.all()

        records_with_payments = base_status_records.annotate(
            paid_sum=Coalesce(Sum("payments__amount"), Decimal("0.00"), output_field=DecimalField()),
            net_prem_annot=Case(
                When(total_premium__gt=F("discount"), then=F("total_premium") - F("discount")),
                default=Decimal("0.00"),
                output_field=DecimalField(),
            )
        )

        status_aggr = records_with_payments.aggregate(
            paid_count=Count(Case(When(paid_sum__gte=F("net_prem_annot"), total_premium__gt=0, then=1))),
            partial_count=Count(
                Case(When(Q(paid_sum__gt=0) & Q(paid_sum__lt=F("net_prem_annot")), then=1))
            ),
            outstanding_count=Count(
                Case(When(Q(paid_sum__lte=0) | Q(net_prem_annot__lte=0, paid_sum__lte=0), then=1))
            ),
            paid_amount=Coalesce(
                Sum(Case(When(paid_sum__gte=F("net_prem_annot"), then=F("paid_sum")), default=Decimal("0.00"))),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            partial_amount=Coalesce(
                Sum(Case(When(Q(paid_sum__gt=0) & Q(paid_sum__lt=F("net_prem_annot")), then=F("paid_sum")), default=Decimal("0.00"))),
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
                    total_discount_sum=Coalesce(
                        Sum("insurance_records__discount", filter=rec_filter),
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
                    total_discount_sum=Coalesce(
                        Sum("insurance_records__discount"),
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
            c_disc = float(getattr(c, "total_discount_sum", 0) or Decimal("0.00"))
            c_coll = float(c.collected_sum or Decimal("0.00"))
            c_out = max(0.0, c_prem - c_disc - c_coll)
            c_share = min(100.0, round((c_prem / context_premium * 100), 1)) if context_premium > 0 else 0.0
            collection_rate = round((c_coll / c_prem * 100), 1) if c_prem > 0 else 0.0

            # Include companies that have policies or were recently active
            if c.policy_count > 0 or c_prem > 0:
                company_wise_summary.append({
                    "company_id": c.id,
                    "company_name": c.name,
                    "policy_count": c.policy_count,
                    "total_premium": c_prem,
                    "discount": c_disc,
                    "premium_collected": c_coll,
                    "outstanding": c_out,
                    "share_percentage": c_share,
                    "collection_rate": collection_rate,
                })

        # ---------------------------------------------------------------------
        # 5. Expiring Today Records (Policies whose expiry date is today)
        # ---------------------------------------------------------------------
        expiring_today_qs = (
            InsuranceRecord.objects.filter(
                policy_expiry_date=today,
                renewed_policy__isnull=True,
            )
            .select_related("customer", "vehicle", "insurance_company")
            .prefetch_related("payments")
            .order_by("-created_at")
        )

        def format_record_item(rec):
            total_prem = float(rec.total_premium or Decimal("0.00"))
            discount = float(rec.discount or Decimal("0.00"))
            net_prem = max(0.0, total_prem - discount)
            paid_sum = sum([p.amount for p in rec.payments.all()], Decimal("0.00"))
            paid_float = float(paid_sum)
            out_float = max(0.0, net_prem - paid_float)

            if paid_float >= net_prem and net_prem > 0:
                rec_status = "Paid"
            elif paid_float > 0:
                rec_status = "Partial"
            else:
                rec_status = "Outstanding"

            formatted_date = (
                rec.entry_date.strftime("%d %b %Y") if rec.entry_date else ""
            )
            formatted_expiry_date = (
                rec.policy_expiry_date.strftime("%d %b %Y") if rec.policy_expiry_date else ""
            )

            return {
                "id": rec.id,
                "policy_number": rec.policy_number,
                "entry_date": str(rec.entry_date),
                "formatted_date": formatted_date,
                "policy_expiry_date": str(rec.policy_expiry_date),
                "formatted_expiry_date": formatted_expiry_date,
                "days_left": rec.days_left,
                "customer_name": rec.customer.name if rec.customer else "Unknown",
                "customer_phone": rec.customer.phone if rec.customer else "",
                "vehicle_number": rec.vehicle.vehicle_number if rec.vehicle else "N/A",
                "vehicle_type": rec.vehicle.vehicle_type if rec.vehicle else "Vehicle",
                "insurance_company": rec.insurance_company.name if rec.insurance_company else "N/A",
                "total_premium": total_prem,
                "discount": discount,
                "net_premium": net_prem,
                "paid_amount": paid_float,
                "outstanding": out_float,
                "status": rec_status,
                "policy_status": rec.status,
            }

        expiring_today_records = [format_record_item(rec) for rec in expiring_today_qs]

        recent_qs = (
            InsuranceRecord.objects.select_related("customer", "vehicle", "insurance_company")
            .prefetch_related("payments")
            .order_by("-entry_date", "-created_at", "-id")[:10]
        )
        recent_records = [format_record_item(rec) for rec in recent_qs]

        return Response(
            {
                "kpis": kpis,
                "business_summary": business_summary,
                "payment_status_summary": payment_status_summary,
                "company_wise_summary": company_wise_summary,
                "expiring_today_records": expiring_today_records,
                "recent_records": recent_records,
            },
            status=status.HTTP_200_OK,
        )


class DashboardBusinessSummaryView(APIView):
    """
    Dedicated endpoint for the Business Summary chart.
    Enforces a strict maximum 6-month window so the dual-bar chart never overflows its container.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        start_month = request.query_params.get("start_month")
        end_month = request.query_params.get("end_month")
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        ref_year = request.query_params.get("ref_year")
        ref_month = request.query_params.get("ref_month")

        try:
            ref_year = int(ref_year) if ref_year else None
        except (ValueError, TypeError):
            ref_year = None

        try:
            ref_month = int(ref_month) if ref_month else None
        except (ValueError, TypeError):
            ref_month = None

        summary = calculate_business_summary(
            start_date=start_date,
            end_date=end_date,
            start_month=start_month,
            end_month=end_month,
            ref_year=ref_year,
            ref_month=ref_month,
            months_count=6,
        )
        return Response({"business_summary": summary}, status=status.HTTP_200_OK)


class DashboardNotificationsView(APIView):
    """
    Dedicated lightweight notification endpoint for the bell icon in the app header.
    STRICTLY returns policies that expire or have expired TODAY (policy_expiry_date == today).
    Does NOT return yesterday's or older expired records.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        InsuranceRecord.activate_due_scheduled()
        today = timezone.localdate()

        # Query strictly policies expiring today (policy_expiry_date == today)
        records_qs = (
            InsuranceRecord.objects.filter(
                policy_expiry_date=today,
                renewed_policy__isnull=True,
            )
            .select_related("customer", "vehicle", "insurance_company")
            .prefetch_related("payments")
            .order_by("-created_at")
        )

        records_data = []
        for rec in records_qs:
            total_prem = float(rec.total_premium or Decimal("0.00"))
            discount = float(rec.discount or Decimal("0.00"))
            net_prem = max(0.0, total_prem - discount)
            paid_sum = sum([p.amount for p in rec.payments.all()], Decimal("0.00"))
            paid_float = float(paid_sum)
            out_float = max(0.0, net_prem - paid_float)

            if paid_float >= net_prem and net_prem > 0:
                rec_status = "Paid"
            elif paid_float > 0:
                rec_status = "Partial"
            else:
                rec_status = "Outstanding"

            records_data.append({
                "id": rec.id,
                "policy_number": rec.policy_number,
                "entry_date": str(rec.entry_date) if rec.entry_date else "",
                "policy_start_date": str(rec.policy_start_date) if rec.policy_start_date else "",
                "policy_expiry_date": str(rec.policy_expiry_date),
                "formatted_expiry_date": rec.policy_expiry_date.strftime("%d %b %Y"),
                "days_left": rec.days_left,
                "customer_name": rec.customer.name if rec.customer else "Unknown",
                "customer_phone": rec.customer.phone if rec.customer else "",
                "vehicle_number": rec.vehicle.vehicle_number if rec.vehicle else "N/A",
                "vehicle_type": rec.vehicle.vehicle_type if rec.vehicle else "Vehicle",
                "insurance_company": rec.insurance_company.name if rec.insurance_company else "N/A",
                "total_premium": total_prem,
                "discount": discount,
                "net_premium": net_prem,
                "paid_amount": paid_float,
                "outstanding": out_float,
                "payment_status": rec_status,
                "status": "expired" if rec.is_expired else "expiring_today",
            })

        return Response(
            {
                "today": str(today),
                "count": len(records_data),
                "records": records_data,
            },
            status=status.HTTP_200_OK,
        )
