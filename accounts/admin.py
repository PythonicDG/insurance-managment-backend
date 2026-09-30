from config.admin import SoftDeleteAdmin
from django.contrib import admin
from .models import UserSessionActivity


@admin.register(UserSessionActivity)
class UserSessionActivityAdmin(SoftDeleteAdmin):
    list_display = ("user", "last_activity")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("last_activity",)

