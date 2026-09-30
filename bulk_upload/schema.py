"""Allowed import fields. Admin mappings cannot write arbitrary model attributes."""
import re

CUSTOMER_FIELDS = {
    "name": ("Customer name", "text"),
    "phone": ("Mobile number", "text"),
    "alternative_mobile_number": ("Alternative mobile number", "text"),
    "email": ("Email", "text"),
    "address": ("Address", "text"),
}
INSURANCE_FIELDS = {
    "customer_name": ("Customer name", "text"),
    "customer_phone": ("Mobile number", "text"),
    "customer_alternative_mobile_number": ("Alternative mobile number", "text"),
    "customer_email": ("Email", "text"),
    "customer_address": ("Address", "text"),
    "vehicle_number": ("Vehicle number", "text"),
    "vehicle_type": ("Vehicle type", "text"),
    "insurance_company_name": ("Insurance company name", "text"),
    "policy_number": ("Policy number", "text"),
    "entry_date": ("Entry date", "date"),
    "policy_start_date": ("Policy start date", "date"),
    "policy_expiry_date": ("Policy expiry date", "date"),
    "total_premium": ("Total premium", "decimal"),
    "discount": ("Discount", "decimal"),
    "remarks": ("Remarks", "text"),
}
FIELDS = {"customers": CUSTOMER_FIELDS, "insurance": INSURANCE_FIELDS}
REQUIRED_FIELDS = {
    "customers": {"phone"},
    "insurance": {"customer_phone", "vehicle_number", "insurance_company_name",
                  "policy_number", "policy_start_date", "policy_expiry_date", "total_premium"},
}
FIELD_CHOICES = [(key, f"{label} ({key})") for key, (label, _) in
                 {**CUSTOMER_FIELDS, **INSURANCE_FIELDS}.items()]


def normalize_header(value):
    return re.sub(r"[\s_-]+", " ", str(value or "").strip()).casefold()


def validate_columns(target, columns):
    from django.core.exceptions import ValidationError

    active = [c for c in columns if c.is_active]
    if not active:
        raise ValidationError("At least one active column is required.")
    headers, fields = set(), set()
    for column in active:
        if column.field_name not in FIELDS.get(target, {}):
            raise ValidationError(f"Field '{column.field_name}' is not available for {target}.")
        if column.field_name in fields:
            raise ValidationError(f"Field '{column.field_name}' is mapped more than once.")
        fields.add(column.field_name)
        for name in [column.column_name, *column.aliases.splitlines()]:
            name = normalize_header(name)
            if not name:
                continue
            if name in headers:
                raise ValidationError("Column names and aliases must be unique (ignoring case, spaces, hyphens and underscores).")
            headers.add(name)
        if column.field_name in REQUIRED_FIELDS[target] and not column.is_required and not column.default_value.strip():
            raise ValidationError(f"'{column.column_name}' must be required or have a default value.")
    missing = REQUIRED_FIELDS[target] - fields
    if missing:
        raise ValidationError("Required mappings cannot be removed or disabled: " + ", ".join(sorted(missing)))
