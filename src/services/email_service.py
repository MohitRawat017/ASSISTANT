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
5. Copy the 16-character password to .env:
   GMAIL_APP_PASSWORD=xyzw abcd efgh ijkl

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

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


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
            sender_password: App Password (16 chars, no spaces)
            recipient_email: Where to send reminders (defaults to sender)
        """
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.recipient_email = recipient_email or sender_email

    def send_reminder(self, subject: str, body: str) -> bool:
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
            print("[EmailService] Gmail credentials not configured")
            return False

        # Create message
        msg = MIMEMultipart()
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            # Connect to Gmail SMTP server
            with smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT) as server:
                # Start TLS encryption
                # This upgrades the connection to encrypted mode
                server.starttls()
                
                # Login with App Password
                server.login(self.sender_email, self.sender_password)
                
                # Send the email
                server.send_message(msg)
                
            return True
        except Exception as e:
            print(f"[EmailService] Error sending email: {e}")
            return False


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: Why use STARTTLS instead of SSL?
A: STARTTLS (port 587): Starts unencrypted, upgrades to TLS
   SSL (port 465): Encrypted from the start
   
   Both are secure. STARTTLS is more modern and flexible.
   Some firewalls work better with STARTTLS.

Q2: What is an App Password and why use it?
A: App Password is a 16-character code that:
   - Is generated in Google Account settings
   - Requires 2-Factor Authentication enabled
   - Acts as a password for specific apps
   - Can be revoked without changing main password
   - Has limited scope (only email, not full account)

Q3: What's the difference between MIMEText and MIMEMultipart?
A: MIMEText: Simple text-only message
   MIMEMultipart: Container for multiple parts (text + attachments)
   
   We use MIMEMultipart even for text-only because it's more flexible
   if we want to add attachments later.

Q4: How would you send HTML emails?
A: Change MIMEText second argument:
   msg.attach(MIMEText(body, "html"))
   
   Or for both text and HTML:
   msg.attach(MIMEText(plain_text, "plain"))
   msg.attach(MIMEText(html_content, "html"))

Q5: What errors can occur with SMTP?
A: Common errors:
   - smtplib.SMTPAuthenticationError: Wrong credentials
   - smtplib.SMTPConnectError: Can't reach server
   - smtplib.SMTPException: General SMTP error
   - socket.gaierror: DNS resolution failed
   - socket.timeout: Connection timed out
   
   All caught by our generic Exception handler.

Q6: Why use context manager (with statement)?
A: The 'with' statement ensures:
   - Connection is properly closed
   - Resources are cleaned up
   - Works even if error occurs
   
   Without it, connection might stay open.

Q7: How would you add attachments?
A: Use MIMEBase:
   from email.mime.base import MIMEBase
   from email import encoders
   
   with open("file.pdf", "rb") as f:
       part = MIMEBase("application", "octet-stream")
       part.set_payload(f.read())
       encoders.encode_base64(part)
       part.add_header("Content-Disposition", "attachment; filename=file.pdf")
       msg.attach(part)

Q8: What's the rate limit for Gmail SMTP?
A: - 500 emails/day for free Gmail
   - 2000 emails/day for Google Workspace
   
   For personal use (alarm reminders), unlikely to hit limits.

Q9: How would you implement email queuing?
A: 1. Store emails in SQLite queue table
   2. Background thread processes queue
   3. Retry failed sends with exponential backoff
   4. Remove from queue after successful send
   
   This prevents email loss during network issues.

Q10: Why not use an email sending service (SendGrid, etc.)?
A: For personal projects, Gmail SMTP is:
   - Free
   - No external dependencies
   - Already have Gmail account
   
   For production/commercial use, services like SendGrid provide:
   - Better deliverability
   - Analytics
   - Higher rate limits
   - Templates
"""