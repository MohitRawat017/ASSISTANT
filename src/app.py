import os
import re
from openai import OpenAI
from src.utils.config import Config
from src.audio_input.asr import ASRHandler
from src.audio_output.tts import TTSHandler
from rich.console import Console

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
        
        queue.task_done()

def summarize_history(client, model: str, old_summary: str, messages_to_summarize: list) -> str:
    """Compress older messages into a rolling summary."""
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

Provide a brief, factual summary (2-3 sentences max):"""

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

def main():
    tts_queue = queue.Queue()
    
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
    
    MODEL = "llama3.2:latest"
    
    system_prompt = """Your name is Tsuzi , You are a helpful ai assitant with a quite cheerful personality. You are to address the user as "Master" and respond to their requests """
    
    conversation_summary = ""  
    recent_messages = []       

    console.print("\n[bold green]✨ Assistant V1 Ready![/bold green] [dim](Press Ctrl+C to stop)[/dim]")
    
    try:
        while True:
            console.print("[bold cyan]🎤 Listening...[/bold cyan]")
            audio_data = asr.listen()
            console.print("[dim]Transcribing...[/dim]")
            user_text = asr.transcribe(audio_data)
            
            if not user_text:
                continue
                
            console.print(f"[bold blue]You:[/bold blue] {user_text}")
            
            cmd = normalize_command(user_text)
            if cmd in ["exit", "quit", "stop"]:
                tts.speak("Goodbye! Master!")
                break
            
            recent_messages.append({"role": "user", "content": user_text})
            
            if len(recent_messages) > RECENT_TURNS:
                messages_to_summarize = recent_messages[:-RECENT_TURNS]
                recent_messages = recent_messages[-RECENT_TURNS:]
                
                console.print("[dim italic](Compressing conversation history...)[/dim italic]")
                conversation_summary = summarize_history(
                    client, MODEL, conversation_summary, messages_to_summarize
                )
                
                # Debug: show the generated summary
                if DEBUG_SUMMARY:
                    console.print("[bold yellow]📝 Summary:[/bold yellow]")
                    console.print(f"[yellow]{conversation_summary}[/yellow]\n")
            
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

if __name__ == "__main__":
    main()