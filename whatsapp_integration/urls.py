from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    WhatsAppConfigView,
    WhatsAppMessageLogViewSet,
    WhatsAppResendLogView,
    WhatsAppSendPaymentView,
    WhatsAppSendPolicyView,
    WhatsAppTestMessageView,
    WhatsAppWebhookView,
    WhatsAppRenewalView,
    WhatsAppRenewalTestView,
)

router = DefaultRouter()
router.register(r"logs", WhatsAppMessageLogViewSet, basename="whatsapp-logs")

urlpatterns = [
    path("renewals/send-test/", WhatsAppRenewalTestView.as_view(), name="whatsapp-renewal-test"),
    path("records/<int:record_id>/renewal/", WhatsAppRenewalView.as_view(), name="whatsapp-renewal"),
    path("config/", WhatsAppConfigView.as_view(), name="whatsapp-config"),
    path("send-test/", WhatsAppTestMessageView.as_view(), name="whatsapp-send-test"),
    path("webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),
    path("records/<int:record_id>/send/", WhatsAppSendPolicyView.as_view(), name="whatsapp-send-policy"),
    path("payments/<int:payment_id>/send/", WhatsAppSendPaymentView.as_view(), name="whatsapp-send-payment"),
    path("logs/<int:log_id>/resend/", WhatsAppResendLogView.as_view(), name="whatsapp-resend-log"),
    path("", include(router.urls)),
]
