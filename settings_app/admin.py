from config.admin import SoftDeleteAdmin
from django.contrib import admin
from .models import BusinessSettings


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(SoftDeleteAdmin):
    list_display = ("business_name", "phone", "email", "updated_at")
