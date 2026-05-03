"""Send the email digest via Brevo's transactional-email REST API.

No new dependency — urllib only. Fail-open: log-and-skip on network error, do
not crash the pipeline (the artifact push is the canonical ship; email is a
best-effort amplifier).
"""
from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

_BREVO = "https://api.brevo.com/v3/smtp/email"


def send_email(
    *,
    from_email: str,
    api_key: str,
    subject: str,
    html: str,
    text: str,
    to_emails: list[str] | None = None,
) -> int:
    payload: dict[str, Any] = {
        "sender": {"email": from_email},
        "to": [{"email": e} for e in (to_emails or [from_email])],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    req = Request(_BREVO, data=json.dumps(payload).encode(),
                  headers={"content-type": "application/json",
                           "api-key": api_key, "accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            return getattr(r, "status", 0)
    except Exception:
        return 0
