"""Send sign-in OTP codes via Resend (https://resend.com)."""
from __future__ import annotations

import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_SUBJECT = "Your Nemo Anki sign-in code"


def _html(code: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:440px;margin:0 auto;padding:8px">
  <p style="font-size:15px;color:#1a1f2e">Here's your Nemo&nbsp;Anki sign-in code:</p>
  <div style="font-size:34px;font-weight:800;letter-spacing:10px;color:#3b5bdb;
              background:#f0f3ff;border-radius:12px;padding:16px;text-align:center;margin:14px 0">{code}</div>
  <p style="font-size:13px;color:#8a90a2">It expires in a few minutes. If you didn't request it, you can ignore this email.</p>
</div>"""


def send_otp_email(to_email: str, code: str) -> bool:
    """Email the OTP code. Returns True if Resend accepted it, else False."""
    if not settings.RESEND_API_KEY:
        return False
    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.OTP_FROM_EMAIL,
                "to": [to_email],
                "subject": _SUBJECT,
                "html": _html(code),
                "text": f"Your Nemo Anki sign-in code is {code}. It expires in a few minutes.",
            },
            timeout=15,
        )
        res.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001 - don't break sign-in on email failure
        logger.warning("OTP email send failed for %s: %s", to_email, exc)
        return False
