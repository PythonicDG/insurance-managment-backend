from rest_framework import serializers
from .models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone",
            "vehicle_type",
            "vehicle_number",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_vehicle_number(self, value):
        normalized = Vehicle.normalize_vehicle_number(value)
        if not normalized:
            raise serializers.ValidationError("Vehicle number cannot be empty.")

        instance = getattr(self, "instance", None)
        qs = Vehicle.objects.filter(vehicle_number__iexact=normalized)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A vehicle with this number already exists.")

        return normalized

    def validate_vehicle_type(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Vehicle type cannot be empty.")
        return trimmed
