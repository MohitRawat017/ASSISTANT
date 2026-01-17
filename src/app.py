import os
import re
# from google import genai
# from google.genai import types
from openai import OpenAI

from src.utils.config import Config
from src.audio_input.asr import ASRHandler
from src.audio_output.tts import TTSHandler

def normalize_command(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text).lower().strip()

def main():
    try:
        asr = ASRHandler()
        tts = TTSHandler()
    except Exception as e:
        print(f"Critical Error loading models: {e}")
        return

    if not Config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not found in .env")
    
    client = OpenAI(
        api_key=Config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )
    
    SYSTEM_PROMPT = """Your name is Tsuzi , You are a helpful ai assitant with a quite cheerful personality. You are to address the user as "Master" and respond to their requests """

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
            stream = client.chat.completions.create(
                model="z-ai/glm-4.5-air:free",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    print(delta.content, end="", flush=True)
                    full_response += delta.content
            print()
            
            tts.speak(full_response)

    except KeyboardInterrupt:
        print("\nStopping...")

if __name__ == "__main__":
    main()