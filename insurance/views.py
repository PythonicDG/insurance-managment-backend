import datetime
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import InsuranceCompany, InsuranceDocument, InsuranceRecord
from .serializers import (
    InsuranceCompanySerializer,
    InsuranceDocumentSerializer,
    InsuranceRecordCreateUpdateSerializer,
    InsuranceRecordDetailSerializer,
    InsuranceRecordListSerializer,
)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        paginate_param = request.query_params.get("paginate", "").lower()
        page_size_param = request.query_params.get("page_size", "").lower()
        if paginate_param in ["false", "0", "no"] or page_size_param in ["all", "none"]:
            return None
        return super().paginate_queryset(queryset, request, view=view)


class InsuranceCompanyViewSet(viewsets.ModelViewSet):
    serializer_class = InsuranceCompanySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = InsuranceCompany.objects.all()

        # Search filter by name
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None and is_active != "":
            if is_active.lower() in ["true", "1"]:
                queryset = queryset.filter(is_active=True)
            elif is_active.lower() in ["false", "0"]:
                queryset = queryset.filter(is_active=False)

        return queryset.order_by("name")

    @action(detail=True, methods=["post"], url_path="toggle-status")
    def toggle_status(self, request, pk=None):
        company = self.get_object()
        company.is_active = not company.is_active
        company.save(update_fields=["is_active", "updated_at"])
        return Response(
            {
                "message": f"Company '{company.name}' is now {'active' if company.is_active else 'inactive'}.",
                "data": self.get_serializer(company).data,
            },
            status=status.HTTP_200_OK,
        )


class InsuranceRecordViewSet(viewsets.ModelViewSet):
    """
    Insurance Records ViewSet:
    - POST   /api/insurance/records/            -> Create Record (auto finds/creates customer & vehicle)
    - GET    /api/insurance/records/            -> List Records (Search, Filter, Pagination)
    - GET    /api/insurance/records/<id>/       -> Record Details
    - PUT    /api/insurance/records/<id>/       -> Update Record
    - PATCH  /api/insurance/records/<id>/       -> Partial Update Record
    - DELETE /api/insurance/records/<id>/       -> Delete Record
    - POST   /api/insurance/records/<id>/documents/ -> Upload Document
    - DELETE /api/insurance/records/<id>/documents/<document_id>/ -> Delete Document
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = (
            InsuranceRecord.objects.select_related(
                "customer", "vehicle", "insurance_company"
            )
            .prefetch_related("documents", "payments")
            .all()
        )

        params = self.request.query_params

        # 1. Search filter
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(policy_number__icontains=search)
                | Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(customer__alternative_mobile_number__icontains=search)
                | Q(alternative_mobile_number__icontains=search)
                | Q(customer__email__icontains=search)
                | Q(vehicle__vehicle_number__icontains=search)
                | Q(vehicle__vehicle_type__icontains=search)
                | Q(insurance_company__name__icontains=search)
                | Q(remarks__icontains=search)
            )

        # Explicit vehicle number filter
        vehicle_number = params.get("vehicle_number", "").strip()
        if vehicle_number:
            queryset = queryset.filter(vehicle__vehicle_number__icontains=vehicle_number)

        # 2. Foreign Key Filters
        customer_id = params.get("customer_id") or params.get("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        vehicle_id = params.get("vehicle_id") or params.get("vehicle")
        if vehicle_id:
            queryset = queryset.filter(vehicle_id=vehicle_id)

        company_id = (
            params.get("insurance_company_id")
            or params.get("insurance_company")
            or params.get("company_id")
            or params.get("company")
        )
        if company_id:
            queryset = queryset.filter(insurance_company_id=company_id)

        # 3. Vehicle Type Filter
        vehicle_type = params.get("vehicle_type", "").strip()
        if vehicle_type:
            queryset = queryset.filter(vehicle__vehicle_type__iexact=vehicle_type)

        # 4. Date Filters
        # Entry date
        entry_date = params.get("entry_date")
        if entry_date:
            queryset = queryset.filter(entry_date=entry_date)

        entry_date_from = params.get("entry_date_from") or params.get("start_entry_date")
        if entry_date_from:
            queryset = queryset.filter(entry_date__gte=entry_date_from)

        entry_date_to = params.get("entry_date_to") or params.get("end_entry_date")
        if entry_date_to:
            queryset = queryset.filter(entry_date__lte=entry_date_to)

        # Policy start date
        policy_start_from = params.get("policy_start_date_from") or params.get("policy_start_from")
        if policy_start_from:
            queryset = queryset.filter(policy_start_date__gte=policy_start_from)

        policy_start_to = params.get("policy_start_date_to") or params.get("policy_start_to")
        if policy_start_to:
            queryset = queryset.filter(policy_start_date__lte=policy_start_to)

        # Policy expiry date
        policy_expiry_from = params.get("policy_expiry_date_from") or params.get("policy_expiry_from")
        if policy_expiry_from:
            queryset = queryset.filter(policy_expiry_date__gte=policy_expiry_from)

        policy_expiry_to = params.get("policy_expiry_date_to") or params.get("policy_expiry_to")
        if policy_expiry_to:
            queryset = queryset.filter(policy_expiry_date__lte=policy_expiry_to)

        # 5. Status Filter (active / expired / expiring_soon / expiring_today)
        record_status = params.get("status", "").strip().lower()
        today = timezone.localdate()
        if record_status == "active":
            queryset = queryset.filter(policy_expiry_date__gte=today)
        elif record_status == "expired":
            queryset = queryset.filter(policy_expiry_date__lt=today)
        elif record_status in ["expiring_soon", "expiring"]:
            ten_days_later = today + timedelta(days=10)
            queryset = queryset.filter(
                policy_expiry_date__gte=today,
                policy_expiry_date__lte=ten_days_later,
            )
        elif record_status in ["expiring_today", "today"]:
            queryset = queryset.filter(policy_expiry_date=today)

        # 6. Payment Status Filter (UNPAID, PARTIAL, PAID)
        payment_status_filter = params.get("payment_status", "").strip().upper()
        if payment_status_filter:
            from decimal import Decimal
            from django.db.models import DecimalField, F, Sum
            from django.db.models.functions import Coalesce

            queryset = queryset.annotate(
                annotated_paid=Coalesce(
                    Sum("payments__amount"),
                    Decimal("0.00"),
                    output_field=DecimalField(),
                )
            )
            if payment_status_filter == "UNPAID":
                queryset = queryset.filter(annotated_paid__lte=0)
            elif payment_status_filter == "PAID":
                queryset = queryset.filter(annotated_paid__gte=F("total_premium"))
            elif payment_status_filter == "PARTIAL":
                queryset = queryset.filter(
                    annotated_paid__gt=0, annotated_paid__lt=F("total_premium")
                )

        # 7. Sorting / Ordering
        ordering = params.get("ordering") or params.get("order_by")
        valid_orderings = [
            "entry_date",
            "-entry_date",
            "policy_start_date",
            "-policy_start_date",
            "policy_expiry_date",
            "-policy_expiry_date",
            "total_premium",
            "-total_premium",
            "created_at",
            "-created_at",
        ]
        if ordering and ordering in valid_orderings:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by("-entry_date", "-created_at")

        return queryset

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return InsuranceRecordCreateUpdateSerializer
        elif self.action == "retrieve":
            return InsuranceRecordDetailSerializer
        return InsuranceRecordListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        record = serializer.save()

        # Auto WhatsApp Notification Trigger
        try:
            from whatsapp_integration.models import WhatsAppConfig
            from whatsapp_integration.services import WhatsAppClient

            wa_cfg = WhatsAppConfig.get_config()
            if wa_cfg.is_enabled and wa_cfg.auto_send_policy_creation:
                WhatsAppClient.send_policy_issued_notification(record, async_send=True)
        except Exception:
            pass

        detail_serializer = InsuranceRecordDetailSerializer(
            record, context={"request": request}
        )
        return Response(
            {
                "message": "Insurance record created successfully.",
                "data": detail_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        detail_serializer = InsuranceRecordDetailSerializer(
            record, context={"request": request}
        )
        return Response(
            {
                "message": "Insurance record updated successfully.",
                "data": detail_serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(
            {"message": "Insurance record deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="check-duplicate")
    def check_duplicate(self, request):
        """
        Check if a policy number already exists (case-insensitive & trimmed).
        Query params:
        - policy_number: string
        - exclude_id: int (optional, for edit mode)
        """
        raw_number = request.query_params.get("policy_number", "")
        trimmed_number = raw_number.strip()
        if not trimmed_number:
            return Response({"is_duplicate": False, "record": None}, status=status.HTTP_200_OK)

        queryset = InsuranceRecord.objects.select_related(
            "customer", "vehicle", "insurance_company"
        ).prefetch_related("documents").filter(policy_number__iexact=trimmed_number)

        exclude_id = request.query_params.get("exclude_id") or request.query_params.get("id")
        if exclude_id:
            try:
                queryset = queryset.exclude(pk=int(exclude_id))
            except (ValueError, TypeError):
                pass

        existing = queryset.first()
        if existing:
            detail_data = InsuranceRecordDetailSerializer(existing, context={"request": request}).data
            customer_name = existing.customer.name if existing.customer and existing.customer.name else (existing.customer.phone if existing.customer else "Unknown Customer")
            vehicle_num = existing.vehicle.vehicle_number if existing.vehicle else "Unknown Vehicle"
            return Response(
                {
                    "is_duplicate": True,
                    "message": f"Policy number '{trimmed_number}' already exists (registered to {customer_name} - {vehicle_num}).",
                    "record": detail_data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "is_duplicate": False,
                "record": None,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="check-vehicle")
    def check_vehicle(self, request):
        """
        Check vehicle insurance status:
        Query params:
        - vehicle_number: string
        - exclude_id: int (optional, for edit mode)
        Returns:
        - exists: bool
        - vehicle_number: string
        - has_active_policy: bool
        - active_record: dict | null
        - has_expired_policy: bool
        - latest_expired_record: dict | null
        - history_count: int
        - message: string
        """
        raw_number = request.query_params.get("vehicle_number", "")
        if not raw_number:
            return Response(
                {
                    "exists": False,
                    "vehicle_number": "",
                    "has_active_policy": False,
                    "active_record": None,
                    "has_expired_policy": False,
                    "latest_expired_record": None,
                    "history_count": 0,
                    "message": "Vehicle number not provided.",
                },
                status=status.HTTP_200_OK,
            )

        from vehicles.models import Vehicle

        normalized = Vehicle.normalize_vehicle_number(raw_number)
        vehicle = Vehicle.objects.filter(vehicle_number__iexact=normalized).first()
        if not vehicle:
            return Response(
                {
                    "exists": False,
                    "vehicle_number": normalized,
                    "has_active_policy": False,
                    "active_record": None,
                    "has_expired_policy": False,
                    "latest_expired_record": None,
                    "history_count": 0,
                    "message": f"Vehicle '{normalized}' does not exist yet. A new vehicle and policy record will be created.",
                },
                status=status.HTTP_200_OK,
            )

        today = timezone.localdate()
        records_qs = (
            InsuranceRecord.objects.select_related(
                "customer", "vehicle", "insurance_company"
            )
            .prefetch_related("documents", "payments")
            .filter(vehicle=vehicle)
            .order_by("-policy_expiry_date", "-id")
        )

        exclude_id = request.query_params.get("exclude_id") or request.query_params.get("id")
        if exclude_id:
            try:
                records_qs = records_qs.exclude(pk=int(exclude_id))
            except (ValueError, TypeError):
                pass

        all_records = list(records_qs)
        if not all_records:
            return Response(
                {
                    "exists": True,
                    "vehicle_number": vehicle.vehicle_number,
                    "vehicle_id": vehicle.id,
                    "vehicle_type": vehicle.vehicle_type,
                    "customer_id": vehicle.customer_id,
                    "customer_name": vehicle.customer.name if vehicle.customer else "",
                    "customer_phone": vehicle.customer.phone if vehicle.customer else "",
                    "customer_alternative_mobile_number": vehicle.customer.alternative_mobile_number if vehicle.customer else "",
                    "has_active_policy": False,
                    "active_record": None,
                    "has_expired_policy": False,
                    "latest_expired_record": None,
                    "history_count": 0,
                    "message": f"Vehicle '{vehicle.vehicle_number}' has no insurance records. A new record can be created.",
                },
                status=status.HTTP_200_OK,
            )

        # Check for active records
        # Sync any record with policy_expiry_date < today to is_active=False
        active_record = None
        expired_records = []
        for r in all_records:
            if r.policy_expiry_date < today and r.is_active:
                r.is_active = False
                r.save(update_fields=["is_active"])

            if r.is_active and r.policy_expiry_date >= today:
                if not active_record:
                    active_record = r
            else:
                expired_records.append(r)

        if active_record:
            detail_data = InsuranceRecordDetailSerializer(active_record, context={"request": request}).data
            return Response(
                {
                    "exists": True,
                    "vehicle_number": vehicle.vehicle_number,
                    "vehicle_id": vehicle.id,
                    "vehicle_type": vehicle.vehicle_type,
                    "customer_id": vehicle.customer_id,
                    "customer_name": vehicle.customer.name if vehicle.customer else "",
                    "customer_phone": vehicle.customer.phone if vehicle.customer else "",
                    "customer_alternative_mobile_number": vehicle.customer.alternative_mobile_number if vehicle.customer else "",
                    "has_active_policy": True,
                    "active_record": detail_data,
                    "has_expired_policy": len(expired_records) > 0,
                    "latest_expired_record": (
                        InsuranceRecordDetailSerializer(expired_records[0], context={"request": request}).data
                        if expired_records
                        else None
                    ),
                    "history_count": len(expired_records),
                    "message": (
                        f"Active policy already exists for vehicle '{vehicle.vehicle_number}' "
                        f"(Policy #{active_record.policy_number}, Expiry: {active_record.policy_expiry_date}). "
                        "Cannot create duplicate record. Please Renew or Update."
                    ),
                },
                status=status.HTTP_200_OK,
            )

        # No active policy, but previous expired policies exist
        latest_expired = expired_records[0] if expired_records else None
        latest_data = (
            InsuranceRecordDetailSerializer(latest_expired, context={"request": request}).data
            if latest_expired
            else None
        )
        return Response(
            {
                "exists": True,
                "vehicle_number": vehicle.vehicle_number,
                "vehicle_id": vehicle.id,
                "vehicle_type": vehicle.vehicle_type,
                "customer_id": vehicle.customer_id,
                "customer_name": vehicle.customer.name if vehicle.customer else "",
                "customer_phone": vehicle.customer.phone if vehicle.customer else "",
                "customer_alternative_mobile_number": vehicle.customer.alternative_mobile_number if vehicle.customer else "",
                "has_active_policy": False,
                "active_record": None,
                "has_expired_policy": True,
                "latest_expired_record": latest_data,
                "history_count": len(expired_records),
                "message": (
                    f"Previous insurance for vehicle '{vehicle.vehicle_number}' is expired. "
                    "Creating a new insurance record is allowed, and old records will be kept as history."
                ),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="renew")
    @transaction.atomic
    def renew(self, request, pk=None):
        """
        POST /api/insurance/records/<id>/renew/
        Renew an existing insurance policy:
        - Marks old record as is_active=False (keeps in history).
        - Creates new insurance record with is_active=True.
        - Preserves documents & payments on old record.
        """
        old_record = self.get_object()
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)

        # 1. Archive old record
        old_record.is_active = False
        old_record.save(update_fields=["is_active", "updated_at"])

        # Also ensure no other record for this vehicle is marked active
        InsuranceRecord.objects.filter(vehicle=old_record.vehicle, is_active=True).update(is_active=False)

        # 2. Prepare payload for new record
        # Inherit customer & vehicle if not specified
        if "customer_id" not in data and "customer" not in data:
            data["customer_id"] = old_record.customer_id
        if "vehicle_id" not in data and "vehicle" not in data and "vehicle_number" not in data:
            data["vehicle_id"] = old_record.vehicle_id
            data["vehicle_number"] = old_record.vehicle.vehicle_number
        if "vehicle_type" not in data and old_record.vehicle:
            data["vehicle_type"] = old_record.vehicle.vehicle_type
        if "insurance_company_id" not in data and "insurance_company" not in data:
            data["insurance_company_id"] = old_record.insurance_company_id
        if "alternative_mobile_number" not in data and old_record.alternative_mobile_number:
            data["alternative_mobile_number"] = old_record.alternative_mobile_number

        # Auto-suggest dates if not provided
        today = timezone.localdate()
        if "policy_start_date" not in data or not data["policy_start_date"]:
            if old_record.policy_expiry_date and old_record.policy_expiry_date >= today:
                data["policy_start_date"] = str(old_record.policy_expiry_date + timedelta(days=1))
            else:
                data["policy_start_date"] = str(today)

        if "policy_expiry_date" not in data or not data["policy_expiry_date"]:
            start = datetime.date.fromisoformat(str(data["policy_start_date"]))
            try:
                data["policy_expiry_date"] = str(start.replace(year=start.year + 1))
            except ValueError:
                data["policy_expiry_date"] = str(start + timedelta(days=365))

        if "total_premium" not in data or not data["total_premium"]:
            data["total_premium"] = str(old_record.total_premium)

        data["is_renewal"] = True

        serializer = InsuranceRecordCreateUpdateSerializer(
            data=data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        new_record = serializer.save()

        # Auto WhatsApp Notification Trigger on Renewal
        try:
            from whatsapp_integration.models import WhatsAppConfig
            from whatsapp_integration.services import WhatsAppClient

            wa_cfg = WhatsAppConfig.get_config()
            if wa_cfg.is_enabled and wa_cfg.auto_send_policy_creation:
                WhatsAppClient.send_policy_issued_notification(new_record, async_send=True)
        except Exception:
            pass

        detail_serializer = InsuranceRecordDetailSerializer(
            new_record, context={"request": request}
        )
        return Response(
            {
                "message": f"Policy renewed successfully. Previous policy #{old_record.policy_number} has been archived to history.",
                "data": detail_serializer.data,
                "previous_record_id": old_record.id,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="vehicle-history")
    def vehicle_history(self, request, pk=None):
        """
        GET /api/insurance/records/<id>/vehicle-history/
        Returns all policies for the vehicle associated with this record.
        """
        record = self.get_object()
        records = (
            InsuranceRecord.objects.select_related(
                "customer", "vehicle", "insurance_company"
            )
            .prefetch_related("documents", "payments")
            .filter(vehicle=record.vehicle)
            .order_by("-policy_expiry_date", "-id")
        )
        serializer = InsuranceRecordListSerializer(
            records, many=True, context={"request": request}
        )
        return Response(
            {
                "vehicle_id": record.vehicle_id,
                "vehicle_number": record.vehicle.vehicle_number,
                "total_records": records.count(),
                "records": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @action(
        detail=True,
        methods=["get", "post"],
        url_path="documents",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def documents(self, request, pk=None):
        """
        GET  /api/insurance/records/<id>/documents/ -> List documents for this record
        POST /api/insurance/records/<id>/documents/ -> Upload document to this record
        """
        record = self.get_object()
        if request.method == "GET":
            docs = record.documents.all()
            serializer = InsuranceDocumentSerializer(
                docs, many=True, context={"request": request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)

        # POST Upload
        file = request.FILES.get("file") or request.FILES.get("document")
        if not file:
            return Response(
                {"file": ["No file provided."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document_name = (
            request.data.get("document_name")
            or request.data.get("name")
            or file.name
        )
        doc = InsuranceDocument.objects.create(
            record=record,
            file=file,
            document_name=document_name,
        )
        serializer = InsuranceDocumentSerializer(doc, context={"request": request})
        return Response(
            {
                "message": "Document uploaded successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["delete"],
        url_path=r"documents/(?P<document_id>[^/.]+)",
    )
    def delete_document(self, request, pk=None, document_id=None):
        """
        DELETE /api/insurance/records/<id>/documents/<document_id>/
        """
        record = self.get_object()
        doc = get_object_or_404(InsuranceDocument, pk=document_id, record=record)
        doc.delete()
        return Response(
            {"message": "Document deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get", "post"], url_path="payments")
    def payments(self, request, pk=None):
        """
        GET  /api/insurance/records/<id>/payments/ -> List payments for this record
        POST /api/insurance/records/<id>/payments/ -> Add a payment to this record
        """
        record = self.get_object()
        from payments.serializers import PaymentSerializer

        if request.method == "GET":
            payments_qs = record.payments.all().order_by("-payment_date", "-created_at")
            serializer = PaymentSerializer(payments_qs, many=True, context={"request": request})

            if request.query_params.get("format") == "summary" or request.query_params.get("summary") == "true":
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

            return Response(serializer.data, status=status.HTTP_200_OK)

        # POST
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data["insurance_record_id"] = record.id
        serializer = PaymentSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(insurance_record=record)
        record.refresh_from_db()

        # Auto WhatsApp Payment Receipt Trigger
        try:
            from whatsapp_integration.models import WhatsAppConfig
            from whatsapp_integration.services import WhatsAppClient

            wa_cfg = WhatsAppConfig.get_config()
            if wa_cfg.is_enabled and wa_cfg.auto_send_payment_receipt:
                payment_inst = serializer.instance
                if payment_inst:
                    WhatsAppClient.send_payment_received_notification(payment_inst, async_send=True)
        except Exception:
            pass

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

    @action(detail=True, methods=["delete"], url_path=r"payments/(?P<payment_id>[^/.]+)")
    def delete_payment(self, request, pk=None, payment_id=None):
        """
        DELETE /api/insurance/records/<id>/payments/<payment_id>/
        """
        record = self.get_object()
        payment = get_object_or_404(record.payments.all(), pk=payment_id)
        payment.delete()
        return Response(
            {"message": "Payment deleted successfully."},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="payment-history")
    def payment_history(self, request, pk=None):
        """
        GET /api/insurance/records/<id>/payment-history/
        """
        record = self.get_object()
        from payments.serializers import PaymentSerializer
        serializer = PaymentSerializer(
            record.payments.all().order_by("-payment_date", "-created_at"),
            many=True,
            context={"request": request},
        )
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


class InsuranceDocumentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Direct Insurance Documents API:
    - POST   /api/insurance/documents/      -> Upload Document (with record or record_id)
    - GET    /api/insurance/documents/      -> List Documents (?record_id=<id>)
    - GET    /api/insurance/documents/<id>/ -> Retrieve Document
    - DELETE /api/insurance/documents/<id>/ -> Delete Document
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InsuranceDocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = InsuranceDocument.objects.select_related("record").all()
        record_id = self.request.query_params.get(
            "record_id"
        ) or self.request.query_params.get("record")
        if record_id:
            queryset = queryset.filter(record_id=record_id)
        return queryset.order_by("-uploaded_at")

    def create(self, request, *args, **kwargs):
        record_id = request.data.get("record_id") or request.data.get("record")
        if not record_id:
            return Response(
                {"record_id": ["Insurance record ID is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record = get_object_or_404(InsuranceRecord, pk=record_id)
        file = request.FILES.get("file") or request.FILES.get("document")
        if not file:
            return Response(
                {"file": ["No file provided."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        document_name = (
            request.data.get("document_name")
            or request.data.get("name")
            or file.name
        )
        doc = InsuranceDocument.objects.create(
            record=record,
            file=file,
            document_name=document_name,
        )
        serializer = self.get_serializer(doc, context={"request": request})
        return Response(
            {
                "message": "Document uploaded successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(
            {"message": "Document deleted successfully."},
            status=status.HTTP_200_OK,
        )
