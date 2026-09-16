from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Customer
from .serializers import CustomerDetailSerializer, CustomerSerializer
from vehicles.serializers import VehicleSerializer


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
    - GET /api/customers/<id>/ (Customer Details)
    - PUT/PATCH /api/customers/<id>/ (Update Customer Details)
    - GET /api/customers/<id>/vehicles/ (Get Customer Vehicles)
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

    @action(detail=True, methods=["get"], url_path="vehicles")
    def vehicles(self, request, pk=None):
        """Returns all vehicles owned by this customer."""
        customer = self.get_object()
        customer_vehicles = customer.vehicles.all().order_by("-created_at")
        serializer = VehicleSerializer(customer_vehicles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
