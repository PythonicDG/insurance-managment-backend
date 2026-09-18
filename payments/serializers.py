from decimal import Decimal
from rest_framework import serializers
from insurance.models import InsuranceRecord
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    insurance_record_id = serializers.PrimaryKeyRelatedField(
        queryset=InsuranceRecord.objects.all(),
        source="insurance_record",
        required=False,
    )
    # Support payment_mode alias from frontend
    payment_mode = serializers.CharField(source="payment_method", required=False)
    # Support date alias from frontend
    date = serializers.DateField(source="payment_date", required=False)
    # Support note / remark alias from frontend
    note = serializers.CharField(source="notes", required=False, allow_blank=True)
    status = serializers.CharField(read_only=True)
    payment_status = serializers.CharField(source="insurance_record.payment_status", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "insurance_record",
            "insurance_record_id",
            "amount",
            "payment_method",
            "payment_mode",
            "payment_date",
            "date",
            "notes",
            "note",
            "status",
            "payment_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "insurance_record",
            "status",
            "payment_status",
            "created_at",
            "updated_at",
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy() if hasattr(data, "copy") else dict(data)
        if "payment_mode" in mutable_data and "payment_method" not in mutable_data:
            mutable_data["payment_method"] = mutable_data["payment_mode"]
        if "note" in mutable_data and "notes" not in mutable_data:
            mutable_data["notes"] = mutable_data["note"]
        elif "remark" in mutable_data and "notes" not in mutable_data:
            mutable_data["notes"] = mutable_data["remark"]
        if "date" in mutable_data and "payment_date" not in mutable_data:
            mutable_data["payment_date"] = mutable_data["date"]
        return super().to_internal_value(mutable_data)

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Payment amount must be greater than zero.")
        return value


class LedgerRecordSerializer(serializers.ModelSerializer):
    customer_id = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    customer_email = serializers.CharField(source="customer.email", read_only=True)
    vehicle_id = serializers.IntegerField(source="vehicle.id", read_only=True)
    vehicle_number = serializers.CharField(source="vehicle.vehicle_number", read_only=True)
    vehicle_type = serializers.CharField(source="vehicle.vehicle_type", read_only=True)
    insurance_company_id = serializers.IntegerField(source="insurance_company.id", read_only=True)
    insurance_company_name = serializers.CharField(source="insurance_company.name", read_only=True)
    paid_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, source="annotated_paid", read_only=True
    )
    outstanding = serializers.DecimalField(
        max_digits=12, decimal_places=2, source="annotated_outstanding", read_only=True
    )
    status = serializers.CharField(source="annotated_status", read_only=True)
    payment_status = serializers.CharField(read_only=True)
    payments_count = serializers.IntegerField(source="payments.count", read_only=True)

    class Meta:
        model = InsuranceRecord
        fields = [
            "id",
            "policy_number",
            "entry_date",
            "policy_start_date",
            "policy_expiry_date",
            "total_premium",
            "paid_amount",
            "outstanding",
            "status",
            "payment_status",
            "customer_id",
            "customer_name",
            "customer_phone",
            "customer_email",
            "vehicle_id",
            "vehicle_number",
            "vehicle_type",
            "insurance_company_id",
            "insurance_company_name",
            "payments_count",
            "remarks",
            "created_at",
            "updated_at",
        ]


class LedgerSummarySerializer(serializers.Serializer):
    total_outstanding = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_customers_pending = serializers.IntegerField()
    total_received = serializers.DecimalField(max_digits=14, decimal_places=2)
    total_premium = serializers.DecimalField(max_digits=14, decimal_places=2)

