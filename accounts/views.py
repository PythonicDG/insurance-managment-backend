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

        return Response(
            {
                "message": "Login successful.",
                "token": token.key,
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        try:
            request.user.auth_token.delete()
        except (Token.DoesNotExist, AttributeError):
            pass

        # Remove session activity
        UserSessionActivity.objects.filter(user=request.user).delete()

        return Response(
            {
                "message": "Logout successful."
            },
            status=status.HTTP_200_OK
        )


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

        return Response(
            {
                "message": "Password changed successfully. Please login again."
            },
            status=status.HTTP_200_OK
        )