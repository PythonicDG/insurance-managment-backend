from django.db import models


class InsuranceCompany(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Insurance Company"
        verbose_name_plural = "Insurance Companies"

    def __str__(self):
        return self.name
