import os
import re
from django.conf import settings
from django.db import models


class WhatsAppConfig(models.Model):
    """
    Configuration settings for Meta WhatsApp Cloud API.
    Can be edited via Web UI or populated from environment variables.
    """
    is_enabled = models.BooleanField(
        default=True,
        help_text="Master toggle to enable or disable WhatsApp sending."
    )
    test_mode = models.BooleanField(
        default=True,
        help_text="When test mode is enabled, messages are redirected to the test phone number instead of customers."
    )
    test_phone_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Admin test phone number (with country code, e.g. 919876543210) for testing before live deployment."
    )
    phone_number_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Meta WhatsApp Phone Number ID (from Meta Developer App -> WhatsApp -> API Setup)."
    )
    waba_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="WhatsApp Business Account ID (WABA ID)."
    )
    access_token = models.TextField(
        blank=True,
        default="",
        help_text="Meta System User Permanent Access Token (or 24-hr Temporary Token for testing)."
    )
    api_version = models.CharField(
        max_length=10,
        default="v21.0",
        help_text="Meta Graph API version (default: v21.0)."
    )
    default_country_code = models.CharField(
        max_length=5,
        default="91",
        help_text="Default country code without plus sign (e.g. 91 for India)."
    )
    policy_template_name = models.CharField(
        max_length=100,
        default="insurance_policy_issued",
        help_text="Meta-approved Template Name for newly issued insurance policies."
    )
    policy_template_language = models.CharField(
        max_length=10,
        default="en",
        help_text="Language code of the approved policy template (e.g. en, en_US, hi)."
    )
    payment_template_name = models.CharField(
        max_length=100,
        default="payment_receipt_collected",
        help_text="Meta-approved Template Name for payment receipts."
    )
    payment_template_language = models.CharField(
        max_length=10,
        default="en",
        help_text="Language code of the approved payment template (e.g. en, en_US, hi)."
    )
    webhook_verify_token = models.CharField(
        max_length=100,
        blank=True,
        default="insure_wa_webhook_secret_key",
        help_text="Secret token configured in Meta Developer App Webhooks to verify endpoint authenticity."
    )
    auto_send_policy_creation = models.BooleanField(
        default=True,
        help_text="Automatically send WhatsApp message when an insurance record is created or renewed."
    )
    auto_send_payment_receipt = models.BooleanField(
        default=True,
        help_text="Automatically send WhatsApp message when a payment is collected."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Configuration"
        verbose_name_plural = "WhatsApp Configuration"

    def __str__(self):
        status = "Active" if self.is_enabled else "Disabled"
        mode = "TEST MODE" if self.test_mode else "LIVE"
        return f"WhatsApp Config ({status}, {mode})"

    @classmethod
    def get_config(cls):
        """
        Get or initialize the single WhatsAppConfig instance.
        Defaults to environment variables if record fields are empty.
        """
        config = cls.objects.first()
        if not config:
            config = cls.objects.create(
                is_enabled=os.getenv("WHATSAPP_ENABLED", "True").strip().lower() in ("true", "1", "t", "yes"),
                test_mode=os.getenv("WHATSAPP_TEST_MODE", "True").strip().lower() in ("true", "1", "t", "yes"),
                test_phone_number=os.getenv("WHATSAPP_TEST_PHONE", "").strip(),
                phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
                waba_id=os.getenv("WHATSAPP_WABA_ID", "").strip(),
                access_token=os.getenv("WHATSAPP_API_TOKEN", "").strip(),
                api_version=os.getenv("WHATSAPP_API_VERSION", "v21.0").strip(),
                default_country_code=os.getenv("WHATSAPP_DEFAULT_COUNTRY_CODE", "91").strip(),
                policy_template_name=os.getenv("WHATSAPP_TEMPLATE_POLICY_CREATED", "insurance_policy_issued").strip(),
                payment_template_name=os.getenv("WHATSAPP_TEMPLATE_PAYMENT_COLLECTED", "payment_receipt_collected").strip(),
                webhook_verify_token=os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "insure_wa_webhook_secret_key").strip(),
            )
        else:
            # Fallback to env for token or phone_number_id if empty in DB
            dirty = False
            if not config.access_token and os.getenv("WHATSAPP_API_TOKEN"):
                config.access_token = os.getenv("WHATSAPP_API_TOKEN").strip()
                dirty = True
            if not config.phone_number_id and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
                config.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID").strip()
                dirty = True
            if not config.waba_id and os.getenv("WHATSAPP_WABA_ID"):
                config.waba_id = os.getenv("WHATSAPP_WABA_ID").strip()
                dirty = True
            if not config.test_phone_number and os.getenv("WHATSAPP_TEST_PHONE"):
                config.test_phone_number = os.getenv("WHATSAPP_TEST_PHONE").strip()
                dirty = True
            if dirty:
                config.save()
        return config


class WhatsAppMessageLog(models.Model):
    """
    Audit log for all outgoing and incoming WhatsApp messages, tracking delivery status,
    parameters sent, response IDs, and errors.
    """
    MESSAGE_TYPES = [
        ("POLICY_ISSUED", "Policy Issued"),
        ("PAYMENT_RECEIPT", "Payment Receipt"),
        ("TEST", "Test Message"),
        ("CUSTOM", "Custom Message"),
    ]

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("sent", "Sent to Meta"),
        ("delivered", "Delivered to Phone"),
        ("read", "Read by Customer"),
        ("failed", "Failed"),
    ]

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )
    insurance_record = models.ForeignKey(
        "insurance.InsuranceRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_logs",
    )

    recipient_phone = models.CharField(max_length=25, db_index=True)
    message_type = models.CharField(max_length=30, choices=MESSAGE_TYPES, default="POLICY_ISSUED")
    template_name = models.CharField(max_length=100, blank=True, default="")
    parameters = models.JSONField(default=dict, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    wamid = models.CharField(max_length=150, blank=True, default="", db_index=True, help_text="Meta WhatsApp Message ID")
    
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    is_test = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "WhatsApp Message Log"
        verbose_name_plural = "WhatsApp Message Logs"

    def __str__(self):
        return f"{self.message_type} -> {self.recipient_phone} ({self.status}) [{self.created_at.strftime('%Y-%m-%d %H:%M')}]"
