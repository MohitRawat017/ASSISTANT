import torch
from google import genai 
from google.genai import types
import os
from dotenv import load_dotenv
import sounddevice as sd
from faster_whisper import WhisperModel 
import numpy as np 
from kokoro import KPipeline, KModel
import re 

def clean_text_for_tts(text: str) -> str:
    text = text.replace("*", "").replace("_", "").replace("`", "")
    return re.sub(r"\n+", " ", text).strip()

def normalize_command(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)  # remove punctuation
    return text

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading TTS model on {device}...")
k_model = KModel(
    repo_id="hexgrad/Kokoro-82M",
    config="models/tts/config.json",
    model="models/tts/kokoro-v1_0.pth"
)
k_model.to(device).eval()

tts_model = KPipeline(
    lang_code='a',
    model=k_model,
    device=device
)
print("Kokoro ready.")

print("Loading ASR model...")
asr_model = WhisperModel(
        "models/asr/",
        device="cuda",
        compute_type="int8",
        )
print("ASR ready.")

def record_and_transcribe(seconds=4):
    samplerate = 16000

    print("Listening...")
    audio = sd.rec(
        int(seconds * samplerate),
        samplerate=samplerate,
        channels=1,
        dtype=np.float32
    )
    sd.wait()

    print("Transcribing...")
    segments, _ = asr_model.transcribe(audio.flatten())
    text = " ".join(seg.text for seg in segments).strip()
    return text

def main():
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    client = genai.Client(api_key=api_key)

    print("API KEY IS FINEEEEE")

    chat= client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction="You are a snarky assistant.",
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        ),
    )

    while True:
        print("You: ", end="", flush=True)
        user_input = record_and_transcribe()
        print(user_input)

        command = normalize_command(user_input)
        if command == "exit":
            speak_text("Goodbye!")
            break

        response = chat.send_message_stream(user_input)
        full_response = ""
        for chunk in response:
            if chunk.text:
                print(chunk.text, end="", flush=True)
                full_response += chunk.text
        print()
        
        clean_text = clean_text_for_tts(full_response)
        speak_text(clean_text)

def speak_text(text):
    if not text:
        return
    generator = tts_model(text, voice='af_heart', speed=1)
    for result in generator:
        if result.audio is not None:
            audio = result.audio.cpu().numpy()
            sd.play(audio, samplerate=24000)
            sd.wait()

if __name__ == '__main__':
    main()