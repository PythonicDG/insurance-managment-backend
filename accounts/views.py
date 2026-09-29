from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token

from .models import UserSessionActivity
from .serializers import (
    LoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
)


def set_auth_cookie(response, token_key):
    """
    Sets the authentication token in a secure HttpOnly cookie.
    - HttpOnly: Prevents client-side scripts (XSS attacks) from reading the token.
    - Secure: Transmitted only over HTTPS in production.
    - SameSite=Lax: Protects against CSRF while allowing navigation across same-site subdomains.
    - No max_age/expires: the cookie is always browser-session-only.
    """
    is_secure = not settings.DEBUG
    samesite = getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax")
    domain = getattr(settings, "AUTH_COOKIE_DOMAIN", None)
    response.set_cookie(
        key="insure_token",
        value=token_key,
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        domain=domain,
        path="/",
    )
    return response


def delete_auth_cookie(response):
    """
    Clears the insure_token cookie from the client browser.
    """
    samesite = getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax")
    domain = getattr(settings, "AUTH_COOKIE_DOMAIN", None)

    response.delete_cookie(
        key="insure_token",
        path="/",
        domain=domain,
        samesite=samesite,
    )
    return response


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        authenticated_user = serializer.validated_data["user"]

        # Serialize logins for this account and rotate its token. This makes the
        # newly logged-in browser the only device with a valid credential.
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=authenticated_user.pk)
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)

            UserSessionActivity.objects.update_or_create(
                user=user,
                defaults={"last_activity": timezone.now()},
            )

        raw_include = request.data.get("include_token", None)
        if isinstance(raw_include, str):
            include_token = raw_include.strip().lower() in ("true", "1")
        elif raw_include is not None:
            include_token = bool(raw_include)
        else:
            include_token = (
                request.query_params.get("include_token", "").strip().lower() in ("true", "1") or
                request.headers.get("X-Include-Token", "").strip().lower() in ("true", "1")
            )

        resp_data = {
            "message": "Login successful.",
            "user": UserProfileSerializer(user).data,
        }
        # If an external client (API tool / mobile / test) explicitly requests the raw token, include it
        if include_token:
            resp_data["token"] = token.key

        response = Response(resp_data, status=status.HTTP_200_OK)
        return set_auth_cookie(response, token.key)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        if request.user and request.user.is_authenticated:
            try:
                request.user.auth_token.delete()
            except (Token.DoesNotExist, AttributeError):
                pass

            # Remove session activity
            UserSessionActivity.objects.filter(user=request.user).delete()

        response = Response(
            {
                "message": "Logout successful."
            },
            status=status.HTTP_200_OK
        )
        return delete_auth_cookie(response)


class PingSessionView(APIView):
    """
    Keep-alive endpoint called by the frontend (e.g. when user clicks 'Stay Logged In'
    or to verify active session). Updates the last_activity timestamp.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        now = timezone.now()
        UserSessionActivity.objects.update_or_create(
            user=request.user,
            defaults={"last_activity": now},
        )
        return Response(
            {
                "message": "Session active.",
                "last_activity": now.isoformat(),
            },
            status=status.HTTP_200_OK
        )


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        serializer = UserProfileSerializer(
            request.user
        )

        return Response(serializer.data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)

        request.user.set_password(
            serializer.validated_data["new_password"]
        )

        request.user.save()

        try:
            request.user.auth_token.delete()
        except (Token.DoesNotExist, AttributeError):
            pass

        UserSessionActivity.objects.filter(user=request.user).delete()

        response = Response(
            {
                "message": "Password changed successfully. Please login again."
            },
            status=status.HTTP_200_OK
        )
        return delete_auth_cookie(response)

