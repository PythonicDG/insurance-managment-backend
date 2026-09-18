from rest_framework import serializers
from .models import Customer
from vehicles.models import Vehicle


class CustomerVehicleSummarySerializer(serializers.ModelSerializer):
    records_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "vehicle_type",
            "vehicle_number",
            "records_count",
            "created_at",
            "updated_at",
        ]


class CustomerVehicleDetailSerializer(serializers.ModelSerializer):
    records_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "vehicle_type",
            "vehicle_number",
            "records_count",
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
    vehicles = CustomerVehicleDetailSerializer(many=True, read_only=True)
    total_records = serializers.IntegerField(read_only=True, default=0)
    total_premium = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, default=0.00
    )
    total_paid = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, default=0.00
    )
    total_outstanding = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, default=0.00
    )

    class Meta(CustomerSerializer.Meta):
        fields = CustomerSerializer.Meta.fields + [
            "vehicles",
            "total_records",
            "total_premium",
            "total_paid",
            "total_outstanding",
        ]


class CustomerDocumentSerializer(serializers.ModelSerializer):
    record_id = serializers.IntegerField(source="record.id", read_only=True)
    policy_number = serializers.CharField(source="record.policy_number", read_only=True)
    vehicle_number = serializers.CharField(source="record.vehicle.vehicle_number", read_only=True)
    company_name = serializers.CharField(source="record.insurance_company.name", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        from insurance.models import InsuranceDocument
        model = InsuranceDocument
        fields = [
            "id",
            "record_id",
            "policy_number",
            "vehicle_number",
            "company_name",
            "document_name",
            "file",
            "file_url",
            "file_size",
            "uploaded_at",
        ]
        read_only_fields = fields

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
