from config.soft_delete import SoftDeleteModel
from decimal import Decimal
import os
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.utils import timezone


class InsuranceCompany(SoftDeleteModel):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        ordering = ["name"]
        verbose_name = "Insurance Company"
        verbose_name_plural = "Insurance Companies"

    def __str__(self):
        return self.name


class InsuranceRecord(SoftDeleteModel):
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
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Discount given in Rs (applicable only for full payment)",
    )
    alternative_mobile_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Alternative Mobile Number",
    )
    remarks = models.TextField(blank=True, default="")
    previous_policy = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="renewed_policy",
        help_text="The policy record that this policy renewed.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_manager_name = "objects"
        base_manager_name = "all_objects"
        ordering = ["-entry_date", "-created_at"]
        verbose_name = "Insurance Record"
        verbose_name_plural = "Insurance Records"
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle"],
                condition=models.Q(is_active=True, deleted_at__isnull=True),
                name="unique_active_insurance_per_vehicle",
            )
        ]

    def clean(self):
        super().clean()
        if self.policy_number:
            self.policy_number = self.policy_number.strip()
            if not self.policy_number:
                raise ValidationError({"policy_number": "Policy number cannot be empty."})

            qs = InsuranceRecord.all_objects.filter(policy_number__iexact=self.policy_number)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                existing = qs.select_related("customer", "vehicle").first()
                cust_info = existing.customer.name if existing and existing.customer else "another customer"
                veh_info = f" ({existing.vehicle.vehicle_number})" if existing and existing.vehicle else ""
                raise ValidationError({
                    "policy_number": f"Policy number '{self.policy_number}' is already registered to {cust_info}{veh_info}. Policy numbers must be unique."
                })

        # Validate discount amount
        if self.discount is not None:
            if self.discount < Decimal("0.00"):
                raise ValidationError({"discount": "Discount cannot be negative."})
            total_prem = self.total_premium or Decimal("0.00")
            if self.discount > total_prem:
                raise ValidationError({
                    "discount": f"Discount (₹{self.discount}) cannot exceed total premium (₹{total_prem})."
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
        if self.alternative_mobile_number:
            from customers.models import Customer
            self.alternative_mobile_number = Customer.normalize_phone(self.alternative_mobile_number)
        # Future policies are scheduled, and past policies are historical.
        today = timezone.localdate()
        if (
            self.policy_start_date
            and self.policy_start_date > today
        ) or (
            self.policy_expiry_date
            and self.policy_expiry_date < today
        ):
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
    def successor(self):
        """Return the linked renewal without leaking RelatedObjectDoesNotExist."""
        try:
            return self.renewed_policy
        except InsuranceRecord.DoesNotExist:
            return None

    @property
    def lifecycle_status(self) -> str:
        """Operational status used by renewal follow-up and the records UI."""
        today = timezone.localdate()
        successor = self.successor

        if successor is not None:
            if self.is_active and self.policy_expiry_date >= today:
                return "current"
            return "renewed"

        if self.policy_start_date > today:
            return "scheduled"
        if self.policy_expiry_date < today:
            return "expired"
        if self.is_active:
            if self.policy_expiry_date == today:
                return "expiring_today"
            if self.days_left <= 10:
                return "expiring_soon"
            return "current"
        return "inactive"

    @property
    def needs_renewal(self) -> bool:
        return self.policy_expiry_date < timezone.localdate() and self.successor is None

    @classmethod
    def activate_due_scheduled(cls, vehicle_id=None):
        """Promote due scheduled renewals and retire the previous current policy."""
        today = timezone.localdate()
        candidates = cls.objects.filter(
            renewed_policy__isnull=True,
            is_active=False,
            policy_start_date__lte=today,
            policy_expiry_date__gte=today,
        )
        if vehicle_id is not None:
            candidates = candidates.filter(vehicle_id=vehicle_id)

        # Portable implementation (SQLite and PostgreSQL): the latest due leaf
        # wins if legacy data somehow contains more than one for a vehicle.
        chosen = {}
        for candidate in candidates.order_by("vehicle_id", "-policy_start_date", "-id"):
            chosen.setdefault(candidate.vehicle_id, candidate)

        for candidate in chosen.values():
            with transaction.atomic():
                cls.objects.filter(vehicle_id=candidate.vehicle_id, is_active=True).exclude(
                    pk=candidate.pk
                ).update(is_active=False)
                cls.objects.filter(pk=candidate.pk).update(is_active=True)

    @property
    def net_premium(self) -> Decimal:
        total_prem = self.total_premium if self.total_premium is not None else Decimal("0.00")
        disc = self.discount if self.discount is not None else Decimal("0.00")
        return max(Decimal("0.00"), total_prem - disc).quantize(Decimal("0.01"))

    @property
    def total_paid(self) -> Decimal:
        total = self.payments.aggregate(total=models.Sum("amount"))["total"]
        if total is None:
            return Decimal("0.00")
        return Decimal(str(total)).quantize(Decimal("0.01"))

    @property
    def outstanding(self) -> Decimal:
        total_paid = self.total_paid
        net_prem = self.net_premium
        diff = max(Decimal("0.00"), net_prem - total_paid)
        return Decimal(str(diff)).quantize(Decimal("0.01"))

    @property
    def payment_status(self) -> str:
        total_paid = self.total_paid
        net_prem = self.net_premium
        if total_paid <= Decimal("0.00") and net_prem > Decimal("0.00"):
            return "UNPAID"
        elif total_paid < net_prem:
            return "PARTIAL"
        else:
            return "PAID"

    def get_payment_status(self) -> str:
        return self.payment_status


def insurance_document_upload_path(instance, filename):
    record_id = instance.record_id or "temp"
    return f"insurance_documents/record_{record_id}/{filename}"


class InsuranceDocument(SoftDeleteModel):
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
        default_manager_name = "objects"
        base_manager_name = "all_objects"
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



# Re-export Payment for convenient import
try:
    from payments.models import Payment  # noqa: F401
except ImportError:
    pass
