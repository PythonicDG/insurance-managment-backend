import html
import logging
import threading
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from .models import BusinessSettings

logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    """Extract client IP address from Django request."""
    if not request:
        return "Unknown"
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "Unknown")
    return ip


def get_recipient_email() -> Optional[str]:
    """
    Retrieve the recipient email address for data export/download alerts.
    Priority:
    1. BusinessSettings.email (configured by the business owner / admin)
    2. settings.ADMIN_NOTIFICATION_EMAIL (configured in .env)
    3. settings.DEFAULT_FROM_EMAIL
    """
    try:
        business_settings = BusinessSettings.objects.filter(id=1).first() or BusinessSettings.objects.first()
        if business_settings and business_settings.email and business_settings.email.strip():
            return business_settings.email.strip()
    except Exception as e:
        logger.warning(f"Could not load BusinessSettings for email recipient: {e}")

    return None


def format_action_title(action_type: str) -> str:
    mapping = {
        "export_csv": "Exported to CSV",
        "save_pdf": "Saved as PDF",
        "print_all": "Printed All Records",
    }
    return mapping.get(action_type.lower(), action_type.replace("_", " ").title())


def format_module_title(source_module: str) -> str:
    mapping = {
        "insurance_records": "Insurance Records",
        "outstanding_ledger": "Outstanding & Payment Ledger",
    }
    return mapping.get(source_module.lower(), source_module.replace("_", " ").title())


def build_email_content(
    business_name: str,
    action_type: str,
    source_module: str,
    record_count: int,
    user_display: str,
    user_email: str,
    client_ip: str,
    formatted_time: str,
    filters: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Constructs both plain-text and responsive HTML email alert notifying
    the business owner that a user has exported/downloaded data.
    Strictly NO attachments are included.
    """
    action_label = format_action_title(action_type)
    module_label = format_module_title(source_module)

    # Format applied filters for presentation
    filter_lines = []
    if filters and isinstance(filters, dict):
        for k, v in filters.items():
            if v not in (None, "", "all", "All", "All Companies", "All Statuses", "0"):
                clean_k = k.replace("_", " ").title()
                filter_lines.append(f"{clean_k}: {v}")

    filters_text = "\n".join(f"  • {f}" for f in filter_lines) if filter_lines else "  • None (All records / default filters)"
    filters_html_items = "".join(f"<li><strong>{html.escape(f.split(':')[0])}:</strong> {html.escape(':'.join(f.split(':')[1:]).strip())}</li>" for f in filter_lines) if filter_lines else "<li><em>None (All records / default filters)</em></li>"

    # Action badge color
    badge_bg = "#eff6ff"
    badge_border = "#bfdbfe"
    badge_color = "#1d4ed8"
    if "csv" in action_type.lower():
        badge_bg = "#ecfdf5"
        badge_border = "#a7f3d0"
        badge_color = "#047857"
    elif "pdf" in action_type.lower():
        badge_bg = "#fef2f2"
        badge_border = "#fecaca"
        badge_color = "#b91c1c"

    # Plain text version
    plain_text = f"""[DATA EXPORT & DOWNLOAD ALERT]
Agency: {business_name}

Hello,

This automated notification is to alert you that data has been exported or downloaded from your InsureLedger system.

ACTIVITY DETAILS:
--------------------------------------------------
• Action Performed: {action_label}
• Module:           {module_label}
• Record Count:     {record_count:,} record(s)
• Performed By:     {user_display} ({user_email or 'No email on file'})
• Timestamp:        {formatted_time}
• Client IP:        {client_ip}

FILTERS APPLIED:
{filters_text}

--------------------------------------------------
SECURITY NOTICE:
As per data security policy, exported files are not attached to this email.
If you did not authorize this data extraction, please verify user activity immediately.

Best regards,
{business_name} Automated Security Alert
"""

    # HTML version
    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Export Notification</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.5;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          
          <!-- Top Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); padding: 24px 28px; text-align: left;">
              <table role="presentation" width="100%">
                <tr>
                  <td>
                    <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #93c5fd; margin-bottom: 4px;">
                      SECURITY &amp; AUDIT ALERT
                    </div>
                    <div style="font-size: 20px; font-weight: 700; color: #ffffff;">
                      {html.escape(business_name)}
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body Content -->
          <tr>
            <td style="padding: 28px;">
              <div style="display: inline-block; padding: 6px 12px; border-radius: 9999px; background-color: {badge_bg}; border: 1px solid {badge_border}; font-size: 13px; font-weight: 600; color: {badge_color}; margin-bottom: 16px;">
                🔔 {html.escape(action_label)} &bull; {html.escape(module_label)}
              </div>

              <h2 style="font-size: 17px; font-weight: 600; color: #0f172a; margin: 0 0 12px 0;">
                Data Download / Export Detected
              </h2>

              <p style="font-size: 14px; color: #475569; margin: 0 0 20px 0;">
                This automated notification is to inform you that a user has downloaded or exported records from your system. Details of the activity are outlined below:
              </p>

              <!-- Event Details Table -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; border-radius: 12px; padding: 16px; font-size: 13px; margin-bottom: 24px;">
                <tr>
                  <td style="padding: 6px 8px; color: #64748b; font-weight: 500; width: 38%;">Action:</td>
                  <td style="padding: 6px 8px; color: #0f172a; font-weight: 600;">{html.escape(action_label)}</td>
                </tr>
                <tr>
                  <td style="padding: 6px 8px; color: #64748b; font-weight: 500;">Module:</td>
                  <td style="padding: 6px 8px; color: #0f172a; font-weight: 600;">{html.escape(module_label)}</td>
                </tr>
                <tr>
                  <td style="padding: 6px 8px; color: #64748b; font-weight: 500;">Records Count:</td>
                  <td style="padding: 6px 8px; color: #0f172a; font-weight: 600;">{record_count:,} record(s)</td>
                </tr>
                <tr>
                  <td style="padding: 6px 8px; color: #64748b; font-weight: 500;">Performed By:</td>
                  <td style="padding: 6px 8px; color: #0f172a; font-weight: 600;">
                    {html.escape(user_display)}
                    {f'<span style="font-weight: 400; color: #64748b;"> ({html.escape(user_email)})</span>' if user_email else ''}
                  </td>
                </tr>
                <tr>
                  <td style="padding: 6px 8px; color: #64748b; font-weight: 500;">Timestamp:</td>
                  <td style="padding: 6px 8px; color: #0f172a; font-weight: 600;">{html.escape(formatted_time)}</td>
                </tr>
                <tr>
                  <td style="padding: 6px 8px; color: #64748b; font-weight: 500;">Client IP:</td>
                  <td style="padding: 6px 8px; color: #0f172a; font-weight: 600; font-family: monospace;">{html.escape(client_ip)}</td>
                </tr>
              </table>

              <!-- Applied Filters Section -->
              <div style="margin-bottom: 24px;">
                <div style="font-size: 13px; font-weight: 600; color: #334155; margin-bottom: 8px;">
                  Active Filters Applied:
                </div>
                <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #475569; line-height: 1.6;">
                  {filters_html_items}
                </ul>
              </div>

              <!-- Notice Box -->
              <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 10px; padding: 12px 14px; font-size: 12px; color: #92400e;">
                <strong>Security Policy Notice:</strong> Exported files are strictly not attached to this email. If this data extraction was unexpected or unauthorized, please review your user accounts and activity immediately.
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 28px; text-align: center; font-size: 12px; color: #94a3b8;">
              This is an automated security audit email sent to the address registered in Business Settings for <strong>{html.escape(business_name)}</strong>.
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    return plain_text, html_content


def _dispatch_email(
    subject: str,
    plain_text: str,
    html_content: str,
    from_email: str,
    to_email: str,
) -> bool:
    """Synchronous email dispatch helper."""
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            from_email=from_email,
            to=[to_email],
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        logger.info(f"Export notification alert successfully sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send export notification alert to {to_email}: {e}", exc_info=True)
        return False


def send_export_notification_email(
    action_type: str,
    source_module: str,
    record_count: int,
    user: Any,
    client_ip: str = "Unknown",
    filters: Optional[Dict[str, Any]] = None,
    async_dispatch: bool = True,
) -> Tuple[bool, str]:
    """
    Sends an email notification alerting the business owner that records
    have been exported/downloaded.
    
    Strictly NO attachments are attached to the email.
    """
    recipient_email = get_recipient_email()
    if not recipient_email:
        msg = "No recipient email configured in Business Settings or .env."
        logger.warning(msg)
        return False, msg

    # Resolve Business Name
    business_name = "InsureLedger Agency"
    try:
        business_settings = BusinessSettings.objects.first()
        if business_settings and business_settings.business_name:
            business_name = business_settings.business_name
    except Exception:
        pass

    # Resolve User details
    user_display = "Unknown User"
    user_email = ""
    if user and getattr(user, "is_authenticated", False):
        full_name = getattr(user, "get_full_name", lambda: "")()
        username = getattr(user, "username", "")
        user_display = f"{full_name} ({username})" if full_name else username
        user_email = getattr(user, "email", "") or ""

    # Current time formatted in local timezone
    now_local = timezone.localtime(timezone.now())
    formatted_time = now_local.strftime("%d %b %Y, %I:%M %p %Z")

    action_label = format_action_title(action_type)
    module_label = format_module_title(source_module)
    subject = f"[Audit Alert] {action_label}: {module_label} ({record_count:,} records) - {business_name}"

    plain_text, html_content = build_email_content(
        business_name=business_name,
        action_type=action_type,
        source_module=source_module,
        record_count=record_count,
        user_display=user_display,
        user_email=user_email,
        client_ip=client_ip,
        formatted_time=formatted_time,
        filters=filters,
    )

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or recipient_email

    import sys
    is_testing = (
        getattr(settings, "TESTING", False)
        or "test" in sys.argv
        or getattr(settings, "EMAIL_BACKEND", "").endswith("locmem.EmailBackend")
    )
    if is_testing:
        async_dispatch = False

    if async_dispatch:
        thread = threading.Thread(
            target=_dispatch_email,
            args=(subject, plain_text, html_content, from_email, recipient_email),
            daemon=True,
        )
        thread.start()
        return True, f"Notification alert queued for dispatch to {recipient_email}."
    else:
        success = _dispatch_email(
            subject=subject,
            plain_text=plain_text,
            html_content=html_content,
            from_email=from_email,
            to_email=recipient_email,
        )
        if success:
            return True, f"Notification alert dispatched to {recipient_email}."
        else:
            return False, f"Failed to send email to {recipient_email}. Check SMTP configuration."


def send_pin_verification_otp_email(
    otp: str,
    business_name: str,
    recipient_email: str,
    async_dispatch: bool = True,
) -> Tuple[bool, str]:
    """
    Sends a 6-digit OTP verification code to the business email
    to authorize setting or resetting the Export Security PIN.
    """
    subject = f"[Security Verification] PIN Setup Code: {otp} - {business_name}"

    plain_text = f"""[SECURITY VERIFICATION]
Agency: {business_name}

Hello,

A request was made to set or reset the Export Security PIN for your InsureLedger system.

YOUR VERIFICATION CODE:
--------------------------------------------------
{otp}
--------------------------------------------------
This code is valid for 10 minutes.

If you did not request this, please disregard this email. Your PIN will not be changed.

Best regards,
{business_name} Security Team
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Verification Code</title></head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <tr>
            <td style="background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%); padding: 22px 24px; text-align: left;">
              <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #93c5fd; margin-bottom: 4px;">
                SECURITY AUTHORIZATION
              </div>
              <div style="font-size: 18px; font-weight: 700; color: #ffffff;">
                {html.escape(business_name)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 28px 24px;">
              <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0 0 10px 0;">
                Export Security PIN Verification
              </h2>
              <p style="font-size: 13px; color: #475569; margin: 0 0 20px 0; line-height: 1.5;">
                A request has been initiated to set or reset the Security PIN required for exporting records and downloading PDFs. Use the 6-digit verification code below:
              </p>
              <div style="background-color: #f1f5f9; border-radius: 12px; padding: 18px; text-align: center; margin-bottom: 20px; border: 1px dashed #cbd5e1;">
                <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; margin-bottom: 6px;">
                  One-Time Verification Code
                </div>
                <div style="font-size: 32px; font-weight: 800; letter-spacing: 0.25em; color: #1e3a8a; font-family: monospace;">
                  {html.escape(otp)}
                </div>
                <div style="font-size: 11px; color: #94a3b8; margin-top: 6px;">
                  Expires in 10 minutes
                </div>
              </div>
              <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px; font-size: 12px; color: #92400e;">
                <strong>Notice:</strong> Never share this verification code with anyone. If you did not make this request, you can safely ignore this email.
              </div>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 14px 24px; text-align: center; font-size: 11px; color: #94a3b8;">
              Automated security message for {html.escape(business_name)}.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or recipient_email

    import sys
    is_testing = (
        getattr(settings, "TESTING", False)
        or "test" in sys.argv
        or getattr(settings, "EMAIL_BACKEND", "").endswith("locmem.EmailBackend")
    )
    if is_testing:
        async_dispatch = False

    if async_dispatch:
        thread = threading.Thread(
            target=_dispatch_email,
            args=(subject, plain_text, html_content, from_email, recipient_email),
            daemon=True,
        )
        thread.start()
        return True, f"Verification code sent to {recipient_email}."
    else:
        success = _dispatch_email(
            subject=subject,
            plain_text=plain_text,
            html_content=html_content,
            from_email=from_email,
            to_email=recipient_email,
        )
        if success:
            return True, f"Verification code sent to {recipient_email}."
        else:
            return False, f"Failed to send verification email to {recipient_email}."


def send_pin_updated_alert_email(
    business_name: str,
    recipient_email: str,
    updated_by: str,
    async_dispatch: bool = True,
) -> Tuple[bool, str]:
    """
    Sends a security alert email confirming that the Export Security PIN has been updated.
    """
    subject = f"[Security Alert] Export Security PIN Updated - {business_name}"

    plain_text = f"""[SECURITY NOTIFICATION]
Agency: {business_name}

Hello,

The Export Security PIN for bulk data downloads (CSV/PDF) in InsureLedger was updated successfully.

Updated by: {updated_by}
Timestamp: {timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p %Z')}

If you did not perform this change, please contact your administrator immediately.

Best regards,
{business_name} Security Team
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>PIN Updated</title></head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <tr>
            <td style="background: linear-gradient(135deg, #059669 0%, #10b981 100%); padding: 20px 24px; text-align: left;">
              <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #d1fae5; margin-bottom: 4px;">
                SECURITY STATUS UPDATE
              </div>
              <div style="font-size: 18px; font-weight: 700; color: #ffffff;">
                {html.escape(business_name)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px;">
              <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0 0 10px 0;">
                Export Security PIN Successfully Updated
              </h2>
              <p style="font-size: 13px; color: #475569; margin: 0 0 16px 0; line-height: 1.5;">
                The Security PIN required for downloading CSV files and printing/saving PDFs was changed.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; border-radius: 10px; padding: 12px; font-size: 13px;">
                <tr>
                  <td style="padding: 4px 8px; color: #64748b; font-weight: 500;">Updated By:</td>
                  <td style="padding: 4px 8px; color: #0f172a; font-weight: 600;">{html.escape(updated_by)}</td>
                </tr>
                <tr>
                  <td style="padding: 4px 8px; color: #64748b; font-weight: 500;">Timestamp:</td>
                  <td style="padding: 4px 8px; color: #0f172a; font-weight: 600;">{html.escape(timezone.localtime(timezone.now()).strftime('%d %b %Y, %I:%M %p %Z'))}</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 14px 24px; text-align: center; font-size: 11px; color: #94a3b8;">
              Automated security message for {html.escape(business_name)}.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or recipient_email

    import sys
    is_testing = (
        getattr(settings, "TESTING", False)
        or "test" in sys.argv
        or getattr(settings, "EMAIL_BACKEND", "").endswith("locmem.EmailBackend")
    )
    if is_testing:
        async_dispatch = False

    if async_dispatch:
        thread = threading.Thread(
            target=_dispatch_email,
            args=(subject, plain_text, html_content, from_email, recipient_email),
            daemon=True,
        )
        thread.start()
        return True, f"Security confirmation email queued for {recipient_email}."
    else:
        success = _dispatch_email(
            subject=subject,
            plain_text=plain_text,
            html_content=html_content,
            from_email=from_email,
            to_email=recipient_email,
        )
        return success, f"Security confirmation email dispatched to {recipient_email}."


def send_pin_removed_alert_email(
    business_name: str,
    recipient_email: str,
    removed_by: str = "Administrator",
    async_dispatch: bool = True,
) -> tuple[bool, str]:
    """
    Sends a security notification email alerting that the Export Security PIN
    has been removed / disabled.
    """
    import html
    from django.utils import timezone

    subject = f"Security Notice: Export Security PIN Removed - {business_name}"

    formatted_time = timezone.localtime(timezone.now()).strftime("%d %b %Y, %I:%M %p %Z")

    plain_text = f"""Security Alert: Export Security PIN Removed

The Export Security PIN for {business_name} has been removed/disabled.
Bulk data exports (CSV, PDF, Print) will no longer require a PIN authorization.

Removed by: {removed_by}
Timestamp: {formatted_time}

If you did not authorize this action, please access your Settings immediately and configure a new Security PIN.

Best regards,
{business_name} Security Team
"""

    html_content = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>PIN Removed</title></head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; padding: 32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <tr>
            <td style="background: linear-gradient(135deg, #e11d48 0%, #f43f5e 100%); padding: 20px 24px; text-align: left;">
              <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #ffe4e6; margin-bottom: 4px;">
                SECURITY STATUS ALERT
              </div>
              <div style="font-size: 18px; font-weight: 700; color: #ffffff;">
                {html.escape(business_name)}
              </div>
            </td>
          </tr>
          <tr>
            <td style="padding: 24px;">
              <h2 style="font-size: 16px; font-weight: 600; color: #0f172a; margin: 0 0 10px 0;">
                Export Security PIN Disabled / Removed
              </h2>
              <p style="font-size: 13px; color: #475569; margin: 0 0 16px 0; line-height: 1.5;">
                The Security PIN required for downloading CSV records and saving/printing PDFs has been removed. Data exports will no longer require a PIN unless reconfigured.
              </p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #fff1f2; border: 1px solid #fecdd3; border-radius: 10px; padding: 12px; font-size: 13px; margin-bottom: 16px;">
                <tr>
                  <td style="padding: 4px 8px; color: #9f1239; font-weight: 500;">Action:</td>
                  <td style="padding: 4px 8px; color: #881337; font-weight: 600;">Security PIN Removed</td>
                </tr>
                <tr>
                  <td style="padding: 4px 8px; color: #9f1239; font-weight: 500;">Removed By:</td>
                  <td style="padding: 4px 8px; color: #881337; font-weight: 600;">{html.escape(removed_by)}</td>
                </tr>
                <tr>
                  <td style="padding: 4px 8px; color: #9f1239; font-weight: 500;">Timestamp:</td>
                  <td style="padding: 4px 8px; color: #881337; font-weight: 600;">{html.escape(formatted_time)}</td>
                </tr>
              </table>
              <div style="font-size: 12px; color: #64748b; line-height: 1.4;">
                If you did not authorize this change, please log in to your account and re-configure your Security PIN in <strong>Account &amp; Security</strong> settings.
              </div>
            </td>
          </tr>
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 14px 24px; text-align: center; font-size: 11px; color: #94a3b8;">
              Automated security message for {html.escape(business_name)}.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or recipient_email

    import sys
    is_testing = (
        getattr(settings, "TESTING", False)
        or "test" in sys.argv
        or getattr(settings, "EMAIL_BACKEND", "").endswith("locmem.EmailBackend")
    )
    if is_testing:
        async_dispatch = False

    if async_dispatch:
        thread = threading.Thread(
            target=_dispatch_email,
            args=(subject, plain_text, html_content, from_email, recipient_email),
            daemon=True,
        )
        thread.start()
        return True, f"Security removal confirmation email queued for {recipient_email}."
    else:
        success = _dispatch_email(
            subject=subject,
            plain_text=plain_text,
            html_content=html_content,
            from_email=from_email,
            to_email=recipient_email,
        )
        return success, f"Security removal confirmation email dispatched to {recipient_email}."


