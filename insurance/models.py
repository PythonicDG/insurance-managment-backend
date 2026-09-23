from decimal import Decimal
import os
from django.core.exceptions import ValidationError
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
    policy_number = models.CharField(unique=True, max_length=100, db_index=True)
    entry_date = models.DateField(default=timezone.localdate)
    policy_start_date = models.DateField()
    policy_expiry_date = models.DateField(db_index=True)
    total_premium = models.DecimalField(max_digits=12, decimal_places=2)
    remarks = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Insurance Record"
        verbose_name_plural = "Insurance Records"
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle"],
                condition=models.Q(is_active=True),
                name="unique_active_insurance_per_vehicle",
            )
        ]

    def clean(self):
        super().clean()
        if self.policy_number:
            self.policy_number = self.policy_number.strip()
            if not self.policy_number:
                raise ValidationError({"policy_number": "Policy number cannot be empty."})

            qs = InsuranceRecord.objects.filter(policy_number__iexact=self.policy_number)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                existing = qs.select_related("customer", "vehicle").first()
                cust_info = existing.customer.name if existing and existing.customer else "another customer"
                veh_info = f" ({existing.vehicle.vehicle_number})" if existing and existing.vehicle else ""
                raise ValidationError({
                    "policy_number": f"Policy number '{self.policy_number}' is already registered to {cust_info}{veh_info}. Policy numbers must be unique."
                })

        # Validate that only one active policy can exist per vehicle
        if self.is_active and self.vehicle_id:
            active_qs = InsuranceRecord.objects.filter(
                vehicle_id=self.vehicle_id,
                is_active=True,
            )
            if self.pk:
                active_qs = active_qs.exclude(pk=self.pk)
            if active_qs.exists():
                existing_active = active_qs.first()
                veh_num = self.vehicle.vehicle_number if getattr(self, "vehicle", None) else ""
                raise ValidationError({
                    "vehicle_number": (
                        f"Active policy already exists for vehicle '{veh_num}' "
                        f"(Policy #{existing_active.policy_number}, Expiry: {existing_active.policy_expiry_date}). "
                        "Only one active policy is allowed per vehicle."
                    )
                })

    def save(self, *args, **kwargs):
        if self.policy_number:
            self.policy_number = self.policy_number.strip()
        # If policy has already expired by date, automatically set is_active to False
        if self.policy_expiry_date and self.policy_expiry_date < timezone.localdate():
            self.is_active = False
        self.clean()
        super().save(*args, **kwargs)

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
        elif days <= 10:
            return "expiring_soon"
        return "active"

    @property
    def total_paid(self) -> Decimal:
        total = self.payments.aggregate(total=models.Sum("amount"))["total"]
        if total is None:
            return Decimal("0.00")
        return Decimal(str(total)).quantize(Decimal("0.01"))

    @property
    def outstanding(self) -> Decimal:
        total_paid = self.total_paid
        total_premium = self.total_premium if self.total_premium is not None else Decimal("0.00")
        diff = total_premium - total_paid
        return Decimal(str(diff)).quantize(Decimal("0.01"))

    @property
    def payment_status(self) -> str:
        total_paid = self.total_paid
        total_premium = self.total_premium if self.total_premium is not None else Decimal("0.00")
        if total_paid <= Decimal("0.00"):
            return "UNPAID"
        elif total_paid < total_premium:
            return "PARTIAL"
        else:
            return "PAID"

    def get_payment_status(self) -> str:
        return self.payment_status


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


# Re-export Payment for convenient import
try:
    from payments.models import Payment  # noqa: F401
except ImportError:
    pass
