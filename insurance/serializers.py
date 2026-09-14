from rest_framework import serializers
from .models import InsuranceCompany


class InsuranceCompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceCompany
        fields = [
            "id",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Company name cannot be empty.")
        
        # Check case-insensitive uniqueness
        instance = getattr(self, "instance", None)
        qs = InsuranceCompany.objects.filter(name__iexact=trimmed)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError("An insurance company with this name already exists.")
            
        return trimmed
