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
