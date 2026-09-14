from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import BusinessSettings
from .serializers import BusinessSettingsSerializer


class BusinessSettingsView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        settings_obj, _ = BusinessSettings.objects.get_or_create(
            id=1,
            defaults={
                "business_name": "InsureLedger Agency",
                "phone": "",
                "email": "",
                "address": "",
            },
        )
        return settings_obj

    def get(self, request):
        settings_obj = self.get_object()
        serializer = BusinessSettingsSerializer(
            settings_obj, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        settings_obj = self.get_object()
        serializer = BusinessSettingsSerializer(
            settings_obj,
            data=request.data,
            partial=False,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "Settings updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        settings_obj = self.get_object()
        serializer = BusinessSettingsSerializer(
            settings_obj,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "Settings updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class RemoveLogoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        settings_obj, _ = BusinessSettings.objects.get_or_create(id=1)
        if settings_obj.logo:
            settings_obj.logo.delete(save=False)
            settings_obj.logo = None
            settings_obj.save(update_fields=["logo", "updated_at"])

        serializer = BusinessSettingsSerializer(
            settings_obj, context={"request": request}
        )
        return Response(
            {
                "message": "Logo removed successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )
