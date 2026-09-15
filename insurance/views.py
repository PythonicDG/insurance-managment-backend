from datetime import timedelta
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
            .prefetch_related("documents")
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
                | Q(customer__email__icontains=search)
                | Q(vehicle__vehicle_number__icontains=search)
                | Q(vehicle__vehicle_type__icontains=search)
                | Q(insurance_company__name__icontains=search)
                | Q(remarks__icontains=search)
            )

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

        # 5. Status Filter (active / expired / expiring_soon)
        record_status = params.get("status", "").strip().lower()
        today = timezone.localdate()
        if record_status == "active":
            queryset = queryset.filter(policy_expiry_date__gte=today)
        elif record_status == "expired":
            queryset = queryset.filter(policy_expiry_date__lt=today)
        elif record_status in ["expiring_soon", "expiring"]:
            thirty_days_later = today + timedelta(days=30)
            queryset = queryset.filter(
                policy_expiry_date__gte=today,
                policy_expiry_date__lte=thirty_days_later,
            )

        # 6. Sorting / Ordering
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
