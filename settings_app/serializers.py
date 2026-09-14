from rest_framework import serializers
from .models import BusinessSettings


class BusinessSettingsSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "logo_url"]
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
