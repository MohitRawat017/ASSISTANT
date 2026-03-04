"""
Gmail API raw functions.
Replaces the SMTP send + IMAP read tools entirely.
No @tool decorators — those live in wrapped_tools.py.
"""

import base64
from email.mime.text import MIMEText

from src.tools.google.auth import get_gmail_service


def send_gmail(to: str, subject: str, body: str) -> dict:
    """
    Sends an email via the Gmail API.

    Returns:
        {"success": True, "message_id": "..."}
    """
    try:
        service = get_gmail_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded})
            .execute()
        )
        return {"success": True, "message_id": sent.get("id", "")}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_unread_emails(max_results: int = 5) -> list:
    """
    Returns unread emails from Gmail inbox.

    Returns:
        list of {"id", "from", "subject", "snippet", "date"}
    """
    try:
        service = get_gmail_service()
        result = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["UNREAD", "INBOX"], maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        emails = []
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata",
                     metadataHeaders=["From", "Subject", "Date"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            emails.append(
                {
                    "id": msg["id"],
                    "from": headers.get("From", "unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": detail.get("snippet", ""),
                    "date": headers.get("Date", ""),
                }
            )
        return emails
    except Exception as e:
        return []


def mark_as_read(message_id: str) -> dict:
    """
    Marks an email as read (removes UNREAD label).

    Returns:
        {"success": True/False}
    """
    try:
        service = get_gmail_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_emails(query: str, max_results: int = 5) -> list:
    """
    Searches Gmail using a query string.
    Supports Gmail search syntax: "from:name", "subject:meeting", "after:2025/3/1"

    Returns:
        list of {"id", "from", "subject", "snippet"}
    """
    try:
        service = get_gmail_service()
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        messages = result.get("messages", [])
        emails = []
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata",
                     metadataHeaders=["From", "Subject"])
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            emails.append(
                {
                    "id": msg["id"],
                    "from": headers.get("From", "unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": detail.get("snippet", ""),
                }
            )
        return emails
    except Exception as e:
        return []
