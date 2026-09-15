import re
from django.db import models


class Customer(models.Model):
    name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self):
        return f"{self.name} ({self.phone})" if self.name else self.phone

    @classmethod
    def normalize_phone(cls, phone: str) -> str:
        """Strip whitespace and special formatting characters."""
        if not phone:
            return ""
        return re.sub(r"[\s\-\(\)]", "", str(phone).strip())

    @classmethod
    def get_or_create_by_phone(cls, phone: str, **defaults):
        """
        Flow helper:
        Enter Phone Number -> Does Customer Exist?
        YES -> Use Existing Customer
        NO  -> Automatically Create Customer
        """
        normalized_phone = cls.normalize_phone(phone)
        return cls.objects.get_or_create(phone=normalized_phone, defaults=defaults)
