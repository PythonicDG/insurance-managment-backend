from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Customer
from .serializers import CustomerDetailSerializer, CustomerSerializer
from vehicles.serializers import VehicleSerializer


class CustomerViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Customers ViewSet:
    - GET /api/customers/ (List + Search)
    - GET /api/customers/<id>/ (Customer Details)
    - PUT/PATCH /api/customers/<id>/ (Update Customer Details)
    - GET /api/customers/<id>/vehicles/ (Get Customer Vehicles)

    * NOTE: POST (Manual create) is disabled; customers are created automatically via phone lookup / insurance flow.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Customer.objects.all().prefetch_related("vehicles")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CustomerDetailSerializer
        return CustomerSerializer

    @action(detail=True, methods=["get"], url_path="vehicles")
    def vehicles(self, request, pk=None):
        """Returns all vehicles owned by this customer."""
        customer = self.get_object()
        customer_vehicles = customer.vehicles.all().order_by("-created_at")
        serializer = VehicleSerializer(customer_vehicles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
