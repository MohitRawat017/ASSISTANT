"""
https://developers.google.com/gmail/api/reference/rest
"""

import base64
from email.mime.text import MIMEText

from src.tools.google.auth import get_gmail_service
from src.utils.config import Config
from src.utils.reliability import (
    execute_google_read,
    execute_google_write,
    failure_result,
    stable_operation_id,
)


def send_gmail(to: str, subject: str, body: str) -> dict:
    """
    Sends an email via the Gmail API.
    
    MESSAGE CONSTRUCTION:
    =====================
    1. Create MIMEText message (standard email format)
    2. Set headers (to, subject)
    3. Encode as base64url (Gmail API requirement)
    4. Send via API
    
    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain text email body
        
    Returns:
        {"success": True, "message_id": "..."} on success
        {"success": False, "error": "..."} on failure
    """
    operation_id = stable_operation_id("gmail", "send")
    try:
        service = get_gmail_service()
        
        # Create MIME message
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        
        # Encode for Gmail API (base64url)
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send the message
        result = execute_google_write(
            lambda: service.users().messages().send(userId="me", body={"raw": encoded}),
            provider="gmail",
            operation_id=operation_id,
        )
        if result.ok:
            result["message_id"] = result.pop("value", {}).get("id", "")
        return result
    except Exception as e:
        return failure_result(e, provider="gmail", operation_id=operation_id)


def read_unread_emails(max_results: int = 5) -> dict:
    """
    Returns unread emails from Gmail inbox.

    FILTERING:
    ==========
    Uses labelIds: ["UNREAD", "INBOX"] to find:
    - Unread messages that are in the inbox

    Note: category tabs (Promotions, Social, Updates, Forums) are extra
    labels layered on top of INBOX, so unread mail in those tabs IS
    included.

    Does NOT include:
    - Read messages
    - Unread messages outside the inbox (archived, sent, spam)

    Args:
        max_results: Maximum number of emails to return

    Returns:
        {"success": True, "emails": [...]} on success, where each email
        has: id, from, subject, snippet, date
        {"success": False, "error": "..."} on failure
    """
    try:
        service = get_gmail_service()
        
        # Get list of unread inbox messages
        result = execute_google_read(
            lambda: service.users().messages().list(
                userId="me",
                labelIds=["UNREAD", "INBOX"],
                maxResults=max_results
            ),
            operation_id=stable_operation_id("gmail", "list-unread", str(max_results)),
            max_retries=Config.GOOGLE_MAX_RETRIES,
        )
        if not result.ok:
            return result
        messages = result.pop("value", {}).get("messages", [])
        emails = []
        
        # Fetch details for each message
        for msg in messages:
            # Get message metadata (headers only, not full body)
            detail_result = execute_google_read(
                lambda: service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                ),
                operation_id=stable_operation_id("gmail", "message", msg["id"]),
                max_retries=Config.GOOGLE_MAX_RETRIES,
            )
            if not detail_result.ok:
                return detail_result
            detail = detail_result.pop("value", {})
            
            # Extract headers into dict
            headers = {
                h["name"]: h["value"]
                for h in detail.get("payload", {}).get("headers", [])
            }
            
            emails.append(
                {
                    "id": msg["id"],
                    "from": headers.get("From", "unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": detail.get("snippet", ""),  # First ~100 chars
                    "date": headers.get("Date", ""),
                }
            )
        result["emails"] = emails
        return result
    except Exception as e:
        return failure_result(e, provider="gmail", operation_id=stable_operation_id("gmail", "list-unread"))


def mark_as_read(message_id: str) -> dict:
    """
    Marks an email as read (removes UNREAD label).
    
    Args:
        message_id: Gmail message ID
        
    Returns:
        {"success": True} on success
        {"success": False, "error": "..."} on failure
    """
    operation_id = stable_operation_id("gmail", "mark-read")
    try:
        service = get_gmail_service()
        return execute_google_write(
            lambda: service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
            ),
            provider="gmail",
            operation_id=operation_id,
        )
    except Exception as e:
        return failure_result(e, provider="gmail", operation_id=operation_id)


def search_emails(query: str, max_results: int = 5) -> dict:
    """
    Searches Gmail using Gmail search syntax.

    GMAIL SEARCH SYNTAX:
    ====================
    - "from:name" - emails from a sender
    - "subject:meeting" - emails with subject containing "meeting"
    - "after:2025/3/1" - emails after a date
    - "is:unread" - unread emails
    - Plain keywords search subject and body

    Args:
        query: Gmail search query
        max_results: Maximum number of results

    Returns:
        {"success": True, "emails": [...]} on success, where each email
        has: id, from, subject, snippet
        {"success": False, "error": "..."} on failure
    """
    try:
        service = get_gmail_service()
        
        # Search for messages
        result = execute_google_read(
            lambda: service.users().messages().list(userId="me", q=query, maxResults=max_results),
            operation_id=stable_operation_id("gmail", "search", f"{query}|{max_results}"),
            max_retries=Config.GOOGLE_MAX_RETRIES,
        )
        if not result.ok:
            return result
        messages = result.pop("value", {}).get("messages", [])
        emails = []
        
        # Fetch details for each message
        for msg in messages:
            detail_result = execute_google_read(
                lambda: service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"]
                ),
                operation_id=stable_operation_id("gmail", "message", msg["id"]),
                max_retries=Config.GOOGLE_MAX_RETRIES,
            )
            if not detail_result.ok:
                return detail_result
            detail = detail_result.pop("value", {})
            
            headers = {
                h["name"]: h["value"]
                for h in detail.get("payload", {}).get("headers", [])
            }
            
            emails.append(
                {
                    "id": msg["id"],
                    "from": headers.get("From", "unknown"),
                    "subject": headers.get("Subject", "(no subject)"),
                    "snippet": detail.get("snippet", ""),
                }
            )
        result["emails"] = emails
        return result
    except Exception as e:
        return failure_result(e, provider="gmail", operation_id=stable_operation_id("gmail", "search"))
