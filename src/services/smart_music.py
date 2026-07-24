from __future__ import annotations  # enables future Python language features
import re  # matches and cleans text with regular expressions
from collections import defaultdict  # provides counters and specialized containers
from typing import Any  # adds type hint helpers


MUSIC_CATEGORIES = [
    "podcast",
    "educational",
    "tutorial",
    "motivational",
    "romantic",
    "sad",
    "love",
    "business",
    "marketing",
    "gaming",
    "funny",
    "meme",
    "horror",
    "cinematic",
    "documentary",
    "news",
    "lifestyle",
    "fitness",
    "calm",
    "energetic",
]


STYLE_TO_CATEGORY = {
    "podcast": "podcast",
    "educational": "educational",
    "tutorial": "tutorial",
    "motivational": "motivational",
    "romantic": "romantic",
    "sad": "sad",
    "love": "love",
    "business": "business",
    "marketing": "marketing",
    "gaming": "gaming",
    "funny": "funny",
    "meme": "meme",
    "horror": "horror",
    "cinematic": "cinematic",
    "documentary": "documentary",
    "news": "news",
    "lifestyle": "lifestyle",
    "fitness": "fitness",
}


KEYWORDS = {
    "sad": [
        "sad", "pain", "hurt", "cry", "tears", "alone", "lonely", "broken", "dard", "dukhi", "rona", "tanhai",
        "abandoned", "lost", "miss", "regret", "depressed", "worst", "goodbye",
    ],
    "romantic": [
        "romance", "romantic", "heart", "kiss", "date", "together", "forever",
        "relationship", "couple", "marry", "wife", "husband",
    ],
    "love": [
        "love", "loved", "loving", "care", "feelings", "heart", "need you",
        "i needed you", "miss you", "trust", "promise",
    ],
    "motivational": [
        "success", "goal", "dream", "discipline", "mindset", "growth",
        "motivation", "focus", "win", "better", "change", "believe", "hard work",
    ],
    "tutorial": [
        "how to", "step", "steps", "tutorial", "guide", "learn", "setup",
        "create", "build", "use this", "do this",
    ],
    "educational": [
        "explain", "education", "lesson", "understand", "meaning", "why", "samjho", "seekho", "sikh",
        "because", "knowledge", "science", "history", "example",
    ],
    "business": [
        "business", "startup", "company", "client", "revenue", "profit",
        "product", "strategy", "market", "finance", "money",
    ],
    "marketing": [
        "marketing", "sales", "brand", "offer", "audience", "viral",
        "content", "creator", "hook", "conversion", "customers",
    ],
    "gaming": [
        "game", "gaming", "player", "level", "win", "kill", "match",
        "stream", "rank", "battle", "score",
    ],
    "funny": [
        "funny", "laugh", "joke", "comedy", "crazy", "hilarious", "lol",
        "roast", "prank", "mazak", "mazaq", "hansi", "hasna", "jugtain", "comedy", "fun",
    ],
    "meme": ["meme", "trend", "viral", "reaction", "internet", "template"],
    "horror": [
        "horror", "scary", "fear", "afraid", "dark", "ghost", "danger",
        "scream", "mystery", "creepy",
    ],
    "news": ["breaking", "news", "report", "today", "update", "headline"],
    "fitness": [
        "fitness", "gym", "workout", "training", "exercise", "run", "sport",
        "athlete", "body",
    ],
    "lifestyle": [
        "life", "vlog", "travel", "food", "daily", "home", "family",
        "routine", "lifestyle",
    ],
    "documentary": ["documentary", "story", "real", "case", "journey", "truth"],
    "calm": ["calm", "peace", "relax", "soft", "quiet", "gentle", "slow"],
    "energetic": ["energy", "fast", "excited", "power", "hype", "intense"],
    "cinematic": ["cinematic", "dramatic", "emotional", "scene", "film", "story"],
    "podcast": ["podcast", "interview", "conversation", "guest", "host", "episode"],
}
def _extract_text(whisper_result: dict[str, Any] | str | None) -> str:  # extracts transcript text from a Whisper result or plain text
    if not whisper_result:
        return ""
    if isinstance(whisper_result, str):
        return whisper_result
    parts: list[str] = []
    for segment in whisper_result.get("segments", []) or []:
        text = str(segment.get("text", "") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts) or str(whisper_result.get("text", "") or "")
def infer_music_category(
    whisper_result: dict[str, Any] | str | None = None,
    editing_style: str = "",
    platform: str = "",
    fallback: str = "cinematic",
) -> tuple[str, dict[str, Any]]:
    text = _extract_text(whisper_result).lower()
    normalized_style = (editing_style or "").strip().lower().replace("-", "_")
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)

    style_category = STYLE_TO_CATEGORY.get(normalized_style)
    if style_category:
        scores[style_category] += 5.0
        reasons[style_category].append(f"editing style matched {normalized_style}")

    for category, words in KEYWORDS.items():
        hits = 0
        for word in words:
            pattern = r"\b" + re.escape(word) + r"\b" if " " not in word else re.escape(word)
            matches = len(re.findall(pattern, text))
            if matches:
                hits += min(matches, 3)
        if hits:
            scores[category] += min(8.0, hits * 1.15)
            reasons[category].append(f"{hits} transcript keyword match(es)")

    if "!" in text:
        scores["energetic"] += 1.0
        reasons["energetic"].append("high-energy punctuation")

    if platform == "tiktok":
        scores["energetic"] += 0.75
        reasons["energetic"].append("TikTok platform preference")

    if not scores:
        scores[fallback] = 1.0
        reasons[fallback].append("no strong signal, using cinematic fallback")

    category = max(scores.items(), key=lambda item: item[1])[0]
    if category not in MUSIC_CATEGORIES:
        category = fallback

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:5]
    return category, {
        "selected": category,
        "style": normalized_style or "none",
        "top_scores": ranked,
        "reasons": reasons.get(category, []),
    }



