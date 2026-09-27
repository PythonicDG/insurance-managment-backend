from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import BusinessSettings
from .serializers import BusinessSettingsSerializer


class BusinessSettingsView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self):
        settings_obj, _ = BusinessSettings.objects.get_or_create(
            id=1,
            defaults={
                "business_name": "InsureLedger Agency",
                "phone": "",
                "email": "",
                "address": "",
            },
        )
        return settings_obj

    def get(self, request):
        settings_obj = self.get_object()
        serializer = BusinessSettingsSerializer(
            settings_obj, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        settings_obj = self.get_object()
        serializer = BusinessSettingsSerializer(
            settings_obj,
            data=request.data,
            partial=False,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "Settings updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        settings_obj = self.get_object()
        serializer = BusinessSettingsSerializer(
            settings_obj,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "message": "Settings updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class RemoveLogoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        settings_obj, _ = BusinessSettings.objects.get_or_create(id=1)
        if settings_obj.logo:
            settings_obj.logo.delete(save=False)
            settings_obj.logo = None
            settings_obj.save(update_fields=["logo", "updated_at"])

        serializer = BusinessSettingsSerializer(
            settings_obj, context={"request": request}
        )
        return Response(
            {
                "message": "Logo removed successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class NotifyExportView(APIView):
    """
    Alerts the business email (configured in BusinessSettings)
    whenever a user downloads / exports records (CSV), saves as PDF,
    or triggers Print All.
    Strictly sends an alert without attaching any files.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .email_service import (
            get_client_ip,
            get_recipient_email,
            send_export_notification_email,
        )

        action_type = request.data.get("action_type", "export_csv")
        source_module = request.data.get("source_module", "insurance_records")
        record_count = request.data.get("record_count", 0)
        filters = request.data.get("filters", {})

        try:
            record_count = int(record_count)
        except (ValueError, TypeError):
            record_count = 0

        client_ip = get_client_ip(request)
        recipient = get_recipient_email()

        if not recipient:
            return Response(
                {
                    "success": False,
                    "message": "No email address found in Business Settings. Please configure an email in Settings > Business.",
                },
                status=status.HTTP_200_OK,
            )

        success, message = send_export_notification_email(
            action_type=action_type,
            source_module=source_module,
            record_count=record_count,
            user=request.user,
            client_ip=client_ip,
            filters=filters,
            async_dispatch=True,
        )

        return Response(
            {
                "success": success,
                "message": message,
                "recipient": recipient,
            },
            status=status.HTTP_200_OK,
        )


class TestEmailView(APIView):
    """
    Allows administrator to verify Django SMTP configuration by sending
    a test notification email to the configured Business email.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        from .email_service import get_recipient_email

        target_email = request.data.get("email") or get_recipient_email()
        if not target_email or not target_email.strip():
            return Response(
                {
                    "success": False,
                    "message": "No recipient email address specified or configured in Business Settings.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_email = target_email.strip()
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or target_email

        subject = "InsureLedger - Test Email Notification"
        body = f"Hello,\n\nThis is a test email sent from InsureLedger to verify your Django SMTP email configuration.\n\nTime: {status.HTTP_200_OK}\nRecipient: {target_email}"

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=from_email,
                to=[target_email],
            )
            msg.send(fail_silently=False)
            return Response(
                {
                    "success": True,
                    "message": f"Test email sent successfully to {target_email}.",
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "success": False,
                    "message": f"Failed to send email: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyExportPinView(APIView):
    """
    Validates the submitted Security PIN before allowing bulk data export
    (CSV, Save as PDF, Print All).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        pin = request.data.get("pin", "")
        if not pin or not str(pin).strip():
            return Response(
                {"success": False, "message": "Please enter your Security PIN."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        settings_obj = BusinessSettings.objects.first()
        if not settings_obj or not settings_obj.export_pin:
            return Response(
                {
                    "success": False,
                    "pin_not_set": True,
                    "message": "Export Security PIN has not been configured yet. Please configure it in Settings > Business.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if settings_obj.check_export_pin(str(pin).strip()):
            return Response(
                {"success": True, "message": "PIN verified successfully."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"success": False, "message": "Incorrect Security PIN. Please try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RequestPinOtpView(APIView):
    """
    Generates a 6-digit OTP and sends it to the Business Email
    to authorize setting or resetting the Export Security PIN.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import secrets
        from datetime import timedelta
        from django.utils import timezone
        from .email_service import send_pin_verification_otp_email

        settings_obj, _ = BusinessSettings.objects.get_or_create(id=1)
        recipient = settings_obj.email.strip() if settings_obj.email else ""

        if not recipient:
            return Response(
                {
                    "success": False,
                    "message": "No business email address found. Please enter and save an email address in Business Settings first.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate 6-digit cryptographically secure numeric OTP
        otp = f"{secrets.randbelow(900000) + 100000}"
        settings_obj.pin_otp = otp
        settings_obj.pin_otp_expires_at = timezone.now() + timedelta(minutes=10)
        settings_obj.save(update_fields=["pin_otp", "pin_otp_expires_at"])

        success, msg = send_pin_verification_otp_email(
            otp=otp,
            business_name=settings_obj.business_name,
            recipient_email=recipient,
            async_dispatch=True,
        )

        return Response(
            {
                "success": success,
                "message": f"Verification code sent to {recipient}.",
                "recipient": recipient,
            },
            status=status.HTTP_200_OK if success else status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class SetExportPinView(APIView):
    """
    Validates the 6-digit OTP and updates the Export Security PIN.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.utils import timezone
        from .email_service import send_pin_updated_alert_email

        otp = str(request.data.get("otp", "")).strip()
        new_pin = str(request.data.get("new_pin", "")).strip()
        confirm_pin = str(request.data.get("confirm_pin", "")).strip()

        settings_obj, _ = BusinessSettings.objects.get_or_create(id=1)

        if not settings_obj.pin_otp:
            return Response(
                {
                    "success": False,
                    "message": "No verification code was requested or code has already been used. Please request a new code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if settings_obj.pin_otp_expires_at and timezone.now() > settings_obj.pin_otp_expires_at:
            return Response(
                {
                    "success": False,
                    "message": "Verification code has expired (10-minute limit). Please request a new code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp != settings_obj.pin_otp:
            return Response(
                {"success": False, "message": "Invalid verification code. Please check your email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not new_pin or len(new_pin) < 4 or len(new_pin) > 8:
            return Response(
                {"success": False, "message": "PIN must be between 4 and 8 digits."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_pin != confirm_pin:
            return Response(
                {"success": False, "message": "New PIN and Confirm PIN do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Securely hash and store the PIN
        settings_obj.set_export_pin(new_pin)
        settings_obj.pin_otp = ""
        settings_obj.pin_otp_expires_at = None
        settings_obj.save(update_fields=["export_pin", "pin_otp", "pin_otp_expires_at", "updated_at"])

        # Send confirmation alert email
        if settings_obj.email:
            updated_by = request.user.get_full_name() or request.user.username
            send_pin_updated_alert_email(
                business_name=settings_obj.business_name,
                recipient_email=settings_obj.email,
                updated_by=updated_by,
                async_dispatch=True,
            )

        return Response(
            {
                "success": True,
                "message": "Export Security PIN updated successfully.",
            },
            status=status.HTTP_200_OK,
        )


class RemoveExportPinView(APIView):
    """
    Validates the 6-digit OTP and removes/disables the Export Security PIN.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.utils import timezone
        from .email_service import send_pin_removed_alert_email

        otp = str(request.data.get("otp", "")).strip()
        settings_obj, _ = BusinessSettings.objects.get_or_create(id=1)

        if not settings_obj.export_pin:
            return Response(
                {"success": False, "message": "No Export Security PIN is currently configured."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not settings_obj.pin_otp:
            return Response(
                {
                    "success": False,
                    "message": "No verification code was requested or code has already been used. Please request a new code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if settings_obj.pin_otp_expires_at and timezone.now() > settings_obj.pin_otp_expires_at:
            return Response(
                {
                    "success": False,
                    "message": "Verification code has expired (10-minute limit). Please request a new code.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if otp != settings_obj.pin_otp:
            return Response(
                {"success": False, "message": "Invalid verification code. Please check your email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Remove the PIN and clear OTP
        settings_obj.export_pin = ""
        settings_obj.pin_otp = ""
        settings_obj.pin_otp_expires_at = None
        settings_obj.save(update_fields=["export_pin", "pin_otp", "pin_otp_expires_at", "updated_at"])

        # Send confirmation alert email
        if settings_obj.email:
            removed_by = request.user.get_full_name() or request.user.username
            send_pin_removed_alert_email(
                business_name=settings_obj.business_name,
                recipient_email=settings_obj.email,
                removed_by=removed_by,
                async_dispatch=True,
            )

        return Response(
            {
                "success": True,
                "message": "Export Security PIN removed successfully. Bulk exports will no longer require a PIN.",
            },
            status=status.HTTP_200_OK,
        )



