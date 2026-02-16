"""
Email service using Gmail SMTP for sending alarm/reminder notifications.

Requires the following environment variables:
    GMAIL_ADDRESS      - Your Gmail address (sender)
    GMAIL_APP_PASSWORD - Gmail App Password (NOT your regular password)
    REMINDER_EMAIL     - Recipient email (defaults to GMAIL_ADDRESS if unset)

To generate an App Password:
    1. Enable 2-Step Verification on your Google account
    2. Go to https://myaccount.google.com/apppasswords
    3. Create an App Password for "Mail"
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class EmailService:
    """Sends emails via Gmail SMTP."""

    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    def __init__(self, sender_email: str, sender_password: str, recipient_email: str = ""):
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipient_email = recipient_email or sender_email

    def send_reminder(self, subject: str, body: str) -> bool:
        """Send a reminder email.

        Returns True on success, False on failure.
        """
        if not self.sender_email or not self.sender_password:
            print("[EmailService] Gmail credentials not configured")
            return False

        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"[EmailService] Error sending email: {e}")
            return False
