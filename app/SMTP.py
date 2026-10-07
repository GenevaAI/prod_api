import resend
from .config import settings          # ← add this

resend.api_key = settings.RESEND_API_KEY

FROM_EMAIL = settings.FROM_EMAIL
FRONTEND_URL = settings.FRONTEND_URL

def send_password_reset_email(to_email: str, reset_token: str) -> None:
    reset_link = f"{FRONTEND_URL}/api/password-reset/confirm?token={reset_token}"

    params = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": "Password Reset Request",
        "html": f"""
        <p>Hello,</p>
        <p>You requested a password reset. Click the button below:</p>
        <p>
          <a href="{reset_link}"
             style="background:#4CAF50;color:white;padding:10px 20px;
                    text-decoration:none;border-radius:5px;">
             Reset Password
          </a>
        </p>
        <p>Or copy this link:<br>{reset_link}</p>
        <p>If you did not request this, ignore this email.</p>
        """,
        "text": f"Reset your password: {reset_link}"
    }

    resend.Emails.send(params)