from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    ProfileView,
    ChangePasswordView,
    PingSessionView,
)

urlpatterns = [
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