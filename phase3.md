# Phase 3 — Telegram Interface Integration
> Context: Adding Telegram as a second interface alongside terminal
> Both terminal and Telegram run simultaneously from the same process
> Stack: python-telegram-bot v20 (async), existing LangGraph agent, Faster-Whisper ASR
> Read entire file before writing any code

---

## What You're Building

```
Current:
  Terminal input → agent → TTS output

After Phase 3:
  Terminal input → agent → TTS output        (unchanged)
  Telegram text  → agent → Telegram reply    (new)
  Telegram voice → ASR → agent → Telegram reply  (new)
  Agent events   → Telegram push notification (new — alarms, timers)
```

Both interfaces share:
- Same LangGraph agent
- Same long-term memory (SQLite store)
- Same tools

Different per interface:
- Short-term memory thread_id (terminal_main vs telegram_{chat_id})
- Output method (TTS speaker vs Telegram message)

---

## Library Decision

Use: `python-telegram-bot==20.7`
Do NOT use: aiogram, telebot, pyTelegramBotAPI, raw API

Why v20 specifically:
- Full async/await — compatible with your existing async agent
- Built-in JobQueue for proactive notifications (alarms, timers)
- ApplicationBuilder pattern is clean and well documented
- v13.x is no longer maintained — do not use it

```bash
uv pip install python-telegram-bot==20.7
```

---

## Step 0 — Create Bot via BotFather (Do This First)

1. Open Telegram → search @BotFather
2. Send /newbot
3. Name: Tsuzi
4. Username: tsuzi_assistant_bot (or any available name)
5. Copy the token — looks like: 7234567890:AAFxxx...
6. Add to .env:

```
TELEGRAM_BOT_TOKEN=7234567890:AAFxxx...
TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id
```

To get your user ID:
- Search @userinfobot on Telegram
- Send /start — it replies with your numeric user ID

Why store allowed user ID: your bot is private, only you should use it.
Reject all messages from other users with a silent return.

Add to Config:
```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
```

---

## Folder Structure — New Files Only

```
src/
├── interfaces/
│   ├── __init__.py
│   ├── terminal.py        # EXISTS or in main.py — leave untouched
│   └── telegram_bot.py    # NEW — entire Telegram interface lives here
├── graph/
│   └── agent.py           # EXISTS — no changes needed
```

---

## Step 1 — `telegram_bot.py` Core Structure

This file contains everything Telegram-related.
It runs in the same asyncio event loop as your existing agent.

```python
# src/interfaces/telegram_bot.py

import os
import asyncio
import logging
from telegram import Update, Bot
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

# ── Security: reject non-owner messages ─────────────────────────
def is_allowed(update: Update) -> bool:
    """Only respond to messages from your Telegram account."""
    return update.effective_user.id == Config.TELEGRAM_ALLOWED_USER_ID

# ── Message handler ──────────────────────────────────────────────
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages."""
    if not is_allowed(update):
        return   # silent reject — don't even acknowledge unknown users

    user_text = update.message.text
    chat_id = update.effective_chat.id
    thread_id = f"telegram_{chat_id}"

    # Show typing indicator while agent processes
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        response = await arun_agent(user_text, thread_id=thread_id)
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Agent error in Telegram handler: {e}")
        await update.message.reply_text("Sorry master, something went wrong.")

# ── Voice note handler ────────────────────────────────────────────
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice note messages — download, transcribe, run agent."""
    if not is_allowed(update):
        return

    chat_id = update.effective_chat.id
    thread_id = f"telegram_{chat_id}"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        # Download voice note (.ogg format from Telegram)
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        ogg_path = f"data/temp/voice_{chat_id}.ogg"
        os.makedirs("data/temp", exist_ok=True)
        await voice_file.download_to_drive(ogg_path)

        # Transcribe using your existing Faster-Whisper ASR
        from src.asr.asr_handler import ASRHandler
        asr = ASRHandler()
        transcribed_text = asr.transcribe_file(ogg_path)

        if not transcribed_text or not transcribed_text.strip():
            await update.message.reply_text("Sorry master, I couldn't hear that clearly.")
            return

        # Echo transcription so you know what was heard
        await update.message.reply_text(f"🎤 Heard: {transcribed_text}")

        # Run agent with transcribed text
        response = await arun_agent(transcribed_text, thread_id=thread_id)
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await update.message.reply_text("Sorry master, voice processing failed.")
    finally:
        # Clean up temp file
        if os.path.exists(ogg_path):
            os.remove(ogg_path)

# ── Command handlers ──────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Hello master! I'm Tsuzi, your personal assistant.\n"
        "Send me a message or voice note and I'll help you out."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    """Clear short-term memory for this Telegram thread."""
    if not is_allowed(update):
        return
    # Clearing is done by switching to a new thread_id
    # Store new thread_id in context.chat_data
    import time
    context.chat_data["thread_id"] = f"telegram_{update.effective_chat.id}_{int(time.time())}"
    await update.message.reply_text("Memory cleared, master. Fresh start!")

# ── Error handler ──────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Telegram error: {context.error}")

# ── Bot builder ────────────────────────────────────────────────────
def build_telegram_app() -> Application:
    """Build and configure the Telegram application."""
    app = (
        ApplicationBuilder()
        .token(Config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_error_handler(error_handler)

    return app
```

---

## Step 2 — Proactive Notifications (Alarms + Timers → Telegram)

This is how completed alarms and timers push to your phone.
Uses python-telegram-bot's built-in JobQueue.

```python
# Add to telegram_bot.py

from telegram.ext import JobQueue

async def send_notification(context: ContextTypes.DEFAULT_TYPE):
    """
    Called by JobQueue to push a notification to Telegram.
    context.job.data must contain: {"chat_id": int, "message": str}
    """
    data = context.job.data
    await context.bot.send_message(
        chat_id=data["chat_id"],
        text=f"🔔 {data['message']}"
    )

def schedule_notification(app: Application, chat_id: int, message: str, delay_seconds: float):
    """
    Schedule a one-time notification after delay_seconds.
    Call this from your alarm/timer tools when they trigger.
    """
    app.job_queue.run_once(
        send_notification,
        when=delay_seconds,
        data={"chat_id": chat_id, "message": message},
        name=f"notification_{chat_id}_{int(delay_seconds)}"
    )
```

To use from your alarm tool — pass the app instance:
```python
# In your set_alarm tool, after alarm triggers:
from src.interfaces.telegram_bot import schedule_notification, get_app
schedule_notification(get_app(), Config.TELEGRAM_ALLOWED_USER_ID, "⏰ Alarm!", delay)
```

Add `get_app()` as a module-level singleton getter so tools can access the bot instance.

---

## Step 3 — Morning Digest (Proactive Daily Summary)

```python
# Add to telegram_bot.py

async def morning_digest(context: ContextTypes.DEFAULT_TYPE):
    """
    Sent every morning at 8am.
    Fetches tasks + weather and sends summary to Telegram.
    """
    chat_id = Config.TELEGRAM_ALLOWED_USER_ID
    thread_id = f"telegram_{chat_id}_digest"

    try:
        # Use agent to generate morning summary
        summary = await arun_agent(
            "Give me a brief morning summary: my tasks for today and current weather in Una. "
            "Keep it under 5 lines.",
            thread_id=thread_id
        )
        await context.bot.send_message(chat_id=chat_id, text=f"☀️ Good morning master!\n\n{summary}")
    except Exception as e:
        logger.error(f"Morning digest error: {e}")

def setup_daily_jobs(app: Application):
    """Register recurring jobs."""
    # Morning digest at 8:00 AM IST every day
    # IST = UTC+5:30, so 8:00 IST = 02:30 UTC
    import datetime
    app.job_queue.run_daily(
        morning_digest,
        time=datetime.time(hour=2, minute=30, tzinfo=datetime.timezone.utc),
        name="morning_digest"
    )
```

---

## Step 4 — Run Telegram + Terminal Simultaneously in `main.py`

This is the critical part. Both interfaces must run in the same asyncio event loop.
Do NOT use threading — PTB v20 is async-native and must stay in one event loop.

```python
# In main.py — replace or extend your existing main() function

import asyncio
from src.interfaces.telegram_bot import build_telegram_app, setup_daily_jobs

async def run_terminal(stop_event: asyncio.Event):
    """Your existing terminal loop — wrapped in async."""
    # Move your existing terminal input loop here
    # Replace blocking input() with asyncio equivalent:
    import sys
    loop = asyncio.get_event_loop()

    while not stop_event.is_set():
        # Run blocking input() in thread pool so it doesn't block event loop
        user_input = await loop.run_in_executor(None, input, "You: ")

        if user_input.lower() in ("exit", "quit", "bye"):
            stop_event.set()
            break

        response = await arun_agent(user_input, thread_id="terminal_main")
        print(f"Tsuzi: {response}")
        # TTS
        tts_handler.speak(response)

async def run_telegram(app, stop_event: asyncio.Event):
    """Run Telegram bot until stop_event is set."""
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        print("✅ Telegram bot started. Message @your_bot to interact.")

        # Wait until terminal signals stop
        await stop_event.wait()

        await app.updater.stop()
        await app.stop()

async def main():
    # Initialize Google auth (from Phase 2)
    initialize_google_auth()

    # Build Telegram app
    telegram_app = build_telegram_app()
    setup_daily_jobs(telegram_app)

    # Shared stop signal between terminal and telegram
    stop_event = asyncio.Event()

    print("✅ Starting Tsuzi — Terminal + Telegram interfaces active")
    print("Type 'exit' to stop both interfaces.\n")

    # Run both concurrently in same event loop
    await asyncio.gather(
        run_terminal(stop_event),
        run_telegram(telegram_app, stop_event),
    )

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Step 5 — ASR Handler Update (For Voice Notes)

Your existing ASR handler probably only handles microphone input.
Add a `transcribe_file()` method that accepts a file path (for Telegram .ogg files):

```python
# In src/asr/asr_handler.py — ADD this method to existing ASRHandler class

def transcribe_file(self, file_path: str) -> str:
    """
    Transcribe an audio file (any format Faster-Whisper supports).
    Telegram sends voice notes as .ogg/opus — Whisper handles this natively.
    """
    segments, info = self.model.transcribe(
        file_path,
        language="en",          # or None for auto-detect
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.5,
            min_speech_duration_ms=250,
            min_silence_duration_ms=500,
        ),
        no_speech_threshold=0.6,
        condition_on_previous_text=False,
    )
    text = " ".join([seg.text for seg in segments]).strip()

    # Filter hallucinations (same as your existing filter)
    HALLUCINATIONS = {"thank you", "thanks for watching", "[music]", ".", ""}
    if text.lower() in HALLUCINATIONS:
        return ""

    return text
```

---

## Step 6 — Security Hardening

Add these to telegram_bot.py — important since your bot has access to your entire PC:

```python
# Rate limiting — max 10 messages per minute from any user
from collections import defaultdict
import time

_message_times = defaultdict(list)

def is_rate_limited(user_id: int) -> bool:
    """Allow max 10 messages per 60 seconds."""
    now = time.time()
    times = _message_times[user_id]
    # Remove messages older than 60 seconds
    _message_times[user_id] = [t for t in times if now - t < 60]
    if len(_message_times[user_id]) >= 10:
        return True
    _message_times[user_id].append(now)
    return False

# Update handle_text and handle_voice to check:
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if is_rate_limited(update.effective_user.id):
        await update.message.reply_text("Slow down master!")
        return
    # ... rest of handler
```

---

## Testing Protocol — ALL must pass before Phase 4

```
TEST 1 — Bot responds to text
  Send "hello" to bot on Telegram
  Pass: response arrives within 10 seconds

TEST 2 — Security
  Ask a friend to message your bot
  Pass: bot does not respond at all to unknown users

TEST 3 — Tool call via Telegram
  Send "what are my tasks for today?"
  Pass: correct task list returned from Google Tasks

TEST 4 — Multi-step via Telegram
  Send "search for latest qwen news and add it as a task"
  Pass: web search happens, task added, confirmation received

TEST 5 — Memory shared with terminal
  Terminal: "my name is [your name]"
  Telegram: "what's my name?"
  Pass: correct name returned (long-term memory shared)

TEST 6 — Memory separate short-term
  Terminal: "remember we were talking about LangGraph"
  Telegram: "what were we just talking about?"
  Pass: Telegram does NOT know about terminal conversation
        (separate short-term thread_ids)

TEST 7 — Voice note
  Record voice: "set a timer for 3 minutes"
  Pass: transcription echoed, timer set, confirmation received

TEST 8 — Proactive notification
  Via terminal: set alarm 2 minutes from now
  Lock screen, watch Telegram
  Pass: notification arrives within 30 seconds of alarm time

TEST 9 — Morning digest (mock test)
  Call morning_digest() manually in code
  Pass: coherent summary with tasks + weather sent to Telegram

TEST 10 — Both interfaces simultaneously
  Start assistant, use terminal AND Telegram at same time
  Pass: both respond correctly, no crashes, no event loop conflicts
```

---

## Common Issues

**`RuntimeError: This event loop is already running`**
You called `asyncio.run()` inside an already-running event loop.
Fix: use `await` instead — never nest `asyncio.run()` calls.
Everything must live in the same event loop via `asyncio.gather()`.

**Bot not responding**
Check token is correct: `uv run python -c "from src.utils.config import Config; print(Config.TELEGRAM_BOT_TOKEN)"`
Check bot is not blocked — send /start first.

**Voice notes not transcribing**
Telegram sends .ogg/opus files. Faster-Whisper handles these natively.
If ffmpeg error appears: `winget install ffmpeg` or `choco install ffmpeg`

**Typing indicator not showing**
`send_chat_action` must be called BEFORE the await on the agent.
If called after, it's too late and user already sees delay.

**JobQueue not running**
Ensure `python-telegram-bot[job-queue]` is installed:
`uv pip install "python-telegram-bot[job-queue]==20.7"`
The job-queue extra is required for JobQueue functionality.

**Two event loops conflict**
Never use `threading.Thread` to run the Telegram bot.
Use `asyncio.gather()` only — both coroutines share one event loop.

---

## Requirements.txt Additions

```
python-telegram-bot[job-queue]==20.7
```

The `[job-queue]` extra is required for proactive notifications (alarms, timers, morning digest).
Without it, `app.job_queue` will be None.