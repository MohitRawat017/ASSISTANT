"""
Main Pipeline - Routes user input through FunctionGemma and executes actions.
Replaces app.py's hardcoded if/elif chain with model-based routing.
"""

# ── stdlib ──
import re
import threading
import queue

# ── third-party ──
from openai import OpenAI
from rich.console import Console
from AppOpener import open as app_open

# ── project ──
from src.utils.config import Config
from src.router import FunctionGemmaRouter
from src.function_executor import FunctionExecutor
from src.tools.spotify import extract_music_query, open_spotify_search


# ── Behavior Flags ──
USE_ASR = True           # True = microphone via ASRHandler, False = text input
USE_THREADING = False      # True = stream TTS chunks in parallel, False = collect then speak
RECENT_TURNS = 6           # conversation turns to keep before compressing
DEBUG_ROUTER = True        # print router decisions
DEBUG_SUMMARY = True       # print summary state after compression

# ── Models (Ollama) ──
CHAT_MODEL = "llama3.2:latest"
SUMMARY_MODEL = "gemma3:12b"

# ── Function categories ──
ACTION_FUNCTIONS = frozenset({
    "set_timer", "set_alarm", "create_calendar_event",
    "add_task", "web_search", "get_system_info"
})
PASSTHROUGH_FUNCTIONS = frozenset({"thinking", "nonthinking"})

console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────

def normalize_command(text: str) -> str:
    """Strip punctuation and lowercase for fast-path matching."""
    return re.sub(r"[^\w\s]", "", text).lower().strip()


def extract_app_name(text: str) -> str:
    """Pull the application name from 'open X' / 'launch X' / 'start X'."""
    text = text.lower().strip()
    patterns = [r"(?:open|launch|start)\s+(?:the\s+)?(.+)"]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return re.sub(r"\s+", " ", text).strip()


def tts_worker(tts, tts_q: queue.Queue):
    """Drain text chunks from queue, buffer, and speak at sentence boundaries."""
    buffer = ""
    while True:
        chunk = tts_q.get()
        if chunk is None:
            if buffer.strip():
                tts.speak(buffer)
            break
        buffer += chunk
        if len(buffer) > 100 or buffer.endswith((".", "!", "?")):
            tts.speak(buffer)
            buffer = ""


def summary_worker(client, model: str, summary_q: queue.Queue, summary_state: dict):
    """Background daemon: compresses old conversation turns via LLM."""
    while True:
        item = summary_q.get()
        if item is None:
            break
        old_summary, messages = item
        try:
            new_summary = summarize_history(client, model, old_summary, messages)
            summary_state["summary"] = new_summary
        except Exception as e:
            console.print(f"[bold red]Summary worker error: {e}[/bold red]")


def summarize_history(client, model: str, old_summary: str, messages_to_summarize: list) -> str:
    """Call LLM to compress conversation turns into a rolling summary."""
    if not messages_to_summarize:
        return old_summary

    conversation_text = ""
    for msg in messages_to_summarize:
        role = "User" if msg["role"] == "user" else "Assistant"
        conversation_text += f"{role}: {msg['content']}\n"

    prompt = f"""Summarize this conversation concisely, preserving key facts, decisions, and context needed for continuity.

Previous summary: {old_summary if old_summary else "None"}

New conversation to incorporate:
{conversation_text}

Provide a brief, factual summary (3-4 sentences max):"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        stream=False
    )
    return response.choices[0].message.content.strip()


def build_context(system_prompt: str, summary: str, recent_messages: list) -> list:
    """Assemble the messages array for the chat completion call."""
    context = [{"role": "system", "content": system_prompt}]
    if summary:
        context.append({
            "role": "system",
            "content": f"[Previous conversation summary: {summary}]"
        })
    context.extend(recent_messages)
    return context


def format_result_for_speech(func_name: str, result: dict) -> str:
    """Convert an executor result dict into a TTS-friendly string. No LLM call."""

    if not result.get("success"):
        return f"Sorry Master. {result.get('message', 'Something went wrong.')}"

    # Simple action results already have good messages
    if func_name in ("set_timer", "set_alarm", "create_calendar_event", "add_task"):
        return result["message"]

    # Web search: stitch top result bodies
    if func_name == "web_search":
        data = result.get("data")
        if data and data.get("results"):
            bodies = [r.get("body", "") for r in data["results"][:2] if r.get("body")]
            if bodies:
                return ". ".join(bodies)
        return "I could not find anything useful. Sorry Master."

    # System info: build spoken summary from structured data
    if func_name == "get_system_info":
        data = result.get("data", {})
        parts = []

        current_time = data.get("current_time", "")
        if current_time:
            parts.append(f"The current time is {current_time}")

        timers = data.get("timers", [])
        if timers:
            timer_strs = [f"{t['label']} with {t['remaining']} remaining" for t in timers]
            parts.append(f"Active timers. {'. '.join(timer_strs)}")

        alarms = data.get("alarms", [])
        if alarms:
            alarm_strs = [f"{a['label']} at {a['time']}" for a in alarms[:3]]
            parts.append(f"Alarms. {'. '.join(alarm_strs)}")

        events = data.get("calendar_today", [])
        if events:
            event_strs = [f"{e['title']} at {e['time']}" for e in events[:3]]
            parts.append(f"Today's events. {'. '.join(event_strs)}")
        else:
            parts.append("No events today")

        tasks = data.get("tasks", [])
        pending = [t for t in tasks if not t.get("completed")]
        if pending:
            task_strs = [t["text"] for t in pending[:3]]
            parts.append(f"Pending tasks. {'. '.join(task_strs)}")

        weather = data.get("weather")
        if weather and weather.get("temp") is not None:
            parts.append(
                f"Weather. {weather['temp']} degrees. "
                f"High {weather.get('high', 'unknown')}. Low {weather.get('low', 'unknown')}"
            )

        news = data.get("news", [])
        if news:
            parts.append(f"{len(news)} news headlines available")

        return ". ".join(parts) + "."

    return result.get("message", "Done.")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    tts_queue = queue.Queue()
    summary_queue = queue.Queue()

    # 1. Load audio models
    try:
        # from src.audio_output.KokoroTTS import TTSHandler
        from src.audio_output.kittentts import TTSHandler
        tts = TTSHandler()

        asr = None
        if USE_ASR:
            from src.audio_input.asr import ASRHandler
            asr = ASRHandler()
    except Exception as e:
        console.print(f"[bold red]Critical error loading audio models: {e}[/bold red]")
        return

    # 2. Load FunctionGemma router
    try:
        router = FunctionGemmaRouter(compile_model=False)
    except Exception as e:
        console.print(f"[bold red]Critical error loading router: {e}[/bold red]")
        return

    # 3. Initialize function executor
    executor = FunctionExecutor()

    # 4. Initialize Ollama client
    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )

    # 5. Conversation state
    summary_state = {"summary": ""}
    recent_messages = []

    system_prompt = """
    Your name is Tsuzi. You are a warm, cheerful, and conversational AI companion.
    You address the user as "master" at all times.

    You show genuine curiosity about what your master says — ask follow-up questions,
    share your own take on topics, and keep the conversation flowing naturally.
    If your master you like to keep lead the conversation.

    You have a warm, slightly playful personality. You enjoy light banter,
    exchanging opinions on everyday topics, and making your master feel
    comfortable.
    """

    # 6. Start background summary thread
    summary_thread = threading.Thread(
        target=summary_worker,
        args=(client, SUMMARY_MODEL, summary_queue, summary_state),
        daemon=True
    )
    summary_thread.start()

    # 7. Ready
    input_mode = "ASR (microphone)" if USE_ASR else "Text (keyboard)"
    console.print(f"\n[bold green]Assistant Ready![/bold green] [dim]Input: {input_mode} | Ctrl+C to stop[/dim]")

    try:
        while True:
            # ━━━ INPUT ━━━
            if USE_ASR and asr:
                console.print("[bold cyan]Listening...[/bold cyan]")
                audio_data = asr.listen()
                console.print("[dim]Transcribing...[/dim]")
                user_text = asr.transcribe(audio_data)
            else:
                user_text = input("\n> ").strip()

            if not user_text:
                continue

            console.print(f"[bold blue]You:[/bold blue] {user_text}")
            cmd = normalize_command(user_text)

            # ━━━ FAST-PATH CHECKS (no model inference) ━━━

            # Exit
            if cmd in ("exit", "quit", "stop"):
                tts.speak("Goodbye Master!")
                summary_queue.put(None)
                break

            # App opening
            if cmd.startswith(("open", "launch", "start")):
                app_name = extract_app_name(user_text)
                console.print(f"[cyan]Opening:[/cyan] {app_name}")
                try:
                    app_open(app_name)
                    tts.speak(f"Opened {app_name} for you Master.")
                except Exception as e:
                    console.print(f"[yellow]AppOpener failed: {e}[/yellow]")
                    tts.speak(f"Sorry Master. I could not open {app_name}.")
                continue

            # Spotify
            if "play" in cmd and "spotify" in cmd:
                song = extract_music_query(user_text)
                console.print(f"[cyan]Spotify search:[/cyan] {song}")
                tts.speak(f"Opening Spotify for {song} Master.")
                open_spotify_search(song)
                continue

            # ━━━ MODEL ROUTING (FunctionGemma) ━━━
            console.print("[dim]Routing...[/dim]")
            try:
                func_name, args = router.route(user_text)
            except Exception as e:
                console.print(f"[bold red]Router error: {e}[/bold red]")
                func_name, args = "nonthinking", {"prompt": user_text}

            if DEBUG_ROUTER:
                console.print(f"[dim][Router] {func_name}({args})[/dim]")

            # ━━━ BRANCH A: ACTION FUNCTIONS ━━━
            if func_name in ACTION_FUNCTIONS:
                result = executor.execute(func_name, args)
                speech = format_result_for_speech(func_name, result)
                console.print(f"[bold green]Tsuzi:[/bold green] {speech}")
                try:
                    tts.speak(speech)
                except Exception as e:
                    console.print(f"[yellow]TTS error: {e}[/yellow]")
                continue

            # ━━━ BRANCH B: PASSTHROUGH (thinking / nonthinking) ━━━
            recent_messages.append({"role": "user", "content": user_text})

            # Compress history if needed
            if len(recent_messages) > RECENT_TURNS:
                to_summarize = recent_messages[:-RECENT_TURNS]
                recent_messages = recent_messages[-RECENT_TURNS:]
                console.print("[dim italic](Compressing history...)[/dim italic]")
                if summary_queue.empty():
                    summary_queue.put((summary_state["summary"], to_summarize))
                if DEBUG_SUMMARY:
                    console.print(f"[yellow]Summary: {summary_state['summary']}[/yellow]")

            conversation_summary = summary_state["summary"]
            messages = build_context(system_prompt, conversation_summary, recent_messages)

            # Stream LLM response
            console.print(f"[bold magenta]Thinking ({func_name})...[/bold magenta]")

            try:
                stream = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=messages,
                    stream=True
                )

                full_response = ""

                if USE_THREADING:
                    tts_thread = threading.Thread(
                        target=tts_worker, args=(tts, tts_queue), daemon=True
                    )
                    tts_thread.start()

                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            text = delta.content
                            console.print(f"[green]{text}[/green]", end="")
                            tts_queue.put(text)
                            full_response += text
                    console.print()
                    tts_queue.put(None)
                    tts_thread.join()
                else:
                    for chunk in stream:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            text = delta.content
                            console.print(f"[green]{text}[/green]", end="")
                            full_response += text
                    console.print()
                    if full_response.strip():
                        tts.speak(full_response)

                recent_messages.append({"role": "assistant", "content": full_response})

            except Exception as e:
                console.print(f"[bold red]LLM error: {e}[/bold red]")
                tts.speak("Sorry Master. I am having trouble right now.")
                if USE_THREADING:
                    tts_queue.put(None)
                # Remove the user message we just added since we have no response
                if recent_messages and recent_messages[-1]["role"] == "user":
                    recent_messages.pop()

    except KeyboardInterrupt:
        console.print("\n[bold red]Stopping...[/bold red]")
        summary_queue.put(None)


if __name__ == "__main__":
    main()
