from __future__ import annotations  # enables future Python language features
import json  # handles JSON encode and decode
import difflib  # compares text sequences and close matches
from pathlib import Path  # provides object-oriented file paths
from typing import List, Tuple, Optional, Dict, Any  # adds type hint helpers
import subprocess  # runs external system commands
import re  # matches and cleans text with regular expressions
import random  # generates random choices and variation
import os  # works with environment variables and OS paths
import threading  # runs and coordinates threads
import urllib.request  # sends HTTP requests
import urllib.error  # handles HTTP/network exceptions
from concurrent.futures import ThreadPoolExecutor, as_completed  # runs thread/process worker pools
from openai import OpenAI  # calls OpenAI API models
from src.pipeline.text_utils import literal_romanize  # project text cleanup helpers
from src.services.music_engine import pick_music_track  # project music selector
from src.services.thumbnail_engine import create_thumbnail_for_short  # project thumbnail generator
from src.services.progress import set_progress  # project progress writer
from src.utils.ffmpeg import cut_clip, reframe_talking_head  # project FFmpeg helper
from src.pipeline.filters import get_filter_vf  # project filter presets
from src.utils.paths import p  # project path helper
from src.pipeline.generate_meta import (  # project metadata helpers
    load_keywords_weighted,
    keyword_hits,
    generate_hooks_titles_description,
    write_meta_txt,
)
from src.pipeline import make_ass  # project pipeline package


# =========================================================
# OpenAI client (shared)
# =========================================================
_openai_client: OpenAI | None = None
def _get_openai_client(settings: Dict[str, Any]) -> OpenAI:  # creates or reuses the OpenAI client using the configured API key
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    ai_cfg = (settings or {}).get("ai_features", {}) or {}
    llm_cfg = (settings or {}).get("openai_llm", {}) or {}
    env_key_name = str(ai_cfg.get("openai_api_key_env", llm_cfg.get("api_key_env", "OPENAI_API_KEY")) or "OPENAI_API_KEY")
    api_key = os.getenv(env_key_name, "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        key_file = str(ai_cfg.get("openai_api_key_file", llm_cfg.get("api_key_file", "config/openai_api_key.txt")) or "config/openai_api_key.txt")
        api_key = _read_secret_file(key_file)

    if api_key:
        _openai_client = OpenAI(api_key=api_key)
    else:
        _openai_client = OpenAI()

    return _openai_client



# =========================================================
# Roman caption dataset (clipforge_roman_caption_correction_200k.jsonl)
# =========================================================

_ROMAN_DATASET_CACHE: Dict[str, Dict[str, str]] | None = None
def _resolve_roman_dataset_path(settings: Dict[str, Any]) -> Optional[Path]:  # finds the Roman caption correction dataset path from settings or defaults
    """
    Settings override:
        settings:
          roman_dataset:
            path: "config/clipforge_roman_caption_correction_200k.jsonl"

    Default: config/clipforge_roman_caption_correction_200k.jsonl
    """

    cfg = (settings or {}).get("roman_dataset", {}) or {}
    cfg_path = str(cfg.get("path", "") or "").strip()

    candidates: list[Path] = []

    # 1) Explicit path from settings (absolute ya project-relative)
    if cfg_path:
        p_raw = Path(cfg_path)
        if p_raw.is_absolute():
            candidates.append(p_raw)
        else:
            parts = [part for part in cfg_path.replace("\\", "/").split("/") if part]
            candidates.append(p(*parts))

    # 2) Default under config/
    candidates.append(p("config", "clipforge_roman_caption_correction_200k.jsonl"))

    for c in candidates:
        try:
            if c.is_file():
                return c
        except Exception:
            continue
    return None
def _ensure_roman_dataset(settings: Dict[str, Any]) -> Dict[str, Dict[str, str]]:  # loads and caches the Roman caption correction dataset if it exists
    """
    Load JSONL dataset once and cache:

    Each line:
      { "english": "...", "urdu": "...", "roman_noisy": "...", "roman_clean": "..." }

    Returns dict with:
      {
        "noisy2clean": { "bghyr": "baghair", ... },
        "urdu2roman":  { "Ã˜Â¨Ã˜ÂºÃ›Å’Ã˜Â±": "baghair", ... },
        "en2roman":    { "practice": "practice", ... }  # rarely used
      }
    """
    global _ROMAN_DATASET_CACHE
    if _ROMAN_DATASET_CACHE is not None:
        return _ROMAN_DATASET_CACHE

    noisy2clean: Dict[str, str] = {}
    urdu2roman: Dict[str, str] = {}
    en2roman: Dict[str, str] = {}

    ds_path = _resolve_roman_dataset_path(settings)
    if ds_path is None:
        print("[WARN] Roman caption dataset path not found; running without dataset corrections.")
        _ROMAN_DATASET_CACHE = {
            "noisy2clean": noisy2clean,
            "urdu2roman": urdu2roman,
            "en2roman": en2roman,
        }
        return _ROMAN_DATASET_CACHE

    try:
        with ds_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue

                eng = str(row.get("english", "") or "").strip()
                urd = str(row.get("urdu", "") or "").strip()
                rc = str(row.get("roman_clean", "") or "").strip()
                rn = str(row.get("roman_noisy", "") or "").strip()

                eng_l = eng.lower()
                rc_l = rc.lower()
                rn_l = rn.lower()

                # noisy roman -> clean roman
                if rn_l and rc_l and rn_l != rc_l:
                    noisy2clean.setdefault(rn_l, rc_l)

                # Urdu script -> clean roman
                if urd and rc_l:
                    urdu2roman.setdefault(urd, rc_l)

                # English word -> clean roman (optional use)
                if eng_l and rc_l:
                    en2roman.setdefault(eng_l, rc_l)

        print(
            f"[INFO] Roman caption dataset loaded: "
            f"{len(noisy2clean)} noisy->clean, {len(urdu2roman)} urdu->roman entries"
        )

    except Exception as e:
        print(f"[WARN] Failed to load roman caption dataset: {e}")

    _ROMAN_DATASET_CACHE = {
        "noisy2clean": noisy2clean,
        "urdu2roman": urdu2roman,
        "en2roman": en2roman,
    }
    return _ROMAN_DATASET_CACHE


# =========================================================
# META Romanization (English Ã¢â€ â€™ Roman Urdu)
# =========================================================
def ai_romanize_text(text: str, settings: Dict[str, Any]) -> str:  # converts Urdu/Hindi or mixed text into clean Roman caption text
    """
    English -> Roman Urdu (plain text only) for META (title/description/hooks).

    STRICT:
      - Output ONLY Roman Urdu text
      - NO emojis, NO hashtags, NO quotes
      - Do NOT change punctuation (as much as model allows)
      - No extra lines

    After model output, we also pass through _rule_based_clean_roman
    + dataset corrections to normalize spellings.
    """
    if not text or not text.strip():
        return text

    ai_cfg = (settings or {}).get("ai_features", {}) or {}
    model = str(ai_cfg.get("openai_model_romanize", "gpt-4o-mini"))

    prompt = (
        "Convert the given English text into Roman Urdu.\n"
        "HARD RULES:\n"
        "1) Output ONLY the Roman Urdu text (no quotes, no markdown).\n"
        "2) No emojis, no hashtags, no extra commentary.\n"
        "3) Keep punctuation the SAME as input (do not add/remove/change punctuation).\n"
        "4) Keep spacing normal (single spaces).\n\n"
        f"INPUT:\n{text}\n\n"
        "OUTPUT:"
    )

    try:
        client = _get_openai_client(settings)
        resp = client.responses.create(
            model=model,
            input=prompt,
            temperature=0,
        )
        out = (resp.output_text or "").strip()

        # remove wrapping quotes if model disobeys
        if (out.startswith('"') and out.endswith('"')) or (out.startswith("'") and out.endswith("'")):
            out = out[1:-1].strip()

        if not out:
            out = text

    except Exception:
        # if model fails, fall back to original text (or later romanization)
        out = text

    # final cleanup: dataset + rule-based
    cleaned = _rule_based_clean_roman(out, settings)
    return cleaned or out


# =========================================================
# Rule-based Roman cleanup (used by captions + meta)
# =========================================================
def _rule_based_clean_roman(text: str, settings: Dict[str, Any] | None = None) -> str:  # applies local spelling and word-fix rules to Roman Urdu/Hindi text
    """
    Safe, non-AI cleanup + dataset:

      1) Baseline whitespace / sms short forms / common Roman Urdu fixes.
      2) clipforge_roman_caption_correction_200k.jsonl se:
         - direct roman_noisy -> roman_clean map
         - agar exact match na mile to difflib se closest noisy word pick.

      Final: ASCII-only output (no emojis / other scripts).
    """
    if not text or not text.strip():
        return text or ""

    settings = settings or {}
    ds = _ensure_roman_dataset(settings)
    noisy_map: Dict[str, str] = ds.get("noisy2clean", {}) or {}

    text = re.sub(r"\s+", " ", text).strip()

    SHORT_FORM_FIXES = {
        # pronouns / helpers
        "hm": "hum",
        "hum": "hum",
        "tm": "tum",
        "tum": "tum",
        "m": "mein",
        "me": "mein",
        "aj": "aaj",
        "aaj": "aaj",

        # kar-family
        "yeh": "yeh",
        "ye": "yeh",
        "mat": "mat",
        "karo": "karo",
        "kar": "kar",
        "kr": "kar",
        "kro": "karo",
        "krna": "karna",
        "krne": "karne",
        "krta": "karta",
        "krti": "kartii",
        "krte": "karte",

        # hai / hain variants
        "h": "hai",
        "hy": "hai",
        "he": "hai",
        "ha": "hai",
        "hyn": "hain",
        "hen": "hain",
        "hae": "hai",
        "hai": "hai",
    }

    ROMAN_URDU_FIXES = {
        "maslaa": "masla",
        "maslae": "masla",
        "masla": "masla",

        "zindgi": "zindagi",
        "zindagy": "zindagi",
        "zindagi": "zindagi",

        "fikar": "fikar",
        "tension": "tension",
        "sahi": "sahi",
        "sai": "sahi",
        "galat": "galat",
        "ghalat": "ghalat",
        "ghalti": "ghalti",
        "galti": "galti",
        "glt": "galat",

        "sykhne": "seekhne",
        "sekhne": "seekhne",
        "sekhnay": "seekhne",
        "seekhny": "seekhne",

        "bat": "baat",
        "baat": "baat",

        "bary": "bare",
        "barey": "bare",

        "myn": "mein",
        "mn": "mein",

        "milty": "milte",
        "milti": "milti",

        "boht": "bohat",
        "floww": "flow",
    }

    PUNJABI_WORDS = {
        "tusi": "tusi",
        "tussi": "tusi",
        "tuada": "tuada",
        "tuhada": "tuhada",
        "twada": "tuada",
        "sada": "sada",
        "saada": "sada",
        "menu": "menu",
        "mainu": "mainu",
        "tenu": "tenu",
        "tainu": "tainu",
        "onu": "onu",
        "ohnu": "ohnu",
        "kiven": "kiven",
        "kidda": "kidda",
        "kiddan": "kiddan",
        "changa": "changa",
        "changi": "changi",
        "changay": "changay",
        "gal": "gal",
        "gall": "gal",
        "gallan": "gallan",
        "karaan": "karaan",
        "karde": "karde",
        "kardi": "kardi",
        "karna": "karna",
        "aida": "aida",
        "edda": "edda",
        "enna": "enna",
        "jeda": "jeda",
        "jede": "jede",
        "jithe": "jithe",
        "othe": "othe",
        "ithe": "ithe",
        "pind": "pind",
        "veer": "veer",
        "pra": "pra",
        "yaar": "yaar",
        "rab": "rab",
        "rabb": "rab",
        "dil": "dil",
    }

    ENGLISH_FIXES = {
        "englash": "English",
        "angylsh": "English",
        "anglish": "English",
        "englsh": "English",
        "englis": "English",
        "english": "English",

        "prakts": "practice",
        "prykts": "practice",
        "prektis": "practice",
        "practis": "practice",

        "kanfydns": "confidence",
        "konfidens": "confidence",
        "sustem": "system",
        "systm": "system",
        "flw": "flow",
        "flo": "flow",

        "spwkng": "speaking",
        "spoking": "speaking",
        "spooking": "speaking",
        "spkng": "speaking",
        "spkn": "speaking",
    }

    PHRASE_FIXES = {
        "slow se follow": "slow se flow",
        "slow sy follow": "slow se flow",
        "slow se flo": "slow se flow",
    }

    lowered = text.lower()
    for bad, good in PHRASE_FIXES.items():
        if bad in lowered:
            lowered = lowered.replace(bad, good)

    tokens = lowered.split()
    cleaned_tokens: List[str] = []

    noisy_keys = list(noisy_map.keys()) if noisy_map else []

    for tok in tokens:
        # hashtags remove (#topic -> topic)
        if tok.startswith("#") and len(tok) > 1:
            tok = tok[1:]

        m = re.match(r"^([A-Za-z]+)([^A-Za-z]*)$", tok)
        if not m:
            cleaned_tokens.append(tok)
            continue

        root = m.group(1)
        suffix = m.group(2) or ""
        base = root.lower()
        fixed = base

        # 1) Hand-written rules first. These protect common Roman Urdu words
        # from noisy dataset mappings such as "mat" -> "maut".
        if base in SHORT_FORM_FIXES:
            fixed = SHORT_FORM_FIXES[base]
        elif base in ROMAN_URDU_FIXES:
            fixed = ROMAN_URDU_FIXES[base]
        elif base in PUNJABI_WORDS:
            # Punjabi words spoken inside Urdu/Hindi clips should stay Punjabi in Roman captions.
            fixed = PUNJABI_WORDS[base]
        elif base in ENGLISH_FIXES:
            fixed = ENGLISH_FIXES[base]

        # 2) Dataset: exact roman_noisy -> roman_clean
        elif base in noisy_map:
            fixed = noisy_map[base]

        # 3) Fuzzy match on dataset (for longer crazy spellings only)
        else:
            if len(base) >= 5 and noisy_keys:
                close = difflib.get_close_matches(base, noisy_keys, n=1, cutoff=0.92)
                if close:
                    fixed = noisy_map[close[0]]
                elif base == "k":
                    fixed = "ke"
                else:
                    fixed = base
            else:
                fixed = base if base != "k" else "ke"

        # preserve capitalization if pehla letter capital tha
        if root[0].isupper():
            fixed = fixed[:1].upper() + fixed[1:]

        cleaned_tokens.append(fixed + suffix)

    out = " ".join(cleaned_tokens)
    out = re.sub(r"\s+", " ", out).strip()

    # ASCII-only (remove emojis / non-latin)
    out = "".join(ch for ch in out if ord(ch) < 128)
    out = re.sub(r"\s+", " ", out).strip()

    return out


# ---------------------------------------------------------
# Auto-detect English-like tokens to preserve in AI cleanup
# ---------------------------------------------------------
def _auto_detect_english_tokens(line: str) -> set[str]:  # finds English words that should stay unchanged during Roman cleanup
    """
    Rough heuristic to detect English-ish words in a Roman Urdu + English line.
    Goal: catch words like English, system, practice, flow, best, app, update, etc.
    Precision does not need to be perfect; false positives are okay.
    """
    tokens = re.findall(r"[A-Za-z]+", line or "")
    result: set[str] = set()
    if not tokens:
        return result

    vowels = set("aeiou")

    # roman-urdu-ish patterns: if token contains these, we will likely skip as "Urdu"
    roman_substrings = (
        "kh", "gh", "sh", "bh", "ph", "aa", "ii", "uu",
        "allah", "insan", "zindag", "bohat", "bht", "aap",
        "tum", "mein", "hain", "hoon", "wala", "wali",
    )

    for tok in tokens:
        t = tok.lower()
        # very short tokens -> usually not English core words
        if len(t) < 3:
            continue

        # must contain at least one vowel
        if not (set(t) & vowels):
            continue

        # skip obvious roman-urdu patterns
        if any(pat in t for pat in roman_substrings):
            continue

        result.add(t)

    return result

# ---------------------------------------------------------
# Roman Engine v2 helpers: filler removal + line merge
# ---------------------------------------------------------
def _is_filler_line_v2(text: str) -> bool:  # detects filler/noise caption lines that should be hidden or merged
    """
    Lines that are basically just 'uh', 'umm', 'haan', 'hmm', etc.
    We can safely drop them from captions.
    """
    if not text or not text.strip():
        return True

    # remove punctuation for checking
    cleaned = re.sub(r"[^A-Za-z\s]", " ", text.lower())
    tokens = [t for t in cleaned.split() if t]

    if not tokens:
        return True

    FILLERS = {
        "uh", "uhh", "uhhh",
        "umm", "um", "mmm", "mm",
        "haan", "han", "hmm",
        "aaa", "aa", "huh",
        "acha", "achha", "accha",
    }

    # small lines which are mostly fillers
    if len(" ".join(tokens)) <= 18 and all(t in FILLERS for t in tokens):
        return True

    return False
def _merge_caption_lines_v2(  # merges tiny caption fragments into more natural subtitle lines
    cap_lines: List[Tuple[str, float, float]],
    *,
    max_gap_sec: float = 0.40,
    min_chars: int = 22,
) -> List[Tuple[str, float, float]]:
    """
    Roman Engine v2:
      - Remove filler-only lines (uh, hmm, haan...)
      - Merge very short lines into the previous line if close in time.
    """

    # 1) drop pure filler lines first
    filtered: List[Tuple[str, float, float]] = []
    for text, s_rel, e_rel in cap_lines:
        if _is_filler_line_v2(text):
            continue
        t = (text or "").strip()
        if not t:
            continue
        filtered.append((t, s_rel, e_rel))

    if not filtered:
        return []

    # 2) merge tiny lines into previous ones
    merged: List[Tuple[str, float, float]] = []
    cur_text, cur_start, cur_end = filtered[0]

    for text, s_rel, e_rel in filtered[1:]:
        gap = s_rel - cur_end
        cur_len = len(cur_text.strip())
        new_len = len(text.strip())

        # condition: lines close in time AND one of them is short
        if gap >= 0 and gap <= max_gap_sec and (cur_len < min_chars or new_len < min_chars):
            # merge into current
            cur_text = (cur_text.strip() + " " + text.strip()).strip()
            cur_end = e_rel
        else:
            merged.append((cur_text, cur_start, cur_end))
            cur_text, cur_start, cur_end = text, s_rel, e_rel

    # last one
    merged.append((cur_text, cur_start, cur_end))

    return merged
def _caption_repeat_key(text: str) -> str:  # normalizes a caption line for duplicate detection
    cleaned = re.sub(r"[^a-z0-9\s]+", "", str(text or "").lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned

def _collapse_repeated_caption_phrases(text: str) -> str:  # removes repeated word groups that make captions loop unnaturally
    tokens = str(text or "").split()
    if len(tokens) < 4:
        return str(text or "")

    def norm(tok: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", tok.lower())

    out: List[str] = []
    i = 0
    while i < len(tokens):
        collapsed = False
        max_n = min(6, (len(tokens) - i) // 2)
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
    cleaned = " ".join(out)
    return re.sub(r"\s+", " ", cleaned).strip()
def _cap_stale_caption_duration(text: str, start_rel: float, end_rel: float, settings: Dict[str, Any] | None = None) -> Tuple[float, float]:  # prevents short captions from staying on screen for an entire long Whisper segment
    cfg = ((settings or {}).get("captions", {}) or {}) if isinstance(settings, dict) else {}
    try:
        max_short = float(cfg.get("max_short_caption_duration_sec", 4.0) or 4.0)
    except Exception:
        max_short = 4.0
    try:
        max_long = float(cfg.get("max_caption_duration_sec", 6.5) or 6.5)
    except Exception:
        max_long = 6.5

    s = float(start_rel or 0.0)
    e = float(end_rel or 0.0)
    if e <= s:
        return s, e

    words = str(text or "").split()
    duration = e - s
    limit = max_short if len(words) <= 8 else max_long
    if duration > limit:
        e = s + limit
    return s, e
def preprocess_caption_lines_v2(  # cleans and merges caption lines before ASS/SRT rendering
    cap_lines: List[Tuple[str, float, float]],
    settings: Dict[str, Any] | None = None,
) -> List[Tuple[str, float, float]]:
    """
    High-level pre-process before Roman/English captions:

      - Drop pure filler noises.
      - Merge tiny broken lines into one more natural sentence.
      - Light whitespace cleanup per line.
    """
    merged = _merge_caption_lines_v2(cap_lines)

    cleaned: List[Tuple[str, float, float]] = []
    last_key = ""
    for text, s_rel, e_rel in merged:
        t = re.sub(r"\s+", " ", text or "").strip()
        t = _collapse_repeated_caption_phrases(t).strip()
        if not t:
            continue
        key = _caption_repeat_key(t)
        if key and key == last_key:
            continue
        s_rel, e_rel = _cap_stale_caption_duration(t, s_rel, e_rel, settings)
        if e_rel <= s_rel:
            continue
        cleaned.append((t, s_rel, e_rel))
        if key:
            last_key = key

    return cleaned
def _read_secret_file(path_value: str) -> str:  # reads the first non-comment secret value from a local key file
    path_value = str(path_value or "").strip()
    if not path_value:
        return ""
    try:
        path = Path(path_value)
        if not path.is_absolute():
            path = p(*[part for part in path_value.replace("\\", "/").split("/") if part])
        if not path.is_file():
            return ""
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                return clean
    except Exception:
        return ""
    return ""
def _openai_roman_cfg(settings: Dict[str, Any]) -> Dict[str, Any]:# opens openai roman cfg safely
    ai_cfg = (settings or {}).get("ai_features", {}) or {}
    roman_cfg = ai_cfg.get("openai_roman_captions", {}) if isinstance(ai_cfg, dict) else {}
    if not isinstance(roman_cfg, dict):
        roman_cfg = {}
    base_cfg = (settings or {}).get("openai_llm", {}) or {}
    if not isinstance(base_cfg, dict):
        base_cfg = {}
    return {
        "enabled": roman_cfg.get("enabled", True),
        "api_key_env": roman_cfg.get("api_key_env", base_cfg.get("api_key_env", "OPENAI_API_KEY")),
        "api_key_file": roman_cfg.get("api_key_file", base_cfg.get("api_key_file", "config/openai_api_key.txt")),
        "model": roman_cfg.get("model", base_cfg.get("model", "gpt-4o-mini")),
        "timeout_sec": roman_cfg.get("timeout_sec", 25),
    }
def _openai_roman_api_key(settings: Dict[str, Any]) -> str:# opens openai roman api key safely
    cfg = _openai_roman_cfg(settings)
    env_name = str(cfg.get("api_key_env", "OPENAI_API_KEY") or "OPENAI_API_KEY").strip()
    key = os.getenv(env_name, "").strip()
    if key:
        return key
    return _read_secret_file(str(cfg.get("api_key_file", "config/openai_api_key.txt") or "config/openai_api_key.txt"))
def _cleanup_one_line_ascii(text_value: str) -> str:  # removes noise and normalizes text/output
    out = str(text_value or "").strip()
    out = out.replace("\r", " ").replace("\n", " ")
    out = re.sub(r"^[\"'`]+|[\"'`]+$", "", out).strip()
    out = re.sub(r"\s+", " ", out).strip()
    out = "".join(ch for ch in out if ord(ch) < 128)
    out = re.sub(r"\s+", " ", out).strip()
    return out
def openai_cleanup_roman_captions(text: str, settings: Dict[str, Any]) -> str:  # uses OpenAI to polish one subtitle line into natural Roman Urdu/Hindi
    if isinstance(settings, dict) and settings.get("_openai_roman_disabled"):
        return ""
    cfg = _openai_roman_cfg(settings)
    if not bool(cfg.get("enabled", True)):
        return ""

    api_key = _openai_roman_api_key(settings)
    if not api_key:
        return ""

    line = str(text or "").strip()
    if not line:
        return ""

    model = str(cfg.get("model", "gpt-4o-mini") or "gpt-4o-mini").strip()
    timeout_sec = float(cfg.get("timeout_sec", 25) or 25)
    prompt = f"""
Convert this subtitle line into clean, natural Roman Urdu/Hindi for short-form video captions.

Rules:
- Keep the meaning exactly the same.
- Fix spelling and awkward romanization.
- Keep English words as English.
- Preserve Punjabi words exactly in Roman form when spoken, such as tusi, menu, kiven, changa, gal, pind, veer; do not translate them into Urdu/Hindi.
- If the line is mixed Urdu/Hindi/Punjabi, keep the same mixed-language meaning and natural local wording.
- Use only ASCII letters, numbers, spaces, and basic punctuation.
- No Urdu/Hindi script.
- No emojis, no hashtags, no quotes, no markdown.
- Output exactly one caption line.

Subtitle line:
{line}
""".strip()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You clean Urdu/Hindi/Punjabi mixed subtitles into natural Roman local-language captions. Preserve Punjabi words in Roman form. Return one plain line only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 120,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ClipForgeAI/1.0 (+roman-captions)",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw_body)
        out = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        out = _cleanup_one_line_ascii(out)
        if not out:
            return ""
        return _rule_based_clean_roman(out, settings)
    except urllib.error.HTTPError as e:
        if isinstance(settings, dict) and e.code in (401, 403, 429):
            settings["_openai_roman_disabled"] = True
        print(f"[roman-openai] skipped: HTTP {e.code}", flush=True)
    except urllib.error.URLError as e:
        if isinstance(settings, dict):
            settings["_openai_roman_disabled"] = True
        print(f"[roman-openai] skipped: network unavailable ({e.reason})", flush=True)
    except Exception as e:
        if isinstance(settings, dict):
            settings["_openai_roman_disabled"] = True
        print(f"[roman-openai] skipped: {e}", flush=True)
    return ""

# =========================================================
# Roman caption cleanup (Urdu/Hindi audio Ã¢â€ â€™ Roman captions)
# =========================================================
def ai_cleanup_roman_captions(text: str, settings: Dict[str, Any]) -> str:  # cleans one Urdu/Hindi/Punjabi subtitle line into Roman captions
    """
    ROMAN ENGINE v2

    Pipeline:
      (1) Original Whisper line (Urdu/Hindi/Punjabi/mixed)
      (2) OpenAI cleanup when enabled and key is available
      (3) Dataset + rule-based cleanup fallback for stable local testing
    """

    if not text or not text.strip():
        return text or ""

    line = text.strip()
    ai_cfg = (settings or {}).get("ai_features", {}) or {}
    ai_enabled = bool(ai_cfg.get("enabled", False))

    if ai_enabled:
        openai_out = openai_cleanup_roman_captions(line, settings)
        if openai_out:
            return openai_out

    rough = literal_romanize(line)
    rough = re.sub(r"\s+", " ", rough).strip()
    return _rule_based_clean_roman(rough, settings)


# =========================================================
# Local helper: text_for_range fallback (NO imports)
# =========================================================
def _text_for_range_fallback(whisper_result: dict, start: float, end: float) -> str:  # collects transcript text that overlaps a selected clip range
    """
    Build text from whisper segments that overlap [start, end].
    Safe fallback if seg['text'] exists but words missing.
    """
    parts: List[str] = []
    for s in whisper_result.get("segments", []) or []:
        ss = float(s.get("start", 0.0) or 0.0)
        ee = float(s.get("end", 0.0) or 0.0)
        if ee <= start:
            continue
        if ss >= end:
            break
        t = (s.get("text") or "").strip()
        if t:
            parts.append(t)

    out = " ".join(parts).strip()
    out = re.sub(r"\s+", " ", out)
    return out


# =========================================================
# QUALITY (CPU x264) - for filter-only / subs re-encode helper
# =========================================================
def _resolve_x264_from_quality(  # converts quality settings into FFmpeg x264 preset/CRF/audio values
    quality: Optional[str],
    encode_cfg: Optional[Dict[str, Any]],
) -> Tuple[str, int, str]:
    if isinstance(encode_cfg, dict) and encode_cfg:
        return (
            str(encode_cfg.get("preset", "fast")),
            int(encode_cfg.get("crf", 20)),
            str(encode_cfg.get("audio_bitrate", "160k")),
        )

    q = (quality or "balanced").strip().lower()
    if q in ("fast", "f"):
        return "veryfast", 22, "128k"
    if q in ("high", "hq", "best", "quality"):
        return "slow", 18, "192k"
    return "fast", 20, "160k"
def _clamp(x: float, lo: float, hi: float) -> float:# limits a value so it stays inside the allowed range
    return max(lo, min(hi, float(x)))
def apply_strength_to_vf(vf: str, strength: float) -> str:  # scales filter strength inside an FFmpeg video-filter string
    if not vf or not vf.strip():
        return ""

    s = _clamp(strength, 0.8, 1.2)
    def repl_eq(m):# handles repl eq behavior
        key = m.group(1)
        val = float(m.group(2))
        if key in ("contrast", "saturation"):
            newv = 1.0 + (val - 1.0) * s
        elif key == "brightness":
            newv = val * s
        else:
            newv = val
        return f"{key}={newv:.4f}"

    vf = re.sub(r"\b(contrast|brightness|saturation)=([0-9]*\.?[0-9]+)\b", repl_eq, vf)
    def repl_unsharp(m):# handles repl unsharp behavior
        a = m.group(1)
        parts = a.split(":")
        if len(parts) >= 3:
            try:
                amt = float(parts[2])
                parts[2] = f"{(amt * s):.4f}"
            except Exception:
                pass
        return "unsharp=" + ":".join(parts)

    vf = re.sub(r"\bunsharp=([0-9:\.]+)\b", repl_unsharp, vf)
    return vf
def apply_filter_to_clip(  # applies the selected preset/style/value
    ffmpeg_path: str,
    inp: Path,
    out: Path,
    vf: str,
    *,
    quality: Optional[str] = None,
    encode_cfg: Optional[Dict[str, Any]] = None,
) -> Path:
    inp = Path(inp)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    preset, crf, ab = _resolve_x264_from_quality(quality, encode_cfg)

    vf = (vf or "").strip()
    if vf:
        vf = f"{vf},format=yuv420p"
    else:
        vf = "format=yuv420p"

    args = [
        ffmpeg_path,
        "-y",
        "-i",
        str(inp),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        ab,
        "-movflags",
        "+faststart",
        str(out),
    ]

    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "apply_filter_to_clip failed")
    return out
def _ffmpeg_escape_path_for_subtitles(pth: Path) -> str:# handles ffmpeg escape path for subtitles behavior
    """
    Escape path for FFmpeg subtitles filter.
    """
    s = str(Path(pth).resolve())
    s = s.replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    return s
def burn_ass_subtitles(# burns styled subtitles into a video file
    ffmpeg_path: str,
    inp: Path,
    out: Path,
    ass_path: Path,
    fonts_dir: Optional[Path] = None,
    *,
    quality: Optional[str] = None,
    encode_cfg: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Re-encode clip with ASS subtitles burned in, using same
    x264 quality logic as filters.

    Ã¢Å¡Â Ã¯Â¸Â FFmpeg same input/output file pe write nahi kar sakta,
       is liye agar inp == out ho to hum temp file use karte hain.
    """
    inp = Path(inp)
    out = Path(out)

    # agar kisi wajah se inp aur out same ho gaye hon
    if inp.resolve() == out.resolve():
        tmp_out = out.with_suffix(out.suffix + ".tmp.mp4")
    else:
        tmp_out = out

    ass_esc = _ffmpeg_escape_path_for_subtitles(ass_path)
    if fonts_dir is not None:
        fonts_esc = _ffmpeg_escape_path_for_subtitles(Path(fonts_dir))
        vf = f"subtitles=filename='{ass_esc}':fontsdir='{fonts_esc}'"
    else:
        vf = f"subtitles=filename='{ass_esc}'"

    # actual ffmpeg call
    result_path = apply_filter_to_clip(
        ffmpeg_path=ffmpeg_path,
        inp=inp,
        out=tmp_out,
        vf=vf,
        quality=quality,
        encode_cfg=encode_cfg,
    )

    # agar humne temp file use ki ho, to usko final naam pe shift karo
    if tmp_out != out:
        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        tmp_out.replace(out)
        return out

    return result_path
def add_background_music(  # adds one item to the current collection/state
    ffmpeg_path,
    input_video,
    music_file,
    output_video,
    music_volume: float = 0.20,
):
    music_volume = max(0.0, min(1.0, float(music_volume)))

    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", str(input_video),
        "-stream_loop", "-1",
        "-i", str(music_file),

        "-filter_complex",
        f"[1:a]volume={music_volume}[music];"
        "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",

        "-map", "0:v",
        "-map", "[aout]",

        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",

        str(output_video),
    ]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
def safe_slug(name: str) -> str:  # sanitizes the value before it is used in paths/API output
    name = name.replace("Ã¢â‚¬â„¢", "'")
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.replace(" ", "_")
    return name[:120]


# =========================================================
# MAIN CUT  (WITH ENGLISH + ROMAN CAPTIONS SUPPORT)
# =========================================================
def cut_all(  # renders all selected segments into final shorts with captions, thumbnails, metadata, and music
    input_video: Path,
    whisper_source_result: Optional[dict] = None,
    whisper_captions_result: Optional[dict] = None,  # captions track (usually source)
    whisper_meta_result: Optional[dict] = None,
    # aliases
    source_whisper_result: Optional[dict] = None,
    captions_whisper_result: Optional[dict] = None,
    meta_whisper_result: Optional[dict] = None,
    whisper_result: Optional[dict] = None,
    segments: list[dict] = None,
    out_dir: Path = Path("data/output/shorts"),
    out_w: int = 1080,
    out_h: int = 1920,
    mode: str = "crop",
    platform: str = "instagram",
    keywords_path: Path = Path("config/keywords.txt"),
    look: dict | None = None,
    # FILTER
    filter_preset: str = "None (No Filter)",
    filter_strength: float = 1.0,
    filter_random_per_short: bool = False,
    filter_apply_after_reframe: bool = True,
    # reframe
    reframe_enabled: bool = False,
    reframe_kind: str = "talking_head",
    reframe_cfg: dict | None = None,
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    # CAPTIONS
    captions_enabled: bool = False,
    captions_dir: Optional[Path] = None,
    caption_start_bias_sec: float = 0.0,
    caption_uppercase: bool = False,
    caption_text_case: str = "normal",
    caption_italic: bool = False,
    captions_strict_timing: bool = False,

    # quality
    quality: Optional[str] = "balanced",
    encode_cfg: Optional[Dict[str, Any]] = None,
    burn_debug: bool = False,
    settings: Optional[Dict[str, Any]] = None,
) -> list[Path]:
    """
    CURRENT MODE:

    - Shorts video generate:
        * cut / reframe / filter
    - Captions:
        * English video  Ã¢â€ â€™ English captions (SOURCE track)
        * Urdu/Hindi/Punjabi/mixed video -> Roman captions when captions_roman_enabled is true
          (no paraphrase; dataset + AI sirf spelling/spacing clean karega)
    - Meta (TITLE/HOOKS/DESCRIPTION) Ã¢â€ â€™ EN or Roman according to settings.
    """

    segments = segments or []
    input_video = Path(input_video)
    settings = settings or {}

    # -------------------------------------------------
    # 1) Resolve SOURCE + META + CAPTIONS whisper tracks
    # -------------------------------------------------
    # original language timing truth
    src = (source_whisper_result or whisper_source_result or whisper_result or {})  # type: ignore

    # detected language (from Whisper SOURCE)
    detected_lang = str(src.get("language", "") or "").strip().lower()

    # META base Ã¢â€ â€™ main.py already decide karta hai translate vs source
    meta_src = (meta_whisper_result or whisper_meta_result or whisper_result or src)  # type: ignore

    # CAPTIONS base Ã¢â€ â€™ ALWAYS source, unless explicitly overridden
    captions_src = (captions_whisper_result or whisper_captions_result or src)  # type: ignore

    # -------------------------------------------------
    # 2) Output dirs
    # -------------------------------------------------
    video_tag = safe_slug(input_video.stem)

    shorts_out = Path(out_dir)

    # Meta base:
    try:
        if shorts_out.name == video_tag and shorts_out.parent.name == "shorts":
            meta_base = shorts_out.parent.parent  # <base>
        else:
            meta_base = p("data", "output")
    except Exception:
        meta_base = p("data", "output")

    meta_out = meta_base / "meta" / video_tag
    thumb_out = meta_base / "thumbnails" / video_tag

    shorts_out.mkdir(parents=True, exist_ok=True)
    meta_out.mkdir(parents=True, exist_ok=True)
    thumb_out.mkdir(parents=True, exist_ok=True)

    # captions directory (subfolder per video)
    if captions_dir is None:
        captions_root = p("data", "output", "captions")
    else:
        captions_root = Path(captions_dir)

    captions_out = captions_root / video_tag / "roman_or_en"
    if captions_enabled:
        captions_out.mkdir(parents=True, exist_ok=True)

    kw_weighted = load_keywords_weighted(keywords_path)
    outputs: List[Path] = []
    total = len(segments)

    platform = (platform or "instagram").lower()
    mode = (mode or "crop").lower()

    fmp = ffmpeg_path or "ffmpeg"
    fpp = ffprobe_path or "ffprobe"

    # -------------------------------------------------
    # 3) Reframe cfg
    # -------------------------------------------------
    rcfg = reframe_cfg or {}
    r_detect_n = int(rcfg.get("detect_every_n_frames", 6))
    r_smooth = float(rcfg.get("smooth_alpha", 0.12))
    r_pan = float(rcfg.get("max_pan_px_per_frame", 12))
    r_lowlight = bool(rcfg.get("enhance_low_light", True))
    r_min_face = int(rcfg.get("min_face", 60))
    r_dead_zone = int(rcfg.get("dead_zone_px", 40))
    r_lock_x = float(rcfg.get("lock_strength_x", 0.25))

    # -------------------------------------------------
    # 4) Filter presets
    # -------------------------------------------------
    preset_pool = [
        "Natural Enhance (Recommended)",
        "Punchy + Clear",
        "Cool Modern",
        "Warm Cinematic",
        "Black & White (Mono)",
    ]
    def resolve_preset_for_short(i: int) -> str:  # converts settings/input into a concrete path or option
        if not filter_random_per_short:
            return filter_preset
        seed = f"{video_tag}::{i}"
        rng = random.Random(seed)
        return rng.choice(preset_pool)

    # -------------------------------------------------
    # 5) META style + CAPTION romanization toggle
    # -------------------------------------------------
    ai_cfg = settings.get("ai_features", {}) or {}
    meta_style = str(settings.get("meta_output_style", "en") or "en").strip().lower()

    # Meta Roman toggle now follows local feature flags.
    romanize_meta = meta_style == "roman" and bool(ai_cfg.get("romanize_meta", True))

    # Caption Roman toggle:
    #  - only if non-English (Urdu/Hindi/Punjabi/mixed)
    #  - settings flag allowed
    is_non_english = bool(detected_lang and not detected_lang.startswith("en"))
    captions_roman_flag = bool(settings.get("captions_roman_enabled", True))

    romanize_captions = is_non_english and captions_roman_flag

    if burn_debug:
        print(
            f"[DBG CUT_ALL] lang={detected_lang} "
            f"| romanize_captions={romanize_captions}"
        )

        # -------------------------------------------------
    # 5.1) Global ROMAN caption "file" (video-level)
    # -------------------------------------------------
    # Idea:
    #   - Saari Whisper segments ko ek dafa AI + dataset se clean Roman banao
    #   - Ek in-memory "roman_whisper" bana do
    #   - Shorts ke captions isi clean roman file se slice honge
    roman_whisper = None

    if romanize_captions and captions_src.get("segments"):
        print("[Roman Engine v2] Precomputing full-video Roman captions...")

        roman_segments: List[dict] = []
        for seg in captions_src.get("segments", []) or []:
            raw_text = (seg.get("text") or "").strip()
            if not raw_text:
                roman_segments.append(dict(seg))
                continue

            # Ã°Å¸â€Â¥ 1) AI + dataset se Roman clean (line-level)
            clean_roman = ai_cleanup_roman_captions(raw_text, settings)
            new_seg = dict(seg)
            new_seg["text"] = clean_roman
            roman_segments.append(new_seg)

        roman_whisper = dict(captions_src)
        roman_whisper["segments"] = roman_segments

        # OPTIONAL: human debugging ke liye Roman transcript file likh do
        try:
            if captions_dir is None:
                captions_root = p("data", "output", "captions")
            else:
                captions_root = Path(captions_dir)

            roman_txt_dir = captions_root / video_tag
            roman_txt_dir.mkdir(parents=True, exist_ok=True)
            roman_txt_path = roman_txt_dir / "roman_full_v2.txt"

            with roman_txt_path.open("w", encoding="utf-8") as f:
                for s in roman_segments:
                    st = float(s.get("start", 0.0) or 0.0)
                    en = float(s.get("end", 0.0) or 0.0)
                    txt = (s.get("text") or "").strip()
                    f.write(f"{st:7.2f} -> {en:7.2f} | {txt}\n")

            print(f"[Roman Engine v2] Saved Roman transcript file: {roman_txt_path}")

        except Exception as e:
            print(f"[WARN] Failed to write Roman transcript file: {e}")


    # -------------------------------------------------
    # 6) Per-short loop
    # -------------------------------------------------
    perf_cfg = (settings.get("performance", {}) or {}) if isinstance(settings, dict) else {}
    max_short_workers = int(perf_cfg.get("max_short_workers", 1) or 1)
    max_short_workers = max(1, min(max_short_workers, max(1, total)))
    max_ffmpeg_workers = int(perf_cfg.get("max_ffmpeg_workers", 2) or 2)
    max_ffmpeg_workers = max(1, min(max_ffmpeg_workers, 4))
    max_thumbnail_ai_workers = int(perf_cfg.get("max_thumbnail_ai_workers", 1) or 1)
    max_thumbnail_ai_workers = max(1, min(max_thumbnail_ai_workers, 3))

    outputs_lock = threading.Lock()
    ffmpeg_semaphore = threading.Semaphore(max_ffmpeg_workers)
    thumbnail_ai_semaphore = threading.Semaphore(max_thumbnail_ai_workers)
    def _run_ffmpeg_limited(fn, *args, **kwargs):  # executes a pipeline step, command, or test
        with ffmpeg_semaphore:
            return fn(*args, **kwargs)
    def _run_thumbnail_limited(fn, *args, **kwargs):  # executes a pipeline step, command, or test
        with thumbnail_ai_semaphore:
            return fn(*args, **kwargs)
    def _process_one_short(i: int, seg: dict):  # starts or manages a processing job
            start = float(seg["start"])
            end = float(seg["end"])
            dur = end - start
            if dur <= 0:
                return None

            # LOG: start of short
            print("\n" + "-" * 48)
            print(
                f"[stage] Start short {i}/{total} | {video_tag} | "
                f"{start:.2f}s -> {end:.2f}s  (dur={dur:.2f}s)"
            )

            raw_clip = shorts_out / f"_raw_short_{i:02d}.mp4"
            reframed_clip = shorts_out / f"_reframed_short_{i:02d}.mp4"
            filtered_after_reframe = shorts_out / f"_filtered_short_{i:02d}.mp4"
            captioned_clip_tmp = shorts_out / f"_captioned_tmp_{i:02d}.mp4"
            final_clip = shorts_out / f"short_{i:02d}.mp4"

            meta_txt = meta_out / f"short_{i:02d}.txt"
            thumbnail_file = thumb_out / f"thumbnail_{i:02d}.png"
            ass_file = captions_out / f"short_{i:02d}.ass" if captions_enabled else None

            use_face_reframe = bool(reframe_enabled) and (
                (reframe_kind or "talking_head").lower() == "talking_head"
            )

            chosen_preset = resolve_preset_for_short(i)
            preset_vf = apply_strength_to_vf(get_filter_vf(chosen_preset), filter_strength)

            # 1) CUT / REFRAME / FILTER (video only)
            if use_face_reframe:
                try:
                    print("   - Reframe (talking_head) enabled -> running face center reframe...")
                    _run_ffmpeg_limited(
                    reframe_talking_head,
                        ffmpeg_path=fmp,
                        ffprobe_path=fpp,
                        inp=input_video,
                        out_final=reframed_clip,
                        start=start,
                        length=dur,
                        target_w=out_w,
                        target_h=out_h,
                        detect_every_n_frames=r_detect_n,
                        smooth_alpha=r_smooth,
                        max_pan_px_per_frame=r_pan,
                        enhance_low_light=r_lowlight,
                        min_face=r_min_face,
                        dead_zone_px=r_dead_zone,
                        lock_strength_x=r_lock_x,
                        log=lambda s: print("   [reframe] " + s, end=""),
                        quality=quality,
                        encode_cfg=encode_cfg,
                    )

                    clip_for_finalize = reframed_clip

                    if filter_apply_after_reframe and preset_vf.strip():
                        print(
                            "   - Applying color filter preset after reframe:"
                            f" {chosen_preset}"
                        )
                        _run_ffmpeg_limited(
                        apply_filter_to_clip,
                            ffmpeg_path=fmp,
                            inp=reframed_clip,
                            out=filtered_after_reframe,
                            vf=preset_vf,
                            quality=quality,
                            encode_cfg=encode_cfg,
                        )
                        clip_for_finalize = filtered_after_reframe

                except Exception as e:
                    print(f"   [WARN] Reframe failed for short_{i:02d}: {e}")
                    print("   - Falling back to direct crop + filter...")
                    _run_ffmpeg_limited(
                    cut_clip,
                        input_video=input_video,
                        start_sec=start,
                        duration_sec=dur,
                        out_mp4=raw_clip,
                        out_w=out_w,
                        out_h=out_h,
                        mode=mode,
                        look=look,
                        filter_vf=preset_vf,
                        ffmpeg_path=fmp,
                        quality=quality,
                        encode_cfg=encode_cfg,
                    )
                    clip_for_finalize = raw_clip
            else:
                print("   - Reframe disabled -> direct crop + filter...")
                _run_ffmpeg_limited(
                    cut_clip,
                    input_video=input_video,
                    start_sec=start,
                    duration_sec=dur,
                    out_mp4=raw_clip,
                    out_w=out_w,
                    out_h=out_h,
                    mode=mode,
                    look=look,
                    filter_vf=preset_vf,
                    ffmpeg_path=fmp,
                    quality=quality,
                    encode_cfg=encode_cfg,
                )
                clip_for_finalize = raw_clip


            # Thumbnail must use the clean pre-caption clip, otherwise burned captions appear in thumbnails.
            clip_for_thumbnail = clip_for_finalize

            # 2) CAPTIONS (Roman / English)
            if captions_enabled and ass_file is not None and captions_src.get("segments"):
                set_progress(5, f"Creating Captions {i}/{total}")
                print("[stage] Building captions track...", flush=True)

                # Agar Roman Engine v2 chal raha hai to roman_whisper, warna original captions_src
                effective_captions_src = roman_whisper if (roman_whisper is not None) else captions_src

                cap_lines = make_ass.build_caption_lines_from_whisper(
                    effective_captions_src,
                    clip_start=start,
                    clip_end=end,
                    bias_sec=(0.0 if captions_strict_timing else caption_start_bias_sec),
                    uppercase=caption_uppercase,
                    text_case=caption_text_case,
                )

                if cap_lines:
                    if not captions_strict_timing:
                        # Normal mode: fillers remove + merge
                        cap_lines = preprocess_caption_lines_v2(cap_lines, settings)
                    else:
                        # Strict mode keeps caption start timing exact, but prevents one short line from staying onscreen for a long Whisper segment.
                        cleaned_cap_lines = []
                        last_key = ""
                        for text, s_rel, e_rel in cap_lines:
                            t = re.sub(r"\s+", " ", text or "").strip()
                            t = _collapse_repeated_caption_phrases(t).strip()
                            if not t:
                                continue
                            key = _caption_repeat_key(t)
                            if key and key == last_key:
                                continue
                            s_rel, e_rel = _cap_stale_caption_duration(t, s_rel, e_rel, settings)
                            if e_rel <= s_rel:
                                continue
                            cleaned_cap_lines.append((t, s_rel, e_rel))
                            if key:
                                last_key = key
                        cap_lines = cleaned_cap_lines
                    caption_style_cfg = (settings or {}).get("caption_style", {}) or {}
                    music_enabled = bool(
                        settings.get("music_enabled", False)
                    )

                    music_category = str(
                        settings.get("music_category", "none")
                    )                

                    music_volume = float(settings.get("music_volume", 0.20))

                    font_name = str(caption_style_cfg.get("font_name", "Montserrat"))
                    font_size = int(caption_style_cfg.get("font_size", 41))
                    margin_l = int(caption_style_cfg.get("margin_l", 90))
                    margin_v = int(caption_style_cfg.get("margin_v", 180))
                    outline = int(caption_style_cfg.get("outline", 3))
                    letter_spacing = int(caption_style_cfg.get("letter_spacing", 9))
                    preset_italic = bool(caption_style_cfg.get("italic", caption_italic))
                    primary_color = str(
                        caption_style_cfg.get("primary_color", "&H00FFFFFF")
                    )

                    outline_color = str(
                        caption_style_cfg.get("outline_color", "&H00000000")
                    )

                    back_color = str(
                        caption_style_cfg.get("back_color", "&H64000000")
                    )

                    bold = int(
                        caption_style_cfg.get("bold", 0)
                    )

                    shadow = int(
                        caption_style_cfg.get("shadow", 0)
                    )

                    word_dynamic = bool(
                        caption_style_cfg.get("word_dynamic", False)
                    )
                    accent_color = str(caption_style_cfg.get("accent_color", "") or "")
                    accent_mode = str(caption_style_cfg.get("accent_mode", "none") or "none")
                    glow_color = str(caption_style_cfg.get("glow_color", "") or "")
                    glow_blur = int(caption_style_cfg.get("glow_blur", 0) or 0)

                    alignment = int(
                        caption_style_cfg.get("alignment", 2)
                    )

                    ass_text = make_ass.build_ass_from_lines(
                        cap_lines,
                        play_res_x=out_w,
                        play_res_y=out_h,
                        font_name=font_name,
                        font_size=font_size,
                        margin_l=margin_l,
                        margin_v=margin_v,
                        outline=outline,
                        italic=preset_italic,
                        letter_spacing=letter_spacing,
                        strict_timing=captions_strict_timing,

                        primary_color=primary_color,
                        outline_color=outline_color,
                        back_color=back_color,
                        bold=bold,
                        shadow=shadow,
                        word_dynamic=word_dynamic,
                        accent_color=accent_color,
                        accent_mode=accent_mode,
                        glow_color=glow_color,
                        glow_blur=glow_blur,
                        alignment=alignment,
                    )
                    make_ass.write_ass_file(ass_text, ass_file)

                    print("[stage] Burning subtitles into video...", flush=True)
                    _run_ffmpeg_limited(
                    burn_ass_subtitles,
                        ffmpeg_path=fmp,
                        inp=clip_for_finalize,
                        out=captioned_clip_tmp,
                        ass_path=ass_file,
                        fonts_dir=p("assets", "fonts"),
                        quality=quality,
                        encode_cfg=encode_cfg,
                    )
                    clip_for_finalize = captioned_clip_tmp
            else:
                if captions_enabled:
                    print("   - Captions enabled but no segments found - skipping captions.")
                else:
                    print("   - Captions disabled for this short.")


            # 3) META (base from meta_src only)
            seg_text = _text_for_range_fallback(meta_src, start, end)
            if not seg_text:
                seg_text = (meta_src.get("text") or "").strip()
            if not seg_text:
                seg_text = (seg.get("text") or "").strip()

            hits = keyword_hits(seg_text, kw_weighted, top_k=10)

            base_text = seg_text

            if romanize_meta:
                print("   - Romanizing META (title/hooks/description)...")
                final_meta_text = ai_romanize_text(base_text, settings)
                meta_lang = "roman"
            else:
                meta_lang = "en"
                final_meta_text = base_text

            meta = generate_hooks_titles_description(
                segment_text=final_meta_text,
                hits=hits,
                lang=meta_lang,
                platform=platform,
                max_hooks=5,
                settings=settings,
            )

            write_meta_txt(
                out_path=meta_txt,
                title=meta["title"],
                hooks=meta["hooks"],
                description=meta["description"],
                start=start,
                end=end,
                keyword_hits_list=hits,
                platform=platform,
                lang=meta_lang,
            )

            try:
                best_hook = meta["hooks"][0] if meta.get("hooks") else meta["title"]

                _run_thumbnail_limited(
                create_thumbnail_for_short,
                    video_path=clip_for_thumbnail,
                    title_text=best_hook,
                    output_path=thumbnail_file,
                    settings=settings,
                    variations=3,
                    transcript_text=final_meta_text,
                )
                set_progress(6, f"Generating Thumbnails {i}/{total}")
                print(f"[stage] Thumbnail created: {thumbnail_file.name} (+ 3 variations)", flush=True)
            except Exception as e:
                print(f"   [WARN] Thumbnail creation failed: {e}")        

            # 4) FINALIZE
            if final_clip.exists():
                final_clip.unlink(missing_ok=True)
            clip_for_finalize.replace(final_clip)

            # 4.1) OPTIONAL BACKGROUND MUSIC
            music_enabled = bool(settings.get("music_enabled", False))
            music_category = str(settings.get("music_category", "none"))
            music_track = str(settings.get("music_track", "") or "")

            if music_enabled:
                selected_music = pick_music_track(music_category, preferred_track=music_track)

                if selected_music:
                    track_label = Path(selected_music).name
                    print(f"   Adding background music: {music_category} / {track_label}")

                    music_tmp = final_clip.with_name(
                        final_clip.stem + "_music.mp4"
                    )

                    _run_ffmpeg_limited(
                    add_background_music,
                        ffmpeg_path=fmp,
                        input_video=final_clip,
                        music_file=selected_music,
                        output_video=music_tmp,
                        music_volume=music_volume,
                    )

                    music_tmp.replace(final_clip)
                else:
                    print(f"   - Music enabled but no track found for: {music_category}")        

            # cleanup temps
            for tmp in [
                raw_clip,
                reframed_clip,
                filtered_after_reframe,
                captioned_clip_tmp,
            ]:
                if tmp.exists() and tmp != final_clip:
                    tmp.unlink(missing_ok=True)

            with outputs_lock:
                outputs.append(final_clip)

            set_progress(6, f"Completed Short {i}/{total}")
            print(f"[stage] Completed short {i}/{total}: {final_clip.name}", flush=True)

    if max_short_workers <= 1 or total <= 1:
        for i, seg in enumerate(segments, start=1):
            try:
                _process_one_short(i, seg)
            except Exception as e:
                print(f"   [ERROR] Short {i}/{total} failed: {e}", flush=True)
    else:
        print(
            f"[stage] Parallel shorts enabled: workers={max_short_workers}, "
            f"ffmpeg_limit={max_ffmpeg_workers}, thumbnail_ai_limit={max_thumbnail_ai_workers}",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=max_short_workers) as executor:
            futures = {
                executor.submit(_process_one_short, i, seg): i
                for i, seg in enumerate(segments, start=1)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"   [ERROR] Short {idx}/{total} failed: {e}", flush=True)

    outputs.sort(key=lambda path: str(path))

    return outputs







