from django.urls import path
from .views import (
    BusinessSettingsView,
    RemoveLogoView,
    NotifyExportView,
    TestEmailView,
    VerifyExportPinView,
    RequestPinOtpView,
    SetExportPinView,
)

urlpatterns = [
    path("", BusinessSettingsView.as_view(), name="business-settings"),
    path("remove-logo/", RemoveLogoView.as_view(), name="remove-logo"),
    path("notify-export/", NotifyExportView.as_view(), name="notify-export"),
    path("test-email/", TestEmailView.as_view(), name="test-email"),
    path("verify-export-pin/", VerifyExportPinView.as_view(), name="verify-export-pin"),
    path("pin/request-otp/", RequestPinOtpView.as_view(), name="pin-request-otp"),
    path("pin/set/", SetExportPinView.as_view(), name="pin-set"),
]


