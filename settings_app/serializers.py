from config.serializers import SoftDeleteModelSerializer
from rest_framework import serializers
from .models import BusinessSettings


class BusinessSettingsSerializer(SoftDeleteModelSerializer):
    logo_url = serializers.SerializerMethodField()
    is_export_pin_set = serializers.SerializerMethodField()

    class Meta:
        model = BusinessSettings
        fields = [
            "id",
            "business_name",
            "logo",
            "logo_url",
            "phone",
            "email",
            "address",
            "is_export_pin_set",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "logo_url", "is_export_pin_set"]
        extra_kwargs = {
            "logo": {"required": False, "allow_null": True},
        }

    def get_logo_url(self, obj):
        if obj.logo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        return None

    def validate(self, attrs):
        # Contact changes must go through the OTP endpoint. Allow first-time
        # email setup only when there is no existing verification recipient.
        if self.instance:
            request = self.context.get("request")
            protected = bool(self.instance.email or (request and request.user.email))
            for field in ("email", "phone"):
                if protected and field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({"message": "Verify an email OTP before changing your email or phone number."})
        return attrs

    def get_is_export_pin_set(self, obj):
        return bool(obj.export_pin)

