from config.soft_delete import SoftDeleteModel
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserSessionActivity(SoftDeleteModel):
    user = models.OneToOneField(
        User,
        on_delete=models.PROTECT,
        related_name="session_activity",
    )
    last_activity = models.DateTimeField(default=timezone.now)

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        verbose_name = "User Session Activity"
        verbose_name_plural = "User Session Activities"

    def __str__(self):
        return f"{self.user.username} - {self.last_activity}"

