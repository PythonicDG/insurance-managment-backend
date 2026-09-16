from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/customers/", include("customers.urls")),
    path("api/vehicles/", include("vehicles.urls")),
    path("api/insurance/", include("insurance.urls")),
    path("api/payments/", include("payments.urls")),
    path("api/settings/", include("settings_app.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)