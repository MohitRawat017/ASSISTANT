"""
================================================================================
TSUZI ASSISTANT - TELEGRAM BOT INTERFACE
================================================================================

This module provides a Telegram bot interface for the assistant, allowing
users to interact via Telegram mobile app. It runs concurrently with the
terminal interface via asyncio.gather().

KEY FEATURES:
=============
1. Text Message Handling: Send/receive text messages
2. Voice Note Processing: Transcribe voice notes with Whisper
3. Proactive Notifications: Push alerts for alarms/reminders
4. Morning Digest: Daily summary at 8 AM IST
5. Rate Limiting: Prevent abuse
6. Security: Only respond to authorized user(s)

ARCHITECTURE: SHARED STATE
==========================
Telegram shares with Terminal:
- Same LangGraph agent (different thread_ids)
- Same long-term memory (user facts)
- Same stop_event (coordinated shutdown)

Telegram has separate:
- Short-term conversation history (thread_id = "telegram_{chat_id}")
- Chat data (stored in context.chat_data)

POLLING VS WEBHOOKS:
====================
This bot uses POLLING (long polling):
- Bot repeatedly asks Telegram servers: "any new messages?"
- Simpler to implement, no public URL needed
- Alternative: Webhooks (Telegram pushes to our server)

WHY POLLING FOR THIS PROJECT:
- No public server/URL required
- Simpler setup for development
- Works behind NAT/firewall

================================================================================
KEY CONCEPTS FOR INTERVIEW:
================================================================================

Q: How does the bot know which user to respond to?
A: is_allowed() checks the user ID against TELEGRAM_ALLOWED_USER_ID.
   Only the configured user can interact with the bot. This prevents
   random people from accessing your assistant.

Q: What is rate limiting and why is it needed?
A: is_rate_limited() tracks messages per user (max 10/minute).
   Without this, a user could:
   - Spam the bot with messages
   - Trigger expensive API calls repeatedly
   - Potentially hit rate limits on Google/Telegram APIs

Q: How do voice notes work?
A: 1. Telegram sends .ogg audio file
   2. Download to temp directory
   3. Faster-Whisper transcribes (supports .ogg natively)
   4. Transcribed text goes to agent
   5. Agent's response sent back as text

================================================================================
"""

import os
import time
import asyncio
import logging
import datetime
from collections import defaultdict

# python-telegram-bot library (v20+ is async)
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

from src.graph.agent import arun_agent
from src.utils.config import Config

logger = logging.getLogger(__name__)

# =============================================================================
# APPLICATION SINGLETON
# =============================================================================
# The Application instance is stored globally so tools can access it
# for proactive notifications (e.g., alarm triggers pushing to Telegram)

_app: Application | None = None


def get_app() -> Application | None:
    """
    Return the running Telegram Application instance.
    
    WHY THIS EXISTS:
    Tools like alarms need to send notifications proactively.
    They can't import telegram_bot (circular import), so they
    call get_app() to get the bot instance.
    
    Returns:
        Application instance or None if not initialized
    """
    return _app


# =============================================================================
# SECURITY
# =============================================================================

def is_allowed(update: Update) -> bool:
    """
    Check if the user is authorized to use the bot.
    
    SECURITY MODEL:
    - Single-user: Only TELEGRAM_ALLOWED_USER_ID can interact
    - Set in .env: TELEGRAM_ALLOWED_USER_ID=123456789
    - Find your ID: Message @userinfobot on Telegram
    
    Without this check, ANYONE who finds your bot could:
    - Read your calendar/emails
    - Execute commands on your PC
    - Access your personal data
    
    Args:
        update: Telegram update object containing message info
        
    Returns:
        True if user is authorized, False otherwise
    """
    return update.effective_user.id == Config.TELEGRAM_ALLOWED_USER_ID


# =============================================================================
# RATE LIMITING
# =============================================================================

# Dictionary to track message timestamps per user
# Key: user_id, Value: list of timestamps
_message_times: dict[int, list[float]] = defaultdict(list)


def is_rate_limited(user_id: int) -> bool:
    """
    Check if user has exceeded rate limit.
    
    RATE LIMIT: 10 messages per 60 seconds per user
    
    IMPLEMENTATION:
    - Store list of message timestamps per user
    - Remove timestamps older than 60 seconds
    - If 10+ remaining, user is rate limited
    
    WHY RATE LIMIT:
    - Prevent accidental spam (user holding enter)
    - Protect against malicious flooding
    - Avoid hitting external API limits
    - Reduce load on LLM/Ollama
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        True if rate limited (should reject), False if OK
    """
    now = time.time()
    
    # Remove timestamps older than 60 seconds
    _message_times[user_id] = [
        t for t in _message_times[user_id] if now - t < 60
    ]
    
    # Check if limit exceeded
    if len(_message_times[user_id]) >= 10:
        return True
    
    # Record this message
    _message_times[user_id].append(now)
    return False


# =============================================================================
# MESSAGE HANDLERS
# =============================================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming text messages from Telegram.
    
    FLOW:
    1. Security check (is user allowed?)
    2. Rate limit check
    3. Get thread_id for this chat
    4. Send "typing" indicator (shows user bot is working)
    5. Call agent with user's message
    6. Send response back
    
    THREAD ID:
    Each chat has its own thread_id (telegram_{chat_id}).
    This keeps conversation history separate per chat.
    If user starts new chat group with bot, it's a new conversation.
    
    Args:
        update: Telegram update with message data
        context: Context object with chat_data for storing state
    """
    # Security: Only respond to authorized user
    if not is_allowed(update):
        return

    # Rate limiting
    if is_rate_limited(update.effective_user.id):
        await update.message.reply_text("Slow down master!")
        return

    # Get or create thread_id for this chat
    chat_id = update.effective_chat.id
    thread_id = context.chat_data.get("thread_id", f"telegram_{chat_id}")
    user_text = update.message.text

    # Show "typing..." indicator while processing
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        # Call the agent with the user's message
        response = await arun_agent(
            user_text,
            thread_id=thread_id,
            source="telegram_text",
        )
        
        # Send the response
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Agent error in Telegram text handler: {e}")
        await update.message.reply_text("Sorry master, something went wrong.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle voice note messages - download, transcribe, respond.
    
    FLOW:
    1. Security and rate limit checks
    2. Download .ogg voice file from Telegram
    3. Transcribe with Faster-Whisper (supports .ogg natively)
    4. Show transcribed text to user
    5. Process with agent
    6. Send response
    
    WHY FASTER-WHISPER:
    - Supports .ogg/opus natively (no conversion needed)
    - Fast with CTranslate2 optimization
    - Good quality transcription
    
    CLEANUP:
    The .ogg file is deleted after processing to save space.
    gc.collect() ensures file handles are released before deletion.
    
    Args:
        update: Telegram update with voice message
        context: Context for chat_data and bot
    """
    if not is_allowed(update):
        return

    if is_rate_limited(update.effective_user.id):
        await update.message.reply_text("Slow down master!")
        return

    chat_id = update.effective_chat.id
    thread_id = context.chat_data.get("thread_id", f"telegram_{chat_id}")

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Prepare temp file path for voice download
    ogg_path = os.path.join(Config.BASE_DIR, "data", "temp", f"voice_{chat_id}.ogg")
    os.makedirs(os.path.dirname(ogg_path), exist_ok=True)

    try:
        # Download voice file from Telegram
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        await voice_file.download_to_drive(ogg_path)

        # Transcribe with Whisper
        from src.audio_input.asr import ASRHandler
        asr = ASRHandler()
        transcribed_text = asr.transcribe_file(ogg_path)

        # Handle empty transcription
        if not transcribed_text or not transcribed_text.strip():
            await update.message.reply_text("Sorry master, I couldn't hear that clearly.")
            return

        # Show user what we heard (for verification)
        await update.message.reply_text(f"Heard: {transcribed_text}")

        # Process with agent
        response = await arun_agent(
            transcribed_text,
            thread_id=thread_id,
            source="telegram_voice",
        )
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await update.message.reply_text("Sorry master, voice processing failed.")
    finally:
        # Cleanup: Delete temp file
        try:
            import gc
            gc.collect()  # Release file handles from ASR model
            if os.path.exists(ogg_path):
                os.remove(ogg_path)
        except PermissionError:
            # File still locked - will be overwritten next time
            pass


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /start command - initial bot interaction.
    
    This is the first command users see when they start the bot.
    It's a friendly welcome message.
    """
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Hello master! I'm Tsuzi, your personal assistant.\n"
        "Send me a message or voice note and I'll help you out."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /help command - show available commands.
    """
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Commands:\n"
        "/start — wake me up\n"
        "/help — this message\n"
        "/clear — clear conversation history\n\n"
        "Or just talk to me normally!"
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /clear command - reset conversation history.
    
    IMPLEMENTATION:
    Instead of actually deleting from the checkpointer (complex),
    we create a new thread_id. The old conversation still exists
    but won't be loaded anymore.
    
    NEW THREAD_ID FORMAT:
    telegram_{chat_id}_{timestamp}
    
    Example: telegram_123456789_1709344800
    
    The timestamp ensures each /clear creates a unique new thread.
    """
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id
    
    # Create new thread_id with timestamp
    context.chat_data["thread_id"] = f"telegram_{chat_id}_{int(time.time())}"
    
    await update.message.reply_text("Memory cleared, master. Fresh start!")


# =============================================================================
# ERROR HANDLER
# =============================================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Global error handler for the Telegram bot.
    
    This catches all unhandled exceptions in the bot.
    Logs the error but doesn't crash - the bot stays running.
    
    Args:
        update: The update that caused the error (may be None)
        context: Context containing the error object
    """
    logger.error(f"Telegram error: {context.error}", exc_info=context.error)


# =============================================================================
# PROACTIVE NOTIFICATIONS
# =============================================================================

async def send_notification(context: ContextTypes.DEFAULT_TYPE):
    """
    JobQueue callback - send a push notification to Telegram.
    
    This is called by the job scheduler for:
    - Alarm triggers
    - Timer completions
    - Any scheduled notification
    
    USAGE FROM TOOLS:
    from src.interfaces.telegram_bot import schedule_notification
    schedule_notification(app, chat_id, "Timer done!", delay_seconds=60)
    
    Args:
        context: Context containing job.data with chat_id and message
    """
    data = context.job.data
    await context.bot.send_message(
        chat_id=data["chat_id"],
        text=f"🔔 {data['message']}",
    )


def schedule_notification(
    app: Application,
    chat_id: int,
    message: str,
    delay_seconds: float,
):
    """
    Schedule a one-time push notification.
    
    This can be called from anywhere (e.g., alarm tools) to
    schedule a Telegram notification.
    
    Args:
        app: Application instance (from get_app())
        chat_id: Telegram chat ID to send to
        message: Message text to send
        delay_seconds: When to send (seconds from now)
    """
    app.job_queue.run_once(
        send_notification,
        when=delay_seconds,
        data={"chat_id": chat_id, "message": message},
        name=f"notification_{chat_id}_{int(time.time())}",
    )


# =============================================================================
# MORNING DIGEST
# =============================================================================

async def morning_digest(context: ContextTypes.DEFAULT_TYPE):
    """
    Daily job: Send morning summary at 8:00 AM IST.
    
    The digest includes:
    - Tasks for today
    - Current weather in user's location
    
    IMPLEMENTATION:
    Uses the agent to generate the summary. This means the agent
    uses its tools (get_tasks, web_search for weather) to gather
    information and format the response.
    
    THREAD ISOLATION:
    Uses a separate thread_id (telegram_{chat_id}_digest) so
    the digest queries don't pollute the main conversation history.
    """
    chat_id = Config.TELEGRAM_ALLOWED_USER_ID
    thread_id = f"telegram_{chat_id}_digest"

    try:
        # Let the agent gather information and format the digest
        summary = await arun_agent(
            "Give me a brief morning summary: my tasks for today and current weather in Una. "
            "Keep it under 5 lines.",
            thread_id=thread_id,
            source="telegram_digest",
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Good morning master!\n\n{summary}",
        )
    except Exception as e:
        logger.error(f"Morning digest error: {e}")


def setup_daily_jobs(app: Application):
    """
    Register recurring jobs on the application's JobQueue.
    
    The JobQueue runs in a background thread and executes
    scheduled jobs at their appointed times.
    
    MORNING DIGEST TIMING:
    - 8:00 AM IST (India Standard Time)
    - IST = UTC + 5:30
    - So 8:00 AM IST = 2:30 AM UTC
    
    Args:
        app: Application instance with job_queue
    """
    app.job_queue.run_daily(
        morning_digest,
        time=datetime.time(hour=2, minute=30, tzinfo=datetime.timezone.utc),
        name="morning_digest",
    )


# =============================================================================
# APPLICATION BUILDER
# =============================================================================

def build_telegram_app() -> Application:
    """
    Build, configure, and return the Telegram Application.
    
    This creates the bot but doesn't start it. The main.py
    calls this and then starts the app with run_telegram().
    
    CONFIGURATION:
    - Token from Config (set in .env)
    - Timeouts for network reliability
    - Handlers for text, voice, commands
    - Global error handler
    
    HANDLERS ARE REGISTERED IN ORDER:
    1. Command handlers (/start, /help, /clear)
    2. Text message handler
    3. Voice message handler
    
    Order matters for message routing!
    
    Returns:
        Configured Application instance (not started yet)
    """
    global _app

    # Build the application with configuration
    app = (
        ApplicationBuilder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)   # Time to establish connection
        .read_timeout(30)      # Time to wait for response
        .write_timeout(30)     # Time to send data
        .pool_timeout(30)      # Time to get connection from pool
        .build()
    )

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    
    # Register message handlers
    # filters.TEXT & ~filters.COMMAND = text messages that aren't commands
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # Global error handler
    app.add_error_handler(error_handler)

    # Store as singleton for tools to access
    _app = app
    return app


# =============================================================================
# INTERVIEW QUESTIONS FOR THIS FILE
# =============================================================================
"""
Q1: What's the difference between polling and webhooks?
A: Polling: Bot repeatedly asks Telegram "any new messages?"
   - Simpler, no public URL needed, works behind NAT
   - Higher latency (polling interval)
   - More API calls (even when no messages)
   
   Webhooks: Telegram pushes messages to your server
   - Lower latency (immediate delivery)
   - Fewer API calls
   - Requires public HTTPS URL
   - More complex setup (need web server)

Q2: How does thread_id isolate conversations?
A: Each chat has a unique thread_id (telegram_{chat_id}). The LangGraph
   checkpointer stores conversation history per thread_id. So:
   - Chat A has history A
   - Chat B has history B
   - They never see each other's context
   
   Terminal uses "terminal_main", Telegram uses "telegram_{chat_id}".

Q3: Why store _app as a global singleton?
A: Tools (like alarms) need to send notifications proactively, but they
   can't import telegram_bot.py (would cause circular imports). Instead:
   1. telegram_bot stores app in global _app
   2. Tools call get_app() to access it
   3. Tools use app.bot.send_message() or schedule_notification()

Q4: How does rate limiting work?
A: We store a list of timestamps for each user. On each message:
   1. Remove timestamps older than 60 seconds
   2. If 10+ timestamps remain, reject the message
   3. Otherwise, add current timestamp and process
   
   This implements a "sliding window" rate limiter - max 10 messages
   in any 60-second window.

Q5: Why does /clear create a new thread_id instead of deleting history?
A: Deleting from LangGraph checkpointer is complex (requires direct DB access).
   Creating a new thread_id is simpler:
   - Old history still exists (could be recovered)
   - New conversation starts fresh
   - No database manipulation needed
   
   For a production system, you might want actual deletion for privacy.

Q6: How would you support multiple users?
A: 1. Store allowed user IDs in a database instead of single env var
   2. Each user gets their own long-term memory (memory.user_id)
   3. Rate limit per user (already done)
   4. User-specific configuration (timezone, preferences)
   
   The main change is making memory user-aware rather than global.

Q7: What happens if the bot crashes?
A: The error_handler catches the exception and logs it, but the bot
   doesn't crash. In main.py, run_telegram() also has a try/except
   that catches errors and logs them without re-raising. Terminal
   continues working even if Telegram fails completely.

Q8: Why use JobQueue for scheduled tasks instead of asyncio.sleep?
A: JobQueue is better because:
   - Persists across restarts (if persistence enabled)
   - Handles timezone conversion
   - Can cancel/repeat jobs
   - Runs in separate thread (doesn't block event loop)
   
   asyncio.sleep would be simpler but less robust.

Q9: How does the morning digest work?
A: 1. At 2:30 AM UTC (8:00 AM IST), JobQueue triggers morning_digest
   2. morning_digest calls arun_agent with a summary request
   3. Agent uses its tools (get_tasks, web_search) to gather info
   4. Agent formats a concise response
   5. Response is sent to Telegram
   The agent does the heavy lifting!

Q10: What's the gc.collect() in voice handler for?
A: After ASR processes the .ogg file, the file handle might still be
   held by the model or libraries. gc.collect() forces Python to
   release unreferenced objects, including file handles. This allows
   os.remove() to succeed and clean up the temp file.
"""
