from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    insurance_record = models.ForeignKey(
        "insurance.InsuranceRecord",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, default="Cash")
    payment_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Payment amount must be greater than zero."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment #{self.id} - {self.amount} ({self.payment_method}) for Record #{self.insurance_record_id}"

    @property
    def status(self) -> str:
        if self.insurance_record_id:
            try:
                return self.insurance_record.payment_status
            except Exception:
                pass
        return "PAID"
