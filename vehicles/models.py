import re
from django.db import models


class Vehicle(models.Model):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="vehicles",
    )
    vehicle_type = models.CharField(max_length=50)
    vehicle_number = models.CharField(max_length=50, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Vehicle"
        verbose_name_plural = "Vehicles"

    def __str__(self):
        return f"{self.vehicle_number} ({self.vehicle_type})"

    @classmethod
    def normalize_vehicle_number(cls, number: str) -> str:
        """Strip whitespaces and convert to uppercase."""
        if not number:
            return ""
        return re.sub(r"\s+", "", str(number).strip()).upper()

    def save(self, *args, **kwargs):
        if self.vehicle_number:
            self.vehicle_number = self.normalize_vehicle_number(self.vehicle_number)
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_vehicle(cls, customer, vehicle_number: str, vehicle_type: str = ""):
        """
        Flow helper:
        Select/Create Customer
                ↓
        Enter Vehicle Number
                ↓
        Already Exists?
                ↓
        YES → Use Existing Vehicle
        NO  → Create Vehicle
        """
        normalized_number = cls.normalize_vehicle_number(vehicle_number)
        vehicle = cls.objects.filter(vehicle_number__iexact=normalized_number).first()
        if vehicle:
            return vehicle, False
        return cls.objects.create(
            customer=customer,
            vehicle_number=normalized_number,
            vehicle_type=vehicle_type,
        ), True
