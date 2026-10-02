"""Email verification for authenticated settings changes."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from settings_app.models import BusinessSettings
from .models import AccountChangeChallenge

PURPOSES = ("password", "email", "phone", "account_email")


def recipient_for(user, purpose):
    business = BusinessSettings.objects.filter(pk=1).first()
    if purpose in ("email", "phone") and business and business.email:
        return business.email.strip()
    return user.email.strip() or (business.email.strip() if business else "")


def consume_verification(user, purpose, token):
    challenge = AccountChangeChallenge.objects.select_for_update().filter(user=user, purpose=purpose).first()
    if (not challenge or not challenge.verified or challenge.consumed
            or challenge.expires_at <= timezone.now()
            or challenge.recipient != recipient_for(user, purpose)
            or not token or not check_password(str(token), challenge.token_hash)):
        raise serializers.ValidationError({"message": "Email verification is required or has expired. Please request a new OTP."})
    challenge.consumed = True
    challenge.save(update_fields=["consumed"])


class RequestChangeOtpView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        purpose = request.data.get("purpose")
        if not isinstance(purpose, str) or purpose not in PURPOSES:
            return Response({"message": "Invalid change type."}, status=400)
        # Serialize sends for the account, including the first challenge creation.
        User.objects.select_for_update().get(pk=request.user.pk)
        recipient = recipient_for(request.user, purpose)
        if not recipient:
            return Response({"message": "No saved email address is available. Contact your administrator to configure it."}, status=400)
        now = timezone.now()
        recent = AccountChangeChallenge.objects.filter(user=request.user, created_at__gt=now - timedelta(seconds=60)).exists()
        if recent:
            return Response({"message": "Please wait 60 seconds before requesting another OTP."}, status=429)
        otp = f"{secrets.randbelow(1000000):06d}"
        challenge, _ = AccountChangeChallenge.objects.update_or_create(
            user=request.user, purpose=purpose,
            defaults=dict(recipient=recipient, otp_hash=make_password(otp), token_hash="",
                          created_at=now, expires_at=now + timedelta(minutes=10),
                          attempts=0, verified=False, consumed=False),
        )
        try:
            sent = send_mail(
                "InsureLedger: verify your settings change",
                f"Your verification code for changing your {purpose.replace('_', ' ')} is {otp}.\n"
                "It expires in 10 minutes. Do not share this code. If you did not request this change, contact your administrator.",
                settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False,
            )
            if not sent:
                raise RuntimeError("Email was not sent")
        except Exception:
            challenge.consumed = True
            challenge.save(update_fields=["consumed"])
            return Response({"message": "Unable to send OTP. Please check the email service and try again."}, status=503)
        return Response({"message": "OTP sent to your saved email address.", "recipient": recipient})


class VerifyChangeOtpView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        purpose = request.data.get("purpose")
        if not isinstance(purpose, str) or purpose not in PURPOSES:
            return Response({"message": "Invalid change type."}, status=400)
        challenge = AccountChangeChallenge.objects.select_for_update().filter(
            user=request.user, purpose=purpose
        ).first()
        if (not challenge or challenge.consumed or challenge.verified or challenge.attempts >= 5
                or challenge.expires_at <= timezone.now()
                or challenge.recipient != recipient_for(request.user, challenge.purpose)):
            return Response({"message": "OTP expired or unavailable. Please request a new code."}, status=400)
        challenge.attempts += 1
        challenge.save(update_fields=["attempts"])
        otp = str(request.data.get("otp", ""))
        if len(otp) != 6 or not otp.isdigit() or not check_password(otp, challenge.otp_hash):
            return Response({"message": "Invalid OTP. Check your email and try again."}, status=400)
        token = secrets.token_urlsafe(32)
        challenge.verified = True
        challenge.token_hash = make_password(token)
        challenge.otp_hash = ""
        challenge.save(update_fields=["verified", "token_hash", "otp_hash"])
        return Response({"message": "Email verified.", "verification_token": token})


class ChangeContactSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=("email", "phone", "account_email"))
    verification_token = serializers.CharField()
    new_value = serializers.CharField(max_length=254)

    def validate(self, attrs):
        value = attrs["new_value"]
        if attrs["purpose"] in ("email", "account_email"):
            value = serializers.EmailField().run_validation(value).lower()
            if attrs["purpose"] == "account_email" and User.objects.filter(email__iexact=value).exclude(pk=self.context["request"].user.pk).exists():
                raise serializers.ValidationError({"message": "This email address is already in use."})
        else:
            import re
            if not re.fullmatch(r"\+?[0-9 ()-]{7,30}", value) or not 7 <= len(re.sub(r"\D", "", value)) <= 15:
                raise serializers.ValidationError({"message": "Enter a valid phone number with 7 to 15 digits."})
        attrs["new_value"] = value
        return attrs


class ChangeContactView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = ChangeContactSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        User.objects.select_for_update().get(pk=request.user.pk)
        business, _ = BusinessSettings.objects.select_for_update().get_or_create(pk=1)
        consume_verification(request.user, data["purpose"], data["verification_token"])
        if data["purpose"] == "account_email":
            request.user.email = data["new_value"]
            request.user.save(update_fields=["email"])
        else:
            setattr(business, data["purpose"], data["new_value"])
            business.save(update_fields=[data["purpose"], "updated_at"])
        return Response({"message": "Contact details updated successfully."})
