import json

from django.apps import apps
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import ActivityLog
from .presentation import OBJECT_NAMES


class RecordTypeFilter(admin.SimpleListFilter):
    title = "record type"
    parameter_name = "record_type"

    def lookups(self, request, model_admin):
        labels = model_admin.get_queryset(request).order_by().values_list("object_type", flat=True).distinct()
        return sorted(((label, OBJECT_NAMES.get(label, label)) for label in labels), key=lambda item: item[1])

    def queryset(self, request, queryset):
        return queryset.filter(object_type=self.value()) if self.value() else queryset


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("date_and_time", "staff_user", "action_label", "activity", "device", "ip_address")
    list_display_links = ("activity",)
    list_filter = ("action", RecordTypeFilter, "occurred_at")
    search_fields = ("search_text", "actor_username", "device", "ip_address", "=actor_id", "=object_id", "=request_id")
    search_help_text = "Search customer name, phone, policy number, vehicle number, staff username, action, browser or IP address."
    date_hierarchy = "occurred_at"
    readonly_fields = (
        "date_and_time", "staff_user", "action_label", "activity", "object_label", "customer_name", "customer_phone",
        "policy_number", "vehicle_number", "device", "ip_address", "change_details", "raw_changes",
        "object_type", "object_id", "actor_id", "request_id", "request_method", "request_path", "source", "user_agent",
    )
    fieldsets = (
        ("Activity", {"fields": ("date_and_time", "staff_user", "action_label", "activity", "object_label")}),
        ("Customer and insurance", {"fields": ("customer_name", "customer_phone", "policy_number", "vehicle_number")}),
        ("Computer / device", {"fields": ("device", "ip_address"),
                               "description": "Browser and operating system reported by the device, plus its network IP address."}),
        ("What changed", {"fields": ("change_details",)}),
        ("Technical details", {"classes": ("collapse",), "fields": (
            "object_type", "object_id", "actor_id", "request_id", "request_method", "request_path", "source", "user_agent", "raw_changes",
        )}),
    )
    actions = None
    list_per_page = 50
    show_full_result_count = False
    empty_value_display = "-"

    @admin.display(description="Date and time", ordering="occurred_at")
    def date_and_time(self, obj):
        value = timezone.localtime(obj.occurred_at) if timezone.is_aware(obj.occurred_at) else obj.occurred_at
        return value.strftime("%d %b %Y, %I:%M:%S %p %Z")

    @admin.display(description="Username", ordering="actor_username")
    def staff_user(self, obj):
        return obj.actor_username or "System (automatic)"

    @admin.display(description="Action", ordering="action")
    def action_label(self, obj):
        if obj.action == "create" and obj.object_type == "payments.payment":
            return "Payment collected"
        return {"create": "Added", "update": "Edited", "delete": "Deleted", "restore": "Restored"}.get(
            obj.action, obj.get_action_display()
        )

    @admin.display(description="Activity", ordering="summary")
    def activity(self, obj):
        return obj.summary or f"{obj.get_action_display()} {OBJECT_NAMES.get(obj.object_type, obj.object_type)} #{obj.object_id}"

    @admin.display(description="Changes")
    def change_details(self, obj):
        if not obj.changes:
            return "No record fields changed."
        try:
            model = apps.get_model(obj.object_type)
        except (LookupError, ValueError):
            model = None

        def label(name):
            if name == "deleted_at":
                return "Deleted on"
            if model:
                for field in model._meta.fields:
                    if field.attname == name:
                        return str(field.verbose_name).capitalize() + (" (record ID)" if field.is_relation else "")
            return name.replace("_", " ").capitalize()

        def value(data):
            if data is None or data == "":
                return "-"
            if isinstance(data, bool):
                return "Yes" if data else "No"
            if isinstance(data, (dict, list)):
                return json.dumps(data, ensure_ascii=False)
            return str(data)

        rows = format_html_join("", "<tr><th>{}</th><td>{}</td><td>{}</td></tr>", (
            (label(name), value(change.get("before")), value(change.get("after")))
            for name, change in sorted(obj.changes.items())
        ))
        return format_html(
            "<table style='width:100%;white-space:normal;overflow-wrap:anywhere'>"
            "<thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead><tbody>{}</tbody></table>", rows
        )

    @admin.display(description="Raw field changes")
    def raw_changes(self, obj):
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", json.dumps(obj.changes, indent=2, ensure_ascii=False))

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
