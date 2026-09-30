from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .soft_delete import SoftDeleteModel


class SoftDeleteModelSerializer(serializers.ModelSerializer):
    """Keep archived identifiers reserved, returning validation errors on reuse."""

    def get_fields(self):
        fields = super().get_fields()
        for field in fields.values():
            for validator in field.validators:
                if isinstance(validator, UniqueValidator):
                    model = validator.queryset.model
                    if issubclass(model, SoftDeleteModel):
                        validator.queryset = model.all_objects.all()
        return fields
