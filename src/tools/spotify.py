import webbrowser
import urllib.parse
import re

def extract_music_query(text: str) -> str:
    
    text = text.lower().strip()

    # 1️⃣ Remove trigger words
    triggers = [
        "play",
        "listen to",
        "put on",
        "start",
    ]

    for trigger in triggers:
        if text.startswith(trigger):
            text = text[len(trigger):].strip()
            break

    # 2️⃣ Remove platform references
    platforms = [
        "on spotify",
        "from spotify",
        "in spotify",
        "using spotify",
    ]

    for platform in platforms:
        text = text.replace(platform, "")

    # 3️⃣ Remove filler words
    fillers = [
        "the song",
        "song",
        "music",
        "track",
        "please",
        "for me",
        "now",
    ]

    for filler in fillers:
        text = text.replace(filler, "")

    # 4️⃣ Remove quotes (single or double)
    text = re.sub(r"[\"']", "", text)

    # 5️⃣ Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def open_spotify_search(song_name: str):
    query = urllib.parse.quote(song_name)
    url = f"https://open.spotify.com/search/{query}"
    webbrowser.open(url)
