from config.admin import SoftDeleteAdmin
from django.contrib import admin
from django.forms.models import BaseInlineFormSet

from django.core.exceptions import ValidationError

from .models import UploadColumn, UploadReceipt, UploadTemplate
from .schema import FIELDS
from .schema import validate_columns


class UploadColumnFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        columns = []
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                columns.append(form.instance)
        validate_columns(self.instance.target, columns)
        from .services import convert
        for column in columns:
            if column.is_active and column.default_value.strip():
                try:
                    convert(column.default_value, FIELDS[self.instance.target][column.field_name][1])
                except (ValueError, TypeError) as exc:
                    raise ValidationError(f"Invalid default for '{column.column_name}': {exc}")


class UploadColumnInline(admin.TabularInline):
    model = UploadColumn
    formset = UploadColumnFormSet
    extra = 1
    fields = ["position", "column_name", "field_name", "aliases", "is_required", "default_value", "is_active"]


@admin.register(UploadTemplate)
class UploadTemplateAdmin(SoftDeleteAdmin):
    list_display = ["name", "target", "is_active", "updated_at"]
    list_filter = ["target", "is_active"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [UploadColumnInline]

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (["target"] if obj else [])


@admin.register(UploadReceipt)
class UploadReceiptAdmin(SoftDeleteAdmin):
    list_display = ["template", "user", "created_count", "skipped_count", "created_at"]
    readonly_fields = ["template", "user", "created_count", "skipped_count", "created_at", "token_hash"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
