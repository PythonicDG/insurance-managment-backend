from config.soft_delete import SoftDeleteModel
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class AccountChangeChallenge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.CharField(max_length=20)
    recipient = models.EmailField()
    otp_hash = models.CharField(max_length=128)
    token_hash = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified = models.BooleanField(default=False)
    consumed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "purpose"], name="unique_account_change_challenge")]


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

