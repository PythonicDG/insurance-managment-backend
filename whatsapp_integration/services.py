from concurrent.futures import ThreadPoolExecutor
import logging
import re
from typing import Any, Dict, List, Optional
import requests

from .models import WhatsAppConfig, WhatsAppMessageLog

logger = logging.getLogger(__name__)

# Background executor for non-blocking message dispatch
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wa_sender")


def normalize_phone_number(phone: str, default_country_code: str = "91") -> str:
    """
    Sanitize phone number for Meta WhatsApp Cloud API.
    - Strips spaces, dashes, brackets, plus signs, leading zeros.
    - If 10 digits (standard Indian mobile), prepends default_country_code (e.g. 91).
    - Returns clean international format without leading '+' (e.g. 919876543210).
    """
    if not phone:
        return ""
    
    # Strip all non-digit characters
    cleaned = re.sub(r"\D", "", str(phone).strip())
    
    # Remove leading zeros
    cleaned = cleaned.lstrip("0")
    
    if not cleaned:
        return ""

    clean_default_cc = re.sub(r"\D", "", str(default_country_code).strip()) or "91"

    # If it's a 10-digit number, prepend default country code
    if len(cleaned) == 10:
        return f"{clean_default_cc}{cleaned}"
    
    return cleaned


class WhatsAppClient:
    """
    Official Meta WhatsApp Cloud API Client.
    Handles template messages, direct text messages, error logging, and background dispatch.
    """

    @staticmethod
    def get_api_endpoint(config: WhatsAppConfig) -> str:
        version = config.api_version.strip() if config.api_version else "v21.0"
        if not version.startswith("v"):
            version = f"v{version}"
        phone_id = config.phone_number_id.strip()
        return f"https://graph.facebook.com/{version}/{phone_id}/messages"

    @classmethod
    def send_template_message(
        cls,
        to_phone: str,
        template_name: str,
        language_code: str = "en",
        body_parameters: Optional[List[str]] = None,
        context_data: Optional[Dict[str, Any]] = None,
        message_type: str = "CUSTOM",
    ) -> WhatsAppMessageLog:
        """
        Sends an approved WhatsApp Template message via Meta Cloud API.
        """
        config = WhatsAppConfig.get_config()
        normalized_recipient = normalize_phone_number(to_phone, config.default_country_code)

        context_data = context_data or {}
        customer = context_data.get("customer")
        record = context_data.get("insurance_record")
        payment = context_data.get("payment")

        # Check if WhatsApp integration is enabled
        if not config.is_enabled:
            logger.info("WhatsApp integration is disabled in configuration. Skipping send.")
            return WhatsAppMessageLog.objects.create(
                customer=customer,
                insurance_record=record,
                payment=payment,
                recipient_phone=normalized_recipient or to_phone,
                message_type=message_type,
                template_name=template_name,
                parameters={"body": body_parameters or []},
                status="failed",
                error_message="WhatsApp integration is disabled in system configuration.",
            )

        # Handle TEST MODE: Redirect to admin's test phone number
        is_test = False
        target_phone = normalized_recipient
        if config.test_mode:
            is_test = True
            if config.test_phone_number:
                admin_test_phone = normalize_phone_number(config.test_phone_number, config.default_country_code)
                logger.info(
                    f"[TEST MODE ACTIVE] Redirecting WhatsApp notification from {normalized_recipient} to admin test number: {admin_test_phone}"
                )
                target_phone = admin_test_phone
            else:
                logger.warning(
                    "[TEST MODE ACTIVE] No test_phone_number configured in WhatsApp settings! Sending to original recipient in test mode."
                )

        if not target_phone:
            return WhatsAppMessageLog.objects.create(
                customer=customer,
                insurance_record=record,
                payment=payment,
                recipient_phone=to_phone,
                message_type=message_type,
                template_name=template_name,
                parameters={"body": body_parameters or []},
                status="failed",
                error_message="Recipient phone number is invalid or empty.",
                is_test=is_test,
            )

        if not config.access_token or not config.phone_number_id:
            msg = "Missing Meta Access Token or Phone Number ID in configuration."
            logger.error(msg)
            return WhatsAppMessageLog.objects.create(
                customer=customer,
                insurance_record=record,
                payment=payment,
                recipient_phone=target_phone,
                message_type=message_type,
                template_name=template_name,
                parameters={"body": body_parameters or []},
                status="failed",
                error_message=msg,
                is_test=is_test,
            )

        # Construct Meta WhatsApp Cloud API Template Payload
        body_params = body_parameters or []
        components = []
        if body_params:
            components.append({
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str(p)} for p in body_params
                ]
            })

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target_phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code or "en"
                }
            }
        }
        if components:
            payload["template"]["components"] = components

        url = cls.get_api_endpoint(config)
        headers = {
            "Authorization": f"Bearer {config.access_token.strip()}",
            "Content-Type": "application/json",
        }

        # Create audit log record
        log = WhatsAppMessageLog.objects.create(
            customer=customer,
            insurance_record=record,
            payment=payment,
            recipient_phone=target_phone,
            message_type=message_type,
            template_name=template_name,
            parameters={"body": body_params, "original_recipient": normalized_recipient},
            request_payload=payload,
            status="queued",
            is_test=is_test,
        )

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=12)
            try:
                res_data = response.json()
            except Exception:
                res_data = {"raw_text": response.text}

            log.response_payload = res_data

            if response.status_code in (200, 201):
                messages = res_data.get("messages", [])
                if messages and isinstance(messages, list):
                    log.wamid = messages[0].get("id", "")
                log.status = "sent"
                log.error_message = ""
                logger.info(f"WhatsApp message sent successfully to {target_phone}. WAMID: {log.wamid}")
            else:
                log.status = "failed"
                err = res_data.get("error", {})
                error_detail = (
                    f"HTTP {response.status_code}: {err.get('message', '')} "
                    f"(type: {err.get('type', '')}, code: {err.get('code', '')}, subcode: {err.get('error_subcode', '')})"
                )
                log.error_message = error_detail.strip()
                logger.error(f"WhatsApp Meta API Error: {error_detail}")

            log.save()
            return log

        except requests.exceptions.RequestException as exc:
            log.status = "failed"
            log.error_message = f"Connection error: {str(exc)}"
            log.save()
            logger.exception("Failed to connect to Meta WhatsApp Cloud API")
            return log

    @classmethod
    def send_text_message(
        cls,
        to_phone: str,
        text: str,
        is_test: bool = False,
    ) -> WhatsAppMessageLog:
        """
        Sends a standard direct text message.
        Note: Freeform text messages via WhatsApp Cloud API are only permitted
        within the 24-hour customer service window or in development sandbox.
        """
        config = WhatsAppConfig.get_config()
        normalized_recipient = normalize_phone_number(to_phone, config.default_country_code)

        target_phone = normalized_recipient
        if config.test_mode and config.test_phone_number:
            target_phone = normalize_phone_number(config.test_phone_number, config.default_country_code)

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target_phone,
            "type": "text",
            "text": {
                "body": text,
                "preview_url": False
            }
        }

        url = cls.get_api_endpoint(config)
        headers = {
            "Authorization": f"Bearer {config.access_token.strip()}",
            "Content-Type": "application/json",
        }

        log = WhatsAppMessageLog.objects.create(
            recipient_phone=target_phone,
            message_type="TEST" if is_test else "CUSTOM",
            parameters={"text": text},
            request_payload=payload,
            status="queued",
            is_test=is_test or config.test_mode,
        )

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=12)
            try:
                res_data = response.json()
            except Exception:
                res_data = {"raw_text": response.text}

            log.response_payload = res_data
            if response.status_code in (200, 201):
                messages = res_data.get("messages", [])
                if messages and isinstance(messages, list):
                    log.wamid = messages[0].get("id", "")
                log.status = "sent"
            else:
                log.status = "failed"
                err = res_data.get("error", {})
                log.error_message = f"HTTP {response.status_code}: {err.get('message', '')}"

            log.save()
            return log
        except Exception as exc:
            log.status = "failed"
            log.error_message = str(exc)
            log.save()
            return log

    @classmethod
    def send_policy_issued_notification(cls, record, async_send: bool = True):
        """
        Dispatches WhatsApp Policy Issued Notification.
        Template variables mapping:
        {{1}} = Customer Name
        {{2}} = Vehicle Number
        {{3}} = Policy Number
        {{4}} = Insurance Company Name
        {{5}} = Expiry Date
        {{6}} = Total Premium
        {{7}} = Paid Amount
        {{8}} = Outstanding Balance
        """
        config = WhatsAppConfig.get_config()
        if not config.is_enabled:
            return None

        customer = getattr(record, "customer", None)
        vehicle = getattr(record, "vehicle", None)
        company = getattr(record, "insurance_company", None)

        customer_name = customer.name if (customer and customer.name) else "Valued Customer"
        vehicle_num = vehicle.vehicle_number if vehicle else "Vehicle"
        policy_num = record.policy_number or "N/A"
        company_name = company.name if company else "Insurance"
        expiry_date = str(record.policy_expiry_date) if record.policy_expiry_date else "N/A"
        total_premium = f"INR {record.total_premium:,.2f}" if record.total_premium is not None else "0.00"
        paid_amount = f"INR {record.total_paid:,.2f}"
        outstanding = f"INR {record.outstanding:,.2f}"

        recipient_phone = ""
        if customer and customer.phone:
            recipient_phone = customer.phone
        elif record.alternative_mobile_number:
            recipient_phone = record.alternative_mobile_number

        body_parameters = [
            customer_name,
            vehicle_num,
            policy_num,
            company_name,
            expiry_date,
            total_premium,
            paid_amount,
            outstanding,
        ]

        context = {
            "customer": customer,
            "insurance_record": record,
        }

        def _execute():
            return cls.send_template_message(
                to_phone=recipient_phone,
                template_name=config.policy_template_name,
                language_code=config.policy_template_language,
                body_parameters=body_parameters,
                context_data=context,
                message_type="POLICY_ISSUED",
            )

        if async_send:
            _executor.submit(_execute)
            return None
        return _execute()

    @classmethod
    def send_payment_received_notification(cls, payment, async_send: bool = True):
        """
        Dispatches WhatsApp Payment Received Receipt.
        Template variables mapping:
        {{1}} = Customer Name
        {{2}} = Vehicle Number
        {{3}} = Receipt / Payment ID
        {{4}} = Paid Amount
        {{5}} = Payment Date
        {{6}} = Payment Method
        {{7}} = Remaining Outstanding Balance
        """
        config = WhatsAppConfig.get_config()
        if not config.is_enabled:
            return None

        record = getattr(payment, "insurance_record", None)
        if not record:
            return None

        customer = getattr(record, "customer", None)
        vehicle = getattr(record, "vehicle", None)

        customer_name = customer.name if (customer and customer.name) else "Valued Customer"
        vehicle_num = vehicle.vehicle_number if vehicle else "Vehicle"
        receipt_id = f"RCP-{payment.id}"
        paid_amount = f"INR {payment.amount:,.2f}"
        payment_date = str(payment.payment_date) if payment.payment_date else "N/A"
        payment_method = payment.payment_method or "Cash"
        outstanding = f"INR {record.outstanding:,.2f}"

        recipient_phone = ""
        if customer and customer.phone:
            recipient_phone = customer.phone
        elif record.alternative_mobile_number:
            recipient_phone = record.alternative_mobile_number

        body_parameters = [
            customer_name,
            vehicle_num,
            receipt_id,
            paid_amount,
            payment_date,
            payment_method,
            outstanding,
        ]

        context = {
            "customer": customer,
            "insurance_record": record,
            "payment": payment,
        }

        def _execute():
            return cls.send_template_message(
                to_phone=recipient_phone,
                template_name=config.payment_template_name,
                language_code=config.payment_template_language,
                body_parameters=body_parameters,
                context_data=context,
                message_type="PAYMENT_RECEIPT",
            )

        if async_send:
            _executor.submit(_execute)
            return None
        return _execute()
