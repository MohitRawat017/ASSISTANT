"""
================================================================================
EMAIL SERVICE - GMAIL SMTP
================================================================================

Simple email service for sending alarm/reminder notifications via Gmail SMTP.

WHY SMTP INSTEAD OF GMAIL API?
=============================
For this standalone reminder script:
- SMTP is simpler (no OAuth flow needed)
- Works with App Passwords (no token refresh)
- Fewer dependencies
- More portable

Gmail API is used in the main app for reading emails, but SMTP is
simpler for just sending notifications.

REQUIREMENTS:
=============
1. Gmail account with 2-Factor Authentication enabled
2. App Password generated at https://myaccount.google.com/apppasswords
3. App Password stored in GMAIL_APP_PASSWORD env variable

SETUP:
======
1. Go to https://myaccount.google.com/security
2. Enable 2-Step Verification
3. Go to App Passwords
4. Generate new App Password (name it "Tsuzi Assistant")
5. Copy the 16-character password to .env WITHOUT spaces
   (spaces are stripped automatically if pasted with them):
   GMAIL_APP_PASSWORD=<paste-your-16-character-app-password>

SECURITY NOTE:
==============
- NEVER use your real Gmail password
- App Passwords are revocable without changing main password
- App Passwords have limited scope (only email)

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: What's the difference between SMTP and Gmail API?
A: SMTP: Standard email protocol, works with any email provider
   Gmail API: Google-specific, requires OAuth, more features
   
   SMTP is simpler for sending only. Gmail API is better for reading,
   searching, and managing emails.

================================================================================
"""

import logging
import smtplib
from src.utils.reliability import ToolResult, stable_operation_id
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class EmailService:
    """
    Sends emails via Gmail SMTP.
    
    USAGE:
    ======
    service = EmailService(
        sender_email="your_email@gmail.com",
        sender_password="your_app_password",  # 16-char App Password
        recipient_email="recipient@example.com"  # Optional, defaults to sender
    )
    
    success = service.send_reminder(
        subject="Alarm Reminder",
        body="Your alarm has fired!"
    )
    """
    
    # Gmail SMTP settings
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587  # TLS port (587) or SSL port (465)

    def __init__(self, sender_email: str, sender_password: str, recipient_email: str = ""):
        """
        Initialize the email service.
        
        Args:
            sender_email: Gmail address (e.g., "you@gmail.com")
            sender_password: App Password (16 chars; spaces are stripped)
            recipient_email: Where to send reminders (defaults to sender)
        """
        self.sender_email = sender_email
        # Google shows App Passwords grouped with spaces ("xxxx xxxx xxxx
        # xxxx") and users paste them as-is; Gmail auth only accepts the
        # bare 16 chars, so strip spaces here.
        self.sender_password = sender_password.replace(" ", "")
        self.recipient_email = recipient_email or sender_email

    def send_reminder(self, subject: str, body: str) -> ToolResult:
        """
        Send a reminder email.
        
        SMTP FLOW:
        ==========
        1. Create MIME message with subject and body
        2. Connect to SMTP server
        3. Start TLS encryption
        4. Login with App Password
        5. Send message
        6. Disconnect
        
        WHY TLS (Port 587)?
        ===================
        - TLS (Transport Layer Security) encrypts connection
        - More secure than unencrypted SMTP
        - Standard for Gmail SMTP
        
        Alternative: SSL on port 465 (encryption from start)
        
        Args:
            subject: Email subject line
            body: Plain text email body
            
        Returns:
            True on success, False on failure
        """
        if not self.sender_email or not self.sender_password:
            logger.warning("Gmail credentials not configured")
            return ToolResult(False, code="not_configured", hint="Gmail credentials are not configured.", error="Gmail credentials not configured", provider="smtp", operation_id=stable_operation_id("smtp", "reminder"))

        # Create message
        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email
        # subject comes from LLM-controlled alarm labels; strip CR/LF so it
        # cannot smuggle extra headers into the message (header injection)
        msg["Subject"] = subject.replace("\r", "").replace("\n", "")
        msg.attach(MIMEText(body, "plain"))

        try:
            # Connect to Gmail SMTP server
            # timeout=30 so a hung connection can't wedge the
            # Task Scheduler process running this send
            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT, timeout=30) as server:
                # Start TLS encryption
                # This upgrades the connection to encrypted mode
                server.starttls()

                # Login with App Password
                server.login(self.sender_email, self.sender_password)

                # Send the email
                server.send_message(msg)

            return ToolResult(True, provider="smtp", operation_id=stable_operation_id("smtp", "reminder"))
        except Exception as e:
            logger.error("Error sending email: %s", e)
            return ToolResult(False, code="unknown_outcome", unknown_outcome=True, hint="SMTP may have accepted the reminder; inspect the mailbox before retrying.", error=str(e), provider="smtp", operation_id=stable_operation_id("smtp", "reminder"))
