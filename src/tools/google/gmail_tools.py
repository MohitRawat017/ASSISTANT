"""
================================================================================
GMAIL API TOOLS
================================================================================

Raw functions for Gmail operations. Replaces SMTP/IMAP with direct API calls.
These functions are wrapped by @tool decorators in wrapped_tools.py.

WHY GMAIL API INSTEAD OF SMTP/IMAP?
===================================
1. OAuth2 authentication (no app passwords needed)
2. Better integration with Google ecosystem
3. Access to labels, threads, and other Gmail features
4. More reliable than SMTP for sending
5. No need to handle email protocols manually

API DOCUMENTATION:
==================
https://developers.google.com/gmail/api/reference/rest

MESSAGE FORMAT:
===============
Gmail messages are in base64url encoding. We use email.mime.text
to construct messages, then encode for the API.

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: Why is the recipient called "me" in Gmail API?
A: "me" is a special user ID that refers to the authenticated user.
   You don't need to know the user's email address.

================================================================================
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


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: Why use base64url encoding for Gmail messages?
A: Gmail API requires messages in base64url format:
   - Standard base64 with +/ replaced by -_
   - No padding (=) at the end
   - JSON-safe encoding for API transport

Q2: What's the difference between format="metadata" and "full"?
A: metadata: Returns headers only (faster, less data)
   full: Returns entire message body (slower, more data)
   raw: Returns raw RFC 2822 message
   
   We use metadata for listing (don't need body) and would use
   full or raw if we needed to read the actual content.

Q3: How would you send an email with attachments?
A: Use MIME Multipart:
   from email.mime.multipart import MIMEMultipart
   from email.mime.base import MIMEBase
   
   message = MIMEMultipart()
   message.attach(MIMEText(body))
   
   # Add attachment
   part = MIMEBase('application', 'octet-stream')
   part.set_payload(attachment_data)
   message.attach(part)

Q4: What is a "snippet" in Gmail API?
A: The first ~100 characters of the message body (without HTML).
   Useful for previews without fetching full message.

Q5: How would you handle pagination for large result sets?
A: Use nextPageToken:
   result = service.users().messages().list(...).execute()
   messages = result.get("messages", [])
   
   while "nextPageToken" in result:
       result = service.users().messages().list(
           pageToken=result["nextPageToken"]
       ).execute()
       messages.extend(result.get("messages", []))

Q6: What are Gmail labels?
A: Labels are Gmail's version of folders. A message can have multiple labels.
   Built-in labels: INBOX, UNREAD, STARRED, IMPORTANT, SENT, DRAFT, SPAM
   Custom labels: User-created categories
   
   We use UNREAD to filter for unread messages.

Q7: How would you implement "mark as important"?
A: Add the IMPORTANT label:
   service.users().messages().modify(
       userId="me",
       id=message_id,
       body={"addLabelIds": ["IMPORTANT"]}
   ).execute()

Q8: What's the rate limit for Gmail API?
A: - 1 billion quota units/day
   - Each operation costs quota units (list=5, get=5, send=100)
   - Approximately 250 quota units/second/user
   
   Very generous for personal use.

Q9: How would you get the full email body?
A: Use format="full" or format="raw":
   detail = service.users().messages().get(
       userId="me",
       id=message_id,
       format="full"
   ).execute()
   
   body = detail["payload"]["body"]["data"]
   Decode base64url to get text.

Q10: How would you reply to an email?
A: Include In-Reply-To and References headers:
   message = MIMEText(body)
   message["to"] = original_from
   message["subject"] = f"Re: {original_subject}"
   message["In-Reply-To"] = original_message_id
   message["References"] = original_message_id
   
   Then send as normal.
"""