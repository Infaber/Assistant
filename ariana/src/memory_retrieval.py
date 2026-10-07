"""Small deterministic local retrieval; no models, embeddings or network calls."""

import math
import re
from collections import Counter

STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "about",
        "at",
        "be",
        "can",
        "do",
        "for",
        "from",
        "have",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "the",
        "to",
        "you",
        "your",
        "what",
        "how",
        "with",
        "please",
        "remember",
        "tell",
        "project",
        "projects",
    ]
)
# Narrow engineering vocabulary expansion, not user-intent classification.
RELATED = {
    "esp32": {
        "esp32",
        "microcontroller",
        "sensors",
        "sensor",
        "automation",
        "led",
        "strips",
        "homeassistant",
    },
    "homeassistant": {
        "homeassistant",
        "esp32",
        "automation",
        "sensor",
        "sensors",
        "led",
    },
}


def tokens(text: str) -> set[str]:
    normalized = text.casefold().replace("home assistant", "homeassistant")
    return {
        word
        for word in re.findall(r"[^\W_]+", normalized)
        if len(word) > 1 and word not in STOP
    }


def relevant_memories(
    rows: list[tuple[str, str]], query: str, limit: int = 6
) -> list[dict]:
    terms = tokens(query)
    if not terms:
        return []
    related = set().union(*(RELATED.get(term, set()) for term in terms)) - terms
    documents = [(topic, fact, tokens(topic), tokens(fact)) for topic, fact in rows]
    frequency = Counter(
        term for _, _, topic, fact in documents for term in topic | fact
    )
    ranked = []
    for topic, fact, tt, ft in documents:
        direct = terms & (tt | ft)
        indirect = related & (tt | ft)
        if not direct and not indirect:
            continue
        score = sum(
            (3 if term in tt else 1) * math.log(2 + len(rows) / (1 + frequency[term]))
            for term in direct
        )
        score += sum(0.3 if term in tt else 0.15 for term in indirect)
        ranked.append((score, topic, fact))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"topic": topic, "fact": fact}
        for _, topic, fact in ranked[: max(1, min(limit, 10))]
    ]
