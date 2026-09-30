import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit entries cannot be changed.")

    def delete(self):
        raise ValidationError("Audit entries cannot be deleted.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Audit entries cannot be changed.")

    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False,
                    update_conflicts=False, update_fields=None, unique_fields=None):
        if update_conflicts or ignore_conflicts:
            raise ValidationError("Audit entries cannot be overwritten.")
        return super().bulk_create(objs, batch_size=batch_size, update_fields=update_fields,
                                   unique_fields=unique_fields)


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Created"
        UPDATE = "update", "Updated"
        DELETE = "delete", "Deleted (archived)"
        RESTORE = "restore", "Restored"
        LOGIN = "login", "Logged in"
        LOGOUT = "logout", "Logged out"
        PASSWORD_CHANGE = "password_change", "Password changed"

    occurred_at = models.DateTimeField(default=timezone.now, editable=False)
    actor_id = models.CharField(max_length=255, blank=True, editable=False)
    actor_username = models.CharField(max_length=255, blank=True, editable=False)
    source = models.CharField(max_length=10, default="system", editable=False)
    action = models.CharField(max_length=20, choices=Action.choices, editable=False)
    object_type = models.CharField(max_length=100, editable=False)
    object_id = models.CharField(max_length=255, editable=False)
    changes = models.JSONField(default=dict, editable=False)
    request_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    request_method = models.CharField(max_length=10, blank=True, editable=False)
    request_path = models.CharField(max_length=512, blank=True, editable=False)
    summary = models.CharField("Activity", max_length=1000, blank=True, editable=False)
    object_label = models.CharField("Affected record", max_length=512, blank=True, editable=False)
    customer_name = models.CharField(max_length=255, blank=True, editable=False)
    customer_phone = models.CharField(max_length=30, blank=True, editable=False)
    policy_number = models.CharField(max_length=100, blank=True, editable=False)
    vehicle_number = models.CharField(max_length=50, blank=True, editable=False)
    search_text = models.TextField(blank=True, editable=False)
    device = models.CharField("Browser / system", max_length=120, blank=True, editable=False,
                              help_text="Reported by the browser; this is not a verified computer name.")
    ip_address = models.GenericIPAddressField("IP address", null=True, blank=True, editable=False)
    user_agent = models.CharField(max_length=512, blank=True, editable=False)

    objects = models.Manager.from_queryset(ImmutableQuerySet)()

    class Meta:
        ordering = ["-occurred_at", "-id"]
        default_permissions = ("view",)
        base_manager_name = "objects"
        verbose_name = "Staff activity"
        verbose_name_plural = "Staff activity logs"
        indexes = [
            models.Index(fields=["occurred_at", "id"], name="audit_time_idx"),
            models.Index(fields=["actor_id", "occurred_at"], name="audit_actor_idx"),
            models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["action", "occurred_at"], name="audit_action_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Audit entries cannot be changed.")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit entries cannot be deleted.")

    def __str__(self):
        return f"{self.actor_username or 'System'}: {self.summary or self.get_action_display()}"
