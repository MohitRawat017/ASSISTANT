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

# The Application instance is stored globally so tools can access it
# for proactive notifications (e.g., alarm triggers pushing to Telegram)

_app: Application | None = None


def get_app() -> Application | None:
    """
    for tools that need to send proactive notifications, like alarms or timers.
    """
    return _app


# Security check 

def is_allowed(update: Update) -> bool:
    return update.effective_user.id == Config.TELEGRAM_ALLOWED_USER_ID


# Dictionary to track message timestamps per user
# Key: user_id, Value: list of timestamps
_message_times: dict[int, list[float]] = defaultdict(list)


def is_rate_limited(user_id: int) -> bool:
    """
    Simple rate limiter: max 10 messages per user per 60 seconds.
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
    """
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id
    
    # Create new thread_id with timestamp
    context.chat_data["thread_id"] = f"telegram_{chat_id}_{int(time.time())}"
    
    await update.message.reply_text("Memory cleared, master. Fresh start!")



async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Telegram error: {context.error}", exc_info=context.error)



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
    if app.job_queue is None:
        logger.warning(
            "Telegram JobQueue unavailable; skipping daily jobs. "
            "Install python-telegram-bot[job-queue] to enable scheduled Telegram jobs."
        )
        return

    app.job_queue.run_daily(
        morning_digest,
        time=datetime.time(hour=2, minute=30, tzinfo=datetime.timezone.utc),
        name="morning_digest",
    )


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

    token = Config.TELEGRAM_BOT_TOKEN.strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    if Config.TELEGRAM_ALLOWED_USER_ID <= 0:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_ID is not configured")

    # Build the application with configuration
    app = (
        ApplicationBuilder()
        .token(token)
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
