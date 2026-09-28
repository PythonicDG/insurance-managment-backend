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
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Discount granted in this transaction",
    )
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
        try:
            amt = Decimal(str(self.amount)) if self.amount is not None else Decimal("0.00")
        except Exception:
            amt = Decimal("0.00")
        try:
            disc = Decimal(str(self.discount)) if self.discount is not None else Decimal("0.00")
        except Exception:
            disc = Decimal("0.00")

        if amt < Decimal("0.00"):
            raise ValidationError({"amount": "Payment amount cannot be negative."})
        if disc < Decimal("0.00"):
            raise ValidationError({"discount": "Discount cannot be negative."})
        if amt <= Decimal("0.00") and disc <= Decimal("0.00"):
            raise ValidationError({"amount": "Payment amount or discount must be greater than zero."})

        if self.insurance_record_id:
            record = self.insurance_record
            total_prem = Decimal(str(record.total_premium)) if record.total_premium is not None else Decimal("0.00")
            other_payments = record.payments.exclude(pk=self.pk) if self.pk else record.payments.all()
            other_paid = other_payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
            other_discount = other_payments.aggregate(total=models.Sum("discount"))["total"] or Decimal("0.00")
            if (other_paid + amt + other_discount + disc) > total_prem:
                remaining = max(Decimal("0.00"), total_prem - other_paid - other_discount)
                raise ValidationError({
                    "amount": f"Payment amount (₹{amt:.2f}) plus discount (₹{disc:.2f}) exceeds the remaining balance (₹{remaining:.2f})."
                })

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
