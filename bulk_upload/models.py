from config.soft_delete import SoftDeleteModel
from django.core.exceptions import ValidationError
from django.db import models

from .schema import FIELD_CHOICES, FIELDS, normalize_header


class UploadTemplate(SoftDeleteModel):
    name = models.CharField(max_length=150, unique=True)
    target = models.CharField(max_length=20, choices=[("customers", "Customers"), ("insurance", "Insurance records")])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        ordering = ["name"]
        verbose_name = "Bulk upload template"

    def __str__(self):
        return self.name


class UploadColumn(SoftDeleteModel):
    template = models.ForeignKey(UploadTemplate, on_delete=models.CASCADE, related_name="columns")
    column_name = models.CharField(max_length=150, help_text="Header displayed in the downloadable Excel template.")
    field_name = models.CharField(max_length=60, choices=FIELD_CHOICES)
    aliases = models.TextField(blank=True, help_text="Alternative Excel headers, one per line.")
    is_required = models.BooleanField(default=False)
    default_value = models.CharField(max_length=255, blank=True, help_text="Used when the column or cell is empty. Dates: YYYY-MM-DD.")
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        ordering = ["position", "id"]
        verbose_name = "Upload column"

    def __str__(self):
        return self.column_name

    def clean(self):
        super().clean()
        self.column_name = self.column_name.strip()
        if not normalize_header(self.column_name):
            raise ValidationError({"column_name": "Enter a column name."})
        if self.template_id and self.field_name not in FIELDS.get(self.template.target, {}):
            raise ValidationError({"field_name": "This field is not available for the selected template type."})


class UploadReceipt(SoftDeleteModel):
    """Prevents a successful preview from being imported twice."""
    token_hash = models.CharField(max_length=64, unique=True)
    template = models.ForeignKey(UploadTemplate, on_delete=models.PROTECT)
    user = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    created_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
