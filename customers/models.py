import re
from django.db import models


class Customer(models.Model):
    name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=20, db_index=True)
    alternative_mobile_number = models.CharField(
        max_length=20, blank=True, default="", verbose_name="Alternative Mobile Number"
    )
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

    @property
    def customer_id(self):
        return self.id

    @classmethod
    def normalize_phone(cls, phone: str) -> str:
        """Strip whitespace and special formatting characters."""
        if not phone:
            return ""
        return re.sub(r"[\s\-\(\)\.]", "", str(phone).strip())

    def save(self, *args, **kwargs):
        if self.phone:
            self.phone = self.normalize_phone(self.phone)
        if self.alternative_mobile_number:
            self.alternative_mobile_number = self.normalize_phone(self.alternative_mobile_number)
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_by_phone(cls, phone: str, **defaults):
        """
        Flow helper:
        Enter Phone Number -> Does Customer Exist?
        YES -> Use Existing Customer
        NO  -> Automatically Create Customer
        Safe for non-unique phone numbers.
        """
        normalized_phone = cls.normalize_phone(phone)
        if not normalized_phone:
            return None, False
        name = defaults.get("name", "")
        qs = cls.objects.filter(phone=normalized_phone)
        if name:
            match = qs.filter(name__iexact=name.strip()).first()
            if match:
                return match, False
        first_match = qs.order_by("created_at").first()
        if first_match and not defaults.get("create_new"):
            return first_match, False
        return cls.objects.create(phone=normalized_phone, **{k: v for k, v in defaults.items() if k != "create_new"}), True
