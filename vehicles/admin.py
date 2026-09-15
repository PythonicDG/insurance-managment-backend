from django.contrib import admin
from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["id", "vehicle_number", "vehicle_type", "customer", "created_at"]
    search_fields = ["vehicle_number", "customer__name", "customer__phone"]
    list_filter = ["vehicle_type", "created_at"]
    ordering = ["-created_at"]
