from __future__ import annotations  # enables future Python language features
import re  # matches and cleans text with regular expressions
from typing import List  # adds type hint helpers
def text_for_range(whisper_result: dict, start: float, end: float) -> str:# handles text for range behavior
    """
    Build text from whisper segments that overlap [start, end].
    Safe fallback for manual / simple_auto segments.
    """
    if not isinstance(whisper_result, dict):
        return ""

    parts: List[str] = []
    for seg in (whisper_result.get("segments") or []) or []:
        if not isinstance(seg, dict):
            continue

        ss = float(seg.get("start", 0.0) or 0.0)
        ee = float(seg.get("end", 0.0) or 0.0)

        if ee <= start:
            continue
        if ss >= end:
            break

        txt = (seg.get("text") or "").strip()
        if txt:
            parts.append(txt)

    out = " ".join(parts).strip()
    out = re.sub(r"\s+", " ", out)
    return out


# ------------------------------------------------------------
# Literal Romanization (Urdu / Hindi script → Roman)
# ------------------------------------------------------------

# Unicode ranges
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")      # Urdu / Arabic script
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")  # Hindi script


# Basic Urdu chars mapping → Roman
_URDU_ROMAN_MAP = {
    "ا": "a",
    "آ": "aa",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ٹ": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ڈ": "d",
    "ذ": "z",
    "ر": "r",
    "ڑ": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "q",
    "ک": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "و": "w",
    "ہ": "h",
    "ھ": "h",
    "ء": "",
    "ی": "y",
    "ۍ": "y",
    "ے": "e",
    "ۃ": "h",
    "ۂ": "h",
    "ں": "n",      # noon ghunna

    # extra hamza/ya variants
    "ؤ": "o",
    "ئ": "i",
    "ۓ": "e",

    # Urdu punctuation → ASCII
    "،": ",",
    "۔": ".",
    "؟": "?",

    # Eastern Arabic digits → ASCII digits
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
}


# VERY small Devanagari map (agar Hindi script aaye)
_DEVANAGARI_ROMAN_MAP = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ii",
    "उ": "u",
    "ऊ": "oo",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",

    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
}
def _romanize_urdu_char(ch: str) -> str:# converts urdu char text into Roman letters
    """Single Urdu/Arabic char → Roman (fallback: char itself)."""
    return _URDU_ROMAN_MAP.get(ch, ch)
def _romanize_devanagari_char(ch: str) -> str:# converts devanagari char text into Roman letters
    """Single Devanagari char → Roman (fallback: char itself)."""
    return _DEVANAGARI_ROMAN_MAP.get(ch, ch)
def literal_romanize(text: str) -> str:# converts literal romanize text into Roman letters
    """
    VERY literal char-level Romanization.

    Rules:
      - Urdu / Arabic script chars → Roman (char map)
      - Basic Devanagari chars → Roman
      - English letters, digits, punctuation, emojis = EXACT as-is
    """
    if not text:
        return ""

    out_chars: List[str] = []
    for ch in text:
        # Urdu / Arabic
        if _ARABIC_RE.match(ch):
            out_chars.append(_romanize_urdu_char(ch))
        # Hindi script
        elif _DEVANAGARI_RE.match(ch):
            out_chars.append(_romanize_devanagari_char(ch))
        else:
            # English / spaces / punctuation / emojis 그대로
            out_chars.append(ch)

    out = "".join(out_chars)
    # Thori si whitespace normalize (multiple spaces -> single)
    out = re.sub(r"\s+", " ", out).strip()
    return out


# ------------------------------------------------------------
# Expanded Roman Urdu / Hinglish hints
# ------------------------------------------------------------

# ------------------------------------------------------------
# Expanded Roman Urdu / Hinglish hints
# ------------------------------------------------------------

_ROMAN_URDU_WORD_HINTS = {
    # Basic pronouns
    "aap", "ap", "tum", "tm", "hum", "mein", "me", "mai",
    "mujhe", "mujh", "mujhko", "ham", "unko", "inko",

    # Common question words
    "kya", "kia", "kyun", "kyu", "q", "kab", "kb", "kahan", "kaha",
    "kaise", "kaisay", "kesay", "kese",

    # Particles / short verbs
    "na", "mat", "kr", "kar", "karo", "krna", "krdo", "kardo",

    # Helping verbs
    "hai", "hain", "hu", "tha", "thi", "thay",
    "raha", "rahe", "rhi", "rhai",

    # Common fillers / slang
    "yar", "yaar", "bhai", "bhaiya", "bro",
    "scene", "masla", "set", "chill", "fikar", "tension",

    # Emotions / tone
    "sach", "such", "raaz", "ghalat", "ghalti",
    "barish", "thand", "nuksan", "faida",
    "zaroor", "bilkul", "bht", "bohat", "bahut",

    # Actions / verbs
    "dekho", "dekhein", "sun", "suno", "bana", "bnado",
    "leao", "lao", "dalo", "daal", "chalao", "chala",
    "chalu", "rok", "roko",

    # Daily use
    "sirf", "abhi", "ab", "kal", "aj", "aaj",
    "phir", "phle", "pehle", "baad", "baadmein",

    # Money / value
    "paisa", "paise", "kamai", "rupees", "rupay", "rs",

    # Ownership forms
    "wala", "wali", "walay",

    # Needs / intention
    "chahiye", "chahye", "chaye", "chahie",
    "zarorat", "zaroorat",

    # Hinglish / Bollywood style
    "timepass", "jugaad", "setting", "vibe",
    "jldi", "jaldi",
    "acha", "achha", "accha",
    "theek", "thik", "tik",

    # Short forms
    "plz", "pls", "haan", "han", "ha", "oky", "okey", "btw",
}

_ROMAN_URDU_PHRASE_HINTS = {
    "mat karo",
    "scene on",
    "scene off",
    "mujhe chahiye",
    "baad me",
}
def detect_lang_bucket(text: str, *, force_english: bool = False) -> str:  # chooses English or Roman metadata style from language/settings
    """
    Returns: 'en' or 'roman'
    (roman covers Roman Urdu/Hindi written in English letters)
    """
    if force_english or not text:
        return "en"

    t = text.lower()
    tokens = re.findall(r"[a-zA-Z']+", t)
    token_set = set(tokens)

    # word-level hits
    score = 0
    for h in _ROMAN_URDU_WORD_HINTS:
        if h in token_set:
            score += 1
            if score >= 2:
                return "roman"

    # phrase-level hits (these are strong signals, 1 is enough)
    for phrase in _ROMAN_URDU_PHRASE_HINTS:
        if phrase in t:
            return "roman"

    return "en"
