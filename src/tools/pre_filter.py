
CASUAL_WORDS = frozenset({
    "hi", "hello", "hey", "hiya", "howdy", "sup", "yo",
    "good morning", "good evening", "good night", "good afternoon",
    "bye", "goodbye", "see ya", "later", "cya",
    "ok", "okay", "sure", "fine", "alright", "cool", "nice",
    "great", "awesome", "perfect", "thanks", "thank you",
    "thx", "ty", "appreciated",
    "yes", "yeah", "yep", "yea", "yup", "no", "nope", "nah",
    "hmm", "hm", "um", "uh", "lol", "haha", "hehe",
    "what's up", "whats up", "how are you", "how r u",
    "what's going on", "nothing", "nothing much", "nm",
})


def is_casual_query(text: str) -> bool:
    cleaned = text.strip().lower()

    if not cleaned:
        return True

    if cleaned in CASUAL_WORDS:
        return True

    words = cleaned.split()
    if len(words) <= 2 and all(w in CASUAL_WORDS for w in words):
        return True

    return False
