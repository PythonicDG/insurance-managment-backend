import os
from django.db import models
from django.utils import timezone


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


class InsuranceRecord(models.Model):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="insurance_records",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.CASCADE,
        related_name="insurance_records",
    )
    insurance_company = models.ForeignKey(
        InsuranceCompany,
        on_delete=models.CASCADE,
        related_name="insurance_records",
    )
    policy_number = models.CharField(max_length=100, db_index=True)
    entry_date = models.DateField(default=timezone.localdate)
    policy_start_date = models.DateField()
    policy_expiry_date = models.DateField(db_index=True)
    total_premium = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Insurance Record"
        verbose_name_plural = "Insurance Records"

    def __str__(self):
        customer_display = self.customer.name or self.customer.phone
        return f"{self.policy_number} - {customer_display} ({self.vehicle.vehicle_number})"

    @property
    def is_expired(self) -> bool:
        if not self.policy_expiry_date:
            return False
        return self.policy_expiry_date < timezone.localdate()

    @property
    def days_left(self) -> int:
        if not self.policy_expiry_date:
            return 0
        return (self.policy_expiry_date - timezone.localdate()).days

    @property
    def status(self) -> str:
        if not self.policy_expiry_date:
            return "unknown"
        days = self.days_left
        if days < 0:
            return "expired"
        elif days <= 30:
            return "expiring_soon"
        return "active"


def insurance_document_upload_path(instance, filename):
    record_id = instance.record_id or "temp"
    return f"insurance_documents/record_{record_id}/{filename}"


class InsuranceDocument(models.Model):
    record = models.ForeignKey(
        InsuranceRecord,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file = models.FileField(upload_to=insurance_document_upload_path)
    document_name = models.CharField(max_length=255, blank=True, default="")
    file_size = models.PositiveIntegerField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Insurance Document"
        verbose_name_plural = "Insurance Documents"

    def __str__(self):
        return self.document_name or (os.path.basename(self.file.name) if self.file else f"Document #{self.id}")

    def save(self, *args, **kwargs):
        if self.file:
            if not self.document_name:
                self.document_name = os.path.basename(self.file.name)
            try:
                self.file_size = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.file:
            try:
                if os.path.isfile(self.file.path):
                    os.remove(self.file.path)
            except Exception:
                pass
        super().delete(*args, **kwargs)
