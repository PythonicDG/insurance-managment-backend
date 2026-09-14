from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import InsuranceCompany
from .serializers import InsuranceCompanySerializer


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
