from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from .models import UserSessionActivity


class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Token authentication for the application.
    Inactivity auto-logout has been disabled so active user sessions are never
    interrupted or expired while working on tasks.
    Session lifecycle is managed via the browser tab (sessionStorage).
    """

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)

        # Update last activity timestamp for tracking without expiring or deleting tokens
        try:
            UserSessionActivity.objects.update_or_create(
                user=user,
                defaults={"last_activity": timezone.now()},
            )
        except Exception:
            pass

        return (user, token)
