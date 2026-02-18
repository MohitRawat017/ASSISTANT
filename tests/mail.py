"""
Test script to verify .env email variables and Gmail SMTP connectivity.

Run from project root:
    python tests/mail.py
"""

import os
import sys
import smtplib

# Add project root to path so dotenv can find .env
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def check_env_file():
    """Check that .env file exists and is loadable."""
    print("\n--- Step 1: .env File ---")
    if not os.path.isfile(ENV_PATH):
        print(f"{FAIL} .env file not found at: {ENV_PATH}")
        return False
    print(f"{PASS} .env file found at: {ENV_PATH}")
    load_dotenv(ENV_PATH, override=True)
    return True


def check_variables():
    """Check that required email variables are set and non-empty."""
    print("\n--- Step 2: Environment Variables ---")
    ok = True

    gmail_address = os.getenv("GMAIL_ADDRESS", "")
    gmail_app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    reminder_email = os.getenv("REMINDER_EMAIL", "")

    # GMAIL_ADDRESS
    if gmail_address:
        print(f"{PASS} GMAIL_ADDRESS = {gmail_address}")
    else:
        print(f"{FAIL} GMAIL_ADDRESS is empty or not set")
        ok = False

    # GMAIL_APP_PASSWORD
    if gmail_app_password:
        masked = gmail_app_password[:4] + "*" * (len(gmail_app_password) - 4)
        print(f"{PASS} GMAIL_APP_PASSWORD = {masked}")
    else:
        print(f"{FAIL} GMAIL_APP_PASSWORD is empty or not set")
        ok = False

    # REMINDER_EMAIL (optional)
    if reminder_email:
        print(f"{PASS} REMINDER_EMAIL = {reminder_email}")
    else:
        print(f"{WARN} REMINDER_EMAIL is not set (will default to GMAIL_ADDRESS)")

    return ok, gmail_address, gmail_app_password, reminder_email


def check_smtp_connection():
    """Check that we can connect to Gmail SMTP and start TLS."""
    print("\n--- Step 3: SMTP Connection ---")
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        print(f"{PASS} Connected to smtp.gmail.com:587 with STARTTLS")
        return server
    except Exception as e:
        print(f"{FAIL} Could not connect to smtp.gmail.com:587 — {e}")
        return None


def check_authentication(server, email, password):
    """Check that login succeeds with the provided credentials."""
    print("\n--- Step 4: SMTP Authentication ---")
    try:
        server.login(email, password)
        print(f"{PASS} Logged in as {email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"{FAIL} Authentication failed — {e}")
        print("      Make sure you are using a Gmail App Password, not your regular password.")
        print("      Generate one at: https://myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"{FAIL} Login error — {e}")
        return False


def send_test_email(server, sender, recipient):
    """Send a short test email to confirm end-to-end delivery."""
    print("\n--- Step 5: Send Test Email ---")
    from email.mime.text import MIMEText

    to_addr = recipient or sender
    msg = MIMEText("This is a test email from the assistant test script.\n\nIf you received this, your email configuration is working correctly.")
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = "Test Email - Assistant Config Check"

    try:
        server.send_message(msg)
        print(f"{PASS} Test email sent to {to_addr}")
        print("      Check your inbox (and spam folder) to confirm delivery.")
        return True
    except Exception as e:
        print(f"{FAIL} Failed to send test email — {e}")
        return False


def main():
    print("=" * 50)
    print("  Email Configuration Test")
    print("=" * 50)

    # Step 1
    if not check_env_file():
        print("\nFix: Create a .env file in the project root with GMAIL_ADDRESS and GMAIL_APP_PASSWORD.")
        return

    # Step 2
    ok, gmail_address, gmail_app_password, reminder_email = check_variables()
    if not ok:
        print("\nFix: Set the missing variables in your .env file.")
        return

    # Step 3
    server = check_smtp_connection()
    if not server:
        print("\nFix: Check your internet connection and firewall settings (port 587 must be open).")
        return

    # Step 4
    if not check_authentication(server, gmail_address, gmail_app_password):
        server.quit()
        return

    # Step 5
    send_test_email(server, gmail_address, reminder_email)
    server.quit()

    print("\n" + "=" * 50)
    print("  All checks complete.")
    print("=" * 50)


if __name__ == "__main__":
    main()
