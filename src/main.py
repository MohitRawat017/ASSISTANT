import asyncio
import time
import logging
from rich.console import Console
from rich.logging import RichHandler
from src.utils.config import Config

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)

USE_ASR = False      # Automatic Speech Recognition (voice input)
DEBUG_MODE = Config.DEBUG_MODE  # Verbose logging and tool call visibility

# Keep third-party logs quiet so debug output stays focused on tool flow.
for _lib in ("httpx", "httpcore", "telegram", "apscheduler", "hpack", "langchain", "langgraph", "urllib3"):
    logging.getLogger(_lib).setLevel(logging.WARNING)


def _clean_terminal_input(text: str) -> str:
    """Normalize stdin text from Windows shells, including BOM-prefixed pipes."""
    return (
        text.replace("\ufeff", "")
        .replace("ï»¿", "")
        .replace("ď»ż", "")
        .strip()
    )


def initialize_google_auth():

    from src.tools.google.auth import get_credentials
    try:
        get_credentials(allow_interactive=False)
        console.print("[bold green]Google services authenticated.[/bold green]")
    except Exception as e:
        # Non-fatal: assistant works, just without Google tools
        console.print(f"[bold yellow]Google auth failed: {e} Google tools unavailable.[/bold yellow]")


async def run_terminal(tts, stop_event: asyncio.Event):

    from src.graph.agent import arun_agent

    asr = None
    if USE_ASR:
        try:
            from src.audio_input.asr import ASRHandler
            asr = ASRHandler()
        except Exception as e:
            console.print(f"[bold yellow]ASR unavailable: {e}[/bold yellow]")

    console.print("[dim]Type your message. Type 'exit' to stop both interfaces.[/dim]\n")
    
    # Get the running event loop - needed for run_in_executor
    loop = asyncio.get_event_loop()

    while not stop_event.is_set():
        try:

            if asr and USE_ASR:
                console.print("[dim]Listening...[/dim]")
                # run_in_executor runs the blocking listen_and_transcribe
                # in a thread pool, then returns the transcribed text
                user_input = await loop.run_in_executor(None, asr.listen_and_transcribe)
                user_input = _clean_terminal_input(user_input or "")
                if not user_input:
                    continue 
                console.print(f"[bold cyan]You:[/bold cyan] {user_input}")
            else:
                # lambda needed because console.input takes a prompt argument
                user_input = await loop.run_in_executor(
                    None, lambda: _clean_terminal_input(console.input("[bold cyan]You:[/bold cyan] "))
                )
                if not user_input:
                    continue 

            if user_input.lower() in ("exit", "quit", "bye"):
                console.print("\n[dim]Bye, master.[/dim]")
                stop_event.set()  
                break

            # Time the response for debugging/optimization
            t_start = time.perf_counter()
            
            source = "terminal_voice" if (asr and USE_ASR) else "terminal_text"
            response = await arun_agent(user_input, thread_id="terminal_main", source=source)
            
            elapsed = time.perf_counter() - t_start

            console.print(f"\n[bold magenta]Tsuzi:[/bold magenta] {response}\n")

            if DEBUG_MODE:
                console.print(f"[dim yellow]Elapsed: {elapsed:.2f}s[/dim yellow]\n")

            # Run TTS in executor so Telegram stays responsive during audio
            # Without this, Telegram would freeze while audio plays
            await loop.run_in_executor(None, tts.speak, response)

        except KeyboardInterrupt:
            # Ctrl+C pressed
            console.print("\n[dim]Bye, master.[/dim]")
            stop_event.set()
            break
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")


async def run_telegram(app, stop_event: asyncio.Event):

    from telegram.error import Conflict
    
    try:
        async with app:
            await app.start()
            # start_polling begins the update loop in a background task
            # drop_pending_updates=True ignores messages from when bot was offline
            await app.updater.start_polling(drop_pending_updates=True)
            console.print("[bold green]Telegram bot online. Message your bot to interact.[/bold green]")
            
            await stop_event.wait()
            
            # Clean shutdown
            await app.updater.stop()
            await app.stop()
            
    except Conflict as e:
        # 409 Conflict = another instance already polling this bot token
        console.print("[bold red]Telegram 409 Conflict: Another bot instance is already running.[/bold red]")
        console.print("[bold yellow]Kill other Python processes or wait a minute and try again.[/bold yellow]")
        console.print("[bold yellow]Telegram disabled. Terminal still works.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold yellow]Telegram offline: {e}[/bold yellow]")


async def main():
    """
    CONCURRENT EXECUTION:
    asyncio.gather() runs run_terminal() and run_telegram() concurrently.
    They share:
    - The same agent instance (different thread_ids)
    - The same long-term memory store
    - The same stop_event (for coordinated shutdown)
    """

    # Google Auth
    initialize_google_auth()

    # Agent
    try:
        from src.graph.agent import initialize_agent
        await initialize_agent()
        console.print("[bold green]Agent initialized with MemorySaver.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to initialize agent: {e}[/bold red]")
        return  # Can't continue without agent

    try:
        from src.audio_output.KokoroTTS import TTSHandler
        tts = TTSHandler()
    except Exception as e:
        console.print(f"[bold red]Failed to load TTS: {e}[/bold red]")
        return  # Can't continue without TTS

    console.print("[bold green]Tsuzi (V2) ready.[/bold green]")


    telegram_app = None
    try:
        from src.interfaces.telegram_bot import build_telegram_app, setup_daily_jobs
        telegram_app = build_telegram_app()
        setup_daily_jobs(telegram_app)  # Morning digest at 8 AM IST
    except Exception as e:
        console.print(f"[bold yellow]Telegram setup failed: {e}[/bold yellow]")


    stop_event = asyncio.Event()

    if telegram_app:
        console.print("[bold green]Starting Tsuzi — Terminal + Telegram active.[/bold green]")
        await asyncio.gather(
            run_terminal(tts, stop_event),
            run_telegram(telegram_app, stop_event),
        )
    else:
        console.print("[bold yellow]Starting Tsuzi — Terminal only.[/bold yellow]")
        await run_terminal(tts, stop_event)


if __name__ == "__main__":
    asyncio.run(main())
