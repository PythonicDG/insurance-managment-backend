from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")

        # Allow logging in with either username or email
        auth_username = username
        if "@" in username:
            try:
                user_obj = User.objects.get(email__iexact=username)
                auth_username = user_obj.username
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                auth_username = username

        user = authenticate(
            username=auth_username,
            password=password
        )

        if not user:
            raise serializers.ValidationError(
                "Invalid username or password."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This account is inactive."
            )

        attrs["user"] = user

        return attrs


class UserProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
        ]
        read_only_fields = fields


class ChangePasswordSerializer(serializers.Serializer):
    verification_token = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        trim_whitespace=False
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"message": "New password and confirmation do not match."})
        return attrs

    def validate_new_password(self, value):
        from django.contrib.auth.password_validation import validate_password

        validate_password(
            value,
            self.context["request"].user
        )

        return value
