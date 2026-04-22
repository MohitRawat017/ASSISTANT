"""
https://developers.google.com/gmail/api/reference/rest
"""

import base64
from email.mime.text import MIMEText

from src.tools.google.auth import get_gmail_service


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
    try:
        service = get_gmail_service()
        
        # Create MIME message
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject
        
        # Encode for Gmail API (base64url)
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send the message
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
    
    FILTERING:
    ==========
    Uses labelIds: ["UNREAD", "INBOX"] to find:
    - Unread messages that are in the inbox
    
    Does NOT include:
    - Read messages
    - Unread messages in other labels (Promotions, Social)
    
    Args:
        max_results: Maximum number of emails to return
        
    Returns:
        List of email dicts with: id, from, subject, snippet, date
        Empty list on error
    """
    try:
        service = get_gmail_service()
        
        # Get list of unread inbox messages
        result = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["UNREAD", "INBOX"],
                maxResults=max_results
            )
            .execute()
        )
        
        messages = result.get("messages", [])
        emails = []
        
        # Fetch details for each message
        for msg in messages:
            # Get message metadata (headers only, not full body)
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]
                )
                .execute()
            )
            
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
        return emails
    except Exception as e:
        return []


def mark_as_read(message_id: str) -> dict:
    """
    Marks an email as read (removes UNREAD label).
    
    Args:
        message_id: Gmail message ID
        
    Returns:
        {"success": True} on success
        {"success": False, "error": "..."} on failure
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
        List of matching email dicts with: id, from, subject, snippet
        Empty list on error
    """
    try:
        service = get_gmail_service()
        
        # Search for messages
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        
        messages = result.get("messages", [])
        emails = []
        
        # Fetch details for each message
        for msg in messages:
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject"]
                )
                .execute()
            )
            
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
        return emails
    except Exception as e:
        return []

