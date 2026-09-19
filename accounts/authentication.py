from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from .models import UserSessionActivity


class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Extends DRF TokenAuthentication to enforce an inactivity/AFK timeout.
    If the elapsed time since the user's last activity exceeds SESSION_INACTIVITY_TIMEOUT
    (default 300 seconds / 5 minutes), the token and session activity are removed,
    and an AuthenticationFailed exception is raised.
    Otherwise, the last_activity timestamp is updated to the current time.
    """

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)

        timeout_seconds = getattr(settings, "SESSION_INACTIVITY_TIMEOUT", 300)
        now = timezone.now()

        # Retrieve or initialize session activity for the user
        activity, created = UserSessionActivity.objects.get_or_create(
            user=user,
            defaults={"last_activity": now},
        )

        if not created:
            elapsed = (now - activity.last_activity).total_seconds()
            if elapsed > timeout_seconds:
                # Session has expired due to inactivity
                try:
                    token.delete()
                except Exception:
                    pass
                activity.delete()
                raise exceptions.AuthenticationFailed(
                    "Session expired due to inactivity. Please log in again."
                )

        # Refresh last activity timestamp for this valid request
        activity.last_activity = now
        activity.save(update_fields=["last_activity"])

        return (user, token)
