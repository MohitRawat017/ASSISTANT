import json
import requests
import datetime
from duckduckgo_search import DDGS

# Ollama settings (matches app.py)
OLLAMA_API_URL = "http://localhost:11434/api"
CURATION_MODEL = "gemma3:12b"


class NewsManager:
    """Fetches and curates news headlines via DuckDuckGo + optional Ollama AI curation."""

    def __init__(self):
        self.ddgs = DDGS()
        self.cache = {}
        self.cache_duration = datetime.timedelta(minutes=15)

    def get_briefing(self, status_callback=None, use_ai: bool = True) -> list:
        """
        Get a curated briefing.
        Fetches 'top' and 'technology' news, then optionally asks AI to pick the best ones.
        """
        if status_callback: status_callback("Checking local cache...")
        cache_key = "briefing_ai" if use_ai else "briefing_raw"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        raw_news = []
        try:
            if status_callback: status_callback("Scanning global headlines...")
            for r in self.ddgs.news("top news", max_results=5):
                r['category'] = 'Top Stories'
                raw_news.append(r)

            if status_callback: status_callback("Retrieving technology sector updates...")
            for r in self.ddgs.news("technology news", max_results=5):
                r['category'] = 'Technology'
                raw_news.append(r)

            for r in self.ddgs.news("science breakthrough", max_results=3):
                r['category'] = 'Science'
                raw_news.append(r)

        except Exception as e:
            print(f"[NewsManager] Error fetching news: {e}")
            return []

        curated_news = None
        if use_ai:
            if status_callback: status_callback("AI is reading and curating stories...")
            curated_news = self._curate_with_ai(raw_news)

        if not curated_news:
            curated_news = self._format_raw_fallback(raw_news)

        self.cache[cache_key] = {
            "timestamp": datetime.datetime.now(),
            "data": curated_news
        }

        return curated_news

    def _get_from_cache(self, key: str):
        if key in self.cache:
            entry = self.cache[key]
            if datetime.datetime.now() - entry["timestamp"] < self.cache_duration:
                return entry["data"]
        return None

    def _format_raw_fallback(self, raw_news):
        """Fallback formatting if AI fails."""
        formatted = []
        seen_titles = set()

        for item in raw_news:
            if item['title'] in seen_titles:
                continue
            seen_titles.add(item['title'])

            formatted.append({
                "title": item.get('title'),
                "source": item.get('source'),
                "date": item.get('date'),
                "category": item.get('category', 'General'),
                "url": item.get('url'),
                "image": item.get('image')
            })
        return formatted[:8]

    def _curate_with_ai(self, raw_news):
        """Send raw news to Ollama LLM to select and format."""

        news_input = [
            {"id": i, "title": n.get('title'), "source": n.get('source'), "category": n.get('category')}
            for i, n in enumerate(raw_news)
        ]

        prompt = f"""
You are an expert News Editor.
Here is a list of raw news articles:
{json.dumps(news_input, indent=2)}

Task:
1. Select the 6 most important and diverse stories.
2. Rewrite the titles to be punchy and short (under 10 words).
3. Assign a category: 'Technology', 'Science', 'Markets', 'Culture', or 'Top Stories'.
4. Return ONLY a JSON array of objects.
   Format: [{{"id": <original_id>, "title": "<new_title>", "category": "<category>"}}]

Do NOT add any markdown or text. Just the JSON array.
"""

        try:
            response = requests.post(
                f"{OLLAMA_API_URL}/chat",
                json={
                    "model": CURATION_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3}
                },
                timeout=60
            )

            if response.status_code == 200:
                content = response.json()['message']['content']
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].strip()

                selected = json.loads(content)

                final_list = []
                for s in selected:
                    original = raw_news[s['id']]
                    final_list.append({
                        "title": s['title'],
                        "source": original.get('source'),
                        "date": original.get('date'),
                        "category": s['category'],
                        "url": original.get('url'),
                        "image": original.get('image'),
                        "body": original.get('body')
                    })
                return final_list

        except Exception as e:
            print(f"[NewsManager] AI Curation failed: {e}")
            return None

        return None
