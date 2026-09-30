from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import ActivityLog
from .services import record_event


@receiver(user_logged_in, dispatch_uid="audit_admin_login")
def logged_in(sender, request, user, **kwargs):
    record_event(ActivityLog.Action.LOGIN, user, actor=user)


@receiver(user_logged_out, dispatch_uid="audit_admin_logout")
def logged_out(sender, request, user, **kwargs):
    if user is not None:
        record_event(ActivityLog.Action.LOGOUT, user, actor=user)
