from django.conf import settings
from django.contrib.auth import logout
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


def set_auth_cookie(response, token_key, remember_me=False):
    """
    Sets the authentication token in a secure HttpOnly cookie.
    - HttpOnly: Prevents client-side scripts (XSS attacks) from reading the token.
    - Secure: Transmitted only over HTTPS in production.
    - SameSite=Lax: Protects against CSRF while allowing navigation across same-site subdomains.
    - max_age: 14 days if remember_me is True, None (session-only, expires on browser close) if False.
    """
    is_secure = not settings.DEBUG
    samesite = getattr(settings, "AUTH_COOKIE_SAMESITE", "Lax")
    domain = getattr(settings, "AUTH_COOKIE_DOMAIN", None)
    max_age = (14 * 24 * 60 * 60) if remember_me else None

    response.set_cookie(
        key="insure_token",
        value=token_key,
        max_age=max_age,
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

        user = serializer.validated_data["user"]

        # Ensure any old token is removed to prevent stale sessions
        Token.objects.filter(user=user).delete()
        token = Token.objects.create(user=user)

        # Initialize/refresh user session activity
        UserSessionActivity.objects.update_or_create(
            user=user,
            defaults={"last_activity": timezone.now()},
        )

        remember_me = bool(request.data.get("remember_me", False))
        include_token = (
            bool(request.data.get("include_token", False)) or 
            request.query_params.get("include_token", "").lower() in ("true", "1")
        )

        resp_data = {
            "message": "Login successful.",
            "user": UserProfileSerializer(user).data,
        }
        # If an external client (API tool / mobile / test) explicitly requests the raw token, include it
        if include_token:
            resp_data["token"] = token.key

        response = Response(resp_data, status=status.HTTP_200_OK)
        return set_auth_cookie(response, token.key, remember_me=remember_me)


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
