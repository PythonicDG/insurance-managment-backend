from rest_framework import serializers
from .models import WhatsAppConfig, WhatsAppMessageLog


class WhatsAppConfigSerializer(serializers.ModelSerializer):
    has_access_token = serializers.SerializerMethodField()
    masked_token = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppConfig
        fields = [
            "id",
            "is_enabled",
            "test_mode",
            "test_phone_number",
            "phone_number_id",
            "waba_id",
            "access_token",
            "has_access_token",
            "masked_token",
            "api_version",
            "default_country_code",
            "policy_template_name",
            "policy_template_language",
            "payment_template_name",
            "payment_template_language",
            "webhook_verify_token",
            "auto_send_policy_creation",
            "auto_send_payment_receipt",
            "updated_at",
        ]
        extra_kwargs = {
            "access_token": {"write_only": False},
        }

    def get_has_access_token(self, obj) -> bool:
        return bool(obj.access_token and obj.access_token.strip())

    def get_masked_token(self, obj) -> str:
        tok = (obj.access_token or "").strip()
        if not tok:
            return ""
        if len(tok) <= 12:
            return "******"
        return f"{tok[:6]}...{tok[-4:]}"

    def update(self, instance, validated_data):
        # If access_token in validated_data is empty string or only stars, do not overwrite existing token
        token = validated_data.get("access_token")
        if token is not None and (token.strip() == "" or "*" in token):
            validated_data.pop("access_token", None)
        return super().update(instance, validated_data)


class WhatsAppMessageLogSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True, default="")
    policy_number = serializers.CharField(source="insurance_record.policy_number", read_only=True, default="")
    vehicle_number = serializers.CharField(source="insurance_record.vehicle.vehicle_number", read_only=True, default="")
    formatted_date = serializers.DateTimeField(source="created_at", format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = WhatsAppMessageLog
        fields = [
            "id",
            "recipient_phone",
            "message_type",
            "template_name",
            "parameters",
            "status",
            "wamid",
            "request_payload",
            "response_payload",
            "error_message",
            "is_test",
            "customer",
            "customer_name",
            "insurance_record",
            "policy_number",
            "vehicle_number",
            "payment",
            "formatted_date",
            "created_at",
            "updated_at",
        ]


class WhatsAppTestMessageSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=True, max_length=25)
    test_type = serializers.ChoiceField(
        choices=["template_policy", "template_payment", "direct_text"],
        default="direct_text",
    )
    custom_text = serializers.CharField(required=False, allow_blank=True, default="")
