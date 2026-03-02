"""
Main Pipeline - Tier 2 LangGraph ReAct Agent (Groq / llama-3.3-70b-versatile).
"""

import time
from rich.console import Console

console = Console()

# Flags
USE_ASR = False       # True = microphone via ASRHandler, False = text input
DEBUG_MODE = True   # True = print token estimates, timing, and selected tools


def _debug_print(user_input: str, response: str, elapsed: float):
    """Print debug info: timing, estimated token counts, tools used."""
    # Use the same retriever the agent uses — so debug output
    # accurately reflects which tools were actually selected
    from src.tools.tool_retriever import get_retriever

    selected_tools = get_retriever().get_tools(user_input)
    tool_names = [t.name for t in selected_tools]

    # Token estimate: ~1 token per 4 chars (standard heuristic)
    input_chars = len(user_input)
    output_chars = len(response)
    est_input_tokens = input_chars // 4
    est_output_tokens = output_chars // 4

    console.print("\n[bold yellow]─── DEBUG ─────────────────────────────[/bold yellow]")
    console.print(f"[yellow]⏱  Time      :[/yellow] {elapsed:.2f}s")
    console.print(f"[yellow]🔧 Tools     :[/yellow] {', '.join(tool_names)}")
    console.print(f"[yellow]📥 Input     :[/yellow] ~{est_input_tokens} tokens  ({input_chars} chars)")
    console.print(f"[yellow]📤 Output    :[/yellow] ~{est_output_tokens} tokens  ({output_chars} chars)")
    console.print(f"[yellow]📊 Total est :[/yellow] ~{est_input_tokens + est_output_tokens} tokens")
    console.print("[bold yellow]────────────────────────────────────────[/bold yellow]\n")


def main():
    # Load TTS
    try:
        # from src.audio_output.kittentts import TTSHandler
        from src.audio_output.KokoroTTS import TTSHandler 
        tts = TTSHandler()
    except Exception as e:
        console.print(f"[bold red]Failed to load TTS: {e}[/bold red]")
        return

    # Load ASR (optional)
    asr = None
    if USE_ASR:
        try:
            from src.audio_input.asr import ASRHandler
            asr = ASRHandler()
        except Exception as e:
            console.print(f"[bold yellow]ASR unavailable: {e}. Falling back to text input.[/bold yellow]")

    # Load agent
    try:
        from src.graph.agent import run_agent
        console.print("[bold green]Tsuzi (Tier 2 / LangGraph) ready.[/bold green]")
        if DEBUG_MODE:
            console.print("[dim yellow]DEBUG MODE ON — token estimates and timing enabled.[/dim yellow]")
    except Exception as e:
        console.print(f"[bold red]Failed to load agent: {e}[/bold red]")
        return

    console.print("[dim]Type your message, or say it if ASR is on. Ctrl+C to quit.[/dim]\n")

    while True:
        try:
            # Get input
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

            # Run agent
            t_start = time.perf_counter()
            response = run_agent(user_input)
            elapsed = time.perf_counter() - t_start

            console.print(f"\n[bold magenta]Tsuzi:[/bold magenta] {response}\n")

            if DEBUG_MODE:
                _debug_print(user_input, response, elapsed)

            # Speak response
            tts.speak(response)

        except KeyboardInterrupt:
            console.print("\n[dim]Bye, master.[/dim]")
            break
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")


if __name__ == "__main__":
    main()