from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserSessionActivity(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="session_activity",
    )
    last_activity = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "User Session Activity"
        verbose_name_plural = "User Session Activities"

    def __str__(self):
        return f"{self.user.username} - {self.last_activity}"

