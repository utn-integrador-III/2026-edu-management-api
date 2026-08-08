import os
import requests

RESEND_API_URL = "https://api.resend.com/emails"

def send_mail(to: str, subject: str, html: str):
    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "from": os.getenv("EMAIL_FROM"),
            "to": [to],
            "subject": subject,
            "html": html,
        },
    )
    response.raise_for_status()
