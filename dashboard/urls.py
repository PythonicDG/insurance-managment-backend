from django.urls import path
from .views import DashboardSummaryView, DashboardBusinessSummaryView

urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("business-summary/", DashboardBusinessSummaryView.as_view(), name="dashboard-business-summary"),
]
