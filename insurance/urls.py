from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InsuranceCompanyViewSet

router = DefaultRouter()
router.register(r"companies", InsuranceCompanyViewSet, basename="insurance-company")

urlpatterns = [
    path("", include(router.urls)),
]
