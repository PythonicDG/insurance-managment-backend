from django.urls import path
from .views import BusinessSettingsView, RemoveLogoView

urlpatterns = [
    path("", BusinessSettingsView.as_view(), name="business-settings"),
    path("remove-logo/", RemoveLogoView.as_view(), name="remove-logo"),
]
