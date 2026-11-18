import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def mail_configured() -> bool:
    return bool(os.getenv("BREVO_API_KEY"))


def send_code(to: str, code: str) -> None:
    if not mail_configured():
        print(f"[MAIL] BREVO_API_KEY не задан, письмо не отправлено. Код для {to}: {code}", flush=True)
        return

    sender_email = os.getenv("BREVO_SENDER_EMAIL", "")
    if not sender_email:
        raise RuntimeError("В .env не задан BREVO_SENDER_EMAIL (подтверждённый отправитель в Brevo)")

    payload = {
        "sender": {"name": os.getenv("BREVO_SENDER_NAME", "Swaply"), "email": sender_email},
        "to": [{"email": to}],
        "subject": "Код подтверждения Swaply",
        "htmlContent": (
            "<p>Ваш код подтверждения:</p>"
            f"<p style=\"font-size:28px;font-weight:700;letter-spacing:4px\">{code}</p>"
            "<p>Код действует 10 минут. Если вы не регистрировались в Swaply, "
            "просто проигнорируйте это письмо.</p>"
        ),
        "textContent": (
            f"Ваш код подтверждения: {code}\n\n"
            "Код действует 10 минут. Если вы не регистрировались в Swaply, просто проигнорируйте это письмо."
        ),
    }
    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": os.getenv("BREVO_API_KEY", ""),
            "accept": "application/json",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15):
            pass
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Brevo вернул {e.code}: {e.read().decode('utf-8', 'replace')}") from e
