from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from .models import UserSessionActivity


class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Dual-mode Authentication:
    1. Modern/Secure: Reads 'insure_token' from HttpOnly cookie.
       Protects tokens from XSS theft, browser extension scraping, and inspect visibility.
    2. Fallback: Reads standard 'Authorization: Token <key>' header for backward
       compatibility with mobile apps, external clients, scripts, and legacy frontends.
    """

    def authenticate(self, request):
        # 1. Try HttpOnly cookie first
        token_key = request.COOKIES.get("insure_token")
        if token_key:
            try:
                return self.authenticate_credentials(token_key)
            except exceptions.AuthenticationFailed:
                # If cookie has a stale/invalid token, ignore it so AllowAny endpoints
                # (like LoginView) do not fail with 401. Protected endpoints will still
                # be rejected by IsAuthenticated permission checks.
                pass

        # 2. Fall back to standard Authorization header
        return super().authenticate(request)

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)

        # Update last activity timestamp for tracking without expiring or deleting tokens
        try:
            UserSessionActivity.all_objects.update_or_create(
                user=user,
                defaults={"last_activity": timezone.now(), "deleted_at": None, "deletion_batch": None},
            )
        except Exception:
            pass

        return (user, token)
