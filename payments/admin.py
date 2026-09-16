from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "insurance_record",
        "amount",
        "payment_method",
        "payment_date",
        "status",
        "created_at",
    )
    list_filter = ("payment_method", "payment_date", "created_at")
    search_fields = (
        "insurance_record__policy_number",
        "insurance_record__customer__name",
        "insurance_record__customer__phone",
        "notes",
        "payment_method",
    )
    ordering = ("-payment_date", "-created_at")
    readonly_fields = ("created_at", "updated_at")
