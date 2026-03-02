import time
import logging
from rich.console import Console
from rich.logging import RichHandler

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)

USE_ASR = False
DEBUG_MODE = True


def main():
    try:
        from src.audio_output.KokoroTTS import TTSHandler
        tts = TTSHandler()
    except Exception as e:
        console.print(f"[bold red]Failed to load TTS: {e}[/bold red]")
        return

    asr = None
    if USE_ASR:
        try:
            from src.audio_input.asr import ASRHandler
            asr = ASRHandler()
        except Exception as e:
            console.print(f"[bold yellow]ASR unavailable: {e}[/bold yellow]")

    try:
        from src.tools.decision_router import route_query
        console.print("[bold green]Tsuzi ready.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to load pipeline: {e}[/bold red]")
        return

    console.print("[dim]Type your message. Ctrl+C to quit.[/dim]\n")

    while True:
        try:
            if asr and USE_ASR:
                console.print("[dim]Listening...[/dim]")
                user_input = asr.listen_and_transcribe()
                if not user_input:
                    continue
                console.print(f"[bold cyan]You:[/bold cyan] {user_input}")
            else:
                user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()
                if not user_input:
                    continue

            t_start = time.perf_counter()
            response = route_query(user_input)
            elapsed = time.perf_counter() - t_start

            console.print(f"\n[bold magenta]Tsuzi:[/bold magenta] {response}\n")

            if DEBUG_MODE:
                console.print(f"[dim yellow]⏱ {elapsed:.2f}s[/dim yellow]\n")

            tts.speak(response)

        except KeyboardInterrupt:
            console.print("\n[dim]Bye, master.[/dim]")
            break
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")


if __name__ == "__main__":
    main()