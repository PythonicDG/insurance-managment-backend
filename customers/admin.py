from config.admin import SoftDeleteAdmin
from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(SoftDeleteAdmin):
    list_display = ["id", "name", "phone", "alternative_mobile_number", "email", "created_at"]
    search_fields = ["name", "phone", "alternative_mobile_number", "email"]
    list_filter = ["created_at"]
    ordering = ["-created_at"]
