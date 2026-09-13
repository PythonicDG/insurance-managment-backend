from django.contrib.auth import logout
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token

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

        token, created = Token.objects.get_or_create(
            user=user
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

        except Token.DoesNotExist:
            pass

        return Response(
            {
                "message": "Logout successful."
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

        request.user.auth_token.delete()

        return Response(
            {
                "message": "Password changed successfully. Please login again."
            },
            status=status.HTTP_200_OK
        )