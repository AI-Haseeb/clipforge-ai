from __future__ import annotations  # enables future Python language features
from pathlib import Path  # provides object-oriented file paths
from typing import List, Tuple, Dict, Any, Optional  # adds type hint helpers
import re  # matches and cleans text with regular expressions
import os  # works with environment variables and OS paths
import json  # handles JSON encode and decode
import urllib.request  # sends HTTP requests
import urllib.error  # handles HTTP/network exceptions


# -------------------------
# Keyword loading (weighted)
# -------------------------
def _looks_number(s: str) -> bool:  # checks whether a keyword weight token looks numeric
    try:
        float(s)
        return True
    except Exception:
        return False
def _parse_keyword_line(line: str) -> Tuple[str, float]:  # parses one weighted keyword config line into keyword and score
    """
    Supports:
      keyword
      keyword | 6
      keyword = 6
      6 | keyword
      6 = keyword
    """
    default_w = 2.0
    x = (line or "").strip()
    if not x or x.startswith("#"):
        return ("", 0.0)

    if "|" in x:
        a, b = [p.strip() for p in x.split("|", 1)]
        if _looks_number(b):
            return (a, float(b))
        if _looks_number(a):
            return (b, float(a))
        return (a or b, default_w)

    if "=" in x:
        a, b = [p.strip() for p in x.split("=", 1)]
        if _looks_number(b):
            return (a, float(b))
        if _looks_number(a):
            return (b, float(a))
        return (a or b, default_w)

    return (x, default_w)
def load_keywords_weighted(path: Path) -> List[Tuple[str, float]]:  # loads weighted keywords used for highlight scoring and metadata
    if not path.exists():
        return []
    out: List[Tuple[str, float]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        kw, w = _parse_keyword_line(raw)
        kw = kw.strip()
        if kw:
            out.append((kw, w))
    return out
def _norm(s: str) -> str:  # normalizes text for comparison, scoring, and duplicate checks
    return re.sub(r"\s+", " ", (s or "").lower()).strip()
def _collapse_repeated_text(text: str) -> str:  # removes repeated word groups before metadata is generated
    tokens = str(text or "").split()
    if len(tokens) < 4:
        return str(text or "")

    def norm(tok: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", tok.lower())

    out: List[str] = []
    i = 0
    while i < len(tokens):
        collapsed = False
        max_n = min(8, (len(tokens) - i) // 2)
        for n in range(max_n, 0, -1):
            group = [norm(t) for t in tokens[i:i + n]]
            if not any(group):
                continue
            repeat_count = 1
            j = i + n
            while j + n <= len(tokens) and [norm(t) for t in tokens[j:j + n]] == group:
                repeat_count += 1
                j += n
            if repeat_count >= 2:
                out.extend(tokens[i:i + n])
                i = j
                collapsed = True
                break
        if not collapsed:
            out.append(tokens[i])
            i += 1
    return re.sub(r"\s+", " ", " ".join(out)).strip()

# âœ… NEW: stopwords so "to/and/the" don't become keywords
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "so", "to", "of", "in", "on", "at", "for", "from",
    "with", "as", "by", "is", "are", "was", "were", "be", "been", "being",
    "i", "you", "he", "she", "it", "we", "they", "me", "my", "your", "our", "their",
    "this", "that", "these", "those", "there", "here",
    "do", "does", "did", "done", "have", "has", "had",
    "not", "no", "yes", "too", "very", "just", "only",
}
def _is_stopword_kw(kw: str) -> bool:  # skips weak keywords that should not drive clip scoring
    k = _norm(kw)
    if " " not in k and k in _STOPWORDS:
        return True
    return False
def keyword_hits(text: str, keywords: List[Tuple[str, float]], top_k: int = 8) -> List[Tuple[str, float]]:  # finds weighted keyword matches inside segment text
    """
    Returns top keyword hits found in text, sorted by weight desc.
    Phrase match (contains).
    """
    t = _norm(text)
    hits: List[Tuple[str, float]] = []
    for kw, w in keywords:
        k = _norm(kw)
        if not k:
            continue
        if _is_stopword_kw(k):
            continue
        if k in t:
            hits.append((kw, float(w)))

    hits.sort(key=lambda x: x[1], reverse=True)

    # unique keep best weight
    seen = set()
    uniq: List[Tuple[str, float]] = []
    for k, w in hits:
        kk = _norm(k)
        if kk in seen:
            continue
        seen.add(kk)
        uniq.append((k, w))
        if len(uniq) >= top_k:
            break
    return uniq


# -------------------------
# Platform handling
# -------------------------
def _platform_bucket(p: str) -> str:  # maps a platform name to the metadata rules bucket
    p = (p or "").lower().strip()
    if p in ("tiktok", "tt"):
        return "tiktok"
    if p in ("instagram", "ig", "reels"):
        return "instagram"
    if p in ("youtube", "yt", "shorts", "youtube_shorts"):
        return "youtube"
    return "instagram"


# -------------------------
# Language detection (simple)
# -------------------------
_ROMAN_URDU_HINTS = {
    "aap", "tum", "ap", "kya", "kyun", "kyu", "kaise", "kaisay", "kese",
    "yeh", "ye", "woh", "wo", "mat", "kar", "karo", "kr", "hai", "hain",
    "bht", "bohat", "sirf", "abhi", "ab", "dekho", "sun", "suno", "gour",
    "raaz", "sach", "ghalti", "nuksan", "faida", "kamai", "paisa",
    "wala", "wali", "chahiye", "zaroor", "bilkul"
}
def detect_lang_bucket(text: str, *, force_english: bool = False) -> str:  # chooses English or Roman metadata style from language/settings
    if force_english:
        return "en"

    """
    Returns: 'en' or 'roman'
    (roman covers Roman Urdu/Hindi written in English letters)
    """
    t = _norm(text)
    tokens = set(re.findall(r"[a-zA-Z']+", t))
    score = 0
    for h in _ROMAN_URDU_HINTS:
        if h in tokens:
            score += 1
    return "roman" if score >= 2 else "en"


# -------------------------
# Hook/Title/Desc templates
# -------------------------
def _templates(lang: str) -> Dict[str, List[str]]:  # returns fallback title/hook/CTA templates for a language
    if lang == "roman":
        return {
            "hooks": [
                "Ruk jao â€” yeh miss mat karna.",
                "Aksar log yeh ghalti kar dete hain.",
                "Yeh raaz bohat kam log jante hain.",
                "End tak dekho â€” point yahin hai.",
                "Agar tum yeh ignore karoge, nuksan hoga.",
                "Yeh simple cheez tumhara result badal degi.",
            ],
            "titles": [
                "Aksar Log Yeh Ghalti Karte Hain",
                "Yeh Simple Trick Tumhara Result Badal De",
                "Yeh Raaz Bohat Kam Log Jante Hain",
                "Is One Step Ko Ignore Mat Karna",
            ],
            "cta": [
                "âœ… Save kar lo aur follow karo for more.",
                "âœ… Helpful ho to share karo.",
                "âœ… Comment me batao tumhara kya experience hai.",
            ],
        }

    return {
        "hooks": [
            "Stop scrolling â€” donâ€™t miss this.",
            "Most people make this mistake.",
            "Hereâ€™s the secret nobody tells you.",
            "Watch till the end â€” the key is here.",
            "If you ignore this, youâ€™ll regret it.",
            "This one simple step changes everything.",
        ],
        "titles": [
            "Most People Make This Mistake",
            "The Secret Nobody Tells You",
            "This Simple Trick Changes Everything",
            "Donâ€™t Ignore This One Step",
        ],
        "cta": [
            "âœ… Save this and follow for more.",
            "âœ… Share if this helped you.",
            "âœ… Comment what you think below.",
        ],
    }
def _best_keyword(hits: List[Tuple[str, float]]) -> Optional[str]:  # chooses the strongest keyword match for the current segment
    return hits[0][0] if hits else None
def _topic_vibe(hits: List[Tuple[str, float]], text: str = "") -> str:  # detects the content tone so metadata does not become generic or wrong
    blob = " ".join([_norm(k) for k, _ in hits] + [_norm(text)])
    if any(x in blob for x in ["funny", "comedy", "joke", "laugh", "meme", "mazak", "mazaq", "hansi", "hasna", "jugtain", "comic", "roast", "prank"]):
        return "funny"
    if any(x in blob for x in ["tutorial", "how to", "step", "guide", "learn", "setup", "sikh", "seekho"]):
        return "tutorial"
    if any(x in blob for x in ["education", "educational", "explain", "lesson", "understand", "samjho", "knowledge", "history", "science"]):
        return "educational"
    if any(x in blob for x in ["business", "marketing", "sales", "clients", "growth", "money", "income", "revenue", "profit", "brand"]):
        return "business"
    if any(x in blob for x in ["motivation", "motivational", "success", "discipline", "mindset", "goal", "dream", "hard work"]):
        return "motivational"
    if any(x in blob for x in ["game", "gaming", "player", "level", "match", "rank", "stream"]):
        return "gaming"
    if any(x in blob for x in ["news", "breaking", "report", "today", "headline", "update"]):
        return "news"
    if any(x in blob for x in ["sad", "pain", "heart", "lonely", "cry", "tears", "breakup", "depressed", "dard", "dukhi", "rona", "tanhai"]):
        return "emotional"
    if any(x in blob for x in ["podcast", "interview", "conversation", "guest", "host", "episode"]):
        return "podcast"
    return "general"

# -------------------------
def _settings_topic_text(settings: Optional[dict]) -> str:  # collects user-selected style/category hints for metadata tone
    if not isinstance(settings, dict):
        return ""
    values = []
    for key in ("editing_style_selected", "music_category", "content_category", "filter_preset_default"):
        value = settings.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return " ".join(values)

def _metadata_content_profile(
    *,
    segment_text: str,
    hits: List[Tuple[str, float]],
    lang: str,
    settings: Optional[dict],
) -> Dict[str, Any]:
    settings_hint = _settings_topic_text(settings)
    category = _topic_vibe(hits, f"{segment_text} {settings_hint}")
    if isinstance(settings, dict):
        selected = str(settings.get("content_category", "") or "").strip().lower()
        style = str(settings.get("editing_style_selected", "") or "").strip().lower()
        for candidate in (style, selected):
            if candidate in {
                "funny", "meme", "educational", "tutorial", "business", "marketing",
                "motivational", "gaming", "news", "podcast", "sad", "romantic",
                "love", "horror", "documentary", "lifestyle", "fitness", "cinematic",
            }:
                category = "emotional" if candidate in {"sad", "romantic", "love"} else candidate
                break

    tone_map = {
        "funny": "witty, playful, punchline-focused",
        "meme": "fast, meme-like, shareable",
        "educational": "clear, useful, explanatory",
        "tutorial": "direct, step-by-step, helpful",
        "business": "practical, growth-focused, credible",
        "marketing": "sharp, high-retention, creator-business focused",
        "motivational": "energetic, inspiring, action-focused",
        "gaming": "high-energy and gaming-native",
        "news": "clear, factual, update-focused",
        "podcast": "conversational and insight-focused",
        "emotional": "sincere and story-driven",
        "horror": "suspenseful, tense, curiosity-focused",
        "documentary": "story-led and factual",
        "lifestyle": "natural, personal, relatable",
        "fitness": "energetic and action-focused",
        "cinematic": "dramatic but still relevant to the clip",
        "general": "specific, simple, and watchable",
    }
    forbidden_map = {
        "funny": "Do not make it sad, heartbreak, pain, motivational, or emotional unless the transcript clearly says that.",
        "meme": "Do not make it serious or sad; keep it playful and viral.",
        "business": "Do not make it emotional; focus on practical result, growth, clients, money, or strategy.",
        "marketing": "Do not make it emotional; focus on hooks, attention, audience, sales, or creator growth.",
        "educational": "Do not exaggerate or make it clickbait; keep it useful and clear.",
        "tutorial": "Do not make it emotional; keep it direct and practical.",
        "news": "Do not invent claims; keep it factual and careful.",
    }
    return {
        "category": category,
        "tone": tone_map.get(category, tone_map["general"]),
        "language": "Roman Urdu/Hindi/Punjabi in English letters" if lang == "roman" else "English",
        "forbidden": forbidden_map.get(category, "Do not add a different emotion or topic that is not present in the transcript."),
        "style": str(settings.get("editing_style_selected", "none") if isinstance(settings, dict) else "none") or "none",
        "keywords": [k for k, _ in hits[:8]],
    }

# Description + Emojis + Hashtags
# -------------------------
def _clean_spaces(text: str) -> str:  # collapses extra whitespace in transcript/metadata text
    return re.sub(r"\s+", " ", (text or "").strip())
def extract_text_from_whisper_range(  # collects transcript text from Whisper segments inside a time range
    whisper_result: dict,
    start: float,
    end: float,
    *,
    pad: float = 0.0,
) -> str:
    s0 = max(0.0, float(start) - float(pad))
    e0 = max(s0, float(end) + float(pad))

    parts: List[str] = []
    for seg in (whisper_result or {}).get("segments", []) or []:
        ss = float(seg.get("start", 0.0) or 0.0)
        ee = float(seg.get("end", 0.0) or 0.0)

        if ee <= s0:
            continue
        if ss >= e0:
            break

        t = (seg.get("text") or "").strip()
        if t:
            parts.append(t)

    return _clean_spaces(" ".join(parts))
def _split_sentences(text: str) -> List[str]:  # splits transcript text into sentence-sized metadata chunks
    text = _clean_spaces(text)
    if not text:
        return []
    sents = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sents if s.strip()]
def _pick_emojis(hits: List[Tuple[str, float]], lang: str) -> List[str]:  # chooses lightweight emojis that match clip keywords
    t = " ".join([_norm(k) for k, _ in hits])

    if _topic_vibe(hits, t) == "funny":
        base = [":D", "LOL", "!"]
    elif any(x in t for x in ["warning", "danger", "risky", "scam", "mistake"]):
        base = ["!", "NO", "OK"]
    elif any(x in t for x in ["money", "earn", "income", "profit", "business", "sales", "marketing"]):
        base = ["$", "UP", "OK"]
    elif any(x in t for x in ["ai", "automation", "tools", "software", "chatgpt"]):
        base = ["AI", "FAST", "OK"]
    elif any(x in t for x in ["secret", "truth", "exposed", "reality"]):
        base = ["SECRET", "SEE", "OK"]
    else:
        base = ["HOT", "SEE", "OK"]

    return base[:3]
def _hashtags_from_hits(hits: List[Tuple[str, float]], max_tags: int = 8) -> List[str]:  # builds hashtags from matched keywords
    tags: List[str] = []
    def slugify(s: str) -> str:  # turns text into a URL/file-safe slug
        s = _norm(s)
        s = re.sub(r"[^a-z0-9\s]+", "", s)
        s = re.sub(r"\s+", "", s)
        return s

    for kw, _w in hits:
        slug = slugify(kw)
        if not slug:
            continue
        if len(slug) > 26:
            continue
        t = "#" + slug
        if t not in tags:
            tags.append(t)
        if len(tags) >= max_tags:
            break

    return tags
def _preset_hashtags(platform: str, lang: str, hits: List[Tuple[str, float]]) -> List[str]:  # returns platform/topic default hashtags
    p = _platform_bucket(platform)
    t = " ".join([_norm(k) for k, _ in hits])

    if p == "tiktok":
        base = ["#fyp", "#foryou", "#viral", "#trending", "#tiktok", "#learnontiktok"]
    elif p == "youtube":
        base = ["#shorts", "#youtubeshorts", "#shortvideo", "#viral"]
    else:
        base = ["#reels", "#instagramreels", "#reelsinstagram", "#viral"]

    # light topic adds
    if _topic_vibe(hits, t) == "funny":
        base += ["#funny", "#comedy", "#mazak", "#desicomedy", "#funnyshorts"]
    if any(x in t for x in ["ai", "automation", "chatgpt", "tools", "software"]):
        base += ["#ai", "#automation", "#chatgpt", "#aitools"]
    if any(x in t for x in ["business", "marketing", "sales", "clients", "ads", "growth"]):
        base += ["#business", "#marketing", "#sales", "#growth"]
    if any(x in t for x in ["money", "earn", "income", "profit", "side hustle"]):
        base += ["#money", "#onlineearning", "#sidehustle"]
    if _topic_vibe(hits) == "emotional":
        base += ["#feelings", "#story", "#hearttouching"]

    if lang == "roman":
        base += ["#pakistan", "#urdu"]

    out: List[str] = []
    for x in base:
        if x not in out:
            out.append(x)
    return out
def _platform_tag_limit(platform: str) -> int:  # returns the hashtag limit for the target platform
    p = _platform_bucket(platform)
    if p == "tiktok":
        return 20
    if p == "youtube":
        return 18
    return 20  # instagram
def _build_description(  # builds a structured description from transcript text, CTA, and hashtags
    segment_text: str,
    lang: str,
    cta: str,
    hits: List[Tuple[str, float]],
    platform: str,
    max_sentences: int = 3,
) -> str:
    # local fallback (non-AI)
    sents = _split_sentences(segment_text)

    kept: List[str] = []
    for s in sents:
        if len(s) < 10:
            continue
        kept.append(s)
        if len(kept) >= max_sentences:
            break

    if not kept:
        kept = [_clean_spaces(segment_text)]

    body = " ".join(kept).strip()

    if _topic_vibe(hits, segment_text) == "funny":
        emojis = [":D", "LOL", "!"]
    else:
        emojis = _pick_emojis(hits, lang)
    emoji_prefix = " ".join(emojis) + " "

    limit = _platform_tag_limit(platform)

    hit_tags = _hashtags_from_hits(hits, max_tags=10)
    preset = _preset_hashtags(platform, lang, hits)

    tags: List[str] = []
    for t in preset + hit_tags:
        if t not in tags:
            tags.append(t)
    tags = tags[:limit]

    hashtags_line = " ".join(tags).strip()

    return f"{emoji_prefix}{body}\n\n{cta}\n\n{hashtags_line}".strip()



# -------------------------
# OpenAI metadata enhancer (SAFE FALLBACK)
# -------------------------
def _project_root_for_meta() -> Path:  # finds the project root for metadata helper file access
    try:
        from src.utils.paths import project_root  # project path helper
        return project_root()
    except Exception:
        return Path.cwd()
def _read_text_file_secret(path_value: str) -> str:  # reads an API key or secret from a local text file
    if not path_value:
        return ""
    pth = Path(path_value)
    if not pth.is_absolute():
        pth = _project_root_for_meta() / pth
    try:
        if not pth.is_file():
            return ""
        for line in pth.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#") and "PASTE_" not in clean:
                return clean
    except Exception:
        return ""
    return ""
def _openai_chat_cfg(settings: Optional[dict]) -> Dict[str, Any]:  # reads OpenAI metadata-enhancer settings
    cfg = _settings_flag(settings, ["openai_meta"], {})
    return cfg if isinstance(cfg, dict) else {}
def _openai_chat_api_key(settings: Optional[dict]) -> str:  # finds the OpenAI metadata key from env or key file
    cfg = _openai_chat_cfg(settings)
    env_name = str(cfg.get("api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY").strip()
    key = (os.getenv(env_name) or "").strip()
    if key:
        return key
    key_file = str(cfg.get("api_key_file", "config/openai_api_key.txt") or "config/openai_api_key.txt").strip()
    return _read_text_file_secret(key_file)
def _openai_chat_model_name(settings: Optional[dict]) -> str:  # returns the OpenAI metadata model name
    cfg = _openai_chat_cfg(settings)
    return str(cfg.get("model", "gpt-4o-mini") or "gpt-4o-mini").strip()
def _is_openai_chat_meta_enabled(settings: Optional[dict]) -> bool:  # checks whether OpenAI metadata enhancement is enabled
    cfg = _openai_chat_cfg(settings)
    return bool(cfg.get("enabled", True))
def _strip_markdown_noise(text_value: str) -> str:  # removes markdown/fence characters from model-generated metadata
    s = str(text_value or "").strip()
    s = s.replace("**", "").replace("__", "").replace("*", "")
    s = s.replace("```json", "").replace("```", "")
    s = re.sub(r"^[>\- \t]+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\s+", " ", s).strip() if "\n" not in s else re.sub(r"[ \t]+", " ", s).strip()
    return s
def _normalize_hashtag(tag: str) -> str:  # converts raw hashtag text into a clean #tag value
    s = _norm(tag)
    s = s.replace("#", "")
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = re.sub(r"\s+", "", s)
    if not s:
        return ""
    return "#" + s[:32]
def _hashtags_from_any(*, description: str, hits: List[Tuple[str, float]], platform: str, lang: str, limit: int = 18) -> List[str]:  # combines model, preset, and keyword hashtags without duplicates
    tags: List[str] = []
    for raw in re.findall(r"#[A-Za-z0-9_]+", description or ""):
        tag = _normalize_hashtag(raw)
        if tag and tag not in tags:
            tags.append(tag)
    for raw in _preset_hashtags(platform, lang, hits) + _hashtags_from_hits(hits, max_tags=12):
        tag = _normalize_hashtag(raw)
        if tag and tag not in tags:
            tags.append(tag)
    vibe = _topic_vibe(hits, description)
    pads_by_vibe = {
        "funny": ["#shorts", "#viral", "#reels", "#funny", "#comedy", "#desicomedy", "#reaction", "#funnyshorts"],
        "meme": ["#shorts", "#viral", "#reels", "#meme", "#reaction", "#trending"],
        "business": ["#shorts", "#viral", "#business", "#marketing", "#growth", "#creator", "#sales"],
        "marketing": ["#shorts", "#viral", "#marketing", "#contentcreator", "#hooks", "#socialmedia", "#growth"],
        "educational": ["#shorts", "#learn", "#education", "#knowledge", "#explained", "#learning"],
        "tutorial": ["#shorts", "#tutorial", "#howto", "#learn", "#tips", "#guide"],
    }
    pads = pads_by_vibe.get(vibe, ["#shorts", "#viral", "#reels", "#contentcreator", "#learning", "#growth"])
    for raw in pads:
        if len(tags) >= limit:
            break
        tag = _normalize_hashtag(raw)
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:limit]
def _comma_hashtags(tags: List[str]) -> str:  # formats hashtags as comma-separated keywords
    return ", ".join(t.lstrip("#") for t in tags if t.strip())
def _remove_hashtag_only_lines(text_value: str) -> str:  # removes lines that contain only hashtags from descriptions
    lines: List[str] = []
    for line in str(text_value or "").splitlines():
        clean = line.strip()
        if not clean:
            lines.append("")
            continue
        parts = clean.split()
        hashtag_count = sum(1 for part in parts if part.startswith("#"))
        if parts and hashtag_count >= max(1, len(parts) - 1):
            continue
        lines.append(clean)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()
def _openai_chat_enhance_meta(  # uses OpenAI Chat Completions to improve metadata while keeping local fallback
    *,
    title: str,
    hooks: List[str],
    description: str,
    segment_text: str,
    lang: str,
    platform: str,
    hits: List[Tuple[str, float]],
    settings: Optional[dict],
) -> Dict[str, Any]:
    api_key = _openai_chat_api_key(settings)
    if not api_key:
        if _meta_debug(settings):
            print("[meta-openai] SKIP: API key missing. Add it to config/openai_api_key.txt or OPENAI_API_KEY.")
        return {"title": title, "hooks": hooks, "description": description}

    model = _openai_chat_model_name(settings)
    lang_rule = "Write in Roman Urdu/Hindi using English letters only." if lang == "roman" else "Write in natural English."
    hits_str = ", ".join([k for k, _ in hits][:8])
    profile = _metadata_content_profile(segment_text=segment_text, hits=hits, lang=lang, settings=settings)
    profile_json = json.dumps(profile, ensure_ascii=False)

    prompt = f"""
Create short-form social media metadata for {platform}.

Rules:
- {lang_rule}
- Return only valid JSON. No markdown, no asterisks, no bullets outside JSON.
- Keep text simple, human, creator-friendly, and specific to the segment.
- Follow this content profile exactly: {profile_json}
- Tone must match content_profile.tone and content_profile.category.
- {profile["forbidden"]}
- If the category is funny or meme, use comedy/reaction/punchline language, not pain/sadness.
- Title max 70 characters.
- Give exactly 5 hooks, each max 80 characters.
- Description must be 3 short plain-text lines plus 1 CTA line.
- Do not use bold markdown. Do not include ** or * anywhere.
- Create 15 to 20 relevant hashtags with #.
- Keywords to consider only if relevant: {hits_str}

Segment text:
{segment_text}

Return JSON exactly like this:
{{"title":"...","hooks":["...","...","...","...","..."],"description":"line 1\nline 2\nline 3\nCTA line","hashtags":["#tag1","#tag2"]}}
""".strip()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You create clean short-form metadata from transcript and style context. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
        body = json.loads(raw_body)
        raw = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        json_text = _repair_json_text(_extract_json_from_text(raw))
        data = json.loads(json_text)

        new_title = _strip_markdown_noise(data.get("title", "")) or title
        if len(new_title) > 70:
            new_title = new_title[:70].rstrip()

        new_hooks_raw = data.get("hooks", hooks)
        if not isinstance(new_hooks_raw, list):
            new_hooks_raw = hooks
        new_hooks = [_strip_markdown_noise(x) for x in new_hooks_raw if _strip_markdown_noise(x)]
        new_hooks = (new_hooks + hooks)[:5]

        new_desc = str(data.get("description", "") or "").strip() or description
        new_desc = "\n".join(_strip_markdown_noise(line) for line in new_desc.splitlines() if _strip_markdown_noise(line))

        llm_tags = []
        if isinstance(data.get("hashtags"), list):
            for item in data.get("hashtags", []):
                tag = _normalize_hashtag(str(item))
                if tag and tag not in llm_tags:
                    llm_tags.append(tag)

        final_tags = []
        for tag in llm_tags + _hashtags_from_any(description=new_desc, hits=hits, platform=platform, lang=lang, limit=20):
            if tag not in final_tags:
                final_tags.append(tag)
        final_tags = final_tags[:20]

        if final_tags:
            new_desc = new_desc.rstrip() + "\n\n" + " ".join(final_tags)

        new_desc = _ensure_desc_structure(new_desc, platform=platform, lang=lang, hits=hits, settings=settings)
        return {"title": new_title, "hooks": new_hooks, "description": new_desc}

    except Exception as e:
        if _meta_debug(settings):
            print(f"[meta-openai] FAIL: {e}")
        return {"title": title, "hooks": hooks, "description": description}


# -------------------------
# OpenAI enhancer (PAID ONLY, SAFE FALLBACK)
# -------------------------
def _settings_flag(settings: Optional[dict], path: List[str], default: Any = None) -> Any:  # reads nested settings flags safely with a default value
    cur: Any = settings or {}
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur
def _meta_debug(settings: Optional[dict]) -> bool:  # checks whether metadata debug logging is enabled
    return bool(_settings_flag(settings, ["ai_features", "meta_debug"], False))
def _is_direct_ai_meta_enabled(settings: Optional[dict]) -> bool:  # checks whether direct OpenAI metadata mode is allowed
    enabled = bool(_settings_flag(settings, ["ai_features", "enabled"], False))
    enhance_meta = bool(_settings_flag(settings, ["ai_features", "enhance_meta"], False))
    allow_local = bool(_settings_flag(settings, ["ai_features", "allow_local_openai_direct"], False))
    return enabled and enhance_meta and allow_local
def _openai_api_key_from_env(settings: Optional[dict]) -> str:  # reads the OpenAI API key from the configured environment variable
    env_name = str(
        _settings_flag(settings, ["ai_features", "openai_api_key_env"], "OPENAI_API_KEY") or "OPENAI_API_KEY"
    ).strip()
    return (os.getenv(env_name) or "").strip()
def _openai_model_name(settings: Optional[dict]) -> str:  # returns the OpenAI metadata model for direct SDK calls
    return str(
        _settings_flag(settings, ["ai_features", "openai_model_meta"], "gpt-4o-mini") or "gpt-4o-mini"
    ).strip()
def _extract_json_from_text(raw: str) -> str:  # extracts the JSON object from raw model output
    """
    Robust JSON extractor:
    - removes ``` fences
    - extracts first {...} object
    - trims trailing junk after last }
    """
    if not raw:
        return ""

    s = raw.strip()

    # remove fences
    s = re.sub(r"^\s*```(?:json)?\s*", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\s*```\s*$", "", s).strip()
    s = s.replace("```", "").strip()

    # pick first json object
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m:
        return s

    obj = m.group(0).strip()

    # trim anything after last }
    last = obj.rfind("}")
    if last != -1:
        obj = obj[: last + 1]

    return obj
def _repair_json_text(s: str) -> str:  # fixes common JSON formatting issues from model responses
    """
    Try to repair common model JSON issues:
    - smart quotes â†’ normal quotes
    - trailing commas
    - stray control chars
    """
    if not s:
        return ""

    # smart quotes â†’ standard
    s = s.replace("â€œ", '"').replace("â€", '"').replace("â€™", "'").replace("â€˜", "'")

    # remove BOM / weird chars
    s = s.replace("\ufeff", "").strip()

    # remove trailing commas before } or ]
    s = re.sub(r",\s*}", "}", s)
    s = re.sub(r",\s*]", "]", s)

    return s.strip()
def _ensure_desc_structure(desc: str, *, platform: str, lang: str, hits: List[Tuple[str, float]], settings: Optional[dict]) -> str:  # forces descriptions into body lines, CTA, and hashtags
    """Normalize description into 3 body lines, one CTA, and hashtags."""
    desc = _strip_markdown_noise(desc or "")

    lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]

    hash_line_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if "#" in lines[i]:
            hash_line_idx = i
            break

    if hash_line_idx is not None:
        body_lines = lines[:hash_line_idx]
    else:
        body_lines = lines

    cta_line = ""
    new_body: List[str] = []
    cta_words = ("save", "share", "comment", "follow", "watch", "try")
    for ln in body_lines:
        clean = _strip_markdown_noise(ln).lstrip("?").strip()
        low = _norm(clean)
        is_cta = any(low.startswith(word + " ") for word in cta_words) or any(word in low for word in ("save this", "share this", "comment below", "follow for"))
        if is_cta and not cta_line:
            cta_line = clean
        else:
            new_body.append(clean)
    body_lines = [ln for ln in new_body if ln]

    profile = _metadata_content_profile(segment_text=desc, hits=hits, lang=lang, settings=settings)
    vibe = str(profile.get("category", "general") or "general")
    if len(body_lines) == 0:
        body_lines = [
            "Yeh clip ka best moment hai.",
            "Scene natural, quick aur watchable rakha gaya hai.",
            "End tak dekho, punchline ya point wahi clear hota hai.",
        ] if lang == "roman" else [
            "This is the strongest moment from the clip.",
            "The edit keeps the scene quick and easy to follow.",
            "Watch the moment through for the real point.",
        ]
    elif len(body_lines) == 1:
        if vibe == "funny" and lang == "roman":
            extra = ["Comedy timing aur reaction is clip ka main maza hai.", "Punchline aur reaction dono clip ko memorable banate hain."]
        elif vibe == "funny":
            extra = ["The timing and reaction make this moment work.", "The punchline keeps the scene memorable."]
        elif lang == "roman":
            extra = ["Isi moment ka context clip ko strong banata hai.", "End tak dekho taake point clear ho."]
        else:
            extra = ["This moment carries the main context.", "Watch it through so the point lands clearly."]
        body_lines = [body_lines[0], *extra]
    elif len(body_lines) == 2:
        body_lines = [
            body_lines[0],
            body_lines[1],
            "Comedy timing yahan sabse strong hai." if vibe == "funny" and lang == "roman" else "The timing makes this clip stand out." if vibe == "funny" else "Yahi moment clip ko yaadgar banata hai." if lang == "roman" else "This is the moment that makes the clip memorable.",
        ]

    body_lines = [_strip_markdown_noise(ln) for ln in body_lines[:3]]

    if not cta_line:
        cta_line = "Save this and share it with someone who needs it."

    limit = max(15, min(_platform_tag_limit(platform), 20))
    tags = _hashtags_from_any(description=desc, hits=hits, platform=platform, lang=lang, limit=limit)
    hashtags_line = " ".join(tags).strip()

    return "\n".join([
        body_lines[0],
        body_lines[1],
        body_lines[2],
        "",
        _strip_markdown_noise(cta_line),
        "",
        hashtags_line,
    ]).strip()
def _openai_enhance_meta(  # uses the OpenAI SDK to improve metadata in direct mode
    *,
    title: str,
    hooks: List[str],
    description: str,
    segment_text: str,
    lang: str,
    platform: str,
    hits: List[Tuple[str, float]],
    settings: Optional[dict],
) -> Dict[str, Any]:
    api_key = _openai_api_key_from_env(settings)
    if not api_key:
        if _meta_debug(settings):
            env_name = _settings_flag(settings, ["ai_features", "openai_api_key_env"], "OPENAI_API_KEY")
            print(f"[meta-ai] SKIP: API key not found in env '{env_name}'")
        return {"title": title, "hooks": hooks, "description": description}

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        if _meta_debug(settings):
            print(f"[meta-ai] SKIP: openai import failed: {e}")
        return {"title": title, "hooks": hooks, "description": description}

    model = _openai_model_name(settings)

    if lang == "roman":
        lang_rule = "Write in Roman Urdu/Hindi (English letters). Do NOT use Urdu/Hindi script."
    else:
        lang_rule = "Write in natural English."

    hits_list = [k for k, _ in hits][:8]
    hits_str = ", ".join(hits_list)
    profile = _metadata_content_profile(segment_text=segment_text, hits=hits, lang=lang, settings=settings)
    profile_json = json.dumps(profile, ensure_ascii=False)

    # strict json output
    # âœ… description: 3 body lines + CTA + 15â€“20 tags
    prompt = f"""
You are optimizing short-form social metadata for {platform}.

Rules:
- {lang_rule}
- MUST relate to the given segment text (same meaning/vibe), but DO NOT copy exact phrases.
- Be specific to the topic of the segment (not generic).
- Follow this content profile exactly: {profile_json}
- Tone must match content_profile.tone and content_profile.category.
- {profile["forbidden"]}
- If the category is funny or meme, use comedy/reaction/punchline language, not pain/sadness.
- Title max 70 chars.
- Hooks: EXACTLY 5 options, each max 80 chars, distinct, high-retention.
- Description MUST be:
  Line1: emojis + sentence (topic summary)
  Line2: deeper context/detail (same topic)
  Line3: takeaway / reassurance (same topic)
  Line4: âœ… CTA (save/share/comment)
  Line5: 15â€“20 platform-relevant hashtags (space-separated)
- Keywords to use ONLY if relevant: {hits_str}
- Return ONLY a JSON object. No backticks. No markdown. No extra text.

Segment text:
{segment_text}

Current draft:
TITLE: {title}
HOOKS: {hooks}
DESCRIPTION:
{description}

Return JSON like:
{{"title":"...","hooks":["...","...","...","...","..."],"description":"..."}}
""".strip()

    try:
        if _meta_debug(settings):
            print(f"[meta-ai] RUN: model={model} platform={platform} lang={lang}")

        client = OpenAI(api_key=api_key)

        # âœ… Try to force JSON mode when supported
        try:
            resp = client.responses.create(
                model=model,
                input=prompt,
                response_format={"type": "json_object"},
            )
        except TypeError:
            # older SDK / models without response_format
            resp = client.responses.create(model=model, input=prompt)

        raw = (resp.output_text or "").strip()

        if _meta_debug(settings):
            print("[meta-ai] RAW:", raw[:220].replace("\n", " ") + ("..." if len(raw) > 220 else ""))

        # --- robust JSON parse with repair ---
        json_text = _extract_json_from_text(raw)
        json_text = _repair_json_text(json_text)

        try:
            data = json.loads(json_text)
        except Exception:
            # second attempt on fully repaired raw
            json_text2 = _extract_json_from_text(_repair_json_text(raw))
            try:
                data = json.loads(json_text2)
            except Exception as e2:
                if _meta_debug(settings):
                    print(f"[meta-ai] PARSE FAIL: {e2}")
                return {"title": title, "hooks": hooks, "description": description}

        new_title = str(data.get("title", "") or "").strip() or title
        new_hooks = data.get("hooks", hooks)

        if not isinstance(new_hooks, list):
            new_hooks = hooks

        new_hooks = [str(x).strip() for x in new_hooks if str(x).strip()]
        if len(new_hooks) < 5:
            new_hooks = (new_hooks + hooks)[:5]
        else:
            new_hooks = new_hooks[:5]

        new_desc = str(data.get("description", "") or "").strip() or description

        # enforce structure + hashtags count
        new_desc = _ensure_desc_structure(new_desc, platform=platform, lang=lang, hits=hits, settings=settings)

        if len(new_title) > 70:
            new_title = new_title[:70].rstrip()

        # anti-copy soft check: if first 10 words from segment appear, fallback to structured version from draft
        seg_tokens = _norm(segment_text).split()
        if len(seg_tokens) >= 12:
            first10 = " ".join(seg_tokens[:10])
            if first10 and first10 in _norm(new_desc):
                # rebuild from draft but structured + tags
                new_desc = _ensure_desc_structure(description, platform=platform, lang=lang, hits=hits, settings=settings)

        return {"title": new_title, "hooks": new_hooks, "description": new_desc}

    except Exception as e:
        if _meta_debug(settings):
            print(f"[meta-ai] FAIL: {e}")
        return {"title": title, "hooks": hooks, "description": description}
def generate_hooks_titles_description(  # creates title, hook, description, and hashtag drafts for a clip
    segment_text: str,
    hits: List[Tuple[str, float]],
    lang: str,
    platform: str,
    max_hooks: int = 5,
    settings: Optional[dict] = None,
) -> Dict[str, Any]:
    segment_text = _collapse_repeated_text(segment_text)
    profile = _metadata_content_profile(segment_text=segment_text, hits=hits, lang=lang, settings=settings)
    vibe = str(profile.get("category", "general") or "general")
    tpl = _templates(lang)
    best_kw = _best_keyword(hits)

    roman_bank = {
        "funny": {
            "title": "Mazay Ka Scene - Timing Dekho",
            "hooks": ["Yeh scene miss mat karna.", "Comedy timing yahan zabardast hai.", "End tak dekho, maza yahin hai.", "Is reaction pe hansi aa jaye gi.", "Dost ko tag karo jisay yeh funny lage."],
            "seed": "Yeh comedy clip ka funny moment hai. Reaction aur timing is scene ko mazaydar banate hain.",
            "cta": "Share karo agar yeh scene funny laga.",
        },
        "business": {
            "title": "Business Growth Ka Real Point",
            "hooks": ["Yeh business point miss mat karna.", "Growth ke liye yeh baat zaroori hai.", "Clients aur sales ka real lesson yahan hai.", "Is strategy ko save kar lo.", "Agar business grow karna hai to yeh dekho."],
            "seed": "Yeh clip business growth aur strategy ka useful point clear karti hai.",
            "cta": "Save kar lo aur next idea ke liye follow karo.",
        },
        "marketing": {
            "title": "Marketing Ka Strong Hook",
            "hooks": ["Yeh marketing hook kaam aa sakta hai.", "Audience attention yahin se pakarti hai.", "Is point ko content mein apply karo.", "Sales aur reach ke liye yeh dekho.", "Creator growth ka yeh useful moment hai."],
            "seed": "Yeh clip marketing, hooks aur audience attention ka practical point deti hai.",
            "cta": "Save karo aur apni next video mein try karo.",
        },
        "educational": {
            "title": "Yeh Concept Asan Ho Gaya",
            "hooks": ["Yeh concept simple tareeqe se samjho.", "Is example se point clear hota hai.", "Seekhne wali baat yahan hai.", "End tak dekho taake idea clear ho.", "Is lesson ko save kar lo."],
            "seed": "Yeh clip ek useful concept ko simple aur clear tareeqe se explain karti hai.",
            "cta": "Helpful lage to save aur share karo.",
        },
        "tutorial": {
            "title": "Is Step Ko Follow Karo",
            "hooks": ["Yeh step miss mat karna.", "Kaam asan karne ka tareeqa yeh hai.", "Is process ko follow karo.", "Beginner ke liye yeh useful hai.", "Save kar lo taake baad mein dekh sako."],
            "seed": "Yeh clip process ka useful step explain karti hai jo follow karna asan hai.",
            "cta": "Save karo aur try kar ke dekho.",
        },
        "emotional": {
            "title": "Dil Ko Lag Jane Wala Moment",
            "hooks": ["Yeh moment feel hota hai.", "Is scene ki baat dil ko lagti hai.", "End tak dekho, emotion yahin hai.", "Yeh line yaad reh jaye gi.", "Agar relate karte ho to share karo."],
            "seed": "Yeh clip ek emotional moment ko simple aur relatable tareeqe se dikhati hai.",
            "cta": "Agar relate kiya to share karna.",
        },
    }
    english_bank = {
        "funny": {
            "title": "Funny Moment - Perfect Timing",
            "hooks": ["Do not miss this moment.", "The comedy timing makes this clip.", "Watch till the end for the payoff.", "This reaction is the whole joke.", "Send this to someone who loves comedy."],
            "seed": "This comedy clip works because of the reaction and timing.",
            "cta": "Share this if the scene made you laugh.",
        },
        "business": {
            "title": "Business Growth Lesson",
            "hooks": ["This business point is worth saving.", "Here is the practical growth lesson.", "This is how creators think about clients.", "Save this strategy for later.", "Watch this before your next business move."],
            "seed": "This clip highlights a practical business growth lesson from the segment.",
            "cta": "Save this and share it with a creator or founder.",
        },
        "marketing": {
            "title": "Marketing Hook That Works",
            "hooks": ["This hook can improve your content.", "Audience attention starts here.", "Use this idea in your next post.", "This is a useful marketing moment.", "Creators should save this one."],
            "seed": "This clip focuses on marketing, hooks, and audience attention.",
            "cta": "Save this and try it in your next video.",
        },
        "educational": {
            "title": "Simple Lesson Explained",
            "hooks": ["This makes the concept easier.", "The example explains the whole point.", "Save this lesson for later.", "Watch this if you want clarity.", "This is the useful part of the clip."],
            "seed": "This clip explains a useful idea in a simple and clear way.",
            "cta": "Save this if it helped you understand the point.",
        },
        "tutorial": {
            "title": "Follow This Simple Step",
            "hooks": ["Do not skip this step.", "This makes the process easier.", "Follow this if you are starting out.", "Save this quick walkthrough.", "Try this in your next project."],
            "seed": "This clip shows a practical step that is easy to follow.",
            "cta": "Save this and try it yourself.",
        },
        "emotional": {
            "title": "Emotional Moment That Hits",
            "hooks": ["This moment feels real.", "The story lands right here.", "Watch till the emotion hits.", "This line stays with you.", "Share this if you relate."],
            "seed": "This clip captures an emotional and relatable moment from the story.",
            "cta": "Share this with someone who will relate.",
        },
    }

    bank = roman_bank if lang == "roman" else english_bank
    alias = {
        "meme": "funny",
        "news": "educational",
        "podcast": "educational",
        "documentary": "educational",
        "sad": "emotional",
        "romantic": "emotional",
        "love": "emotional",
        "motivational": "business",
        "gaming": "funny",
        "horror": "emotional",
        "lifestyle": "educational",
        "fitness": "motivational",
        "cinematic": "emotional",
    }
    selected = bank.get(vibe) or bank.get(alias.get(vibe, ""))
    if selected is None:
        selected = {
            "title": tpl["titles"][0],
            "hooks": tpl["hooks"],
            "seed": segment_text,
            "cta": tpl["cta"][0],
        }

    hooks: List[str] = []
    if best_kw and vibe not in {"funny", "meme", "emotional"}:
        if lang == "roman":
            hooks.extend([
                f"{best_kw.title()} ka real point yeh hai.",
                f"{best_kw.title()} wali baat miss mat karna.",
            ])
        else:
            hooks.extend([
                f"Here is the real point about {best_kw}.",
                f"Do not miss this {best_kw} moment.",
            ])
    hooks.extend(selected["hooks"])

    seen = set()
    uniq_hooks: List[str] = []
    for h in hooks:
        clean = _strip_markdown_noise(str(h))
        hh = _norm(clean)
        if not clean or hh in seen:
            continue
        seen.add(hh)
        uniq_hooks.append(clean)
        if len(uniq_hooks) >= max_hooks:
            break

    title = str(selected["title"])
    if best_kw and vibe in {"business", "marketing", "educational", "tutorial"}:
        title = f"{best_kw.title()} - {title}"[:70].rstrip()

    description = _build_description(
        segment_text=str(selected.get("seed") or segment_text),
        lang=lang,
        cta=str(selected.get("cta") or tpl["cta"][0]),
        hits=hits,
        platform=platform,
        max_sentences=3,
    )
    description = _ensure_desc_structure(description, platform=platform, lang=lang, hits=hits, settings=settings)

    out = {"hooks": uniq_hooks, "title": title[:70].rstrip(), "description": description}

    if _is_openai_chat_meta_enabled(settings):
        improved = _openai_chat_enhance_meta(
            title=out["title"],
            hooks=out["hooks"],
            description=out["description"],
            segment_text=segment_text,
            lang=lang,
            platform=platform,
            hits=hits,
            settings=settings,
        )
        out.update(improved)
    elif _is_direct_ai_meta_enabled(settings):
        improved = _openai_enhance_meta(
            title=out["title"],
            hooks=out["hooks"],
            description=out["description"],
            segment_text=segment_text,
            lang=lang,
            platform=platform,
            hits=hits,
            settings=settings,
        )
        out.update(improved)
    else:
        if _meta_debug(settings):
            enabled = _settings_flag(settings, ["ai_features", "enabled"], False)
            enhance = _settings_flag(settings, ["ai_features", "enhance_meta"], False)
            allow_local = _settings_flag(settings, ["ai_features", "allow_local_openai_direct"], False)
            print(f"[meta-ai] OFF: enabled={enabled} enhance_meta={enhance} allow_local={allow_local}")

    return out

def write_meta_txt(  # writes the metadata text file for one generated short
    out_path: Path,
    title: str,
    hooks: List[str],
    description: str,
    start: float,
    end: float,
    keyword_hits_list: List[Tuple[str, float]],
    platform: str,
    lang: str,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    lines.append("TITLE:")
    lines.append(title.strip())
    lines.append("")
    lines.append("HOOK OPTIONS:")
    for h in hooks:
        lines.append(f"- {h.strip()}")
    lines.append("")
    clean_description = _strip_markdown_noise(description.strip())
    tags = _hashtags_from_any(
        description=clean_description,
        hits=keyword_hits_list,
        platform=platform,
        lang=lang,
        limit=20,
    )

    display_description = _remove_hashtag_only_lines(clean_description)

    lines.append("DESCRIPTION:")
    lines.append(display_description)
    lines.append("")
    lines.append("HASHTAGS:")
    lines.append(" ".join(tags))
    lines.append("")
    lines.append("HASHTAGS COMMA:")
    lines.append(_comma_hashtags(tags))
    lines.append("")
    lines.append("META:")
    lines.append(f"- platform: {platform}")
    lines.append(f"- lang: {lang}")
    lines.append("")
    lines.append("CLIP RANGE:")
    lines.append(f"- start: {start:.3f}s")
    lines.append(f"- end:   {end:.3f}s")
    lines.append("")
    lines.append("KEYWORDS HIT:")
    if keyword_hits_list:
        for k, w in keyword_hits_list:
            lines.append(f"- {k} ({w:g})")
    else:
        lines.append("- (none)")

    out_path.write_text("\n".join(lines), encoding="utf-8")


















