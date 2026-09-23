from django.contrib import admin
from .models import InsuranceCompany, InsuranceDocument, InsuranceRecord


class InsuranceDocumentInline(admin.TabularInline):
    model = InsuranceDocument
    extra = 1
    fields = ("file", "document_name", "file_size", "uploaded_at")
    readonly_fields = ("file_size", "uploaded_at")


@admin.register(InsuranceCompany)
class InsuranceCompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


class PaymentInline(admin.TabularInline):
    from payments.models import Payment
    model = Payment
    extra = 0
    fields = ("amount", "payment_method", "payment_date", "notes", "created_at")
    readonly_fields = ("created_at",)


@admin.register(InsuranceRecord)
class InsuranceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "customer",
        "alternative_mobile_number",
        "vehicle",
        "insurance_company",
        "total_premium",
        "total_paid",
        "outstanding",
        "payment_status",
        "entry_date",
        "policy_start_date",
        "policy_expiry_date",
        "status",
    )
    list_filter = (
        "insurance_company",
        "entry_date",
        "policy_start_date",
        "policy_expiry_date",
    )
    search_fields = (
        "policy_number",
        "alternative_mobile_number",
        "customer__name",
        "customer__phone",
        "customer__alternative_mobile_number",
        "vehicle__vehicle_number",
        "insurance_company__name",
    )
    inlines = [InsuranceDocumentInline, PaymentInline]


@admin.register(InsuranceDocument)
class InsuranceDocumentAdmin(admin.ModelAdmin):
    list_display = ("document_name", "record", "file_size", "uploaded_at")
    search_fields = ("document_name", "record__policy_number")
