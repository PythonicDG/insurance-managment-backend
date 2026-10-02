from django.urls import path
from .change_verification import RequestChangeOtpView, VerifyChangeOtpView, ChangeContactView

from .views import (
    LoginView,
    LogoutView,
    ProfileView,
    ChangePasswordView,
    PingSessionView,
)

urlpatterns = [
    path("change/request-otp/", RequestChangeOtpView.as_view(), name="request-change-otp"),
    path("change/verify-otp/", VerifyChangeOtpView.as_view(), name="verify-change-otp"),
    path("change/contact/", ChangeContactView.as_view(), name="change-contact"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("ping/", PingSessionView.as_view(), name="ping-session"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path(
        "change-password/",
        ChangePasswordView.as_view(),
        name="change-password"
    ),
]
