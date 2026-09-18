from decimal import Decimal
from django.db.models import Count, Q, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Customer
from .serializers import (
    CustomerDetailSerializer,
    CustomerDocumentSerializer,
    CustomerSerializer,
    CustomerVehicleDetailSerializer,
)


class CustomerViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Customers ViewSet:
    - GET /api/customers/ (List + Search)
    - POST /api/customers/ (Create Customer)
    - GET /api/customers/<id>/ (Customer Details + KPI Stats)
    - PUT/PATCH /api/customers/<id>/ (Update Customer Details)
    - GET /api/customers/<id>/records/ (Get Customer Insurance Records)
    - GET /api/customers/<id>/vehicles/ (Get Customer Vehicles with records count)
    - GET /api/customers/<id>/documents/ (Get All Documents across customer's records)
    - GET /api/customers/lookup/?phone=<phone> (Lookup Customer by normalized phone)
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Customer.objects.all().prefetch_related("vehicles")
        search = self.request.query_params.get("search", "").strip()
        phone = self.request.query_params.get("phone", "").strip()

        if phone:
            normalized_phone = Customer.normalize_phone(phone)
            if normalized_phone:
                if len(normalized_phone) >= 10:
                    last_10 = normalized_phone[-10:]
                    queryset = queryset.filter(
                        Q(phone=normalized_phone) | Q(phone=last_10) | Q(phone__endswith=last_10)
                    )
                else:
                    queryset = queryset.filter(phone=normalized_phone)

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action in ("retrieve", "lookup"):
            return CustomerDetailSerializer
        return CustomerSerializer

    def retrieve(self, request, *args, **kwargs):
        customer = self.get_object()

        # Compute summary metrics for this customer
        records_qs = customer.insurance_records.all()
        total_records = records_qs.count()
        total_premium = records_qs.aggregate(total=Sum("total_premium"))["total"] or Decimal("0.00")

        from payments.models import Payment
        total_paid = Payment.objects.filter(
            insurance_record__customer=customer
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        total_outstanding = max(
            Decimal("0.00"), Decimal(str(total_premium)) - Decimal(str(total_paid))
        )

        customer_vehicles = customer.vehicles.annotate(
            records_count=Count("insurance_records")
        ).order_by("-created_at")

        serializer = self.get_serializer(customer)
        data = dict(serializer.data)
        data["total_records"] = total_records
        data["total_premium"] = str(total_premium)
        data["total_paid"] = str(total_paid)
        data["total_outstanding"] = str(total_outstanding)
        data["vehicles"] = CustomerVehicleDetailSerializer(customer_vehicles, many=True).data
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="lookup")
    def lookup(self, request):
        """
        Lookup customer(s) by normalized phone number:
        GET /api/customers/lookup/?phone=<phone>
        """
        phone = request.query_params.get("phone", "").strip()
        if not phone:
            return Response(
                {"error": "Phone query parameter is required.", "found": False, "customers": []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized = Customer.normalize_phone(phone)
        if not normalized:
            return Response(
                {"error": "Valid phone number is required.", "found": False, "customers": []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Primary search on normalized phone
        queryset = Customer.objects.filter(phone=normalized).prefetch_related("vehicles")

        # Fallback to match by last 10 digits if standard 10+ digits provided
        if not queryset.exists() and len(normalized) >= 10:
            last_10 = normalized[-10:]
            queryset = Customer.objects.filter(
                Q(phone=last_10) | Q(phone__endswith=last_10)
            ).prefetch_related("vehicles")

        queryset = queryset.order_by("-created_at")
        serializer = CustomerDetailSerializer(queryset, many=True)
        data = serializer.data

        return Response(
            {
                "phone": normalized,
                "found": len(data) > 0,
                "count": len(data),
                "customers": data,
                "customer": data[0] if data else None,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="records")
    def records(self, request, pk=None):
        """Returns all insurance records for this customer."""
        customer = self.get_object()
        from insurance.serializers import InsuranceRecordListSerializer

        ordering = request.query_params.get("ordering", "-entry_date")
        valid_orderings = [
            "entry_date",
            "-entry_date",
            "total_premium",
            "-total_premium",
            "policy_expiry_date",
            "-policy_expiry_date",
            "created_at",
            "-created_at",
        ]
        if ordering not in valid_orderings:
            ordering = "-entry_date"

        records_qs = (
            customer.insurance_records.select_related(
                "vehicle", "insurance_company", "customer"
            )
            .prefetch_related("documents", "payments")
            .order_by(ordering, "-created_at")
        )
        serializer = InsuranceRecordListSerializer(
            records_qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="vehicles")
    def vehicles(self, request, pk=None):
        """Returns all vehicles owned by this customer with linked records count."""
        customer = self.get_object()
        customer_vehicles = customer.vehicles.annotate(
            records_count=Count("insurance_records")
        ).order_by("-created_at")
        serializer = CustomerVehicleDetailSerializer(customer_vehicles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="documents")
    def documents(self, request, pk=None):
        """Returns all insurance documents for this customer across all records."""
        customer = self.get_object()
        from insurance.models import InsuranceDocument

        docs = (
            InsuranceDocument.objects.filter(record__customer=customer)
            .select_related("record", "record__vehicle", "record__insurance_company")
            .order_by("-uploaded_at")
        )
        serializer = CustomerDocumentSerializer(docs, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)
