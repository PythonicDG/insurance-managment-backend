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
    customer_id = serializers.IntegerField(source="id", read_only=True)
    vehicles_count = serializers.IntegerField(source="vehicles.count", read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "customer_id",
            "name",
            "phone",
            "email",
            "address",
            "vehicles_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "customer_id", "vehicles_count", "created_at", "updated_at"]

    def validate_phone(self, value):
        normalized = Customer.normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError("Phone number cannot be empty.")
        return normalized


class CustomerDetailSerializer(CustomerSerializer):
    vehicles = CustomerVehicleSummarySerializer(many=True, read_only=True)

    class Meta(CustomerSerializer.Meta):
        fields = CustomerSerializer.Meta.fields + ["vehicles"]
