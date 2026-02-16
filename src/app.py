import os
import re
from openai import OpenAI
from src.utils.config import Config
from src.audio_input.asr import ASRHandler
from src.audio_output.KokoroTTS import TTSHandler
# from src.audio_output.QwenTTS import TTSHandler
from rich.console import Console
from src.tools.web_search import web_search
from AppOpener import open as app_open, close as app_close
from src.tools.spotify import open_spotify_search, extract_music_query
import platform

import threading 
import queue

USE_THREADING = False
RECENT_TURNS = 6
DEBUG_SUMMARY = True  

console = Console()

def normalize_command(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text).lower().strip()

# wait for text chunks , sends them to tts , exits when receives None
def tts_worker(tts: TTSHandler, queue: queue.Queue):
    buffer = ""
    while True:
        chunk = queue.get()
        if chunk is None:
            # flush the remaining text 
            if buffer.strip():
                tts.speak(buffer)
            break
        buffer += chunk

        if len(buffer) > 100 or buffer.endswith((".","!","?")):
            tts.speak(buffer)
            buffer = ""
        
        # queue.task_done()
        # queue.join()

def summary_worker(client, model: str, summary_queue: queue.Queue, summary_state: dict):
    while True:
        item = summary_queue.get()
        if item is None:
            break
        old_summary, messages = item 
        try:
            new_summary = summarize_history(client, model, old_summary, messages)
            summary_state["summary"] = new_summary 
        except Exception as e:
            console.print(f"[bold red]Error in summary worker: {e}[/bold red]")

def summarize_history(client, model: str, old_summary: str, messages_to_summarize: list) -> str:

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
    context = [{"role": "system", "content": system_prompt}]
    
    if summary:
        context.append({
            "role": "system", 
            "content": f"[Previous conversation summary: {summary}]"
        })
    
    context.extend(recent_messages)
    return context

def is_search_command(text: str) -> bool:
    return text.lower().startswith("search ")

def extract_search_query(text: str) -> str:
    return text.lower().replace("search", "", 1).strip()

import re

def extract_app_name(text: str) -> str:
    text = text.lower().strip()
    # Common command prefixes
    patterns = [
        r"(?:open|launch|start)\s+(?:the\s+)?(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            app = match.group(1)
            break
    else:
        app = text
    # Normalize spaces
    app = re.sub(r"\s+", " ", app).strip()
    return app

def main():
    tts_queue = queue.Queue()
    summary_queue = queue.Queue()
    
    try:
        asr = ASRHandler()
        tts = TTSHandler()
    except Exception as e:
        print(f"Critical Error loading models: {e}")
        return

    if not Config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in .env")
    
    client = OpenAI(
        # OpenRouter
        # api_key=Config.OPENROUTER_API_KEY,
        # base_url="https://openrouter.ai/api/v1"

        # Ollama
        base_url="http://localhost:11434/v1",
        api_key="ollama"
    )
    summary_state = {"summary": ""}

    summary_thread = threading.Thread(
        target=summary_worker,
        args=(client, "gemma3:12b", summary_queue, summary_state),
        daemon=True
    )
    summary_thread.start()
    
    MODEL = "llama3.2:latest"
    
    system_prompt = """
    Your name is Tsuzi. You are a helpful AI assistant with a cheerful personality. 
    You are to address the user as "master".

    CRITICAL LATENCY RULES:
    1. DO NOT use special characters (no *, -, :, ;, or emojis).
    2. Use ONLY full stops (.) to separate thoughts. Avoid commas if possible.
    """
    conversation_summary = ""  
    recent_messages = []       

    console.print("\n[bold green]✨ Assistant V1 Ready![/bold green] [dim](Press Ctrl+C to stop)[/dim]")
    
    try:
        while True:
            # console.print("[bold cyan]🎤 Listening...[/bold cyan]")
            # audio_data = asr.listen()
            audio_data = str(input("\nPress Enter to simulate audio input..."))
            console.print("[dim]Transcribing...[/dim]")
            # user_text = asr.transcribe(audio_data)
            user_text = audio_data
            
            if not user_text:
                continue
                
            console.print(f"[bold blue]You:[/bold blue] {user_text}")
            
            cmd = normalize_command(user_text)
            if cmd in ["exit", "quit", "stop"]:
                tts.speak("Goodbye! Master!")
                summary_queue.put(None)
                break

            if cmd.startswith(("open", "launch", "start")):
                app_name = extract_app_name(user_text)

                console.print(f"[cyan]🚀 Opening application:[/cyan] {app_name}")

                try:
                    app_open(app_name)
                    tts.speak(f"Opened {app_name} for you, Master.")
                    continue

                except Exception as e:
                    console.print(f"[yellow]AppOpener failed for {app_name}: {e}[/yellow]")

                # ---- OS fallback ----
                try:
                    os_name = platform.system()

                    if os_name == "Windows":
                        open_app_windows(app_name)
                    elif os_name == "Darwin":
                        open_app_mac(app_name)
                    elif os_name == "Linux":
                        open_app_linux(app_name)
                    else:
                        raise RuntimeError("Unsupported OS")

                    tts.speak(f"Opened {app_name} for you, Master.")

                except Exception as e:
                    console.print(f"[bold red]Fallback Error opening {app_name}: {e}[/bold red]")
                    tts.speak(f"Sorry Master, I couldn't open {app_name}.")

                continue
                
            if "play" in cmd and "spotify" in cmd:
                song = extract_music_query(user_text)

                console.print(f"[cyan]🎵 Opening Spotify search for:[/cyan] {song}")
                tts.speak(f"Opening Spotify with search results for {song}, Master.")
                open_spotify_search(song)
                continue

            
            if cmd.startswith("search"):
                query = extract_search_query(user_text)

                console.print(f"[cyan]🔍 Performing web search for:[/cyan] {query}")
                tts.speak(f"Searching for {query}")

                try:
                    results = web_search(query)

                    if not results:
                        tts.speak(f"Extremely sorry Master, I couldn't find anything useful.")
                    else:
                        # for i, result in enumerate(results, 1):
                        #     console.print(f"[green]{i}. {result}[/green]")
                        #     tts.speak(result)
                        combined_results = " ".join(results)
                        response = client.chat.completions.create(
                            model=MODEL,
                            messages=[
                                {"role": "system", "content": "You are a helpful assistant that provide concise and accurate answers based on the provided web search results."},
                                {"role": "user", "content": f"Based on the following search results, provide a concise answer to the query: {query}\n\nSearch Results:\n{combined_results}"}
                            ]
                        )
                        answer = response.choices[0].message.content.strip()
                        console.print(f"[bold green]📝 Answer:[/bold green] {answer}")
                        tts.speak(answer)
                    
                except Exception as e:
                    console.print(f"[bold red]Error during web search: {e}[/bold red]")
                    tts.speak("Sorry Master, I encountered an error while searching the web.")
                continue
            
            recent_messages.append({"role": "user", "content": user_text})
            
            if len(recent_messages) > RECENT_TURNS:
                messages_to_summarize = recent_messages[:-RECENT_TURNS] 
                recent_messages = recent_messages[-RECENT_TURNS:]
                
                console.print("[dim italic](Compressing conversation history...)[/dim italic]")
                # conversation_summary = summarize_history(
                #     client, MODEL, conversation_summary, messages_to_summarize
                # )
                if summary_queue.empty():
                    summary_queue.put(
                        (summary_state["summary"], messages_to_summarize)
                    )

                # Debug: show the generated summary
                if DEBUG_SUMMARY:
                    console.print("[bold yellow]📝 Summary:[/bold yellow]")
                    console.print(f"[yellow]{summary_state['summary']}[/yellow]\n")
            
            conversation_summary = summary_state["summary"]
            # Build context for LLM
            messages = build_context(system_prompt, conversation_summary, recent_messages)
            
            console.print("[bold magenta]🧠 Thinking...[/bold magenta]")
            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                stream=True
            )
            
            full_response = ""
            
            if USE_THREADING:
                # Threaded mode: stream chunks to TTS worker in parallel
                tts_thread = threading.Thread(target=tts_worker, args=(tts, tts_queue), daemon=True)
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
                tts_thread.join()  # Wait for TTS to finish before listening again
            else:
                # Direct mode: collect full response first, then speak (faster for small models)
                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        text = delta.content
                        console.print(f"[green]{text}[/green]", end="")
                        full_response += text
                console.print()
                # Speak the complete response at once
                if full_response.strip():
                    tts.speak(full_response)
            
            # Add assistant response to recent messages
            recent_messages.append({"role": "assistant", "content": full_response})

    except KeyboardInterrupt:
        console.print("\n[bold red]Stopping...[/bold red]")
        summary_queue.put(None)

if __name__ == "__main__":
    main()