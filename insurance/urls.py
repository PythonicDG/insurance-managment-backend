from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import (
    InsuranceCompanyViewSet,
    InsuranceDocumentViewSet,
    InsuranceRecordViewSet,
)

router = DefaultRouter()
router.register(r"companies", InsuranceCompanyViewSet, basename="insurance-company")
router.register(r"records", InsuranceRecordViewSet, basename="insurance-record")
router.register(r"documents", InsuranceDocumentViewSet, basename="insurance-document")

urlpatterns = [
    path("", include(router.urls)),
]
