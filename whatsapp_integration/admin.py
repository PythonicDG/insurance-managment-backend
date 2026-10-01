from config.admin import SoftDeleteAdmin
from django.contrib import admin
from .models import WhatsAppConfig, WhatsAppMessageLog, RenewalReminderJob, RenewalReminderOptOut


@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(SoftDeleteAdmin):
    list_display = (
        "id",
        "is_enabled",
        "test_mode",
        "test_phone_number",
        "phone_number_id",
        "policy_template_name",
        "payment_template_name",
        "updated_at",
    )
    fieldsets = (
        (
            "Service Status & Test Mode",
            {
                "fields": (
                    "is_enabled",
                    "test_mode",
                    "test_phone_number",
                ),
                "description": "When 'Test Mode' is active, all outgoing messages are redirected to 'Test Phone Number' to safeguard actual customers during testing.",
            },
        ),
        (
            "Meta Cloud API Credentials",
            {
                "fields": (
                    "phone_number_id",
                    "waba_id",
                    "access_token",
                    "api_version",
                    "default_country_code",
                )
            },
        ),
        (
            "Template Settings",
            {
                "fields": (
                    "policy_template_name",
                    "policy_template_language",
                    "payment_template_name",
                    "payment_template_language",
                )
            },
        ),
        (
            "Automation Toggles",
            {
                "fields": (
                    "auto_send_policy_creation",
                    "auto_send_payment_receipt",
                    "webhook_verify_token",
                )
            },
        ),
        ("Renewal reminders", {"fields": ("renewal_enabled", "renewal_send_time", "renewal_skip_sundays",
            "renewal_skip_holidays", "renewal_holidays", "renewal_stages", "renewal_daily_cap", "renewal_language")}),
    )


@admin.register(WhatsAppMessageLog)
class WhatsAppMessageLogAdmin(SoftDeleteAdmin):
    list_display = (
        "id",
        "recipient_phone",
        "message_type",
        "template_name",
        "status",
        "is_test",
        "created_at",
    )
    list_filter = ("status", "message_type", "is_test", "created_at")
    search_fields = (
        "recipient_phone",
        "template_name",
        "wamid",
        "customer__name",
        "insurance_record__policy_number",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "request_payload",
        "response_payload",
        "delivery_events",
    )


@admin.register(RenewalReminderJob)
class RenewalReminderJobAdmin(admin.ModelAdmin):
    list_display = ("id", "record", "stage", "source", "status", "recipient_phone", "attempted_at")
    list_filter = ("status", "stage", "source", "is_test")
    readonly_fields = tuple(field.name for field in RenewalReminderJob._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RenewalReminderOptOut)
class RenewalReminderOptOutAdmin(SoftDeleteAdmin):
    list_display = ("recipient_phone", "created_at")
    readonly_fields = ("created_at",)
