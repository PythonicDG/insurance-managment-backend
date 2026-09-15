from rest_framework import serializers
from .models import Customer
from vehicles.models import Vehicle


class CustomerVehicleSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = [
            "id",
            "vehicle_type",
            "vehicle_number",
            "created_at",
            "updated_at",
        ]


class CustomerSerializer(serializers.ModelSerializer):
    vehicles_count = serializers.IntegerField(source="vehicles.count", read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "address",
            "vehicles_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "vehicles_count", "created_at", "updated_at"]

    def validate_phone(self, value):
        normalized = Customer.normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError("Phone number cannot be empty.")

        instance = getattr(self, "instance", None)
        qs = Customer.objects.filter(phone=normalized)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A customer with this phone number already exists.")

        return normalized


class CustomerDetailSerializer(CustomerSerializer):
    vehicles = CustomerVehicleSummarySerializer(many=True, read_only=True)

    class Meta(CustomerSerializer.Meta):
        fields = CustomerSerializer.Meta.fields + ["vehicles"]
