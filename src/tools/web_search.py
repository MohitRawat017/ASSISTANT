from ddgs import DDGS


def web_search(query: str, max_results: int = 3) -> list[str]:
    """
    Perform a web search using DuckDuckGo.

    Returns a list of short textual answers suitable for TTS.
    """
    results = []

    with DDGS() as ddgs:
        # Get text search results
        search_results = ddgs.text(query, max_results=max_results)

        for result in search_results:
            # Combine title and body for a complete answer
            title = result.get("title", "")
            body = result.get("body", "")

            if body:
                results.append(f"{title}: {body}")
            elif title:
                results.append(title)

    return results[:max_results]
