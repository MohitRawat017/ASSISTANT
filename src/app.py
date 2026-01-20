import os
import re
from openai import OpenAI
from src.utils.config import Config
from src.audio_input.asr import ASRHandler
from src.audio_output.tts import TTSHandler

import threading 
import queue

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

        # speak when buffer is "readY"
        if len(buffer) > 100 or buffer.endswith((".","!","?")):
            tts.speak(buffer)
            buffer = ""
        
        queue.task_done()

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
    
    messages = [
        {"role": "system", "content": """Your name is Tsuzi , You are a helpful ai assitant with a quite cheerful personality. You are to address the user as "Master" and respond to their requests """}
    ]

    print("\n Assistant V1 Ready! (Press Ctrl+C to stop)")
    
    try:
        while True:
            audio_data = asr.listen()
            user_text = asr.transcribe(audio_data)
            
            if not user_text:
                continue
                
            print(f"You: {user_text}")
            
            cmd = normalize_command(user_text)
            if cmd in ["exit", "quit", "stop"]:
                tts.speak("Goodbye!")
                break
            print("Thinking...")
            messages.append({"role": "user", "content": user_text})
            stream = client.chat.completions.create(
                model="llama3.2:latest",
                messages=messages,
                stream=True
            )
            
            tts_thread = threading.Thread(target=tts_worker, args=(tts, tts_queue), daemon=True)
            tts_thread.start()

            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    text = delta.content
                    print(text, end="", flush=True)
                    tts_queue.put(text)
                    full_response += text
            print()
            messages.append({"role": "assistant", "content": full_response})
            tts_queue.put(None)
            tts_thread.join()  # Wait for TTS to finish speaking before listening again

    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    main()