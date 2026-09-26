import json
import logging
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from insurance.models import InsuranceRecord
from payments.models import Payment
from .models import WhatsAppConfig, WhatsAppMessageLog
from .serializers import (
    WhatsAppConfigSerializer,
    WhatsAppMessageLogSerializer,
    WhatsAppTestMessageSerializer,
)
from .services import WhatsAppClient, normalize_phone_number

logger = logging.getLogger(__name__)


class StandardPagination(PageNumberPagination):
    page_size = 15
    page_size_query_param = "page_size"
    max_page_size = 100


class WhatsAppConfigView(APIView):
    """
    GET  /api/whatsapp/config/ -> Fetch current WhatsApp Meta API settings
    PUT  /api/whatsapp/config/ -> Update WhatsApp Meta API settings
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        config = WhatsAppConfig.get_config()
        serializer = WhatsAppConfigSerializer(config)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        config = WhatsAppConfig.get_config()
        serializer = WhatsAppConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "WhatsApp configuration updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class WhatsAppTestMessageView(APIView):
    """
    POST /api/whatsapp/send-test/
    Send a test WhatsApp message to verify Meta Cloud API connectivity.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WhatsAppTestMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_phone = data["phone_number"]
        test_type = data["test_type"]
        config = WhatsAppConfig.get_config()

        if test_type == "direct_text":
            text_body = data.get("custom_text") or (
                "🧪 *InsureLedger WhatsApp Test*\n\n"
                "Congratulations! Your Meta WhatsApp Cloud API connection has been verified successfully.\n\n"
                "Policy and payment updates will now automatically be dispatched through this number."
            )
            log = WhatsAppClient.send_text_message(
                to_phone=target_phone,
                text=text_body,
                is_test=True,
            )
        elif test_type == "template_policy":
            body_params = [
                "Test Customer",
                "MH 12 AB 1234",
                "POL-TEST-001",
                "Test General Insurance",
                "2026-12-31",
                "INR 15,000.00",
                "INR 5,000.00",
                "INR 10,000.00",
            ]
            log = WhatsAppClient.send_template_message(
                to_phone=target_phone,
                template_name=config.policy_template_name,
                language_code=config.policy_template_language,
                body_parameters=body_params,
                message_type="TEST",
            )
        elif test_type == "template_payment":
            body_params = [
                "Test Customer",
                "MH 12 AB 1234",
                "RCP-TEST-99",
                "INR 5,000.00",
                "2026-09-25",
                "UPI",
                "INR 5,000.00",
            ]
            log = WhatsAppClient.send_template_message(
                to_phone=target_phone,
                template_name=config.payment_template_name,
                language_code=config.payment_template_language,
                body_parameters=body_params,
                message_type="TEST",
            )
        else:
            return Response(
                {"error": "Invalid test_type specified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_data = WhatsAppMessageLogSerializer(log).data
        success = log.status in ("sent", "delivered", "read")
        msg = (
            f"Test message sent successfully to {log.recipient_phone}!"
            if success
            else f"Failed to send test message: {log.error_message}"
        )

        return Response(
            {
                "success": success,
                "message": msg,
                "log": log_data,
            },
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )


class WhatsAppMessageLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/whatsapp/logs/ -> List delivery audit logs with filtering and pagination
    GET /api/whatsapp/logs/<id>/ -> View detailed log
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WhatsAppMessageLogSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        queryset = WhatsAppMessageLog.objects.select_related(
            "customer", "insurance_record", "insurance_record__vehicle", "payment"
        ).all()

        params = self.request.query_params
        msg_type = params.get("message_type")
        msg_status = params.get("status")
        phone = params.get("phone") or params.get("recipient")
        search = params.get("search")
        is_test = params.get("is_test")

        if msg_type:
            queryset = queryset.filter(message_type__iexact=msg_type.strip())
        if msg_status:
            queryset = queryset.filter(status__iexact=msg_status.strip())
        if phone:
            clean_phone = normalize_phone_number(phone)
            queryset = queryset.filter(recipient_phone__icontains=clean_phone)
        if search:
            queryset = queryset.filter(
                recipient_phone__icontains=search
            ) | queryset.filter(
                template_name__icontains=search
            ) | queryset.filter(
                customer__name__icontains=search
            ) | queryset.filter(
                wamid__icontains=search
            )
        if is_test is not None and is_test != "":
            queryset = queryset.filter(is_test=is_test.lower() in ("true", "1"))

        return queryset.order_by("-created_at")


class WhatsAppSendPolicyView(APIView):
    """POST /api/whatsapp/records/<record_id>/send/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, record_id):
        record = get_object_or_404(InsuranceRecord, pk=record_id)
        log = WhatsAppClient.send_policy_issued_notification(record, async_send=False)
        if not log:
            return Response(
                {"error": "WhatsApp sending is disabled or could not be initiated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        success = log.status in ("sent", "delivered", "read")
        return Response(
            {
                "success": success,
                "message": f"WhatsApp policy notification {'sent' if success else 'failed'}.",
                "log": WhatsAppMessageLogSerializer(log).data,
            },
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )


class WhatsAppSendPaymentView(APIView):
    """POST /api/whatsapp/payments/<payment_id>/send/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, pk=payment_id)
        log = WhatsAppClient.send_payment_received_notification(payment, async_send=False)
        if not log:
            return Response(
                {"error": "WhatsApp sending is disabled or could not be initiated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        success = log.status in ("sent", "delivered", "read")
        return Response(
            {
                "success": success,
                "message": f"WhatsApp payment receipt {'sent' if success else 'failed'}.",
                "log": WhatsAppMessageLogSerializer(log).data,
            },
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )


class WhatsAppResendLogView(APIView):
    """POST /api/whatsapp/logs/<log_id>/resend/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, log_id):
        original_log = get_object_or_404(WhatsAppMessageLog, pk=log_id)
        config = WhatsAppConfig.get_config()

        if original_log.template_name:
            body_params = original_log.parameters.get("body", [])
            new_log = WhatsAppClient.send_template_message(
                to_phone=original_log.recipient_phone,
                template_name=original_log.template_name,
                language_code="en",
                body_parameters=body_params,
                context_data={
                    "customer": original_log.customer,
                    "insurance_record": original_log.insurance_record,
                    "payment": original_log.payment,
                },
                message_type=original_log.message_type,
            )
        else:
            text = original_log.parameters.get("text", "")
            new_log = WhatsAppClient.send_text_message(
                to_phone=original_log.recipient_phone,
                text=text,
                is_test=original_log.is_test,
            )

        success = new_log.status in ("sent", "delivered", "read")
        return Response(
            {
                "success": success,
                "message": f"Resend {'succeeded' if success else 'failed'}.",
                "log": WhatsAppMessageLogSerializer(new_log).data,
            },
            status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
        )


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(APIView):
    """
    Official Meta Cloud API Webhook Handler:
    - GET  /api/whatsapp/webhook/ -> Hub challenge verification
    - POST /api/whatsapp/webhook/ -> Real-time status updates (sent, delivered, read, failed)
    """
    permission_classes = [AllowAny]

    def get(self, request):
        mode = request.GET.get("hub.mode")
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        config = WhatsAppConfig.get_config()
        configured_secret = (config.webhook_verify_token or "insure_wa_webhook_secret_key").strip()

        if mode == "subscribe" and verify_token == configured_secret:
            logger.info("Meta WhatsApp Webhook successfully verified with challenge.")
            return HttpResponse(challenge, content_type="text/plain", status=200)

        logger.warning(
            f"Meta WhatsApp Webhook verification failed. Received mode={mode}, verify_token={verify_token}"
        )
        return HttpResponse("Verification token mismatch", status=403)

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            payload = request.data

        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                statuses = value.get("statuses", [])

                for item in statuses:
                    wamid = item.get("id")
                    meta_status = item.get("status")  # sent, delivered, read, failed

                    if not wamid or not meta_status:
                        continue

                    logs = WhatsAppMessageLog.objects.filter(wamid=wamid)
                    if logs.exists():
                        log = logs.first()
                        if meta_status in ("sent", "delivered", "read", "failed"):
                            log.status = meta_status

                        if meta_status == "failed":
                            errors = item.get("errors", [])
                            err_str = "; ".join([e.get("title", "") or e.get("message", "") for e in errors])
                            log.error_message = f"Delivery failed: {err_str}"

                        log.save()
                        logger.info(f"Updated WhatsApp log wamid {wamid} status to {meta_status}")

        return HttpResponse("EVENT_RECEIVED", status=200)
