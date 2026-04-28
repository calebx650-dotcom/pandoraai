"""Resend email sender. Falls back to no-op if RESEND_API_KEY isn't set."""
import os
import resend

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FROM_ADDRESS = os.environ.get("EMAIL_FROM", "reports@ighsafety.com")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def send_report_email(to_address, subject, html_body):
    """Send a report email via Resend. Returns (ok, error_or_id)."""
    if not RESEND_API_KEY:
        return False, "RESEND_API_KEY not configured"
    if not to_address:
        return False, "no recipient"
    try:
        r = resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to_address],
            "subject": subject,
            "html": html_body,
        })
        return True, r.get("id", "sent")
    except Exception as e:
        return False, str(e)
