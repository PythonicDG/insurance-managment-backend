from config.soft_delete import SoftDeleteModel
from django.db import models
from django.contrib.auth.hashers import make_password, check_password


class BusinessSettings(SoftDeleteModel):
    business_name = models.CharField(max_length=255, default="InsureLedger Agency")
    logo = models.ImageField(upload_to="business_logos/", null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Security PIN for exporting bulk data (CSV/PDF/Print)
    export_pin = models.CharField(max_length=128, blank=True, default="")
    pin_otp = models.CharField(max_length=6, blank=True, default="")
    pin_otp_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        verbose_name = "Business Settings"
        verbose_name_plural = "Business Settings"

    def __str__(self):
        return self.business_name

    def set_export_pin(self, raw_pin: str):
        self.export_pin = make_password(str(raw_pin).strip())

    def check_export_pin(self, raw_pin: str) -> bool:
        if not self.export_pin:
            return False
        return check_password(str(raw_pin).strip(), self.export_pin)

    @property
    def is_export_pin_set(self) -> bool:
        return bool(self.export_pin)

