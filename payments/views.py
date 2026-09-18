from decimal import Decimal
from django.db.models import (
    Case,
    CharField,
    Count,
    DecimalField,
    F,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from insurance.models import InsuranceRecord
from .models import Payment
from .serializers import (
    LedgerRecordSerializer,
    LedgerSummarySerializer,
    PaymentSerializer,
)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Payment Transactions API:
    - GET    /api/payments/?insurance_record_id=<id> -> List payments for a record
    - POST   /api/payments/                         -> Create a payment
    - GET    /api/payments/<id>/                    -> Retrieve payment
    - PUT    /api/payments/<id>/                    -> Update payment
    - PATCH  /api/payments/<id>/                    -> Partial update payment
    - DELETE /api/payments/<id>/                    -> Delete payment
    - GET    /api/payments/history/?insurance_record_id=<id> -> Detailed payment history & summary
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer

    def get_queryset(self):
        # Requirement: Payment history must always be fetched using insurance_record_id, never customer phone/customer_id.
        params = self.request.query_params
        customer_phone = params.get("customer_phone") or params.get("phone")
        customer_id = params.get("customer_id") or params.get("customer")

        record_id = (
            params.get("insurance_record_id")
            or params.get("insurance_record")
            or params.get("record_id")
            or params.get("record")
        )

        if customer_phone or customer_id:
            if not record_id:
                raise ValidationError(
                    {"insurance_record_id": "Payment history must always be fetched using insurance_record_id, never customer phone/customer_id."}
                )

        queryset = Payment.objects.select_related("insurance_record").all()
        if record_id:
            queryset = queryset.filter(insurance_record_id=record_id)
        return queryset.order_by("-payment_date", "-created_at")

    def create(self, request, *args, **kwargs):
        record_id = (
            request.data.get("insurance_record_id")
            or request.data.get("insurance_record")
            or request.data.get("record_id")
            or request.data.get("record")
        )
        if not record_id:
            raise ValidationError({"insurance_record_id": "insurance_record_id is required."})

        record = get_object_or_404(InsuranceRecord, pk=record_id)
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data["insurance_record_id"] = record.id

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save(insurance_record=record)
        record.refresh_from_db()

        return Response(
            {
                "message": "Payment recorded successfully.",
                "data": serializer.data,
                "total_paid": f"{record.total_paid:.2f}",
                "outstanding": f"{record.outstanding:.2f}",
                "payment_status": record.payment_status,
                "status": record.payment_status,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="history")
    def history(self, request):
        """
        GET /api/payments/history/?insurance_record_id=<id>
        """
        record_id = (
            request.query_params.get("insurance_record_id")
            or request.query_params.get("insurance_record")
            or request.query_params.get("record_id")
            or request.query_params.get("record")
        )
        if not record_id:
            raise ValidationError(
                {"insurance_record_id": "insurance_record_id is required to fetch payment history."}
            )

        record = get_object_or_404(InsuranceRecord, pk=record_id)
        payments = record.payments.all().order_by("-payment_date", "-created_at")
        serializer = self.get_serializer(payments, many=True)

        return Response(
            {
                "insurance_record_id": record.id,
                "total_premium": f"{record.total_premium:.2f}",
                "total_paid": f"{record.total_paid:.2f}",
                "outstanding": f"{record.outstanding:.2f}",
                "status": record.payment_status,
                "payment_status": record.payment_status,
                "payments": serializer.data,
                "transactions": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class LedgerPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class LedgerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    High-Performance Outstanding & Ledger API:
    - GET /api/payments/ledger/         -> Paginated records + Top 4 KPI summary cards in a single fast SQL trip
    - GET /api/payments/ledger/summary/ -> Just the KPI summary metrics
    - GET /api/payments/ledger/<id>/    -> Record details with payments transaction history
    """
    permission_classes = [IsAuthenticated]
    serializer_class = LedgerRecordSerializer
    pagination_class = LedgerPagination

    def get_annotated_queryset(self):
        return (
            InsuranceRecord.objects.select_related(
                "customer", "vehicle", "insurance_company"
            )
            .annotate(
                annotated_paid=Coalesce(
                    Sum("payments__amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .annotate(
                annotated_outstanding=Coalesce(
                    Case(
                        When(
                            annotated_paid__gte=F("total_premium"),
                            then=Value(Decimal("0.00")),
                        ),
                        default=F("total_premium") - F("annotated_paid"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .annotate(
                annotated_status=Case(
                    When(annotated_paid__lte=Decimal("0.00"), then=Value("Outstanding")),
                    When(annotated_paid__gte=F("total_premium"), then=Value("Paid")),
                    default=Value("Partial"),
                    output_field=CharField(),
                )
            )
        )

    def apply_filters(self, queryset, params, include_status_filter=True):
        # 1. Search filter
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(vehicle__vehicle_number__icontains=search)
                | Q(policy_number__icontains=search)
                | Q(insurance_company__name__icontains=search)
            )

        # 2. Insurance company filter
        company_id = (
            params.get("insurance_company_id")
            or params.get("company_id")
            or params.get("company")
        )
        if company_id and str(company_id).lower() not in ["all", "all companies", ""]:
            try:
                queryset = queryset.filter(insurance_company_id=int(company_id))
            except (ValueError, TypeError):
                queryset = queryset.filter(insurance_company__name__icontains=str(company_id).strip())

        # 3. Date range filters (entry_date)
        date_from = params.get("date_from") or params.get("entry_date_from") or params.get("start_date")
        if date_from:
            queryset = queryset.filter(entry_date__gte=date_from)

        date_to = params.get("date_to") or params.get("entry_date_to") or params.get("end_date")
        if date_to:
            queryset = queryset.filter(entry_date__lte=date_to)

        # 4. Payment status filter
        if include_status_filter:
            payment_status = params.get("payment_status", "outstanding_partial").strip().lower()
            if payment_status in ["outstanding_partial", "outstanding & partial", "pending"]:
                queryset = queryset.filter(annotated_outstanding__gt=0)
            elif payment_status in ["outstanding", "unpaid"]:
                queryset = queryset.filter(annotated_paid__lte=0)
            elif payment_status == "partial":
                queryset = queryset.filter(annotated_paid__gt=0, annotated_paid__lt=F("total_premium"))
            elif payment_status == "paid":
                queryset = queryset.filter(annotated_paid__gte=F("total_premium"))
            elif payment_status in ["all", "all statuses"]:
                pass

        return queryset

    def compute_summary(self, queryset):
        aggr = queryset.aggregate(
            total_premium=Coalesce(Sum("total_premium"), Decimal("0.00"), output_field=DecimalField()),
            total_received=Coalesce(Sum("annotated_paid"), Decimal("0.00"), output_field=DecimalField()),
            total_outstanding=Coalesce(Sum("annotated_outstanding"), Decimal("0.00"), output_field=DecimalField()),
            total_customers_pending=Count(
                "customer_id",
                filter=Q(annotated_outstanding__gt=0),
                distinct=True,
            ),
        )
        return {
            "total_premium": float(aggr["total_premium"]),
            "total_received": float(aggr["total_received"]),
            "total_outstanding": float(aggr["total_outstanding"]),
            "total_customers_pending": aggr["total_customers_pending"],
        }

    def get_queryset(self):
        qs = self.get_annotated_queryset()
        qs = self.apply_filters(qs, self.request.query_params, include_status_filter=True)

        ordering = self.request.query_params.get("ordering", "-entry_date")
        valid_orderings = [
            "entry_date", "-entry_date",
            "total_premium", "-total_premium",
            "annotated_paid", "-annotated_paid",
            "annotated_outstanding", "-annotated_outstanding",
            "created_at", "-created_at",
        ]
        if ordering in valid_orderings:
            qs = qs.order_by(ordering, "-id")
        else:
            qs = qs.order_by("-entry_date", "-id")

        return qs

    def list(self, request, *args, **kwargs):
        # 1. Base annotated queryset
        base_qs = self.get_annotated_queryset()

        # 2. Scoped queryset for summary
        summary_scope = request.query_params.get("summary_scope", "scope").lower()
        if summary_scope == "table":
            summary_qs = self.apply_filters(base_qs, request.query_params, include_status_filter=True)
        else:
            summary_qs = self.apply_filters(base_qs, request.query_params, include_status_filter=False)

        summary_data = self.compute_summary(summary_qs)

        # 3. Filtered queryset for table listing
        queryset = self.filter_queryset(self.get_queryset())

        # 4. Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginator = self.paginator
            return Response({
                "summary": summary_data,
                "count": paginator.page.paginator.count,
                "page": paginator.page.number,
                "page_size": paginator.get_page_size(request),
                "total_pages": paginator.page.paginator.num_pages,
                "results": serializer.data,
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "summary": summary_data,
            "count": queryset.count(),
            "results": serializer.data,
        })

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        base_qs = self.get_annotated_queryset()
        summary_qs = self.apply_filters(base_qs, request.query_params, include_status_filter=False)
        data = self.compute_summary(summary_qs)
        return Response(data, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_annotated_queryset().filter(pk=kwargs.get("pk")).first()
        if not instance:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        payments = instance.payments.all().order_by("-payment_date", "-created_at")
        payments_data = PaymentSerializer(payments, many=True).data
        res = dict(serializer.data)
        res["payments"] = payments_data
        res["transactions"] = payments_data
        return Response(res, status=status.HTTP_200_OK)

