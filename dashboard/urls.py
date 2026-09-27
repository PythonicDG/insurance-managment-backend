from django.urls import path
from .views import (
    DashboardSummaryView,
    DashboardBusinessSummaryView,
    DashboardNotificationsView,
)

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("business-summary/", DashboardBusinessSummaryView.as_view(), name="dashboard-business-summary"),
    path("notifications/", DashboardNotificationsView.as_view(), name="dashboard-notifications"),
]

