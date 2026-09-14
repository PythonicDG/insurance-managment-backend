from django.db import models


class BusinessSettings(models.Model):
    business_name = models.CharField(max_length=255, default="InsureLedger Agency")
    logo = models.ImageField(upload_to="business_logos/", null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business Settings"
        verbose_name_plural = "Business Settings"

    def __str__(self):
        return self.business_name
