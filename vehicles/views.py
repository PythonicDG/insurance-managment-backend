from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Vehicle
from .serializers import VehicleSerializer


class VehicleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Vehicles ViewSet:
    - GET /api/vehicles/?customer_id=<id> (Get Customer Vehicles / Filter by customer)
    - GET /api/vehicles/customer/<customer_id>/ (Get Customer Vehicles)
    - GET /api/vehicles/<id>/ (Retrieve Vehicle Details)
    - PUT/PATCH /api/vehicles/<id>/ (Update Vehicle Details)
    - DELETE /api/vehicles/<id>/ (Delete Vehicle)

    * NOTE: POST (Manual create) is disabled; vehicles are created through the insurance record flow.
    """

    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Vehicle.objects.select_related("customer").all()

        customer_id = self.request.query_params.get(
            "customer_id"
        ) or self.request.query_params.get("customer")
        if customer_id:
            queryset = queryset.filter(customer_id=customer_id)

        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(vehicle_number__icontains=search)
                | Q(vehicle_type__icontains=search)
                | Q(customer__name__icontains=search)
                | Q(customer__phone__icontains=search)
            )

        return queryset.order_by("-created_at")

    @action(detail=False, methods=["get"], url_path=r"customer/(?P<customer_id>[^/.]+)")
    def customer_vehicles(self, request, customer_id=None):
        """Get all vehicles for a specific customer: GET /api/vehicles/customer/<customer_id>/"""
        vehicles = self.get_queryset().filter(customer_id=customer_id)
        serializer = self.get_serializer(vehicles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
